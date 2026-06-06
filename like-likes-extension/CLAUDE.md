# Like the Likes — Chrome Extension

A Chrome MV3 extension that injects a heart button and a "N ♡" count next to each liker on a Bluesky post's liked-by page. Clicking the heart creates an `app.bsky.feed.like` record whose subject is that person's like — "liking the like". Clicking the count opens a likes-of-likes overlay showing who liked that like, with recursive drill-down support.

## File Overview

| File | Role |
|------|------|
| `manifest.json` | MV3 manifest. `"permissions": ["storage"]`. All ATProto endpoints in `host_permissions`. Content scripts match `bsky.app/*`. |
| `navigation-bridge.js` | Injected at `document_start` in the **MAIN world**. Patches `history.pushState`/`replaceState` to dispatch `ltl:navigate` on `window`. |
| `content.js` | Injected into all `bsky.app/*` pages. Guards on `isLikedByPage()`. Injects ♡ buttons and "N ♡" counts, manages overlay, handles liked state. |
| `content.css` | Styles for `.ltl-btn`, `.ltl-count`, and the overlay + card components. |
| `background.js` | MV3 service worker (`"type": "module"`). Handles `LIKE_THE_LIKE`, `DELETE_LIKE`, `GET_LIKE_URI`. Caches like record URIs. |
| `api.js` | Pure ATProto fetch helpers. No Chrome APIs. |
| `popup.html` | Static toolbar popup, no JS. |
| `icons/` | Placeholder directory — needs actual PNGs. |

## How It Works

### SPA Navigation

Bluesky is a React SPA — Chrome only injects content scripts on the initial page load URL, not on client-side navigation. To handle this:

- `navigation-bridge.js` runs at `document_start` in the **MAIN world** (Chrome 111+ MV3 feature) and patches `history.pushState`/`replaceState` on the real `window.history` before any page code runs.
- When React Router navigates, the patch fires `window.dispatchEvent(new CustomEvent('ltl:navigate'))`.
- `content.js` (isolated world) listens for `ltl:navigate` and `popstate`, calling `init()` on each.
- `init()` guards with `isLikedByPage()` and is a no-op on non-liked-by pages.

Content scripts cannot patch `history.pushState` in the isolated world — each world has its own copy of the JS globals, so the page's React Router would call a different object. The MAIN world bridge is required.

### Authentication

The extension reads the active session from `localStorage.getItem("BSKY_STORAGE")` on `bsky.app`. Content scripts share `localStorage` with the page (same origin). The data shape is:

```json
{
  "session": {
    "currentAccount": { "did": "did:plc:..." },
    "accounts": [{ "did": "...", "accessJwt": "...", "refreshJwt": "...", "pdsUrl": "https://bsky.social/" }]
  }
}
```

`account.pdsUrl` is the correct field for the PDS URL (not `account.service`). It includes a trailing slash — strip with `.replace(/\/$/, "")`.

### DOM Selector

Each liker card is rendered by `ProfileCard.Link` as:
```html
<a role="link" href="/profile/<handle>">
  <div>
    <div>  ← header row: avatar | name | follow button | [♡ button] [N ♡ count]
```

Selector: `a[role="link"][href^="/profile/"]:has(a[role="link"])`

The `:has(a[role="link"])` clause identifies the outer card link (which contains an inner avatar link) vs the avatar link itself. `aria-label` was abandoned because Bluesky uses Unicode apostrophes (U+2019). `data-testid` visible in React source does not appear in the rendered DOM.

### Like / Unlike Flow

1. `content.js` reads session from `localStorage`
2. Sends `LIKE_THE_LIKE` to background with `{ likerHandle, postAuthority, postRkey, storageKey, likeCreatedAt, subjectUri?, session }`
3. Background calls `getLikeRecord()` (cache-first) to get the liker's like record `{ uri, cid }`
4. Calls `createLike` in the user's PDS with that like record as subject
5. Stores `storageKey → createdLikeUri` in `chrome.storage.local`; button flips to ♥

Unlike: button has `data-like-uri` → sends `DELETE_LIKE` → `deleteRecord` + remove from storage → button resets to ♡.

### Likes-of-Likes Count

Each card gets a `ltl-count` element. `loadLikesCount()` runs async:
1. Sends `GET_LIKE_URI` → background resolves + caches the like record URI
2. Content fetches `app.bsky.feed.getLikes?uri=<likeRecordUri>&limit=100` from the public AppView
3. Count updates to `N ♡`; if N > 0 the element is enabled and opens the overlay on click

`app.bsky.feed.getLikes` accepts any AT URI — not just posts. The AppView indexes likes of likes the same way. No backend needed.

### Likes-of-Likes Overlay

Clicking "N ♡" sets `location.hash = #ltl/<encodedLikeUri>`, pushing a browser history entry. A `hashchange` listener calls `renderOverlay(likeUri)`.

