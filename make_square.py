#!/usr/bin/env python3

import argparse
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("output")
parser.add_argument(
    "--color",
    default="#ff0000",
    help="Color name or hex value (e.g. red, blue, #ff0000)",
)
parser.add_argument(
    "--size",
    type=int,
    default=1024,
    help="Image width and height in pixels",
)

args = parser.parse_args()

img = Image.new(
    "RGB",
    (args.size, args.size),
    color=args.color,
)

img.save(args.output)

print(f"Wrote {args.output}")