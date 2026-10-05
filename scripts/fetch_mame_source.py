"""Fetch MAME's 6800 CPU core source at the pinned release, with hashes.

Every trace in docs/mame-oracle.md was taken with MAME **0.285**, so 0.285 is
what the documents quote.  Read the core from this script's download, not from
whatever MAME source tree happens to sit on the machine: the one here was
**0.261**, whose 6800 core differs in ways that matter — the `CLI`/`SEI`/`TAP`
interrupt-delay handling was rewritten between the two releases — so a document
derived from it would be wrong.

This script downloads the six files of the core from the `mame0285` tag into a
gitignored directory and verifies each SHA-256.  MAME's CPU cores carry
`// license:BSD-3-Clause`; the files are fetched for reference and are not
redistributed here.

    python scripts/fetch_mame_source.py [--dest DIR]

docs/validation.md records these hashes.  Everything the documents say about
"what MAME does" can be re-checked against exactly these bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

TAG = "mame0285"
BASE = f"https://raw.githubusercontent.com/mamedev/mame/{TAG}/src/devices/cpu/m6800/"

PINNED_SHA256 = {
    "m6800.cpp": "974d0c205992d81bfa5c60bb4e2bccf03b7102c047b272c60285bf30180e4485",
    "m6800.h": "42cf7ecb77327d9d660519d666c2b06918898360c2a40d97f53573ba2a05c7c4",
    "m6801.cpp": "f744e99e7deb17c1d4c47747611c58f5ad13a47531a55c163067e18c42b75e95",
    "m6801.h": "4b6351d17f6d901a7a05204ad4fccb1a56bbc33a76832c2af67ecfce0853a2be",
    "6800ops.hxx": "f4c692a1c51435a9c0b76a36c66dc8060fc6e6963da7cba84d75ac65fcc5dec1",
    "6800dasm.cpp": "34b6497ef445231f27d2bc97adcd6e028381b849161e1cab86685b538a5b626f",
}

DEFAULT_DEST = Path(__file__).resolve().parents[1] / "reference" / TAG


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    dest = parser.parse_args().dest
    dest.mkdir(parents=True, exist_ok=True)

    for name, expected in PINNED_SHA256.items():
        target = dest / name
        if not target.exists():
            with urllib.request.urlopen(BASE + name) as response:
                target.write_bytes(response.read())
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected:
            raise SystemExit(f"{name}: expected SHA-256 {expected}, got {digest}")
        print(f"{name:<14} {target.stat().st_size:>7,} bytes  {digest}  ok")
    print(f"MAME {TAG} 6800 core in {dest}")


if __name__ == "__main__":
    main()
