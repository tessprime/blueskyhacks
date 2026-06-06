// ATProto API helpers used by the background service worker.

const PLC_DIRECTORY = "https://plc.directory";
const BSKY_PUBLIC_API = "https://public.api.bsky.app";

export async function resolveHandle(handle) {
  const url = `https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle=${encodeURIComponent(handle)}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`resolveHandle failed: ${resp.status}`);
  return (await resp.json()).did;
}

export async function getPds(did) {
  let url;
  if (did.startsWith("did:plc:")) {
    url = `${PLC_DIRECTORY}/${encodeURIComponent(did)}`;
  } else if (did.startsWith("did:web:")) {
    const domain = did.slice("did:web:".length);
    url = `https://${domain}/.well-known/did.json`;
  } else {
    throw new Error(`Unsupported DID method: ${did}`);
  }
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`getPds failed for ${did}: ${resp.status}`);
  const doc = await resp.json();
  for (const service of doc.service ?? []) {
    if (service.type === "AtprotoPersonalDataServer") {
      return service.serviceEndpoint.replace(/\/$/, "");
    }
  }
  throw new Error(`No PDS found for ${did}`);
}

// ATProto TID: 64-bit value = (timestamp_us << 10) | clockid, encoded as
// 13-char base32 using the s32 alphabet.
const S32 = '234567abcdefghijklmnopqrstuvwxyz';

function createdAtToTidCursor(createdAt, bufferMs = 5000) {
  // Produce a TID just after the target timestamp so listRecords (newest-first)
  // starts paging from right above the target record.
  const ms = BigInt(Date.parse(createdAt) + bufferMs);
  const tidInt = (ms * 1000n << 10n) | 1023n; // max clockid
  let tid = '';
  let n = tidInt;
  for (let i = 0; i < 13; i++) {
    tid = S32[Number(n & 31n)] + tid;
    n >>= 5n;
  }
  return tid;
}

// Walk the liker's like records on their PDS to find the one pointing at postUri.
// likeCreatedAt (ISO string) is optional — if provided, a TID cursor is used to
// jump straight to the right spot instead of crawling from the beginning.
export async function findLikeRecord(likerDid, postUri, likeCreatedAt) {
  const pds = await getPds(likerDid);
  const cursor = likeCreatedAt ? createdAtToTidCursor(likeCreatedAt) : undefined;

  // With a good cursor, the record should be in the first page.
  // Without one, we page through everything (slow for prolific likers).
  const params = new URLSearchParams({
    repo: likerDid,
    collection: "app.bsky.feed.like",
    limit: "100",
  });
  if (cursor) params.set("cursor", cursor);

  const resp = await fetch(`${pds}/xrpc/com.atproto.repo.listRecords?${params}`);
  if (!resp.ok) throw new Error(`listRecords failed for ${likerDid}: ${resp.status}`);
  const data = await resp.json();

  for (const record of data.records ?? []) {
    if (record.value?.subject?.uri === postUri) {
      return { uri: record.uri, cid: record.cid };
    }
  }
  return null;
}

// Create a like record in the authenticated user's PDS pointing at subjectUri/subjectCid.
export async function createLike(pds, accessJwt, repoDid, subjectUri, subjectCid) {
  const resp = await fetch(`${pds}/xrpc/com.atproto.repo.createRecord`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessJwt}`,
    },
    body: JSON.stringify({
      repo: repoDid,
      collection: "app.bsky.feed.like",
      record: {
        $type: "app.bsky.feed.like",
        subject: { uri: subjectUri, cid: subjectCid },
        createdAt: new Date().toISOString(),
      },
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`createLike failed: ${resp.status} ${text}`);
  }
  return resp.json(); // { uri, cid }
}

export async function deleteRecord(pds, accessJwt, repoDid, collection, rkey) {
  const resp = await fetch(`${pds}/xrpc/com.atproto.repo.deleteRecord`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessJwt}`,
    },
    body: JSON.stringify({ repo: repoDid, collection, rkey }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`deleteRecord failed: ${resp.status} ${text}`);
  }
}

// Use the refreshJwt to get a new accessJwt without re-entering the password.
// Returns an updated session object.
export async function refreshSession(session) {
  const resp = await fetch(`${session.pds}/xrpc/com.atproto.server.refreshSession`, {
    method: "POST",
    headers: { Authorization: `Bearer ${session.refreshJwt}` },
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Token refresh failed: ${resp.status} ${text}`);
  }
  const data = await resp.json();
  return { ...session, accessJwt: data.accessJwt, refreshJwt: data.refreshJwt };
}

// Decode the exp claim from a JWT without verifying the signature.
export function jwtExpiresAt(jwt) {
  try {
    const payload = JSON.parse(atob(jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.exp ? payload.exp * 1000 : null; // ms
  } catch {
    return null;
  }
}
