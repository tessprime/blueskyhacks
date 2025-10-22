import asyncio
import json
import websockets
import time

# Only posts; remove the query param to see *everything*
URI = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"

async def main():
    prev = time.time()
    cur = prev
    records = 0
    async with websockets.connect(URI, ping_interval=20) as ws:
        async for raw in ws:
            try:
                event = json.loads(raw)
                records += 1
                cur = time.time()
                if cur - prev >= 5:
                    print(f"Received {records} records in the last {cur - prev:.1f} seconds")
                    records = 0
                    prev = cur
                if event.get('kind') == 'commit' and event["commit"].get('operation') == 'create':
                    commit = event.get('commit') or {}
                    record = commit.get('record') or {}
                    if commit.get('collection') == 'app.bsky.feed.post':
                        #print(f"[{record.get('createdAt')}] {event.get('did')}: {record.get('text')}")
                        pass
            except Exception as e:
                print("Parse error:", e)

if __name__ == "__main__":
    asyncio.run(main())