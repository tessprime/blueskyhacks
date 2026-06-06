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

function storageKey(handle, postAuthority, postRkey) {
  return `ltl:${handle}:${postAuthority}:${postRkey}`;
}

function likeTheLike(handle, postAuthority, postRkey, button) {
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
    const key = storageKey(handle, postAuthority, postRkey);
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
    { type: "LIKE_THE_LIKE", likerHandle: handle, postAuthority, postRkey, storageKey: storageKey(handle, postAuthority, postRkey), likeCreatedAt: button.dataset.likeCreatedAt || undefined, session },
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

async function loadLikesCount(handle, postAuthority, postRkey, likeCreatedAt, countEl) {
  const response = await new Promise(resolve =>
    chrome.runtime.sendMessage(
      { type: "GET_LIKE_URI", likerHandle: handle, postAuthority, postRkey, likeCreatedAt },
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
  } catch {
    countEl.textContent = "";
  }
}

function makeLikeButton(handle, postAuthority, postRkey) {
  const btn = document.createElement("button");
  btn.className = "ltl-btn";
  btn.textContent = "♡";
  btn.title = `Like @${handle}'s like`;
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    likeTheLike(handle, postAuthority, postRkey, btn);
  });
  return btn;
}

function injectButtons(postAuthority, postRkey, storedLikes, likeCreatedAts = {}) {
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
    const key = storageKey(handle, postAuthority, postRkey);
    if (storedLikes[key]) {
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
  console.log("[like-the-likes] init", { authority, rkey });

  const [allStorage, likeCreatedAts] = await Promise.all([
    chrome.storage.local.get(null),
    fetchLikeCreatedAts(authority, rkey),
  ]);

  const storedLikes = Object.fromEntries(
    Object.entries(allStorage).filter(([k]) => k.startsWith("ltl:") && k.endsWith(`:${authority}:${rkey}`))
  );

  injectButtons(authority, rkey, storedLikes, likeCreatedAts);

  activeObserver = new MutationObserver(() => {
    if (!isLikedByPage()) {
      activeObserver.disconnect();
      activeObserver = null;
      return;
    }
    injectButtons(authority, rkey, storedLikes, likeCreatedAts);
  });
  activeObserver.observe(document.body, { childList: true, subtree: true });
}

// navigation-bridge.js (MAIN world) dispatches 'ltl:navigate' on pushState/replaceState.
window.addEventListener("ltl:navigate", init);
window.addEventListener("popstate", init);

init();
