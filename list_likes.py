#!/usr/bin/env python3
"""List all likes on a post, showing each liker's handle, DID, and like record."""

import asyncio
import json
import sys
import urllib.parse
import urllib.request

import supersecret
from async_client_rate_limited import AsyncClientRateLimited
from atproto_client.exceptions import BadRequestError


def parse_input(arg: str) -> str:
    """Return an AT URI from a bsky.app URL or pass through an AT URI."""
    if arg.startswith("at://"):
        return arg
    parsed = urllib.parse.urlparse(arg)
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 4 or parts[0] != "profile" or parts[2] != "post":
        raise ValueError(f"Unrecognised bsky.app URL format: {arg}")
    handle, rkey = parts[1], parts[3]
    return f"at://{handle}/app.bsky.feed.post/{rkey}"


def _resolve_pds_sync(did: str) -> str | None:
    url = f"https://plc.directory/{urllib.parse.quote(did)}"
    try:
        with urllib.request.urlopen(url) as resp:
            doc = json.loads(resp.read())
        for service in doc.get("service", []):
            if service.get("type") == "AtprotoPersonalDataServer":
                return service["serviceEndpoint"].rstrip("/")
    except Exception:
        pass
    return None


async def resolve_pds(did: str) -> str | None:
    return await asyncio.to_thread(_resolve_pds_sync, did)


async def find_like_uri(
    actor_did: str, post_uri: str, pds_clients: dict[str, AsyncClientRateLimited]
) -> str | None:
    pds = await resolve_pds(actor_did)
    if pds is None:
        print(f"Could not resolve PDS for {actor_did}", file=sys.stderr)
        return None

    if pds not in pds_clients:
        pds_clients[pds] = AsyncClientRateLimited(base_url=pds)
    pds_client = pds_clients[pds]

    cursor = None
    for _ in range(5):
        try:
            resp = await pds_client.com.atproto.repo.list_records(
                {"repo": actor_did, "collection": "app.bsky.feed.like", "limit": 100, "cursor": cursor, "reverse": False}
            )
        except BadRequestError as e:
            print(f"BadRequestError for {actor_did} on {pds}: {e.response.content}", file=sys.stderr)
            return None
        for record in resp.records:
            print(record, post_uri)
            if getattr(getattr(record.value, "subject", None), "uri", None) == post_uri:
                return record.uri
        cursor = resp.cursor
        if not cursor:
            return None
    return None


async def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bsky-url-or-at-uri>", file=sys.stderr)
        return 1
    uri = parse_input(sys.argv[1])

    client = AsyncClientRateLimited()
    await client.login(
        supersecret.getSecret("bsky.app", "username"),
        supersecret.getSecret("bsky.app", "api_token"),
    )

    # Normalize handle to DID so it matches stored subject URIs in like records.
    authority = uri[len("at://"):].split("/")[0]
    if not authority.startswith("did:"):
        resolved = await client.resolve_handle(authority)
        uri = f"at://{resolved.did}/{'/'.join(uri[len('at://'):].split('/')[1:])}"

    likes = []
    cursor = None
    while True:
        resp = await client.app.bsky.feed.get_likes({"uri": uri, "limit": 100, "cursor": cursor})
        likes.extend(resp.likes)
        cursor = resp.cursor
        if not cursor:
            break

    pds_clients: dict[str, AsyncClientRateLimited] = {}
    like_uris = await asyncio.gather(
        *[find_like_uri(like.actor.did, uri, pds_clients) for like in likes]
    )

    for like, like_uri in zip(likes, like_uris):
        a = like.actor
        print(f"handle  : {a.handle}")
        print(f"did     : {a.did}")
        print(f"at uri  : {like_uri or '(not found)'}")
        print(f"created : {like.created_at}")
        print()

    print(f"Total likes: {len(likes)}")
    return 0


sys.exit(asyncio.run(main()))
