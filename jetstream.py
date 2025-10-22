import asyncio
import json
import websockets

# Only posts; remove the query param to see *everything*
URI = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"

async def main():
    async with websockets.connect(URI, ping_interval=20) as ws:
        async for raw in ws:
            try:
                event = json.loads(raw)
                if event.get('kind') == 'commit' and event["commit"].get('operation') == 'create':
                    commit = event.get('commit') or {}
                    record = commit.get('record') or {}
                    if commit.get('collection') == 'app.bsky.feed.post':
                        print(f"[{record.get('createdAt')}] {event.get('did')}: {record.get('text')}")
                        pass
            except Exception as e:
                print("Parse error:", e)

if __name__ == "__main__":
    asyncio.run(main())