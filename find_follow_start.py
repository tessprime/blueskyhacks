#!/usr/bin/env python3
import argparse
import requests

APPVIEW = "https://public.api.bsky.app"
COLLECTION = "app.bsky.graph.follow"


def xrpc_get(host, method, params):
    r = requests.get(f"{host}/xrpc/{method}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_handle(handle):
    handle = handle.removeprefix("@")
    data = xrpc_get(APPVIEW, "com.atproto.identity.resolveHandle", {
        "handle": handle,
    })
    return data["did"]

def describe_repo(did):
    return xrpc_get(APPVIEW, "com.atproto.repo.describeRepo", {
        "repo": did,
    })

def resolve_did_doc(did):
    if did.startswith("did:plc:"):
        return requests.get(f"https://plc.directory/{did}", timeout=30).json()

    if did.startswith("did:web:"):
        domain = did.removeprefix("did:web:").replace(":", "/")
        return requests.get(f"https://{domain}/.well-known/did.json", timeout=30).json()

    raise ValueError(f"Unsupported DID method: {did}")


def get_pds_for_did(did):
    doc = resolve_did_doc(did)

    for service in doc.get("service", []):
        if (
            service.get("id") == "#atproto_pds"
            or service.get("id", "").endswith("#atproto_pds")
        ):
            return service["serviceEndpoint"].rstrip("/")

    raise RuntimeError(f"No PDS endpoint found for {did}")


def find_follow_record(source_handle, target_handle):
    source_did = resolve_handle(source_handle)
    target_did = resolve_handle(target_handle)

    pds = get_pds_for_did(source_did)

    cursor = None

    while True:
        params = {
            "repo": source_did,
            "collection": COLLECTION,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor

        data = xrpc_get(pds, "com.atproto.repo.listRecords", params)

        for rec in data.get("records", []):
            value = rec.get("value", {})
            if value.get("subject") == target_did:
                return {
                    "source_handle": source_handle,
                    "source_did": source_did,
                    "target_handle": target_handle,
                    "target_did": target_did,
                    "uri": rec.get("uri"),
                    "cid": rec.get("cid"),
                    "createdAt": value.get("createdAt"),
                    "record": value,
                }

        cursor = data.get("cursor")
        if not cursor:
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Find when one Bluesky account followed another."
    )
    parser.add_argument("source", help="Handle of the account doing the following")
    parser.add_argument("target", help="Handle of the account being followed")
    args = parser.parse_args()

    result = find_follow_record(args.source, args.target)

    if result is None:
        print(f"{args.source} does not currently follow {args.target}, or no record was found.")
        return

    print(f"{result['source_handle']} follows {result['target_handle']}")
    print(f"createdAt: {result['createdAt']}")
    print(f"uri:       {result['uri']}")
    print(f"cid:       {result['cid']}")


if __name__ == "__main__":
    main()
