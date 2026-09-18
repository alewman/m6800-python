"""Fetch the pinned Motorola reference scans this project's documents cite.

These are the **datasheet-tier** sources: under this project's oracle-tier rule
(docs/validation.md) they are the judge for documented behaviour, because no
hardware-captured corpus exists for the 6800 family.  Every one is a bitsavers
scan of a Motorola publication; Motorola's copyright stands, the scans are
fetched for reference only, and nothing here is redistributed — the download
directory is gitignored.

    python scripts/fetch_reference_docs.py [--dest DIR] [--only SHORTNAME]

Each file is checked against the SHA-256 recorded below, which is also printed
in docs/validation.md.  A mismatch means bitsavers replaced the scan: do not
silently update the hash, record the change.

bitsavers answers 403 to a default urllib user agent, so one is set.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

BASE = "https://www.bitsavers.org/components/motorola/"

DOCUMENTS = {
    "M68PRM": (
        "6800/Motorola_M6800_Programming_Reference_Manual_M68PRM(D)_Nov76.pdf",
        "M6800 Programming Reference Manual, M68PRM(D), Nov 1976",
    ),
    "MCSDD": (
        "6800/MC6800_Microcomputer_System_Design_Data_1976.pdf",
        "MC6800 Microcomputer System Design Data, 1976 (contains the MC6800 data sheet)",
    ),
    "M6801RM": (
        "6801/MC6801RM_AD2_MC6801_Reference_Manual_May84.pdf",
        "MC6801 Reference Manual, MC6801RM/AD2, May 1984 (covers MC6801/68701/MC6803)",
    ),
    "APPS": (
        "6800/M6800_Microprocessor_Applications_Manual_1975.pdf",
        "M6800 Microprocessor Applications Manual, 1975",
    ),
}

# SHA-256 of each scan as fetched on 2026-09-12; recorded in docs/validation.md.
PINNED_SHA256 = {
    "M68PRM": "c2ca7c06d3eca33467aa11dab35cb65e3fe8a12f97c98007239ea3a45e379835",
    "MCSDD": "b6b7b88fcdc9dfc536e9898b7ae396cdc9cc328067c017749c891ad3e7eded8a",
    "M6801RM": "1b4a5b321664fb73e7a8b1e3ea042512ed673dc133dbc2b3a81fd5196622f075",
    "APPS": "d0131b26a2e353d86d5b719a9c57413fdeec3b521c9c24b136d64df8bd42234b",
}

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) m6800-python/docs-fetch"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str, dest: Path) -> Path:
    relative, title = DOCUMENTS[name]
    target = dest / f"{name}.pdf"
    if not target.exists():
        request = urllib.request.Request(BASE + relative, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request) as response, target.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    digest = _sha256(target)
    expected = PINNED_SHA256[name]
    status = "ok" if digest == expected else ("UNPINNED" if expected == "REPLACE" else "MISMATCH")
    print(f"{name:<9} {target.stat().st_size:>10,} bytes  {digest}  {status}  {title}")
    if status == "MISMATCH":
        raise SystemExit(f"{name}: expected SHA-256 {expected}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", type=Path, default=Path(__file__).resolve().parents[1] / "reference"
    )
    parser.add_argument("--only", choices=sorted(DOCUMENTS))
    arguments = parser.parse_args()
    arguments.dest.mkdir(parents=True, exist_ok=True)
    for name in [arguments.only] if arguments.only else sorted(DOCUMENTS):
        fetch(name, arguments.dest)


if __name__ == "__main__":
    main()
