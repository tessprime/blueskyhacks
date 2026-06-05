# Like the Likes — Chrome Extension

A Chrome MV3 extension that injects a heart button next to each liker on a Bluesky post's liked-by page. Clicking the button creates an `app.bsky.feed.like` record in the user's own PDS whose subject is that person's like record — i.e., "liking the like".

## File Overview

| File | Role |
|------|------|
| `manifest.json` | MV3 manifest. No `permissions` except `"storage"`. All ATProto endpoints are in `host_permissions`. |
| `content.js` | Injected into `bsky.app/profile/*/post/*/liked-by`. Reads session from localStorage, injects buttons, handles toggle state. |
| `content.css` | Styles for the `.ltl-btn` heart button. |
| `background.js` | MV3 service worker (`"type": "module"`). Handles `LIKE_THE_LIKE` and `DELETE_LIKE` messages, writes to `chrome.storage.local`. |
| `api.js` | Pure ATProto fetch helpers. No Chrome APIs. |
| `popup.html` | Static toolbar popup, no JS. |
| `icons/` | Placeholder directory — needs actual PNGs to load in Chrome. |

## How It Works

### Authentication
The extension reads the user's active Bluesky session directly from `localStorage.getItem("BSKY_STORAGE")` on the `bsky.app` page. Content scripts share `localStorage` with the page (same origin), so no login UI is needed. The data shape is:

```json
{
  "session": {
    "currentAccount": { "did": "did:plc:..." },
    "accounts": [{ "did": "...", "accessJwt": "...", "refreshJwt": "...", "pdsUrl": "..." }]
  }
}
```

This key and schema come from `src/state/persisted/index.web.ts` in the Bluesky social-app source (`external_src/social-app`).

### DOM Selector
Each liker card is rendered by `ProfileCard.Link` as:
```html
<a role="link" href="/profile/<handle>" aria-label="View ...'s profile">
  <div>
    <div>  ← header row: avatar | name | follow button | [our button]
    ...
```

Selector: `a[role="link"][href^="/profile/"][aria-label$="'s profile"]`  
Handle is extracted from `href`. Button is appended to `:scope > div > div:first-child`.

The `data-testid="profileCard-<handle>-link"` attribute visible in the React source does **not** appear in the rendered web DOM.

### Like Flow (per button click)
1. `content.js` reads session from `localStorage`
2. Sends `LIKE_THE_LIKE` message to background with `{ likerHandle, postAuthority, postRkey, storageKey, session }`
3. `background.js` resolves handles to DIDs, calls `findLikeRecord` to walk the liker's PDS and find their like record pointing at the post
4. Calls `createLike` to write `app.bsky.feed.like` in the user's PDS with that like record as subject
5. Stores `storageKey → createdLikeUri` in `chrome.storage.local`
6. Returns the created AT URI; button flips to ♥ and URI is shown on hover

### Unlike Flow
1. Button already has `data-like-uri` set from a previous like
2. Sends `DELETE_LIKE` message with `{ likeUri, storageKey, session }`
3. `background.js` calls `deleteRecord` and removes the key from `chrome.storage.local`
4. Button resets to ♡

### Token Refresh
Access JWTs expire after ~2 hours. Before each API call, `background.js` checks the `exp` claim (decoded from the JWT payload without a library) and calls `refreshSession` if expiry is within 60 seconds. The refreshed token is used for that request only — the page manages its own token lifecycle in `localStorage`.

### State Persistence
`chrome.storage.local` key format: `ltl:<likerHandle>:<postAuthority>:<postRkey>`  
Value: the created like's AT URI (e.g. `at://did:plc:.../app.bsky.feed.like/...`)

On page load, `content.js` reads all storage, filters by suffix `:${authority}:${rkey}` to find likes for the current post, and restores the ♥ state on matching buttons without any extra network calls.

## ATProto Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `com.atproto.identity.resolveHandle` | Handle → DID |
| `com.atproto.repo.listRecords` | Walk a user's like records to find the one for this post |
| `com.atproto.repo.createRecord` | Create our like pointing at their like |
| `com.atproto.repo.deleteRecord` | Delete our like (unlike) |
| `com.atproto.server.refreshSession` | Refresh expired access token |
| PLC directory (`plc.directory/<did>`) | DID → PDS URL |

## Known Limitations / Things to Verify

- **DOM selector fragility**: The `aria-label$="'s profile"` selector and `:scope > div > div:first-child` header row path were derived from a single real DOM sample. If Bluesky updates their markup these may break.
- `findLikeRecord` walks the liker's entire like history in pages of 100 — can be slow for prolific likers.
- The `icons/` directory is empty; Chrome will warn on load until real PNGs are added.
- `storedLikes` in `content.js` is read once at init and not updated when likes happen in the same session — the in-memory `button.dataset.likeUri` is the source of truth for toggle state after init.
