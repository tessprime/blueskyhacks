# Like the Likes — Chrome Extension

A Chrome MV3 extension that injects a heart button next to each liker on a Bluesky post's liked-by page. Clicking the button creates an `app.bsky.feed.like` record in the user's own PDS whose subject is that person's like record — i.e., "liking the like". Each card also shows a "N ♡" count of how many people have liked that like.

## File Overview

| File | Role |
|------|------|
| `manifest.json` | MV3 manifest. `"permissions": ["storage"]`. All ATProto endpoints are in `host_permissions`. Content script matches `bsky.app/*`. |
| `navigation-bridge.js` | Injected at `document_start` in the **MAIN world**. Patches `history.pushState`/`replaceState` to dispatch `ltl:navigate` on `window` so the isolated-world content script can detect SPA navigation. |
| `content.js` | Injected into all `bsky.app/*` pages. Guards on `isLikedByPage()`. Reads session from localStorage, injects ♡ buttons and "N ♡" count elements, handles toggle state. |
| `content.css` | Styles for `.ltl-btn` (heart button) and `.ltl-count` (likes count). |
| `background.js` | MV3 service worker (`"type": "module"`). Handles `LIKE_THE_LIKE`, `DELETE_LIKE`, and `GET_LIKE_URI` messages. Caches like record URIs. Writes to `chrome.storage.local`. |
| `api.js` | Pure ATProto fetch helpers. No Chrome APIs. |
| `popup.html` | Static toolbar popup, no JS. |
| `icons/` | Placeholder directory — needs actual PNGs to load in Chrome. |

## How It Works

### SPA Navigation

Bluesky is a React SPA — Chrome only injects content scripts on the initial page load URL, not on client-side navigation. To handle this:

- `navigation-bridge.js` runs at `document_start` in the **MAIN world** (Chrome 111+ MV3 feature) and patches `history.pushState`/`replaceState` on the real `window.history` before any page code runs.
- When React Router navigates, the patch fires `window.dispatchEvent(new CustomEvent('ltl:navigate'))`.
- `content.js` (isolated world) listens for `ltl:navigate` and `popstate`, calling `init()` on each.
- `init()` guards with `isLikedByPage()` and is a no-op on non-liked-by pages.

Content scripts cannot patch `history.pushState` in the isolated world because each world has its own copy of the JS globals — the page's React Router calls a different `history` object. The MAIN world bridge is required.

### Authentication
The extension reads the user's active Bluesky session directly from `localStorage.getItem("BSKY_STORAGE")` on the `bsky.app` page. Content scripts share `localStorage` with the page (same origin), so no login UI is needed. The data shape is:

```json
{
  "session": {
    "currentAccount": { "did": "did:plc:..." },
    "accounts": [{ "did": "...", "accessJwt": "...", "refreshJwt": "...", "pdsUrl": "https://bsky.social/" }]
  }
}
```

This key and schema come from `src/state/persisted/index.web.ts` in the Bluesky social-app source (`external_src/social-app`).

**Important:** `account.pdsUrl` is the correct field for the PDS URL (not `account.service`). It is reliably populated but includes a trailing slash — strip it with `.replace(/\/$/, "")` before use.

### DOM Selector
Each liker card is rendered by `ProfileCard.Link` as:
```html
<a role="link" href="/profile/<handle>">
  <div>
    <div>  ← header row: avatar | name | follow button | [♡ button] [N ♡ count]
    ...
```

Selector: `a[role="link"][href^="/profile/"]:has(a[role="link"])`

The `:has(a[role="link"])` clause distinguishes the outer card link from the inner avatar link (which is nested inside it). The `aria-label$="'s profile"` approach was abandoned because Bluesky may use Unicode apostrophes (U+2019).

Handle is extracted from `href`. Button is appended to `:scope > div > div:first-child` (the flex-row header).

The `data-testid="profileCard-<handle>-link"` attribute visible in the React source does **not** appear in the rendered web DOM.

### Like Flow (per button click)
1. `content.js` reads session from `localStorage`
2. Sends `LIKE_THE_LIKE` message to background with `{ likerHandle, postAuthority, postRkey, storageKey, likeCreatedAt, session }`
3. `background.js` calls `getLikeRecord()` (cache-first) to get the liker's like record URI + CID
4. Calls `createLike` to write `app.bsky.feed.like` in the user's PDS with that like record as subject
5. Stores `storageKey → createdLikeUri` in `chrome.storage.local`
6. Returns the created AT URI; button flips to ♥ and URI is shown on hover; URI is logged to console

### Unlike Flow
1. Button already has `data-like-uri` set from a previous like
2. Sends `DELETE_LIKE` message with `{ likeUri, storageKey, session }`
3. `background.js` calls `deleteRecord` and removes the key from `chrome.storage.local`
4. Button resets to ♡

### Likes-of-Likes Count
Each card gets a `ltl-count` element injected alongside the heart button. After injection, `loadLikesCount()` runs async:
1. Sends `GET_LIKE_URI` to background → `getLikeRecord()` (cache-first) returns the liker's like record URI
2. Content script directly fetches `app.bsky.feed.getLikes?uri=<likeRecordUri>&limit=100` from the public AppView API
3. Count element updates to `N ♡`