**Overlay positioning**: `getCenterColumn()` traverses up from a liker card to find the `div[style*="max-width: 600px"]` container (Bluesky's center content column). The overlay is `position: fixed` with `left`/`right` from that element's `getBoundingClientRect()`, and `top: 0; bottom: 0`. A `ResizeObserver` repositions on window resize.

**Theme**: `getPageTheme()` walks up from the center column to find the first ancestor with a non-transparent background color, reads it directly, and computes dark/light from luminance. This handles Bluesky's light, dark, and "dim" themes without hardcoding colors.

**Card rendering**: Each `renderLikerCard(actor, likeCreatedAt, subjectUri, storedLikes, actorDid)` builds a profile card with avatar, display name, handle, a ♡ like button, and a "N ♡" count. Cards have `data-ltl-injected` to prevent the main `injectButtons` MutationObserver from processing them.

**Drill-down**: Clicking a card sends `GET_LIKE_URI` with the current overlay's `likeUri` as `subjectUri` to find that person's like-of-the-like record, then pushes a new hash. This is recursive — each level of the overlay works the same way.

**Closing**: Browser back / clicking ← pops the hash history entry → `hashchange` → `destroyOverlay()`.

### Recursive Likes (subjectUri)

`getLikeRecord` and `handleLikeTheLike` both accept an optional `subjectUri`. When provided, it is used as the subject URI directly (bypassing the hardcoded `app.bsky.feed.post` collection construction). This allows the same like/count/overlay machinery to work at any recursion depth.

Cache key when `subjectUri` is provided: `ltl:likerec:<likerHandle>:<subjectUri>`  
Cache key for top-level (post): `ltl:likerec:<likerHandle>:<postAuthority>:<postRkey>`

### TID Cursor Optimisation

`findLikeRecord` walks a liker's like records on their PDS to find the one matching the subject. Without a hint it would page through their entire history.

`fetchLikeCreatedAts()` calls `getLikes` on the post at init and builds a `handle → createdAt` map. For overlay cards, `createdAt` comes from the `getLikes` response for the like record. This is stored on each button as `data-like-created-at` and passed in messages.

`createdAt` (client-stamped) is always ≤ the TID (PDS-stamped after receiving the request). For descending `listRecords`, the cursor must be above the TID, so we add a 5-second buffer: `cursor = TID(createdAt + 5000ms)`.

### Like Record Cache

`background.js` caches `{ uri, cid }` in `chrome.storage.local`. Key formats:

- Top-level: `ltl:likerec:<likerHandle>:<postAuthority>:<postRkey>`
- Recursive: `ltl:likerec:<likerHandle>:<subjectUri>`

Not scoped to `actorDid` — the liker's record URI is a global fact independent of who is viewing.

### State Persistence

Created-like key: `ltl:<actorDid>:<likerHandle>:<postAuthority>:<postRkey>`

For overlay likes, `postAuthority` and `postRkey` are extracted from the `subjectUri` AT URI via `parseAtUri()`, keeping the key format consistent. Scoped to `actorDid` so multiple accounts don't share liked state.

### Token Refresh

Access JWTs expire after ~2 hours. Before each API call, background checks `exp` and calls `refreshSession` if expiry is within 60 seconds.

## ATProto Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `app.bsky.feed.getLikes` (public AppView) | Post's likers + `createdAt`; counts at any level |
| `com.atproto.identity.resolveHandle` | Handle → DID |
| `com.atproto.repo.listRecords` | Walk a user's like records to find the one for a subject |
| `com.atproto.repo.createRecord` | Create our like |
| `com.atproto.repo.deleteRecord` | Delete our like |
| `com.atproto.server.refreshSession` | Refresh expired access token |
| PLC directory (`plc.directory/<did>`) | DID → PDS URL |

## Known Bugs

- **Overlay mispositioned on refresh**: `getCenterColumn()` traverses up from a liker card (`a[role="link"]:has(a[role="link"])`). On a hard refresh with a hash already set, `renderOverlay` is called before the liked-by list has rendered, so no liker cards exist yet and `getCenterColumn()` returns null — the overlay falls back to full-viewport. Fix: defer overlay rendering until cards are present, or find the center column by a different selector that doesn't depend on card presence.

- **Excessive underlines in recursive overlay**: The `<a>` card elements in the overlay (and their nested `<a>` avatar links) pick up some inherited or injected underline style when drilling into recursive like pages. Needs investigation — likely a `text-decoration` inheritance issue on `.ltl-card` or `.ltl-card-avatar-wrap` that should be explicitly reset.

## Known Limitations

- **Count capped at 100**: `getLikes` is fetched with `limit=100`. Counts above 100 show as 100. Unlikely to matter for likes-of-likes in practice.
- **`storedLikes` read once at init / overlay open**: in-memory `button.dataset.likeUri` is the source of truth for toggle state within a session.
- **DOM selector fragility**: The `:scope > div > div:first-child` header row path was derived from a real DOM sample. Bluesky markup changes may break it.
- The `icons/` directory is empty; Chrome will warn on load.

## Next Steps

### 1. Fix overlay positioning on refresh

When the page is hard-refreshed with `#ltl/...` in the URL, `getCenterColumn()` finds no cards and returns null. Options:
- Wait for the first MutationObserver callback (cards present) before calling `renderOverlay`
- Find the center column via a selector that exists before cards render (e.g. `div[style*="max-width: 600px"]` with a fallback to the last match, not the first)

### 2. Fix underline inheritance in overlay

Audit `text-decoration` on `.ltl-card`, `.ltl-card-avatar-wrap`, and their children. Add explicit resets where needed.

### 3. Use deterministic rkeys

`com.atproto.repo.createRecord` accepts an optional `rkey`. A deterministic encoding of the subject AT URI (e.g. base64url) would let "have I liked this?" become a direct `getRecord` — O(1), no PDS crawl. Removes `findLikeRecord`, the TID cursor, and the like record cache entirely.

The rkey must match `[a-zA-Z0-9._~-]{1,512}`. Base64url (uses `A-Z a-z 0-9 - _`) works and AT URIs are well under 512 chars encoded.
