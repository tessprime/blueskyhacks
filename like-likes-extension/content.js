// Runs on https://bsky.app/profile/*/post/*/liked-by
//
// Reads the active Bluesky session directly from localStorage (key: BSKY_STORAGE),
// then injects a heart button next to each liker on the page.

function readBskySession() {
  try {
    const raw = localStorage.getItem("BSKY_STORAGE");
    if (!raw) return null;
    const data = JSON.parse(raw);
    const currentDid = data?.session?.currentAccount?.did;
    if (!currentDid) return null;
    const account = data.session.accounts.find(a => a.did === currentDid);
    if (!account?.accessJwt) return null;
    return {
      did: account.did,
      accessJwt: account.accessJwt,
      refreshJwt: account.refreshJwt,
      pds: (account.pdsUrl || "https://bsky.social").replace(/\/$/, ""),
    };
  } catch {
    return null;
  }
}

function postInfoFromUrl() {
  // /profile/<authority>/post/<rkey>/liked-by
  const parts = location.pathname.split("/");
  return { authority: parts[2], rkey: parts[4] };
}

function storageKey(actorDid, likerHandle, postAuthority, postRkey) {
  return `ltl:${actorDid}:${likerHandle}:${postAuthority}:${postRkey}`;
}

function parseAtUri(uri) {
  const m = uri.match(/^at:\/\/([^/]+)\/[^/]+\/([^/]+)$/);
  return m ? { authority: m[1], rkey: m[2] } : null;
}

function likeTheLike(handle, postAuthority, postRkey, button, subjectUri = null) {
  const session = readBskySession();
  if (!session) {
    button.textContent = "✗";
    button.title = "Not logged in to Bluesky";
    return;
  }

  button.disabled = true;
  button.textContent = "…";

  // Toggle: if we already liked this, delete the record instead.
  if (button.dataset.likeUri) {
    const likeUri = button.dataset.likeUri;
    const key = storageKey(session.did, handle, postAuthority, postRkey);
    chrome.runtime.sendMessage(
      { type: "DELETE_LIKE", likeUri, storageKey: key, session },
      (response) => {
        if (chrome.runtime.lastError || !response?.ok) {
          const error = response?.error ?? chrome.runtime.lastError?.message ?? "Error";
          console.error("[like-the-likes] failed to unlike @%s's like: %s", handle, error);
          button.textContent = "♥";
          button.title = likeUri;
          button.disabled = false;
        } else {
          console.log("[like-the-likes] unliked @%s's like: %s", handle, likeUri);
          delete button.dataset.likeUri;
          button.textContent = "♡";
          button.title = `Like @${handle}'s like`;
          button.classList.remove("ltl-liked");
          button.disabled = false;
        }
      }
    );
    return;
  }

  chrome.runtime.sendMessage(
    { type: "LIKE_THE_LIKE", likerHandle: handle, postAuthority, postRkey, storageKey: storageKey(session.did, handle, postAuthority, postRkey), likeCreatedAt: button.dataset.likeCreatedAt || undefined, subjectUri: subjectUri || undefined, session },
    (response) => {
      if (chrome.runtime.lastError || !response?.ok) {
        const error = response?.error ?? chrome.runtime.lastError?.message ?? "Error";
        console.error("[like-the-likes] failed to like @%s's like: %s", handle, error);
        button.textContent = "✗";
        button.title = error;
        button.disabled = false;
      } else {
        console.log("[like-the-likes] liked @%s's like: %s", handle, response.uri);
        button.dataset.likeUri = response.uri;
        button.textContent = "♥";
        button.title = response.uri;
        button.classList.add("ltl-liked");
        button.disabled = false; // re-enable so it can be toggled off
      }
    }
  );
}

function makeCountEl() {
  const el = document.createElement("button");
  el.className = "ltl-count";
  el.textContent = "…";
  el.disabled = true;
  return el;
}

