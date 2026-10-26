"""
TFast Digital - brand integrity guard.

Enhanced, multi-layered anti-tamper for the TFast MTK Bootloader Tool. This
module is the enforcement engine; :mod:`bl_core.tfast_brand` holds the brand
data it protects.

Layers
------
1. **In-memory constants** - :func:`bl_core.tfast_brand.verify` re-derives the
   attribution from primitives and compares it to the canonical string plus its
   SHA-256 seal.
2. **On-disk manifest** - ``tfast-brand.json`` records the SHA-256 of every
   protected file (brand module, shim, guard, notice, icon).
3. **Manifest self-seal** - the manifest carries its own seal over its body, so
   editing the recorded hashes is detected too.
4. **Source watermark** - ``bl.py`` and ``gui.py`` must still contain the
   ``@brand tfast-digital`` marker. Marker-based so ordinary edits are fine.
5. **Import-hijack detection** - the loaded brand module must be the real file
   on disk, not a stub injected into ``sys.modules``.
6. **Runtime re-check** - :func:`watch` lets a long-running GUI re-verify on a
   timer, so patching the process after startup is caught.

Honest scope
------------
Python source can always be edited by someone with the ability and the
determination to recompute the seal. This guard makes removal **tamper-evident
and loud**: a stripped or altered build refuses to start and names the failing
file, instead of silently shipping an unattributed copy. It is not a
cryptographic guarantee, and it is not a substitute for a licence agreement.

Re-seal after a legitimate change:

    python tools/tfast_seal.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import tfast_brand as brand

#: Exit code used when brand integrity fails (kept stable for scripts).
EXIT_BRAND_FAILURE = 3

MANIFEST_ALGORITHM = "sha256"
MANIFEST_SCHEMA = 1


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def project_root() -> Path:
    """Project root (the folder that contains ``bl.py``)."""
    return Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str | None:
    """Return the SHA-256 of a file, or None when it cannot be read."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def manifest_body(entries: dict) -> dict:
    """The canonical, seal-free body of the manifest."""
    return {
        "product": brand.PRODUCT,
        "brand_id": brand.BRAND_ID,
        "version": brand.PRODUCT_VERSION,
        "algorithm": MANIFEST_ALGORITHM,
        "schema": MANIFEST_SCHEMA,
        "files": dict(sorted(entries.get("files", {}).items())),
    }


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def seal_of(entries: dict) -> str:
    return hashlib.sha256(
        canonical_json(manifest_body(entries)).encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def build_manifest(root: Path | None = None) -> dict:
    """Compute a fresh manifest for the current on-disk files."""
    root = root or project_root()
    files: dict[str, str] = {}
    for rel in brand.HASHED_FILES:
        digest = sha256_file(root / rel)
        if digest:
            files[rel] = digest
    body = {"files": files}
    manifest = manifest_body(body)
    manifest["seal"] = seal_of(body)
    return manifest


def write_manifest(path: Path | None = None, root: Path | None = None) -> Path:
    root = root or project_root()
    target = path or (root / brand.MANIFEST_REL)
    manifest = build_manifest(root)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return target


def load_manifest(root: Path | None = None) -> tuple[dict | None, str | None]:
    root = root or project_root()
    path = root / brand.MANIFEST_REL
    if not path.exists():
        return None, f"Integrity manifest is missing: {brand.MANIFEST_REL}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"Integrity manifest is unreadable: {exc}"
    if not isinstance(data, dict) or "files" not in data or "seal" not in data:
        return None, "Integrity manifest is malformed (missing files/seal)."
    return data, None


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def _check_memory() -> list[str]:
    ok, msg = brand.verify()
    return [] if ok else [msg]


def _check_manifest(root: Path) -> list[str]:
    problems: list[str] = []
    data, err = load_manifest(root)
    if err:
        return [err]

    assert data is not None
    if not isinstance(data.get("files"), dict):
        return ["Integrity manifest 'files' entry is not an object."]

    # --- self-seal -------------------------------------------------------- #
    claimed = str(data.get("seal", ""))
    computed = seal_of({"files": data["files"]})
    if claimed != computed:
        problems.append(
            "The integrity manifest has been edited (self-seal mismatch). "
            f"{brand.MANIFEST_REL} must be regenerated with tools/tfast_seal.py."
        )

    if data.get("brand_id") != brand.BRAND_ID:
        problems.append("The integrity manifest belongs to a different brand.")

    recorded = data["files"]
    for rel in brand.HASHED_FILES:
        path = root / rel
        if not path.exists():
            problems.append(f"Protected file is missing: {rel}")
            continue
        expected = recorded.get(rel)
        if not expected:
            problems.append(f"Protected file is not covered by the seal: {rel}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            problems.append(
                f"Protected file has been modified: {rel}\n"
                f"    expected {expected}\n"
                f"    actual   {actual}"
            )
    return problems


def _check_markers(root: Path) -> list[str]:
    problems: list[str] = []
    for rel in brand.MARKED_FILES:
        path = root / rel
        if not path.exists():
            problems.append(f"Source file is missing: {rel}")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"Cannot read {rel}: {exc}")
            continue
        if brand.SOURCE_MARKER_TAG not in text:
            problems.append(
                f"Brand watermark removed from {rel} "
                f"(expected marker {brand.SOURCE_MARKER_TAG!r})."
            )
    return problems


