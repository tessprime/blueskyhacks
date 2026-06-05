
import argparse

from multiformats import CID
from multiformats.multihash import digest


def compute_cid(path):
    with open(path, "rb") as f:
        data = f.read()

    mh = digest(data, "sha2-256")

    # ATProto blobs use CIDv1 + raw codec
    cid = CID("base32", 1, "raw", mh)

    return str(cid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()

    print(compute_cid(args.file))


if __name__ == "__main__":
    main()