async function loadLikesCount(handle, postAuthority, postRkey, likeCreatedAt, countEl, subjectUri = null) {
  const response = await new Promise(resolve =>
    chrome.runtime.sendMessage(
      { type: "GET_LIKE_URI", likerHandle: handle, postAuthority, postRkey, likeCreatedAt, subjectUri: subjectUri || undefined },
      resolve
    )
  );
  if (!response?.ok || !response.uri) {
    countEl.textContent = "";
    return;
  }
  try {
    const resp = await fetch(
      `https://public.api.bsky.app/xrpc/app.bsky.feed.getLikes?uri=${encodeURIComponent(response.uri)}&limit=100`
    );
    if (!resp.ok) { countEl.textContent = ""; return; }
    const data = await resp.json();
    const count = (data.likes ?? []).length;
    countEl.textContent = `${count} ♡`;
    countEl.title = `${count} like${count === 1 ? "" : "s"} of this like`;
    countEl.dataset.likeUri = response.uri;
    if (count > 0) {
      countEl.disabled = false;
      countEl.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        location.hash = `ltl/${encodeURIComponent(response.uri)}`;
      });
    }
  } catch {
    countEl.textContent = "";
  }
}

// ── Overlay ──────────────────────────────────────────────────────────────────

function parseOverlayHash() {
  const m = location.hash.match(/^#ltl\/(.+)$/);
  return m ? decodeURIComponent(m[1]) : null;
}

let overlayResizeObserver = null;

function destroyOverlay() {
  overlayResizeObserver?.disconnect();
  overlayResizeObserver = null;
  document.getElementById("ltl-overlay")?.remove();
}

function positionOverlay(overlay) {
  const col = getCenterColumn();
  if (!col) return;
  const rect = col.getBoundingClientRect();
  overlay.style.left = rect.left + "px";
  overlay.style.right = (window.innerWidth - rect.right) + "px";
}

function getCenterColumn() {
  let el = document.querySelector('a[role="link"][href^="/profile/"]:has(a[role="link"])');
  while (el) {
    if (el.style.maxWidth === '600px') return el;
    el = el.parentElement;
  }
  return null;
}

function getPageTheme() {
  let el = getCenterColumn() || document.body;
  while (el) {
    const bg = getComputedStyle(el).backgroundColor;
    if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
      const m = bg.match(/\d+/g);
      if (m && m.length >= 3) {
        const [r, g, b] = m.map(Number);
        return { dark: (r * 299 + g * 587 + b * 114) / 1000 < 128, bg };
      }
    }
    el = el.parentElement;
  }
  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  return { dark, bg: dark ? '#000' : '#fff' };
}

function renderLikerCard(actor, likeCreatedAt, subjectUri, storedLikes = {}, actorDid = null) {
  const parsed = parseAtUri(subjectUri);
  const subjectAuthority = parsed?.authority ?? "";
  const subjectRkey = parsed?.rkey ?? "";

  const card = document.createElement("a");
  card.setAttribute("role", "link");
  card.href = `/profile/${actor.handle}`;
  card.className = "ltl-card";
  card.dataset.ltlInjected = "1"; // prevent injectButtons from adding heart buttons

  card.addEventListener("click", async (e) => {
    e.preventDefault();
    card.classList.add("ltl-card-loading");
    const response = await new Promise(resolve =>
      chrome.runtime.sendMessage(
        { type: "GET_LIKE_URI", likerHandle: actor.handle, likeCreatedAt, subjectUri },
        resolve
      )
    );
    card.classList.remove("ltl-card-loading");
    if (response?.ok && response.uri) {
      location.hash = `ltl/${encodeURIComponent(response.uri)}`;
    }
  });

  const avatarLink = document.createElement("a");
  avatarLink.setAttribute("role", "link");
  avatarLink.href = `/profile/${actor.handle}`;
  avatarLink.className = "ltl-card-avatar-wrap";

  const img = document.createElement("img");
  img.className = "ltl-card-avatar";
  img.src = actor.avatar || "";
  img.alt = "";
  avatarLink.appendChild(img);

  const nameBlock = document.createElement("div");
  nameBlock.className = "ltl-card-names";

  const displayName = document.createElement("span");
  displayName.className = "ltl-card-displayname";
  displayName.textContent = actor.displayName || actor.handle;

  const handle = document.createElement("span");
  handle.className = "ltl-card-handle";
  handle.textContent = `@${actor.handle}`;

  nameBlock.append(displayName, handle);

  const btn = makeLikeButton(actor.handle, subjectAuthority, subjectRkey, subjectUri);
  if (likeCreatedAt) btn.dataset.likeCreatedAt = likeCreatedAt;

  const key = actorDid ? storageKey(actorDid, actor.handle, subjectAuthority, subjectRkey) : null;
  if (key && storedLikes[key]) {
    btn.dataset.likeUri = storedLikes[key];
    btn.textContent = "♥";
    btn.title = storedLikes[key];
    btn.classList.add("ltl-liked");
  }

  const countEl = makeCountEl();

  const row = document.createElement("div");
  row.className = "ltl-card-row";
  row.append(avatarLink, nameBlock, btn, countEl);

  card.appendChild(row);

  loadLikesCount(actor.handle, subjectAuthority, subjectRkey, likeCreatedAt, countEl, subjectUri);

  return card;
}

