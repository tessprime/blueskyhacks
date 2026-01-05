import asyncio
import fasttext
import json
import websockets
import re

# Only posts; remove the query param to see *everything*
URI = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"

model = fasttext.load_model("lid.176.ftz")
ignore_list = {"did:plc:7ia5gyyqv2will5wxhrdey5h"}

def print_event(event, output):
    commit = event.get("commit")
    record = commit.get("record")
    print(event.get("did"), record.get("text"))
    output.write(json.dumps(event)+"\n")

async def main():
    with open("output.jsonl", "a") as output:
        async with websockets.connect(URI, ping_interval=20) as ws:
            async for raw in ws:
                try:
                    event = json.loads(raw)
                    if event.get('kind') == 'commit' and event["commit"].get('operation') == 'create':
                        if event.get("did") in ignore_list:
                            continue
                        commit = event.get('commit', {})
                        record = commit.get('record', {})
                        embed = record.get("embed", {})
                        facets = record.get("facets", {})
                        if embed.get("$type") == "app.bsky.embed.external":
                            continue
                        if facets:
                            continue
                        if commit.get('collection') == 'app.bsky.feed.post':
                            #print(f"[{record.get('createdAt')}] {event.get('did')}: {record.get('text')}")
                            text = record.get("text").replace("\n", "") 
                            if len(text) < 20:
                                continue
                            if "@" and "bsky" in text:
                                continue
                            # No spaces yet at least 20 chars long? Interesting.
                            # do we recognize the language?
                            lang, prob = model.predict(text.strip("\n"))
                            if ("en" in lang[0] and " " not in text):
                                # long sequence of characters with no spaces?
                                pass
                            elif prob[0] > .5:
                                continue
                            #sufficiently interesting.
                            print_event(event, output)
                except Exception as e:
                    print("Parse error:", e)

if __name__ == "__main__":
    asyncio.run(main())
