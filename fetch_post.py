#!/usr/bin/env python3
"""Fetch a Bluesky record directly from the user's PDS.

Accepts:
  - bsky.app post URL:  https://bsky.app/profile/<handle>/post/<rkey>
  - AT URI:             at://<did-or-handle>/<collection>/<rkey>
"""

import sys
import json
import urllib.request
import urllib.parse
from urllib.error import URLError


def resolve_handle(handle: str) -> str:
    url = f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle={urllib.parse.quote(handle)}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())["did"]


def get_pds_and_handle(did: str) -> tuple[str, str | None]:
    """Return (pds_endpoint, handle_or_None) from a DID document."""
    if did.startswith("did:plc:"):
        url = f"https://plc.directory/{urllib.parse.quote(did)}"
    elif did.startswith("did:web:"):
        domain = did[len("did:web:"):]
        url = f"https://{domain}/.well-known/did.json"
    else:
        raise ValueError(f"Unsupported DID method: {did}")

    with urllib.request.urlopen(url) as resp:
        doc = json.loads(resp.read())

    pds = None
    for service in doc.get("service", []):
        if service.get("type") == "AtprotoPersonalDataServer":
            pds = service["serviceEndpoint"].rstrip("/")
            break

    if pds is None:
        raise ValueError(f"No AtprotoPersonalDataServer found in DID doc for {did}")

    handle = None
    for aka in doc.get("alsoKnownAs", []):
        if aka.startswith("at://"):
            handle = aka[len("at://"):]
            break

    return pds, handle


def fetch_record(pds: str, did: str, collection: str, rkey: str) -> dict:
    params = urllib.parse.urlencode({
        "repo": did,
        "collection": collection,
        "rkey": rkey,
    })
    url = f"{pds}/xrpc/com.atproto.repo.getRecord?{params}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def parse_bsky_url(url: str) -> tuple[str, str, str]:
    """Return (handle_or_did, collection, rkey) from a bsky.app post URL."""
    parsed = urllib.parse.urlparse(url)
    parts = parsed.path.strip("/").split("/")
    # expected: profile/<handle>/post/<rkey>
    if len(parts) != 4 or parts[0] != "profile" or parts[2] != "post":
        raise ValueError(f"Unrecognised bsky.app URL format: {url}")
    return parts[1], "app.bsky.feed.post", parts[3]


def parse_at_uri(uri: str) -> tuple[str, str, str]:
    """Return (handle_or_did, collection, rkey) from an AT URI."""
    # at://<authority>/<collection>/<rkey>
    if not uri.startswith("at://"):
        raise ValueError(f"Not an AT URI: {uri}")
    rest = uri[len("at://"):]
    parts = rest.split("/", 2)
    if len(parts) != 3:
        raise ValueError(f"AT URI must have authority/collection/rkey: {uri}")
    return parts[0], parts[1], parts[2]


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bsky-post-url-or-at-uri>", file=sys.stderr)
        sys.exit(1)

    arg = sys.argv[1]
    if arg.startswith("at://"):
        authority, collection, rkey = parse_at_uri(arg)
    else:
        authority, collection, rkey = parse_bsky_url(arg)

    if authority.startswith("did:"):
        did = authority
        print(f"DID    : {did}")
    else:
        print(f"Handle : {authority}")
        did = resolve_handle(authority)
        print(f"DID    : {did}")

    pds, handle = get_pds_and_handle(did)
    print(f"PDS    : {pds}")

    if collection == "app.bsky.feed.post" and handle:
        print(f"URL    : https://bsky.app/profile/{handle}/post/{rkey}")

    print(f"Collection: {collection}")

    record = fetch_record(pds, did, collection, rkey)
    print(f"\n--- Record ---")
    print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
