import supersecret
import requests
import json
import asyncio

from tqdm.asyncio import trange, tqdm

from atproto import AsyncClient

BLUESKY_API_URL="https://bsky.social/xrpc/"

# Raw requests versions
def get_api_token(username, password):
    """Authenticate and return an API token."""
    response = requests.post(f"{BLUESKY_API_URL}com.atproto.server.createSession", json={
        "identifier": username,
        "password":password 
    })
    response.raise_for_status()
    return response.json()["accessJwt"]

def get_blocked_users(token):
    """Retrieve a list of blocked users."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BLUESKY_API_URL}app.bsky.graph.getBlocks", headers=headers)
    response.raise_for_status()
    return [user for user in response.json().get("blocks", [])]

async def main():
    client = AsyncClient()
    token = await client.login(
        supersecret.getSecret("bsky.app", "username"),
        supersecret.getSecret("bsky.app", "api_token"))
    blocked = await client.app.bsky.graph.block.list(client.me.did)
    print(blocked.records)
    mutes = []
    for key, record in blocked.records.items():
        print(record.subject)
        mutes.append(client.mute(record.subject))
    await tqdm.gather(*mutes)

    # warning:
    # If something never existed, deleting it will return succeess,
    # so if you screw up the rkey, you'll be none the wiser.
    unblocks = []
    for key, record in blocked.records.items():
        unblocks.append(client.app.bsky.graph.block.delete(client.me.did, key.split("/")[-1]))
    res = await tqdm.gather(*unblocks)
    
asyncio.get_event_loop().run_until_complete(main())
