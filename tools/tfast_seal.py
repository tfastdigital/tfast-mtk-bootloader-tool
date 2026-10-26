#!/usr/bin/env python3
"""
Regenerate the TFast Digital integrity seal (``tfast-brand.json``).

Run this after an intentional change to any protected brand file (for example
bumping the copyright year). Until you do, the application refuses to start and
names the file whose hash no longer matches.

    python tools/tfast_seal.py            # write the seal
    python tools/tfast_seal.py --check    # verify only, change nothing
    python tools/tfast_seal.py --list     # show what is covered

What gets sealed
----------------
Every file listed in ``bl_core.tfast_brand.HASHED_FILES``: the brand module,
the compatibility shim, the guard itself, ``tfast-NOTICE.txt`` and the icon.
Source files ``bl.py`` / ``gui.py`` are checked for the ``@brand tfast-digital``
watermark instead of a hash, so ordinary edits to them never break the seal.

Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
https://tfastdigital.com/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bl_core import tfast_brand as brand  # noqa: E402
from bl_core import tfast_guard as guard  # noqa: E402


def cmd_list() -> int:
    root = guard.project_root()
    print(f"{brand.PRODUCT} v{brand.PRODUCT_VERSION} - protected files")
    print(f"root: {root}\n")
    print("HASHED (bytes must match the seal):")
    for rel in brand.HASHED_FILES:
        path = root / rel
        state = "present" if path.exists() else "MISSING"
        print(f"  {rel:34s} {state}")
    print("\nWATERMARKED (must contain {}):".format(brand.SOURCE_MARKER_TAG))
    for rel in brand.MARKED_FILES:
        path = root / rel
        state = "present" if path.exists() else "MISSING"
        print(f"  {rel:34s} {state}")
    print(f"\nMANIFEST:\n  {brand.MANIFEST_REL}")
    return 0


def cmd_check() -> int:
    ok, msg = guard.verify()
    if ok:
        print("[+] " + msg)
        return 0
    print(msg)
    return guard.EXIT_BRAND_FAILURE


def cmd_write() -> int:
    root = guard.project_root()

    missing = [rel for rel in brand.HASHED_FILES if not (root / rel).exists()]
    if missing:
        print("[-] Cannot seal: these protected files are missing:")
        for rel in missing:
            print(f"      {rel}")
        return 1

    marked_missing = [rel for rel in brand.MARKED_FILES if not (root / rel).exists()]
    if marked_missing:
        print("[!] Warning: watermarked source files missing:")
        for rel in marked_missing:
            print(f"      {rel}")

    path = guard.write_manifest(root=root)
    print(f"[+] Seal written: {path}")
    for rel in brand.HASHED_FILES:
        digest = guard.sha256_file(root / rel)
        print(f"    {rel:34s} {digest}")
    print(f"    {'manifest seal':34s} {guard.build_manifest(root)['seal']}")

    ok, msg = guard.verify(root)
    if ok:
        print("[+] Verification passed.")
        return 0
    print("[-] Verification still failing after sealing:")
    print(msg)
    return guard.EXIT_BRAND_FAILURE


def main(argv: list[str]) -> int:
    if "--list" in argv:
        return cmd_list()
    if "--check" in argv:
        return cmd_check()
    return cmd_write()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
