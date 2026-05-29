#!/usr/bin/env python3

import requests
import sys

def resolve_handle(handle: str):
    """
    Resolve a Bluesky handle -> DID
    """
    url = "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle"
    r = requests.get(url, params={"handle": handle}, timeout=10)
    r.raise_for_status()
    return r.json()["did"]


def get_did_doc(did: str):
    """
    Fetch DID document from PLC directory
    """
    if not did.startswith("did:plc:"):
        raise ValueError("Only did:plc supported in this simple example")

    plc_id = did.split(":")[-1]
    url = f"https://plc.directory/{did}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def extract_pds(did_doc: dict):
    """
    Find the PDS endpoint from service entries
    """
    for svc in did_doc.get("service", []):
        if svc.get("type") == "AtprotoPersonalDataServer":
            return svc.get("serviceEndpoint")
    return None

def download_repo(did: str, pds: str, out_path: str) -> None:
    """
    Download the user's ATProto repo as a CAR file from their PDS.
    """
    url = f"{pds.rstrip('/')}/xrpc/com.atproto.sync.getRepo"

    with requests.get(url, params={"did": did}, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

def main():
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} handle.bsky.social [out.car]")
        sys.exit(2)

    handle = sys.argv[1].lstrip("@")
    out_path = sys.argv[2] if len(sys.argv) == 3 else f"{handle}.car"

    did = resolve_handle(handle)
    did_doc = get_did_doc(did)
    pds = extract_pds(did_doc)

    print(f"handle: {handle}")
    print(f"did:    {did}")
    print(f"pds:    {pds or 'not found'}")

    if not pds:
        raise RuntimeError("No PDS endpoint found in DID document")

    download_repo(did, pds, out_path)
    print(f"saved:  {out_path}")

if __name__ == "__main__":
    main()