async function renderOverlay(likeUri) {
  destroyOverlay();

  const { dark, bg } = getPageTheme();

  const overlay = document.createElement("div");
  overlay.id = "ltl-overlay";
  overlay.style.backgroundColor = bg;
  if (dark) overlay.classList.add("ltl-dark");
  positionOverlay(overlay);

  const header = document.createElement("div");
  header.className = "ltl-overlay-header";

  const backBtn = document.createElement("button");
  backBtn.className = "ltl-overlay-back";
  backBtn.setAttribute("aria-label", "Go back");
  backBtn.textContent = "←";
  backBtn.addEventListener("click", () => history.back());

  const title = document.createElement("span");
  title.className = "ltl-overlay-title";
  title.textContent = "Liked by";

  header.append(backBtn, title);

  const list = document.createElement("div");
  list.className = "ltl-overlay-list";

  const status = document.createElement("div");
  status.className = "ltl-overlay-status";
  status.textContent = "Loading…";
  list.appendChild(status);

  overlay.append(header, list);
  document.body.appendChild(overlay);

  overlayResizeObserver = new ResizeObserver(() => positionOverlay(overlay));
  overlayResizeObserver.observe(document.documentElement);

  try {
    const resp = await fetch(
      `https://public.api.bsky.app/xrpc/app.bsky.feed.getLikes?uri=${encodeURIComponent(likeUri)}&limit=100`
    );
    if (!resp.ok) throw new Error(resp.status);
    const data = await resp.json();
    list.textContent = "";

    if (!data.likes?.length) {
      const empty = document.createElement("div");
      empty.className = "ltl-overlay-status";
      empty.textContent = "No likes yet.";
      list.appendChild(empty);
      return;
    }

    const parsed = parseAtUri(likeUri);
    const actorDid = readBskySession()?.did ?? null;
    const allStorage = actorDid ? await chrome.storage.local.get(null) : {};
    const storedLikes = actorDid && parsed
      ? Object.fromEntries(
          Object.entries(allStorage).filter(([k]) =>
            k.startsWith(`ltl:${actorDid}:`) && k.endsWith(`:${parsed.authority}:${parsed.rkey}`)
          )
        )
      : {};

    for (const like of data.likes) {
      list.appendChild(renderLikerCard(like.actor, like.createdAt, likeUri, storedLikes, actorDid));
    }
  } catch {
    list.textContent = "";
    const err = document.createElement("div");
    err.className = "ltl-overlay-status";
    err.textContent = "Failed to load likes.";
    list.appendChild(err);
  }
}

function makeLikeButton(handle, postAuthority, postRkey, subjectUri = null) {
  const btn = document.createElement("button");
  btn.className = "ltl-btn";
  btn.textContent = "♡";
  btn.title = `Like @${handle}'s like`;
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    likeTheLike(handle, postAuthority, postRkey, btn, subjectUri);
  });
  return btn;
}