`app.bsky.feed.getLikes` works on any AT URI — not just posts. The AppView indexes likes of like records the same way. No backend needed.

### TID Cursor Optimisation
`findLikeRecord` in `api.js` walks a liker's like records on their PDS to find the one pointing at the post. Without a hint this would page through their entire like history.

At `init()`, `fetchLikeCreatedAts()` calls `getLikes` on the post (public API) and builds a `handle → createdAt` map. This `createdAt` is stored on each button as `data-like-created-at` and passed in `LIKE_THE_LIKE` and `GET_LIKE_URI` messages.

`createdAt` is the client's timestamp when the like was created; the rkey TID is generated by the PDS when it processes the request. Because the PDS stamps the TID after receiving the request, the TID is always ≥ `createdAt`. For `listRecords` (descending, newest-first), we need the cursor to be above the TID, so we add a buffer: `cursor = TID(createdAt + 5000ms)`. This is conservative but safe — the buffer needs to exceed one-way network latency between the liker's client and their PDS.

### Like Record Cache
`background.js` caches each liker's like record as `{ uri, cid }` in `chrome.storage.local`:

Key format: `ltl:likerec:<likerHandle>:<postAuthority>:<postRkey>`

This is **not** scoped to the logged-in account because the liker's record is a global fact. Both `LIKE_THE_LIKE` and `GET_LIKE_URI` go through `getLikeRecord()` which checks this cache before calling `findLikeRecord`.

### Token Refresh
Access JWTs expire after ~2 hours. Before each API call, `background.js` checks the `exp` claim (decoded from the JWT payload without a library) and calls `refreshSession` if expiry is within 60 seconds. The refreshed token is used for that request only — the page manages its own token lifecycle in `localStorage`.

### State Persistence
Created-like storage key format: `ltl:<actorDid>:<likerHandle>:<postAuthority>:<postRkey>`  
Value: the created like's AT URI (e.g. `at://did:plc:.../app.bsky.feed.like/...`)

Scoped to `actorDid` so multiple Bluesky accounts on the same Chrome profile don't share liked state. On page load, `content.js` reads all storage, filters by `ltl:<actorDid>:` prefix and `:${authority}:${rkey}` suffix to find likes for the current post, and restores the ♥ state on matching buttons without extra network calls.

## ATProto Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `app.bsky.feed.getLikes` (public AppView) | Post's likers + their `createdAt`; likes-of-likes counts |
| `com.atproto.identity.resolveHandle` | Handle → DID |
| `com.atproto.repo.listRecords` | Walk a user's like records to find the one for this post |
| `com.atproto.repo.createRecord` | Create our like pointing at their like |
| `com.atproto.repo.deleteRecord` | Delete our like (unlike) |
| `com.atproto.server.refreshSession` | Refresh expired access token |
| PLC directory (`plc.directory/<did>`) | DID → PDS URL |

## Known Limitations / Things to Verify

- **DOM selector fragility**: The `:scope > div > div:first-child` header row path was derived from a real DOM sample. If Bluesky updates their markup it may break.
- **Count capped at 100**: `getLikes` is fetched with `limit=100`. If a like has more than 100 likes, the count will show 100. In practice this is unlikely for likes-of-likes.
- **`storedLikes` read once at init**: not updated when likes happen in the same session — the in-memory `button.dataset.likeUri` is the source of truth for toggle state after init.
- The `icons/` directory is empty; Chrome will warn on load until real PNGs are added.

## Next Steps

### 1. Use deterministic rkeys to replace the `findLikeRecord` crawl

`com.atproto.repo.createRecord` accepts an optional `rkey`. If we set it to a deterministic encoding of the subject like's AT URI (e.g. base64url of `at://did/app.bsky.feed.like/rkey`), then:
- Checking "have I liked this like?" becomes a direct `getRecord` call — O(1), no crawling
- Deleting is equally direct
- The `findLikeRecord` page-walking approach and the TID cursor optimisation can be removed entirely

The rkey must match `[a-zA-Z0-9._~-]{1,512}`. Base64url encoding (uses `A-Z a-z 0-9 - _`) works cleanly and AT URIs encode to well under 512 chars.

### 2. "N ♡" count as a link to a likes-of-likes page

The count element is currently a disabled `<button>`. It should become a link that opens a likes-of-likes list.

Bluesky has no native URL for `liked-by` on an arbitrary record. Options:
- Inject a panel/drawer into the existing page (same approach as the heart button)
- Open a new tab with a custom `chrome-extension://` page the extension controls
- Intercept a synthetic URL pattern (e.g. `https://bsky.app/likes-of-like/<encoded-uri>`) via a declarativeNetRequest rule

**Recursive depth**: a likes-of-likes page could itself show like counts per entry, enabling arbitrary recursion. Decide upfront whether to support this or cap at one level deep.
