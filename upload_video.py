import argparse
import datetime as dt
import time

import requests
import supersecret

PDS = "https://bsky.social"
APPVIEW = "https://public.api.bsky.app"


def xrpc(service, method):
    return f"{service}/xrpc/{method}"

import json
import subprocess

def get_video_dimensions(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    info = json.loads(result.stdout)

    video_stream = next(
        s for s in info["streams"]
        if s["codec_type"] == "video"
    )

    return video_stream["width"], video_stream["height"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--text", default="Direct PDS video upload test")
    args = ap.parse_args()

    width, height = get_video_dimensions(args.video)

    handle = supersecret.getSecret("bluesky", "USERNAME")
    password = supersecret.getSecret("bluesky", "PASSWORD")

    sess = requests.post(
        xrpc(PDS, "com.atproto.server.createSession"),
        json={"identifier": handle, "password": password},
        timeout=30,
    )
    sess.raise_for_status()

    session = sess.json()
    token = session["accessJwt"]
    did = session["did"]

    headers = {"Authorization": f"Bearer {token}"}

    with open(args.video, "rb") as f:
        up = requests.post(
            xrpc(PDS, "com.atproto.repo.uploadBlob"),
            headers={**headers, "Content-Type": "video/mp4"},
            data=f,
            timeout=120,
        )
    up.raise_for_status()

    blob = up.json()["blob"]

    print("Uploaded blob:")
    print(blob)

    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    record = {
        "$type": "app.bsky.feed.post",
        "text": args.text,
        "createdAt": now,
        "embed": {
            "$type": "app.bsky.embed.video",
            "video": blob,
            "aspectRatio": {
                "width": width,
                "height": height,
            },
        },
    }

    cr = requests.post(
        xrpc(PDS, "com.atproto.repo.createRecord"),
        headers=headers,
        json={
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=30,
    )
    cr.raise_for_status()

    created = cr.json()
    uri = created["uri"]

    print("Created post:", uri)

    for i in range(30):
        gp = requests.get(
            xrpc(APPVIEW, "app.bsky.feed.getPosts"),
            params={"uris": uri},
            timeout=30,
        )
        gp.raise_for_status()

        posts = gp.json().get("posts", [])
        embed = posts[0].get("embed") if posts else None

        print(f"\nPoll {i}:")
        print(embed)

        if embed and embed.get("$type") == "app.bsky.embed.video#view":
            if embed.get("playlist"):
                print("\nPlayable playlist appeared:", embed["playlist"])
                break

        time.sleep(2)


if __name__ == "__main__":
    main()