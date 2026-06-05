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
      pds: account.pdsUrl || "https://bsky.social",
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
    { type: "LIKE_THE_LIKE", likerHandle: handle, postAuthority, postRkey, storageKey: storageKey(handle, postAuthority, postRkey), session },
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

function injectButtons(postAuthority, postRkey, storedLikes) {
  const cards = document.querySelectorAll(
    'a[role="link"][href^="/profile/"][aria-label$="\'s profile"]:not([data-ltl-injected])'
  );

  for (const card of cards) {
    card.dataset.ltlInjected = "1";

    const handle = card.getAttribute("href").replace(/^\/profile\//, "");
    if (!handle) continue;

    const headerRow = card.querySelector(":scope > div > div:first-child");
    if (!headerRow) continue;

    const btn = makeLikeButton(handle, postAuthority, postRkey);

    // Restore liked state if we've previously liked this person's like.
    const key = storageKey(handle, postAuthority, postRkey);
    if (storedLikes[key]) {
      btn.dataset.likeUri = storedLikes[key];
      btn.textContent = "♥";
      btn.title = storedLikes[key];
      btn.classList.add("ltl-liked");
    }

    headerRow.appendChild(btn);
  }
}

async function init() {
  const { authority, rkey } = postInfoFromUrl();

  // Load all stored likes once; filter to keys for this post.
  const allStorage = await chrome.storage.local.get(null);
  const storedLikes = Object.fromEntries(
    Object.entries(allStorage).filter(([k]) => k.startsWith("ltl:") && k.endsWith(`:${authority}:${rkey}`))
  );

  injectButtons(authority, rkey, storedLikes);

  const observer = new MutationObserver(() => injectButtons(authority, rkey, storedLikes));
  observer.observe(document.body, { childList: true, subtree: true });
}

init();
