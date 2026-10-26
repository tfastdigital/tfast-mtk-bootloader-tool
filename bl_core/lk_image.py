"""
MediaTek LK (Little Kernel) image analysis and in-place lock-state patching.

This implements the **in-place** model described in the TFast Digital LK
research, not the "download a pre-made binary" model:

    read the device's OWN lk partition
      -> validate the MTK image header
      -> score the content markers and select a device profile
      -> locate the lock-state getter site(s)
      -> refuse when the profile match is ambiguous
      -> back up the original
      -> apply the documented 4-byte stubs in place (image size unchanged)
      -> write back to the same partition

Why in-place matters: a pre-made binary must match the model *and* the exact
firmware revision, or it bricks the device. Patching the image the device
already boots removes that coupling entirely.

Documented technique A stubs (Transsion / AArch64), from the research:

    ORIGINAL  88 00 80 52 / 08 00 00 B9 / E0 03 1F 2A / C0 03 5F D6
              MOV W8,#4   ; LKS_LOCK
              STR W8,[X0]
              MOV W0,WZR
              RET

    NF2F1337  28 00 80 52 / 08 00 00 B9 / C0 03 5F D6 / 1F 20 03 D5   -> #1 LKS_DEFAULT
    PF327090  68 00 80 52 / 08 00 00 B9 / E0 03 1F 2A / C0 03 5F D6   -> #3 LKS_UNLOCK
    D91BB63E  1F 00 00 B9 / E0 03 1F 2A / C0 03 5F D6                  -> #0 store zero

`LKS_*` values cross-checked against mtkclient's seccfg enum:
    LKS_DEFAULT 1, LKS_MP_DEFAULT 2, LKS_UNLOCK 3, LKS_LOCK 4,
    LKS_VERIFIED 5, LKS_CUSTOM 6

HONEST SCOPE
------------
* Only the AArch64 technique-A path is implemented. There is **no documented
  ARM32 stub pattern**, so ARM32 images are analysed and then refused rather
  than patched with guessed bytes.
* Three of the five documented profiles (DA80523A, CB20200E, B88E59B0) had
  their marker sets inside the obfuscator VM and are not published, so they
  cannot be matched here. They fall through to the two autonomous profiles.
* Static analysis cannot prove a patched image unlocks a device. Only a device
  can. Everything here is pre-flight validation, not a guarantee.

Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
https://tfastdigital.com/
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------- #
# MTK image header
# --------------------------------------------------------------------------- #
MTK_MAGIC = 0x58881688
MTK_HEADER_SIZE = 512
MTK_HEADER_FMT = "<II"           # magic, size (the name follows separately)
MTK_NAME_LEN = 32


# --------------------------------------------------------------------------- #
# Technique A instruction patterns (AArch64, little-endian on disk)
# --------------------------------------------------------------------------- #
#: The stock `get_lock_state` store form: MOV W8,#4 (LKS_LOCK) / STR / MOV W0,WZR / RET
STOCK_LOCK_SITE = bytes.fromhex("88008052" "080000B9" "E0031F2A" "C0035FD6")

#: `CBZ W8, #8` — the branch that precedes every observed stock site. Used as a
#: confidence anchor so an accidental byte match is not mistaken for the getter.
SITE_ANCHOR_CBZ_W8 = bytes.fromhex("48000034")

PATCH_STUBS: dict[int, bytes] = {
    # value written to *X0, stub bytes
    1: bytes.fromhex("28008052" "080000B9" "C0035FD6" "1F2003D5"),            # LKS_DEFAULT
    3: bytes.fromhex("68008052" "080000B9" "E0031F2A" "C0035FD6"),            # LKS_UNLOCK
    0: bytes.fromhex("1F0000B9" "E0031F2A" "C0035FD6"),                      # store zero
}

STUB_NAMES = {1: "NF2F1337", 3: "PF327090", 0: "D91BB63E"}
STUB_VALUES = {1: "LKS_DEFAULT(1)", 3: "LKS_UNLOCK(3)", 0: "zero(0)"}

DEFAULT_PATCH_VALUE = 3          # explicit LKS_UNLOCK

#: How many zero bytes follow the short #3/#0 stubs in the vendor layout. The
#: tail is NOP padding, not part of the semantic patch, but matching it makes
#: already-patched detection stricter.
STUB_NOP_TAIL = bytes.fromhex("1F2003D5")

# --------------------------------------------------------------------------- #
# Architecture probes
# --------------------------------------------------------------------------- #
A64_RET = bytes.fromhex("C0035FD6")
THUMB_BX_LR = bytes.fromhex("7047")
ARM_BX_LR = bytes.fromhex("1EFF2FE1")


# --------------------------------------------------------------------------- #
# Profiles (from the research marker sets)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    priority: int
    arch: str
    markers: tuple[tuple[str, int], ...]
    stub_value: int
    archs: tuple[str, ...] = ()
    implemented: bool = True
    note: str = ""

    def applies_to(self, arch: str) -> bool:
        return not self.archs or arch in self.archs


#: `D81438B4` — MediaTek ARM32 Thumb, autonomous discovery, rev3 (priority 110).
PROFILE_ARM32_REV3 = Profile(
    key="D81438B4",
    name="MediaTek ARM32 Thumb - autonomous discovery / rev3",
    priority=110,
    arch="ARM32",
    markers=(
        ("flashing unlock", 3),
        ("flashing get_unlock_ability", 3),
        ("frp paritition does not exist", 3),      # the original's typo - unique anchor
        ("unlock_allowed_flag_offset", 2),
        ("Unlock bootloader?", 2),
        ("Start unlock flow", 2),
        ("seccfg", 1),
        ("SEC_UNLOCK", 1),
    ),
    stub_value=3,
    archs=("ARM32-Thumb", "ARM32"),
    implemented=False,
    note="No documented ARM32 stub bytes exist, so the image is analysed but not patched.",
)

#: `P71A03AA` — MediaTek AArch64, autonomous discovery, rev2 / P7 (priority 100).
PROFILE_A64_P7 = Profile(
    key="P71A03AA",
    name="MediaTek AArch64 - autonomous discovery / rev2 P7",
    priority=100,
    arch="AArch64",
    markers=(
        ("Start unlock flow", 3),
        ("Unlock key verify failed", 3),
        ("Unlock auth failed!", 3),
        ("Unlock auth ok!", 3),
        ("flashing unlock", 3),
        ("flashing get_unlock_ability", 3),
        ("seccfg", 1),
        ("unlocked", 1),
        ("secure", 1),
    ),
    stub_value=3,
    archs=("AArch64",),
    implemented=True,
)

#: Profiles whose marker sets lived inside the obfuscator VM and are unpublished.
UNPUBLISHED_PROFILES = (
    ("DA80523A", "Transsion X6858 / MT6789 (x6858_h8917) / rev5", 200),
    ("CB20200E", "Infinix X6728 / MT6769 / MT6768 (x6728) / ARM32 Thumb", 200),
    ("B88E59B0", "Transsion X6855 / MT6789 (x6855_h8917) / rev5", 200),
)

IMPLEMENTED_PROFILES = (PROFILE_A64_P7, PROFILE_ARM32_REV3)

# --------------------------------------------------------------------------- #
# Content scoring table (research `N106E684`)
# --------------------------------------------------------------------------- #
CONTENT_SCORE: tuple[tuple[str, int], ...] = (
    ("flashing unlock", 600),
    ("get_unlock_ability", 600),
    ("Start unlock flow", 400),
    ("unlock_allowed", 300),
    ("SEC_UNLOCK", 250),
    ("seccfg", 250),
    ("fastboot", 200),
    ("Unlock bootloader?", 150),
)
SIZE_BONUS = 40
SIZE_BONUS_THRESHOLD = 64 * 1024
RET_BONUS = 40
BXL_R_BONUS = 20


# --------------------------------------------------------------------------- #
# States
# --------------------------------------------------------------------------- #
class State:
    NO_MATCH = "NoMatch"
    CANDIDATE = "Candidate"
    READY = "Ready"
    ALREADY_PATCHED = "AlreadyPatched"
    MIXED = "Mixed"
    AMBIGUOUS = "Ambiguous"
    INVALID = "Invalid"


# --------------------------------------------------------------------------- #
# MTK header
# --------------------------------------------------------------------------- #
@dataclass
class MtkHeader:
    magic: int
    declared_size: int
    name: str
    file_size: int
    header_size: int = MTK_HEADER_SIZE

    @property
    def magic_ok(self) -> bool:
        return self.magic == MTK_MAGIC

    @property
    def size_ok(self) -> bool:
        return self.header_size <= self.declared_size <= self.file_size

    @property
    def trailing_padding(self) -> int:
        """Bytes after the declared image - stale leftover partition content."""
        return max(0, self.file_size - self.declared_size)

    def problems(self) -> list[str]:
        out: list[str] = []
        if not self.magic_ok:
            out.append(
                f"MTK magic mismatch (0x{self.magic:08X}, expected 0x{MTK_MAGIC:08X}) "
                "- this is not an MTK image"
            )
        if self.declared_size < self.header_size:
            out.append(f"Declared size {self.declared_size:,} is smaller than the header")
        elif self.declared_size > self.file_size:
            out.append(
                f"Declared size {self.declared_size:,} exceeds the file size "
                f"{self.file_size:,} - the image is truncated"
            )
        return out


def parse_mtk_header(data: bytes) -> MtkHeader:
    if len(data) < MTK_HEADER_SIZE:
        raise ValueError(f"File is only {len(data)} bytes; too small for an MTK header")
    magic, size = struct.unpack(MTK_HEADER_FMT, data[:8])
    raw_name = data[8:8 + MTK_NAME_LEN].split(b"\x00", 1)[0]
    name = raw_name.decode("ascii", "replace").strip()
    return MtkHeader(magic=magic, declared_size=size, name=name, file_size=len(data))


def payload_of(data: bytes, header: MtkHeader | None = None) -> bytes:
    """The LK payload without the 512-byte MTK header or trailing padding."""
    header = header or parse_mtk_header(data)
    end = header.declared_size if header.size_ok else len(data)
    return data[header.header_size:end]


# --------------------------------------------------------------------------- #
# Architecture
# --------------------------------------------------------------------------- #
def detect_arch(payload: bytes) -> tuple[str, dict[str, int]]:
    counts = {
        "aarch64_ret": payload.count(A64_RET),
        "thumb_bx_lr": payload.count(THUMB_BX_LR),
        "arm_bx_lr": payload.count(ARM_BX_LR),
    }
    if counts["aarch64_ret"] > 0 and counts["aarch64_ret"] >= counts["thumb_bx_lr"]:
        arch = "AArch64"
    elif counts["thumb_bx_lr"] > 0:
        arch = "ARM32-Thumb"
    elif counts["arm_bx_lr"] > 0:
        arch = "ARM32"
    else:
        arch = "unknown"
    return arch, counts


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def content_score(payload: bytes) -> tuple[int, list[str]]:
    score = 0
    hits: list[str] = []
    for marker, weight in CONTENT_SCORE:
        if marker.encode() in payload:
            score += weight
            hits.append(marker)
    if len(payload) >= SIZE_BONUS_THRESHOLD:
        score += SIZE_BONUS
    if A64_RET in payload:
        score += RET_BONUS
    if THUMB_BX_LR in payload:
        score += BXL_R_BONUS
    return score, hits


def score_profile(profile: Profile, payload: bytes) -> tuple[int, list[str]]:
    """Fraction-of-markers style score used for profile ranking."""
    score = 0
    found: list[str] = []
    for marker, weight in profile.markers:
        if marker.encode() in payload:
            score += weight
            found.append(marker)
    return score, found


# --------------------------------------------------------------------------- #
# Site location
# --------------------------------------------------------------------------- #
@dataclass
class Site:
    offset: int                  # offset within the payload
    anchored: bool               # preceded by CBZ W8
    written_value: int           # 4 = stock, 1/3/0 = patched
    context: str = ""


def _all_offsets(hay: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    if not needle:
        return out
    i = hay.find(needle)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def find_sites(payload: bytes) -> list[Site]:
    """Every lock-state store-form site, stock or already patched."""
    sites: list[Site] = []
    for value, stub in PATCH_STUBS.items():
        for off in _all_offsets(payload, stub):
            sites.append(Site(off, _anchored(payload, off), value))
    for off in _all_offsets(payload, STOCK_LOCK_SITE):
        sites.append(Site(off, _anchored(payload, off), 4))
    sites.sort(key=lambda s: s.offset)
    for s in sites:
        lo = max(0, s.offset - 8)
        hi = min(len(payload), s.offset + 20)
        s.context = payload[lo:hi].hex(" ").upper()
    return sites


def _anchored(payload: bytes, offset: int) -> bool:
    """Was this site preceded by the `CBZ W8, #8` branch seen in real images?"""
    lo = offset - 8
    if lo < 0:
        return False
    return SITE_ANCHOR_CBZ_W8 in payload[lo:offset]


def stock_sites(payload: bytes) -> list[Site]:
    return [s for s in find_sites(payload) if s.written_value == 4]


def patched_sites(payload: bytes) -> list[Site]:
    return [s for s in find_sites(payload) if s.written_value != 4]


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
@dataclass
class Analysis:
    state: str
    header: MtkHeader | None
    arch: str
    arch_counts: dict[str, int]
    content_score: int
    content_markers: list[str]
    profile: Profile | None
    profile_score: int
    profile_markers: list[str]
    profile_ranking: list[tuple[int, int, str, int]] = field(default_factory=list)
    sites: list[Site] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def stock_site_count(self) -> int:
        return sum(1 for s in self.sites if s.written_value == 4)

    @property
    def patchable(self) -> bool:
        return (
            self.state == State.READY
            and self.arch == "AArch64"
            and self.stock_site_count > 0
            and not self.problems
        )

    def summary_lines(self) -> list[str]:
        out = [
            f"state           : {self.state}",
            f"architecture    : {self.arch}  {self.arch_counts}",
        ]
        if self.header:
            out += [
                f"mtk header      : magic=0x{self.header.magic:08X} name={self.header.name!r} "
                f"declared={self.header.declared_size:,} file={self.header.file_size:,}",
                f"trailing padding: {self.header.trailing_padding:,} bytes "
                "(stale partition content after the declared image)",
            ]
        out.append(f"content score   : {self.content_score}")
        if self.content_markers:
            out.append(f"  markers       : {', '.join(self.content_markers)}")
        if self.profile:
            out.append(f"profile         : {self.profile.key} {self.profile.name}")
            out.append(f"  score         : {self.profile_score} "
                       f"({', '.join(self.profile_markers) or 'none'})")
        else:
            out.append("profile         : none matched")
        if len(self.profile_ranking) > 1:
            out.append("  ranking       : " + ", ".join(
                f"{k}={s}(pri{p})" for _st, s, k, p in self.profile_ranking))
        out.append(f"lock sites      : {len(self.sites)} "
                   f"(stock {self.stock_site_count}, patched {len(self.sites) - self.stock_site_count})")
        for s in self.sites:
            label = {4: "STOCK #4", 1: "#1", 3: "#3", 0: "#0"}[s.written_value]
            out.append(f"  @payload+0x{s.offset:06X}  {label:9s} "
                       f"{'anchored' if s.anchored else 'unanchored'}  {s.context}")
        for p in self.problems:
            out.append(f"PROBLEM: {p}")
        for n in self.notes:
            out.append(f"note    : {n}")
        return out


def analyze(data: bytes) -> Analysis:
    """Full static analysis of an LK image. Never mutates the input."""
    problems: list[str] = []
    notes: list[str] = []

    try:
        header = parse_mtk_header(data)
    except ValueError as exc:
        return Analysis(State.INVALID, None, "unknown", {}, 0, [], None, 0, [],
                        problems=[str(exc)])

    problems.extend(header.problems())
    payload = payload_of(data, header)
    if not payload:
        problems.append("Payload is empty")
        return Analysis(State.INVALID, header, "unknown", {}, 0, [], None, 0, [],
                        problems=problems)

    arch, counts = detect_arch(payload)
    cscore, cmarkers = content_score(payload)

    # --- profile ranking -------------------------------------------------- #
    ranking: list[tuple[int, int, str, int]] = []
    scored: list[tuple[Profile, int, list[str]]] = []
    skipped: list[str] = []
    for prof in IMPLEMENTED_PROFILES:
        s, found = score_profile(prof, payload)
        ranking.append((0, s, prof.key, prof.priority))
        # An ARM32 image must never be matched to an AArch64 profile (or the
        # reverse): the marker strings are largely shared, so raw scores are
        # not comparable across architectures.
        if not prof.applies_to(arch):
            skipped.append(f"{prof.key} ({prof.arch}) does not apply to {arch}")
            continue
        scored.append((prof, s, found))
    scored.sort(key=lambda t: (t[1], t[0].priority), reverse=True)
    ranking.sort(key=lambda t: (t[1], t[3]), reverse=True)

    top_profile, top_score, top_markers = scored[0] if scored else (None, 0, [])
    second_profile, second_score, _ = scored[1] if len(scored) > 1 else (None, 0, [])
    if top_score == 0:
        top_profile = None
    notes.extend(skipped)

    # --- site scan -------------------------------------------------------- #
    sites = find_sites(payload)
    n_stock = sum(1 for s in sites if s.written_value == 4)
    n_patched = len(sites) - n_stock

    # --- state resolution ------------------------------------------------ #
    if problems:
        state = State.INVALID
    elif top_profile and second_profile and top_score == second_score \
            and top_profile.priority == second_profile.priority:
        state = State.AMBIGUOUS
        problems.append(
            f"Profiles {top_profile.key} and {second_profile.key} tie at "
            f"{top_score} points with equal priority {top_profile.priority}; "
            "refusing to guess. Both candidates named above."
        )
    elif n_stock and n_patched:
        state = State.MIXED
        notes.append(
            f"{n_stock} stock site(s) and {n_patched} patched site(s) coexist; "
            "a partial patch was applied earlier."
        )
    elif n_patched and not n_stock:
        state = State.ALREADY_PATCHED
    elif n_stock:
        state = State.READY
    elif top_profile:
        state = State.CANDIDATE
        notes.append("Markers matched a profile but no known lock-state site was located.")
    else:
        state = State.NO_MATCH

    if arch != "AArch64" and state == State.READY:
        problems.append(
            f"Image is {arch} but only AArch64 technique-A stubs are documented; "
            "refusing to patch with guessed bytes."
        )
        state = State.CANDIDATE

    if top_profile and not top_profile.implemented:
        notes.append(f"{top_profile.key}: {top_profile.note}")

    notes.append(
        "Static analysis cannot prove the patch unlocks a device; verify on hardware."
    )

    return Analysis(
        state=state,
        header=header,
        arch=arch,
        arch_counts=counts,
        content_score=cscore,
        content_markers=cmarkers,
        profile=top_profile,
        profile_score=top_score,
        profile_markers=top_markers,
        profile_ranking=ranking,
        sites=sites,
        problems=problems,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Patch planning / application
# --------------------------------------------------------------------------- #
@dataclass
class PatchPlan:
    value: int
    sites: list[Site]
    total_sites: int

    @property
    def stub(self) -> bytes:
        return PATCH_STUBS[self.value]

    @property
    def stub_name(self) -> str:
        return STUB_NAMES[self.value]

    def lines(self) -> list[str]:
        out = [
            f"patch value     : {self.value} {STUB_VALUES[self.value]} "
            f"(stub {self.stub_name})",
            f"stub bytes      : {self.stub.hex(' ').upper()}",
            f"sites to patch  : {len(self.sites)} of {self.total_sites}",
        ]
        for s in self.sites:
            out.append(f"  @payload+0x{s.offset:06X}  {s.context}")
        return out


def plan_patch(analysis: Analysis, value: int = DEFAULT_PATCH_VALUE) -> PatchPlan:
    if value not in PATCH_STUBS:
        raise ValueError(f"Unsupported patch value {value}; choose one of {sorted(PATCH_STUBS)}")
    if analysis.state not in (State.READY, State.MIXED):
        raise ValueError(
            f"Cannot plan a patch for state {analysis.state}. "
            "Only Ready or Mixed images have stock sites to replace."
        )
    if analysis.arch != "AArch64":
        raise ValueError(
            f"Cannot plan a patch for {analysis.arch}; only AArch64 stubs are documented."
        )
    stock = [s for s in analysis.sites if s.written_value == 4]
    if not stock:
        raise ValueError("No stock lock-state sites were found to patch.")
    return PatchPlan(value=value, sites=stock, total_sites=len(analysis.sites))


def apply_plan(data: bytes, plan: PatchPlan) -> bytes:
    """Return a new image with the plan applied. Original length is preserved."""
    header = parse_mtk_header(data)
    out = bytearray(data)
    base = header.header_size
    for site in plan.sites:
        start = base + site.offset
        end = start + len(plan.stub)
        if start < 0 or end > len(out):
            raise ValueError(f"Patch site 0x{site.offset:X} falls outside the image")
        current = bytes(out[start:start + len(STOCK_LOCK_SITE)])
        if current != STOCK_LOCK_SITE:
            raise ValueError(
                f"Site 0x{site.offset:X} no longer holds the stock pattern "
                f"(found {current.hex(' ').upper()}); refusing a partial patch"
            )
        stub = plan.stub
        out[start:start + len(stub)] = stub
        # The #1 stub is exactly 16 bytes and fully covers the original; the
        # #3 stub is also 16. Zero the remaining original bytes so no stale
        # instruction survives after a shorter stub.
        if len(stub) < len(STOCK_LOCK_SITE):
            out[start + len(stub):start + len(STOCK_LOCK_SITE)] = b"\x00" * (
                len(STOCK_LOCK_SITE) - len(stub))
    if len(out) != len(data):
        raise AssertionError("Patch changed the image size; it must not")
    return bytes(out)


def verify_patch(data: bytes, value: int) -> tuple[bool, list[str]]:
    """Re-analyse a patched image and confirm no stock site survives."""
    a = analyze(data)
    problems: list[str] = []
    stock = [s for s in a.sites if s.written_value == 4]
    if stock:
        problems.append(
            f"{len(stock)} stock lock site(s) still present at "
            + ", ".join(f"0x{s.offset:X}" for s in stock)
        )
    want = [s for s in a.sites if s.written_value == value]
    if not want:
        problems.append(f"No site carrying the requested value {value} was found")
    return (not problems), problems


# --------------------------------------------------------------------------- #
# File helpers
# --------------------------------------------------------------------------- #
def sha256_of_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_path_for(path: str | Path, suffix: str = ".original") -> Path:
    p = Path(path)
    candidate = p.with_name(p.name + suffix)
    n = 1
    while candidate.exists():
        candidate = p.with_name(f"{p.name}{suffix}.{n}")
        n += 1
    return candidate


def describe_profiles() -> Iterable[str]:
    for p in IMPLEMENTED_PROFILES:
        state = "implemented" if p.implemented else "analysis only (no documented stubs)"
        yield (f"{p.key}  priority={p.priority}  {p.arch}  {state}\n    {p.name}\n"
               f"    markers: {', '.join(m for m, _ in p.markers)}")
    for key, name, prio in UNPUBLISHED_PROFILES:
        yield (f"{key}  priority={prio}  marker set unpublished (lived in the obfuscator VM)\n"
               f"    {name}")
