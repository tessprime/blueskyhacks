import {
  resolveHandle,
  findLikeRecord,
  createLike,
  deleteRecord,
  refreshSession,
  jwtExpiresAt,
} from "./api.js";

async function refreshIfNeeded(session) {
  const exp = jwtExpiresAt(session.accessJwt);
  if (exp && exp - Date.now() < 60_000) {
    return refreshSession(session);
  }
  return session;
}

// Resolves and caches the like record (uri + cid) for a given liker on a given subject.
// subjectUri can be passed directly (e.g. a like record at://did/feed.like/rkey);
// otherwise it is constructed from postAuthority + postRkey as a feed.post URI.
async function getLikeRecord(likerHandle, postAuthority, postRkey, likeCreatedAt, subjectUri) {
  const cacheKey = subjectUri
    ? `ltl:likerec:${likerHandle}:${subjectUri}`
    : `ltl:likerec:${likerHandle}:${postAuthority}:${postRkey}`;
  const stored = await chrome.storage.local.get(cacheKey);
  if (stored[cacheKey]) return JSON.parse(stored[cacheKey]);

  let resolvedSubjectUri = subjectUri;
  if (!resolvedSubjectUri) {
    const resolvedPostDid = postAuthority.startsWith("did:")
      ? postAuthority
      : await resolveHandle(postAuthority);
    resolvedSubjectUri = `at://${resolvedPostDid}/app.bsky.feed.post/${postRkey}`;
  }

  const likerDid = likerHandle.startsWith("did:")
    ? likerHandle
    : await resolveHandle(likerHandle);

  const record = await findLikeRecord(likerDid, resolvedSubjectUri, likeCreatedAt);
  if (!record) return null;

  await chrome.storage.local.set({ [cacheKey]: JSON.stringify(record) });
  return record;
}

async function handleLikeTheLike({ likerHandle, postAuthority, postRkey, storageKey, likeCreatedAt, subjectUri, session }) {
  session = await refreshIfNeeded(session);
  const likeRecord = await getLikeRecord(likerHandle, postAuthority, postRkey, likeCreatedAt, subjectUri);
  if (!likeRecord) throw new Error(`No like record found for @${likerHandle} on this post`);
  const result = await createLike(session.pds, session.accessJwt, session.did, likeRecord.uri, likeRecord.cid);
  await chrome.storage.local.set({ [storageKey]: result.uri });
  return result;
}

async function handleDeleteLike({ likeUri, storageKey, session }) {
  session = await refreshIfNeeded(session);

  // at://<did>/<collection>/<rkey>
  const [, collection, rkey] = likeUri.replace("at://", "").split("/");
  await deleteRecord(session.pds, session.accessJwt, session.did, collection, rkey);
  await chrome.storage.local.remove(storageKey);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "LIKE_THE_LIKE") {
    handleLikeTheLike(message)
      .then((result) => sendResponse({ ok: true, uri: result.uri }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === "GET_LIKE_URI") {
    getLikeRecord(message.likerHandle, message.postAuthority, message.postRkey, message.likeCreatedAt, message.subjectUri)
      .then(record => sendResponse({ ok: true, uri: record?.uri ?? null }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === "DELETE_LIKE") {
    handleDeleteLike(message)
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});
