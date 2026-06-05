#!/usr/bin/env python3
"""Like any ATProto record given a bsky.app URL or AT URI."""

import sys
import json
import asyncio
import urllib.request
import urllib.parse

import supersecret
from atproto import AsyncClient


def resolve_handle(handle: str) -> str:
    url = f"https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle={urllib.parse.quote(handle)}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())["did"]


def get_pds(did: str) -> str:
    if did.startswith("did:plc:"):
        url = f"https://plc.directory/{urllib.parse.quote(did)}"
    elif did.startswith("did:web:"):
        domain = did[len("did:web:"):]
        url = f"https://{domain}/.well-known/did.json"
    else:
        raise ValueError(f"Unsupported DID method: {did}")
    with urllib.request.urlopen(url) as resp:
        doc = json.loads(resp.read())
    for service in doc.get("service", []):
        if service.get("type") == "AtprotoPersonalDataServer":
            return service["serviceEndpoint"].rstrip("/")
    raise ValueError(f"No PDS found for {did}")


def fetch_record_cid(pds: str, did: str, collection: str, rkey: str) -> str:
    params = urllib.parse.urlencode({"repo": did, "collection": collection, "rkey": rkey})
    url = f"{pds}/xrpc/com.atproto.repo.getRecord?{params}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())["cid"]


def parse_input(arg: str) -> tuple[str, str, str]:
    """Return (authority, collection, rkey) from a bsky.app URL or AT URI."""
    if arg.startswith("at://"):
        rest = arg[len("at://"):]
        parts = rest.split("/", 2)
        if len(parts) != 3:
            raise ValueError(f"AT URI must be at://<authority>/<collection>/<rkey>: {arg}")
        return parts[0], parts[1], parts[2]
    else:
        parsed = urllib.parse.urlparse(arg)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 4 or parts[0] != "profile" or parts[2] != "post":
            raise ValueError(f"Unrecognised bsky.app URL format: {arg}")
        return parts[1], "app.bsky.feed.post", parts[3]


async def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bsky-url-or-at-uri>", file=sys.stderr)
        sys.exit(1)

    authority, collection, rkey = parse_input(sys.argv[1])

    did = authority if authority.startswith("did:") else resolve_handle(authority)
    pds = get_pds(did)
    cid = fetch_record_cid(pds, did, collection, rkey)
    at_uri = f"at://{did}/{collection}/{rkey}"

    print(f"URI : {at_uri}")
    print(f"CID : {cid}")

    client = AsyncClient()
    await client.login(
        supersecret.getSecret("bsky.app", "username"),
        supersecret.getSecret("bsky.app", "api_token"),
    )
    print(client)
    result = await client.like(at_uri, cid)
    print(f"Liked: {result.uri}")


asyncio.get_event_loop().run_until_complete(main())
