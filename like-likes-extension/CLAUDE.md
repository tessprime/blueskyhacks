# Like the Likes — Chrome Extension

A Chrome MV3 extension that injects a heart button next to each liker on a Bluesky post's liked-by page. Clicking the button creates an `app.bsky.feed.like` record in the user's own PDS whose subject is that person's like record — i.e., "liking the like".

## File Overview

| File | Role |
|------|------|
| `manifest.json` | MV3 manifest. `"permissions": ["storage"]`. All ATProto endpoints are in `host_permissions`. |
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
    <div>  ← header row: avatar | name | follow button | [our button]
    ...
```

Selector: `a[role="link"][href^="/profile/"]:has(a[role="link"])`

The `:has(a[role="link"])` clause distinguishes the outer card link from the inner avatar link (which is nested inside it). The `aria-label$="'s profile"` approach was abandoned because Bluesky may use Unicode apostrophes (U+2019).

Handle is extracted from `href`. Button is appended to `:scope > div > div:first-child` (the flex-row header).

The `data-testid="profileCard-<handle>-link"` attribute visible in the React source does **not** appear in the rendered web DOM.

### Like Flow (per button click)
1. `content.js` reads session from `localStorage`
2. Sends `LIKE_THE_LIKE` message to background with `{ likerHandle, postAuthority, postRkey, storageKey, session }`
3. `background.js` resolves handles to DIDs, calls `findLikeRecord` to walk the liker's PDS and find their like record pointing at the post
4. Calls `createLike` to write `app.bsky.feed.like` in the user's PDS with that like record as subject
5. Stores `storageKey → createdLikeUri` in `chrome.storage.local`
6. Returns the created AT URI; button flips to ♥ and URI is shown on hover; URI is logged to console

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

- **DOM selector fragility**: The `:scope > div > div:first-child` header row path was derived from a real DOM sample. If Bluesky updates their markup it may break.
- `findLikeRecord` walks the liker's entire like history in pages of 100 — can be slow for prolific likers. This is a candidate for replacement by deterministic rkeys (see Next Steps).
- The `icons/` directory is empty; Chrome will warn on load until real PNGs are added.
- `storedLikes` in `content.js` is read once at init and not updated when likes happen in the same session — the in-memory `button.dataset.likeUri` is the source of truth for toggle state after init.

## Next Steps

### 1. Use deterministic rkeys to replace the slow `findLikeRecord` crawl

`com.atproto.repo.createRecord` accepts an optional `rkey`. If we set it to a deterministic encoding of the subject like's AT URI (e.g. base64url of `at://did/app.bsky.feed.like/rkey`), then:
- Checking "have I liked this like?" becomes a direct `getRecord` call — O(1), no crawling
- Deleting is equally direct
- The current `findLikeRecord` page-walking approach can be removed entirely

The rkey must match `[a-zA-Z0-9._~-]{1,512}`. Base64url encoding (uses `A-Z a-z 0-9 - _`) works cleanly and AT URIs encode to well under 512 chars.

### 2. "X likes" count button + navigation to a likes-of-likes page

**No backend needed.** `app.bsky.feed.getLikes` accepts any AT URI as its `uri` parameter — not just posts. The AppView indexes likes of like records exactly like likes of posts. Verified: calling it with a like record AT URI returns the correct likers list.

Each liker row should show a secondary count: `♡ 3`. The extension fetches `app.bsky.feed.getLikes?uri=<likeRecordUri>` and displays `likes.length`. To get the liker's like record URI efficiently, use deterministic rkeys (step 1) — a single `getRecord` call instead of crawling.

**Displaying the likes-of-likes list**

Bluesky has no native URL for `liked-by` on an arbitrary record. Options:
- Inject a panel/drawer into the existing page (same approach as the heart button)
- Open a new tab with a custom `chrome-extension://` page the extension controls
- Intercept a synthetic URL pattern (e.g. `https://bsky.app/likes-of-like/<encoded-uri>`) via a declarativeNetRequest rule

**Recursive depth**

A likes-of-likes page could itself show like counts per entry, enabling arbitrary recursion. Decide upfront whether to support this or cap at one level deep.
