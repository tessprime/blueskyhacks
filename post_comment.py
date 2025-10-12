import supersecret
import requests
import json
import asyncio

from atproto import AsyncClient
BLUESKY_API_URL="https://bsky.social/xrpc/"

async def main():
    client = AsyncClient()
    token = await client.login(
        supersecret.getSecret("bsky.app", "username"),
        supersecret.getSecret("bsky.app", "api_token"))
    
asyncio.get_event_loop().run_until_complete(main())