function injectButtons(postAuthority, postRkey, storedLikes, likeCreatedAts = {}, actorDid = null) {
  // The outer card link is the only a[role="link"] that contains another
  // a[role="link"] inside it (the avatar link). This avoids depending on
  // aria-label text which may use Unicode apostrophes (U+2019).
  const cards = document.querySelectorAll(
    'a[role="link"][href^="/profile/"]:has(a[role="link"]):not([data-ltl-injected])'
  );

  console.log("[like-the-likes] found %d card(s)", cards.length);
  for (const card of cards) {
    card.dataset.ltlInjected = "1";

    const handle = card.getAttribute("href").replace(/^\/profile\//, "");
    if (!handle) continue;

    const headerRow = card.querySelector(":scope > div > div:first-child");
    if (!headerRow) continue;

    const btn = makeLikeButton(handle, postAuthority, postRkey);

    const likeCreatedAt = likeCreatedAts[handle];
    if (likeCreatedAt) btn.dataset.likeCreatedAt = likeCreatedAt;

    // Restore liked state if we've previously liked this person's like.
    const key = actorDid ? storageKey(actorDid, handle, postAuthority, postRkey) : null;
    if (key && storedLikes[key]) {
      btn.dataset.likeUri = storedLikes[key];
      btn.textContent = "♥";
      btn.title = storedLikes[key];
      btn.classList.add("ltl-liked");
    }

    const countEl = makeCountEl();
    headerRow.appendChild(btn);
    headerRow.appendChild(countEl);

    loadLikesCount(handle, postAuthority, postRkey, likeCreatedAt, countEl);
  }
}

// Fetch the first page of likes for the post and return a handle→createdAt map.
// Used to compute TID cursors so findLikeRecord can jump straight to the right spot.
async function fetchLikeCreatedAts(authority, rkey) {
  try {
    const uri = `at://${authority}/app.bsky.feed.post/${rkey}`;
    const resp = await fetch(`https://public.api.bsky.app/xrpc/app.bsky.feed.getLikes?uri=${encodeURIComponent(uri)}&limit=100`);
    if (!resp.ok) return {};
    const data = await resp.json();
    return Object.fromEntries(
      (data.likes ?? []).map(l => [l.actor.handle, l.createdAt])
    );
  } catch {
    return {};
  }
}

function isLikedByPage() {
  return /^\/profile\/[^/]+\/post\/[^/]+\/liked-by\/?$/.test(location.pathname);
}

let activeObserver = null;

async function init() {
  if (activeObserver) {
    activeObserver.disconnect();
    activeObserver = null;
  }

  if (!isLikedByPage()) return;

  const { authority, rkey } = postInfoFromUrl();
  const actorDid = readBskySession()?.did ?? null;
  console.log("[like-the-likes] init", { authority, rkey, actorDid });

  const [allStorage, likeCreatedAts] = await Promise.all([
    chrome.storage.local.get(null),
    fetchLikeCreatedAts(authority, rkey),
  ]);

  const storedLikes = actorDid
    ? Object.fromEntries(
        Object.entries(allStorage).filter(([k]) => k.startsWith(`ltl:${actorDid}:`) && k.endsWith(`:${authority}:${rkey}`))
      )
    : {};

  injectButtons(authority, rkey, storedLikes, likeCreatedAts, actorDid);

  activeObserver = new MutationObserver(() => {
    if (!isLikedByPage()) {
      activeObserver.disconnect();
      activeObserver = null;
      return;
    }
    injectButtons(authority, rkey, storedLikes, likeCreatedAts, actorDid);
  });
  activeObserver.observe(document.body, { childList: true, subtree: true });
}

// navigation-bridge.js (MAIN world) dispatches 'ltl:navigate' on pushState/replaceState.
window.addEventListener("ltl:navigate", init);
window.addEventListener("popstate", init);

// Hash-based overlay: #ltl/<encodedLikeUri> opens the likes-of-likes list.
// Setting location.hash adds a browser history entry; back button pops it and
// fires hashchange, which destroys the overlay.
window.addEventListener("hashchange", () => {
  const likeUri = parseOverlayHash();
  if (likeUri) renderOverlay(likeUri);
  else destroyOverlay();
});

init();

// Open overlay if the page was loaded/refreshed with a hash already set.
const _initLikeUri = parseOverlayHash();
if (_initLikeUri) renderOverlay(_initLikeUri);
