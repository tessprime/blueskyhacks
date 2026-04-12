import requests
import json
import supersecret
import argparse
import sys

def get_did_from_handle(handle: str) -> str:
    """Resolve a Bluesky handle to its DID."""
    r = requests.get(
        "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle},
    )
    r.raise_for_status()
    return r.json()["did"]

def get_pds_from_handle(handle: str) -> str:
    """Resolve a Bluesky handle to its PDS URL."""
    # 1. Resolve handle -> DID
    r1 = requests.get(
        "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle},
    )
    r1.raise_for_status()
    did = r1.json()["did"]

    # 2. Query PLC directory for DID -> PDS
    r2 = requests.get(f"https://plc.directory/{did}")
    r2.raise_for_status()
    doc = r2.json()

    # 3. Extract serviceEndpoint
    for service in doc.get("service", []):
        if service.get("type") == "AtprotoPersonalDataServer":
            return service["serviceEndpoint"]

    raise ValueError(f"No PDS endpoint found for {handle} ({did})")

def get_all_posts_authenticated(did, access_token, pds_url="https://bsky.social"):
    base = f"https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed"
    cursor = None
    all_posts = []

    headers = {"Authorization": f"Bearer {access_token}"}

    while True:
        params = {"actor": did, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(base, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        print(f"Fetched {len(data['feed'])} records", file=sys.stderr)
        #print(f"Fetched {data['feed']} records", file=sys.stderr)
        feed = data.get("feed", [])
        all_posts.extend(feed)

        cursor = data.get("cursor")
        if not cursor or not feed:
            break

    return all_posts


def login(handle: str, app_password: str, pds_url="https://bsky.social"):
    url = f"{pds_url.rstrip('/')}/xrpc/com.atproto.server.createSession"
    payload = {"identifier": handle, "password": app_password}
    resp = requests.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["accessJwt"], data["did"]

def main():
    parser = argparse.ArgumentParser(description="Fetch all posts from a Bluesky user.")
    parser.add_argument("user", help="Bluesky handle (e.g., user.bsky.social) or DID")
    parser.add_argument("-o", "--output", help="Output file path (default: <user>.json)")
    options = parser.parse_args()
    target_user = options.user
    output_file = options.output or f"{target_user}.json"
    user, password = supersecret.getSecret("bluesky", "USERNAME"), supersecret.getSecret("bluesky", "PASSWORD")
    jwt, did = login(user, password)
    posts = get_all_posts_authenticated(target_user, jwt, get_pds_from_handle(target_user))

    print(f"Fetched {len(posts)} posts", file=sys.stderr)
    with open(output_file, "w") as f:
        json.dump(posts, f)

if __name__ == "__main__":
    # Example usage:
    # If the user is hosted on bsky.social, use its PDS endpoint.
    main()
