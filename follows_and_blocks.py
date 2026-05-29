#!/usr/bin/env python3
"""Download the follow and block lists for a Bluesky user."""
 
import argparse
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
 
 
def resolve_handle(handle: str) -> dict:
    """Resolve a handle to a DID and find the user's PDS."""
    # Step 1: resolve handle -> DID
    url = (
        "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?"
        + urllib.parse.urlencode({"handle": handle})
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    did = data["did"]
 
    # Step 2: resolve DID -> DID document to find PDS
    if did.startswith("did:plc:"):
        doc_url = f"https://plc.directory/{did}"
    elif did.startswith("did:web:"):
        domain = did.split(":", 2)[2]
        doc_url = f"https://{domain}/.well-known/did.json"
    else:
        raise ValueError(f"Unsupported DID method: {did}")
 
    with urllib.request.urlopen(doc_url) as resp:
        doc = json.loads(resp.read())
 
    pds = None
    for service in doc.get("service", []):
        if service.get("id") == "#atproto_pds":
            pds = service["serviceEndpoint"]
            break
 
    if not pds:
        raise ValueError(f"No PDS found for {did}")
 
    return {"did": did, "handle": handle, "pds": pds}
 
 
def list_records(pds: str, did: str, collection: str) -> list:
    """Page through all records in a collection for a given repo."""
    records = []
    cursor = None
 
    while True:
        params = {
            "repo": did,
            "collection": collection,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
 
        url = pds + "/xrpc/com.atproto.repo.listRecords?" + urllib.parse.urlencode(params)
 
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
 
        records.extend(data.get("records", []))
        cursor = data.get("cursor")
 
        if not cursor or not data.get("records"):
            break
 
    return records
 
 
def extract_follows(records: list) -> list:
    """Pull out the subject DID and createdAt from follow records."""
    follows = []
    for rec in records:
        val = rec.get("value", {})
        follows.append({
            "did": val.get("subject"),
            "created_at": val.get("createdAt"),
            "uri": rec.get("uri"),
        })
    return follows
 
 
def extract_blocks(records: list) -> list:
    """Pull out the subject DID and createdAt from block records."""
    blocks = []
    for rec in records:
        val = rec.get("value", {})
        blocks.append({
            "did": val.get("subject"),
            "created_at": val.get("createdAt"),
            "uri": rec.get("uri"),
        })
    return blocks
 
 
def main():
    parser = argparse.ArgumentParser(description="Download follow/block lists for a Bluesky user")
    parser.add_argument("handle", help="Bluesky handle (e.g. alice.bsky.social)")
    parser.add_argument("-o", "--output", help="Output file prefix (default: <handle>)", default=None)
    parser.add_argument("--json", action="store_true", help="Pretty-print to stdout instead of saving files")
    args = parser.parse_args()
 
    handle = args.handle.lstrip("@")
    prefix = args.output or handle.replace(".", "_")
 
    # Resolve identity
    print(f"Resolving {handle}...", file=sys.stderr)
    try:
        identity = resolve_handle(handle)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Error resolving handle: {e}", file=sys.stderr)
        sys.exit(1)
 
    print(f"  DID: {identity['did']}", file=sys.stderr)
    print(f"  PDS: {identity['pds']}", file=sys.stderr)
 
    # Fetch follows
    print("Fetching follows...", file=sys.stderr)
    follow_records = list_records(identity["pds"], identity["did"], "app.bsky.graph.follow")
    follows = extract_follows(follow_records)
    print(f"  {len(follows)} follows", file=sys.stderr)
 
    # Fetch blocks
    print("Fetching blocks...", file=sys.stderr)
    block_records = list_records(identity["pds"], identity["did"], "app.bsky.graph.block")
    blocks = extract_blocks(block_records)
    print(f"  {len(blocks)} blocks", file=sys.stderr)
 
    result = {
        "handle": handle,
        "did": identity["did"],
        "pds": identity["pds"],
        "follows": follows,
        "blocks": blocks,
    }
 
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        follows_file = f"{prefix}_follows.json"
        blocks_file = f"{prefix}_blocks.json"
 
        with open(follows_file, "w") as f:
            json.dump({"handle": handle, "did": identity["did"], "follows": follows}, f, indent=2)
        print(f"Saved {len(follows)} follows to {follows_file}", file=sys.stderr)
 
        with open(blocks_file, "w") as f:
            json.dump({"handle": handle, "did": identity["did"], "blocks": blocks}, f, indent=2)
        print(f"Saved {len(blocks)} blocks to {blocks_file}", file=sys.stderr)
 
 
if __name__ == "__main__":
    main()