def _check_import_hijack(root: Path) -> list[str]:
    """The loaded brand module must be the real file on disk."""
    problems: list[str] = []
    mod = sys.modules.get(__name__.rsplit(".", 1)[0] + ".tfast_brand")
    if mod is None:
        return ["The brand module is not loaded."]
    loaded = getattr(mod, "__file__", None)
    if not loaded:
        return ["The brand module has no file origin (possible stub injection)."]
    try:
        loaded_path = Path(loaded).resolve()
        expected_path = (root / brand.BRAND_MODULE_REL).resolve()
    except OSError:
        return ["Cannot resolve the brand module path."]
    if loaded_path != expected_path:
        problems.append(
            "The brand module was replaced in memory "
            f"({loaded_path} != {expected_path})."
        )
    return problems


def _check_notice(root: Path) -> list[str]:
    path = root / brand.NOTICE_REL
    if not path.exists():
        return [f"Copyright notice is missing: {brand.NOTICE_REL}"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"Cannot read {brand.NOTICE_REL}: {exc}"]
    if brand.AGENCY_LONG not in text:
        return [f"{brand.NOTICE_REL} no longer names {brand.AGENCY_LONG}."]
    return []


def check(root: Path | None = None) -> list[str]:
    """Run every layer. Returns a list of problems (empty means healthy)."""
    root = root or project_root()
    problems: list[str] = []
    problems += _check_memory()
    problems += _check_manifest(root)
    problems += _check_markers(root)
    problems += _check_notice(root)
    problems += _check_import_hijack(root)
    # de-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def verify(root: Path | None = None) -> tuple[bool, str]:
    problems = check(root)
    if not problems:
        return True, "Brand and copyright integrity verified."
    return False, format_failure(problems)


def format_failure(problems: list[str]) -> str:
    lines = [
        "BRAND INTEGRITY FAILURE",
        "",
        f"This copy of {brand.PRODUCT} has had its TFast Digital copyright or",
        "branding altered, and will not run.",
        "",
        "Problems found:",
    ]
    for i, p in enumerate(problems, 1):
        lines.append(f"  {i}. {p}")
    lines += [
        "",
        "This software is proprietary. The copyright notice and attribution are",
        "a condition of the licence under which it was supplied.",
        "",
        "To restore a legitimate copy:",
        f"  {brand.URL_GITHUB}",
        "",
        "If you made an intentional change to the brand files, re-seal the build:",
        "  python tools/tfast_seal.py",
        "",
        f"{brand.COPYRIGHT_LINE}",
        f"{brand.URL_WEBSITE}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Enforcement
# --------------------------------------------------------------------------- #
def enforce(root: Path | None = None, stream=None) -> int:
    """Verify and, on failure, print the report. Returns a process exit code."""
    ok, msg = verify(root)
    if ok:
        return 0
    out = stream or sys.stderr
    try:
        print("\n" + msg + "\n", file=out)
    except Exception:
        print(msg)
    return EXIT_BRAND_FAILURE


class GuardWatch:
    """Periodic re-verification for long-running processes (the GUI).

    Call :meth:`poll` from the UI timer. ``poll`` is rate-limited internally so
    it is cheap enough to call on every tick.
    """

    def __init__(self, interval_seconds: float = 45.0, root: Path | None = None) -> None:
        self.interval = float(interval_seconds)
        self.root = root or project_root()
        self._last = 0.0
        self._failures = 0

    def poll(self, now: float) -> tuple[bool, str]:
        """Return ``(healthy, report)``. Healthy until a check fails."""
        if now - self._last < self.interval:
            return True, ""
        self._last = now
        problems = check(self.root)
        if problems:
            self._failures += 1
            return False, format_failure(problems)
        return True, ""

    @property
    def failure_count(self) -> int:
        return self._failures
