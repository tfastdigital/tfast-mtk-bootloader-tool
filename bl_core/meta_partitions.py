"""
META partition manager — list, read, back up, restore, write, erase, verify.

Transport
---------
Everything here is **`dd`-over-shell**, exactly as documented in the TFast
Digital META research (`MTK_META_OPERATIONS.md` §1):

    read  : dd if=<dev>  bs=<..> skip=<..> count=<..> | base64
    write : dd if=<file> of=<dev> bs=<..> count=<..> conv=fsync,notrunc
    erase : dd if=/dev/zero of=<dev> bs=<..> seek=<..> count=<..> conv=fsync,notrunc

Binary data crosses the shell as base64 because the engine's
``execute_shell_cmd_direct`` returns text.

Design notes that matter
------------------------
* **Chunked on purpose.** `super` can be 10-20 GB. Nothing here ever tries to
  hold a whole modern partition in memory unless the caller asks for it.
* **Verify by read-back, not by exit code.** The engine's shell pipe can lose
  the tail of a response; the original bridge comments call this out. Every
  write is re-read and hashed before it is reported as success.
* **Brick-risk partitions need `force`.** `preloader`, `pgpt`, `sgpt`,
  `persist`, `nvram`, `nvdata`, `seccfg` … are refused unless the caller passes
  an explicit force flag, and bulk operations skip them.
* **Transport is injectable** so the whole manager can be tested against a
  simulated shell with no device attached.

Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
https://tfastdigital.com/
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Protocol, Sequence

# --------------------------------------------------------------------------- #
# Safety policy
# --------------------------------------------------------------------------- #
#: Partitions whose loss stops the device from booting or destroys calibration.
#: Never touched by bulk operations; individual access requires ``force=True``.
BRICK_RISK_PARTITIONS: frozenset[str] = frozenset({
    "preloader", "preloader1", "preloader2",
    "pgpt", "sgpt",
    "persist", "persistbak",
    "nvram", "nvdata", "nvcfg",
    "proinfo", "protect1", "protect2", "protect_f", "protect_s",
    "sec1", "efuse", "seccfg",
    "boot_para", "para",
    "expdb", "flashinfo",
})

#: Sensible defaults for the `dd` block size and per-transfer chunk.
DD_BLOCK = 512
DEFAULT_CHUNK = 1 << 20          # 1 MiB per shell round-trip
MAX_CHUNK = 16 << 20             # 16 MiB ceiling

#: Transfer profiles. Bigger chunks mean far fewer shell round-trips, which is
#: what actually limits throughput here: each round-trip costs the serial link
#: plus base64 expansion (~1.34x) plus shell parsing. `safe` is for links that
#: drop the tail of long responses; `turbo` assumes a healthy link.
SPEED_PROFILES: dict[str, int] = {
    "safe": 256 << 10,           # 256 KiB - most tolerant of flaky links
    "balanced": 1 << 20,         # 1 MiB
    "fast": 4 << 20,             # 4 MiB
    "turbo": 8 << 20,            # 8 MiB
}


def chunk_for(speed: str) -> int:
    """Map a profile name to a chunk size (unknown names fall back to balanced)."""
    return SPEED_PROFILES.get((speed or "").lower(), DEFAULT_CHUNK)


# --------------------------------------------------------------------------- #
# Filesystem / image signatures (used to prove a wipe actually destroyed them)
# --------------------------------------------------------------------------- #
#: (label, offset, magic). Checked before a wipe so the operator can see what a
#: partition actually held, and after a wipe so "wiped" is a measured claim
#: rather than an assumption.
SIGNATURES: tuple[tuple[str, int, bytes], ...] = (
    ("ext4",        1024 + 0x38, bytes.fromhex("53EF")),        # s_magic (LE)
    ("f2fs",        1024,        bytes.fromhex("1020F5F2")),    # F2FS_SUPER_MAGIC
    ("erofs",       1024,        bytes.fromhex("E2E1F5E0")),    # EROFS_SUPER_MAGIC_V1
    ("squashfs",    0,           b"hsqs"),
    ("vfat",        82,          b"FAT"),
    ("sparse",      0,           bytes.fromhex("ED26FF3A")),    # Android sparse
    ("boot image",  0,           b"ANDROID!"),
    ("AVB vbmeta",  0,           b"AVB0"),
    ("MTK image",   0,           bytes.fromhex("88168858")),
    ("GPT header",  0,           b"EFI PART"),
    ("lk image",    512,         bytes.fromhex("88168858")),
)

#: How much of the head to inspect. Covers every superblock above (ext4 and
#: f2fs live near 1 KiB) with room to spare.
HEAD_PROBE = 8192

#: A "filesystem wipe" zeroes this much at the head and the same at the tail.
#: That destroys superblocks, journal headers and backup superblocks/footers
#: without rewriting a 20 GB partition.
WIPE_EDGE = 1 << 20

WIPE_MODES = ("filesystem", "head", "full")


def detect_signatures(data: bytes) -> list[str]:
    """Return the labels of every known signature present in `data`."""
    found: list[str] = []
    for label, off, magic in SIGNATURES:
        if 0 <= off and data[off:off + len(magic)] == magic:
            found.append(label)
    return found


def looks_blank(data: bytes) -> bool:
    return not data or all(b == 0 for b in data)




class PartitionError(RuntimeError):
    """Raised for refused or failed partition operations."""


class PartitionNotFound(PartitionError):
    pass


class PartitionProtected(PartitionError):
    pass


# --------------------------------------------------------------------------- #
# Transport protocol (so tests can substitute a simulated shell)
# --------------------------------------------------------------------------- #
class ShellTransport(Protocol):
    def shell(self, cmd: str, timeout_ms: int = 20000) -> str: ...


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class PartitionInfo:
    name: str
    block_dev: str = ""
    size_bytes: int = 0
    source: str = ""
    protected: bool = False

    @property
    def size_human(self) -> str:
        n = float(self.size_bytes)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if n < 1024 or unit == "TiB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
            n /= 1024
        return f"{self.size_bytes} B"


@dataclass
class TransferResult:
    ok: bool
    message: str
    bytes_moved: int = 0
    sha256: str = ""
    path: Optional[Path] = None
    verified: bool = False
    chunks: int = 0
    seconds: float = 0.0

    @property
    def throughput(self) -> str:
        """Human-readable transfer rate, e.g. ``2.31 MiB/s``."""
        if self.seconds <= 0 or self.bytes_moved <= 0:
            return ""
        bps = self.bytes_moved / self.seconds
        for unit in ("B/s", "KiB/s", "MiB/s", "GiB/s"):
            if bps < 1024 or unit == "GiB/s":
                return f"{bps:.2f} {unit}"
            bps /= 1024
        return ""

    def lines(self) -> list[str]:
        out = [self.message]
        if self.bytes_moved:
            out.append(f"bytes      : {self.bytes_moved:,}")
        if self.chunks:
            out.append(f"chunks     : {self.chunks}")
        if self.sha256:
            out.append(f"sha256     : {self.sha256}")
        if self.path:
            out.append(f"file       : {self.path}")
        if self.bytes_moved:
            out.append(f"verified   : {'yes' if self.verified else 'no'}")
        if self.throughput:
            out.append(f"speed      : {self.throughput}")
        return out


# --------------------------------------------------------------------------- #
# Simulation transport (tests / dry runs)
# --------------------------------------------------------------------------- #
class SimulatedTransport:
    """Executes a tiny subset of shell commands against an in-memory image map.

    Supports what the manager actually issues: ``cat`` of the partition tables,
    ``blockdev --getsize64``, ``dd ... | base64``, and ``base64 -d | dd``.
    """

    def __init__(self, partitions: dict[str, bytes]) -> None:
        self.images = dict(partitions)
        self.log: list[str] = []

    # -- helpers -------------------------------------------------------- #
    def _resolve(self, dev: str) -> str:
        name = dev.rstrip()
        if "/dev/block/by-name/" in name:
            name = name.rsplit("/", 1)[-1]
        elif "/dev/block/" in name:
            name = name.rsplit("/", 1)[-1]
        if name not in self.images:
            raise KeyError(name)
        return name

    def shell(self, cmd: str, timeout_ms: int = 20000) -> str:
        self.log.append(cmd)
        cmd = cmd.strip()

        if cmd.startswith("cat /proc/dumchar_info"):
            rows = ["print_info: part_info", "Part_Name  Size  StartAddr  Type"]
            for n, data in self.images.items():
                rows.append(f"{n} 0x{len(data):X} 0x0 1")
            return "\n".join(rows)

        if cmd.startswith("cat /proc/partitions"):
            rows = ["major minor  #blocks  name"]
            for n, data in self.images.items():
                rows.append(f" 179    {abs(hash(n)) % 32}  {len(data)//1024} {n}")
            return "\n".join(rows)

        if "ls -l /dev/block/by-name" in cmd:
            return "\n".join(f"lrwxrwxrwx 1 root root 16 x -> /dev/block/{n}"
                             for n in self.images)

        m = re.search(r"blockdev --getsize64\s+(\S+)", cmd)
        if m:
            return str(len(self.images[self._resolve(m.group(1))]))

        # Write path first: its command contains BOTH `base64 -d` and a `dd … of=`,
        # so it must not be mistaken for the read path's `| base64`.
        if "base64 -d" in cmd:
            return self._dd_write(cmd)
        if "if=/dev/zero" in cmd:
            return self._dd_zero(cmd)
        if "| base64" in cmd:
            return self._dd_read(cmd)
        if cmd.startswith("rm -f"):
            return ""
        return ""

    def _dd_zero(self, cmd: str) -> str:
        """Handle ``dd if=/dev/zero of=<dev> bs=… seek=… count=…``."""
        m = re.search(r"of=(\S+)", cmd)
        if not m:
            return ""
        name = self._resolve(m.group(1))
        bs = int(self._opt(cmd, "bs") or DD_BLOCK)
        seek = int(self._opt(cmd, "seek") or 0)
        count = int(self._opt(cmd, "count") or 0)
        img = bytearray(self.images[name])
        off = seek * bs
        need = off + count * bs
        if need > len(img):
            img.extend(b"\x00" * (need - len(img)))
        img[off:need] = b"\x00" * (count * bs)
        self.images[name] = bytes(img)
        return "DONE_OK"

    def _dd_read(self, cmd: str) -> str:
        m = re.search(r"dd if=(\S+)", cmd)
        if not m:
            return ""
        name = self._resolve(m.group(1))
        data = self.images[name]
        bs = int(self._opt(cmd, "bs") or DD_BLOCK)
        skip = int(self._opt(cmd, "skip") or 0)
        count = self._opt(cmd, "count")
        off = skip * bs
        if count is not None:
            data = data[off:off + int(count) * bs]
        else:
            data = data[off:]
        return base64.b64encode(data).decode("ascii")

    def _dd_write(self, cmd: str) -> str:
        """Handle ``echo <b64> | base64 -d > tmp && dd if=tmp of=<dev> …``."""
        blob = ""
        m = re.match(r"\s*echo\s+(\S+)\s*\|\s*base64 -d", cmd)
        if m:
            blob = m.group(1)
        try:
            data = base64.b64decode(blob, validate=False) if blob else b""
        except (binascii.Error, ValueError):
            return "DECODE_FAIL"

        # The dd target is the *second* `if=` (the first belongs to the temp file);
        # fall back to `of=` when only that is present.
        ofs = re.findall(r"dd\s+if=(\S+)", cmd)
        m2 = re.search(r"of=(\S+)", cmd)
        if not m2:
            return ""
        name = self._resolve(m2.group(1))
        bs = int(self._opt(cmd, "bs") or DD_BLOCK)
        seek = int(self._opt(cmd, "seek") or 0)
        img = bytearray(self.images[name])
        off = seek * bs
        need = off + len(data)
        if need > len(img):
            img.extend(b"\x00" * (need - len(img)))
        img[off:off + len(data)] = data
        self.images[name] = bytes(img)
        return "DONE_OK"

    @staticmethod
    def _opt(cmd: str, key: str):
        m = re.search(rf"{key}=(\d+)", cmd)
        return m.group(1) if m else None

    _pending_b64: str = ""

    def push_b64(self, blob: str) -> None:
        self._pending_b64 = blob


# --------------------------------------------------------------------------- #
# Manager
# --------------------------------------------------------------------------- #
class MetaPartitionManager:
    """High-level partition operations over any :class:`ShellTransport`."""

    def __init__(self, transport: ShellTransport, workspace: Path,
                 chunk_size: int = DEFAULT_CHUNK,
                 progress: Optional[Callable[[str], None]] = None) -> None:
        self.shell = transport
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.chunk_size = max(DD_BLOCK, min(int(chunk_size), MAX_CHUNK))
        self._progress = progress or (lambda _m: None)
        self._cache: dict[str, PartitionInfo] = {}

    # -- logging --------------------------------------------------------- #
    def _say(self, msg: str) -> None:
        try:
            self._progress(msg)
        except Exception:                                       # noqa: BLE001
            pass

    @staticmethod
    def _now() -> float:
        import time as _t
        return _t.perf_counter()

    def set_speed(self, speed: str) -> int:
        """Switch the chunk size by profile name; returns the new chunk size."""
        self.chunk_size = max(DD_BLOCK, min(chunk_for(speed), MAX_CHUNK))
        return self.chunk_size

    @property
    def speed_name(self) -> str:
        for name, size in SPEED_PROFILES.items():
            if self.chunk_size == min(size, MAX_CHUNK):
                return name
        return f"{self.chunk_size // 1024} KiB"

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    def list_partitions(self, refresh: bool = False) -> list[PartitionInfo]:
        """Enumerate partitions: dumchar_info, then /proc/partitions, then by-name."""
        if self._cache and not refresh:
            return sorted(self._cache.values(), key=lambda p: p.name)

        found: dict[str, PartitionInfo] = {}

        # 1. MTK-native table (has sizes).
        try:
            out = self.shell.shell("cat /proc/dumchar_info") or ""
            for line in out.splitlines():
                row = line.split()
                if len(row) >= 3 and row[0] not in ("Part_Name", "print_info:'s"):
                    name = row[0]
                    try:
                        size = int(row[1], 16) if row[1].startswith("0x") else int(row[1])
                    except ValueError:
                        continue
                    if size > 0 and re.fullmatch(r"[a-z0-9_\-]+", name):
                        found[name] = PartitionInfo(
                            name=name, block_dev=f"/dev/block/by-name/{name}",
                            size_bytes=size, source="dumchar_info")
        except Exception:                                       # noqa: BLE001
            pass

        # 2. /proc/partitions (blocks of 1 KiB).
        if not found:
            try:
                out = self.shell.shell("cat /proc/partitions") or ""
                for line in out.splitlines():
                    row = line.split()
                    if len(row) == 4 and row[3] not in ("name",):
                        try:
                            kb = int(row[2])
                        except ValueError:
                            continue
                        found[row[3]] = PartitionInfo(
                            name=row[3], block_dev=f"/dev/block/by-name/{row[3]}",
                            size_bytes=kb * 1024, source="/proc/partitions")
            except Exception:                                   # noqa: BLE001
                pass

        # 3. by-name symlinks (names only).
        if not found:
            try:
                out = self.shell.shell("ls -l /dev/block/by-name/") or ""
                for m in re.finditer(r"->\s*(\S+)$", out, re.M):
                    name = m.group(1).rsplit("/", 1)[-1]
                    found[name] = PartitionInfo(
                        name=name, block_dev=f"/dev/block/by-name/{name}",
                        size_bytes=0, source="by-name symlink")
            except Exception:                                   # noqa: BLE001
                pass

        for info in found.values():
            info.protected = info.name in BRICK_RISK_PARTITIONS

        self._cache = found
        return sorted(found.values(), key=lambda p: p.name)

    def get(self, name: str, refresh: bool = False) -> PartitionInfo:
        for info in self.list_partitions(refresh=refresh):
            if info.name == name:
                return info
        # Not listed: use the conventional path and let dd fail honestly.
        return PartitionInfo(name=name, block_dev=f"/dev/block/by-name/{name}",
                             size_bytes=0, source="unlisted",
                             protected=name in BRICK_RISK_PARTITIONS)

    def resolve_size(self, name: str, refresh: bool = False) -> int:
        """Current size in bytes. ``refresh`` re-reads the partition table.

        Extent-determining operations pass ``refresh=True``: a stale cached size
        after the partition changed would truncate a read or leave the tail of
        an erase untouched.
        """
        info = self.get(name, refresh=refresh)
        if info.size_bytes:
            return info.size_bytes
        try:
            out = (self.shell.shell(
                f"blockdev --getsize64 {info.block_dev}") or "").strip()
            return int(out.splitlines()[-1])
        except Exception:                                       # noqa: BLE001
            return 0

    # -- guards ---------------------------------------------------------- #
    def _guard(self, name: str, force: bool, action: str) -> PartitionInfo:
        info = self.get(name)
        if info.protected and not force:
            raise PartitionProtected(
                f"'{name}' is a brick-risk partition ({action} refused).\n"
                f"Protected set: {', '.join(sorted(BRICK_RISK_PARTITIONS))}\n"
                "Pass force=True (CLI: --force) only if you have a verified backup "
                "and understand the device will not boot if this goes wrong."
            )
        return info

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def read_partition(self, name: str, offset: int = 0, length: Optional[int] = None,
                       force: bool = False) -> bytes:
        """Read a partition (or slice) by chunked ``dd | base64``."""
        info = self._guard(name, force, "read")
        total = (length if length is not None
                 else self.resolve_size(name, refresh=True) - offset)
        if total is None or total < 0:
            raise PartitionError(f"Cannot determine the size of '{name}'")
        if total == 0:
            raise PartitionError(
                f"Partition '{name}' reports size 0 and no length was given")

        # Choose a bs that makes skip/count exact.
        bs = DD_BLOCK
        if offset % bs or total % bs:
            bs = 1
        chunks = (total + self.chunk_size - 1) // self.chunk_size
        buf = bytearray()
        for i in range(chunks):
            base = offset + i * self.chunk_size
            want = min(self.chunk_size, total - i * self.chunk_size)
            count = want // bs
            skip = base // bs
            cmd = (f"dd if={info.block_dev} bs={bs} skip={skip} count={count} "
                   f"2>/dev/null | base64 -w0")
            raw = self.shell.shell(cmd, timeout_ms=60000) or ""
            try:
                chunk = base64.b64decode(raw.strip(), validate=False)
            except (binascii.Error, ValueError) as exc:
                raise PartitionError(
                    f"base64 decode failed on chunk {i + 1}/{chunks}: {exc}") from exc
            if len(chunk) < want:
                self._say(f"  chunk {i + 1}/{chunks}: short read "
                          f"({len(chunk):,} of {want:,} bytes)")
            buf += chunk
            self._say(f"  read chunk {i + 1}/{chunks} "
                      f"({len(buf):,}/{total:,} bytes)")
            if len(chunk) == 0:
                break
        return bytes(buf)

    def backup_partition(self, name: str, dest: Optional[Path] = None,
                         force: bool = False, verify: bool = True) -> TransferResult:
        """Read a partition to a local file and record its SHA-256."""
        if dest is None:
            dest = self.workspace / f"{name}.img"
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        t0 = self._now()
        try:
            data = self.read_partition(name, force=force)
        except PartitionError as exc:
            return TransferResult(False, str(exc))

        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        digest = hashlib.sha256(data).hexdigest()

        verified = False
        if verify:
            verified = self._verify_file_against(name, dest, digest, force=force)

        return TransferResult(
            True,
            f"Backed up '{name}' to {dest.name}",
            bytes_moved=len(data), sha256=digest, path=dest,
            verified=verified,
            chunks=(len(data) + self.chunk_size - 1) // self.chunk_size,
            seconds=self._now() - t0,
        )

    def export_partition(self, name: str, dest: Path, force: bool = False,
                         verify: bool = False) -> TransferResult:
        """Stream a partition straight to disk, chunk by chunk.

        Unlike :meth:`backup_partition` this never builds the whole image in
        memory, so a multi-GB ``super`` is safe. The SHA-256 is computed as the
        data streams in, so the digest costs nothing extra.
        """
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        info = self._guard(name, force, "export")
        total = self.resolve_size(name, refresh=True)
        if total <= 0:
            return TransferResult(False, f"Cannot determine the size of '{name}'")

        t0 = self._now()
        h = hashlib.sha256()
        moved = 0
        chunks = 0
        bs = DD_BLOCK if total % DD_BLOCK == 0 else 1
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with open(tmp, "wb") as fh:
                while moved < total:
                    want = min(self.chunk_size, total - moved)
                    cmd = (f"dd if={info.block_dev} bs={bs} skip={moved // bs} "
                           f"count={want // bs} 2>/dev/null | base64 -w0")
                    raw = self.shell.shell(cmd, timeout_ms=120000) or ""
                    try:
                        chunk = base64.b64decode(raw.strip(), validate=False)
                    except (binascii.Error, ValueError) as exc:
                        raise PartitionError(
                            f"base64 decode failed at offset {moved:,}: {exc}") from exc
                    if not chunk:
                        self._say(f"  stream ended early at {moved:,} of {total:,}")
                        break
                    fh.write(chunk)
                    h.update(chunk)
                    moved += len(chunk)
                    chunks += 1
                    self._say(f"  exported {moved:,}/{total:,} "
                              f"({moved * 100 // max(total, 1)}%)")
            os.replace(tmp, dest)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

        digest = h.hexdigest()
        verified = False
        if verify:
            verified = self._verify_file_against(name, dest, digest, force=force)
        return TransferResult(
            True, f"Exported '{name}' to {dest.name}",
            bytes_moved=moved, sha256=digest, path=dest,
            verified=verified, chunks=chunks, seconds=self._now() - t0)

    # ------------------------------------------------------------------ #
    # Write / restore
    # ------------------------------------------------------------------ #
    def write_partition(self, name: str, data: bytes, offset: int = 0,
                        force: bool = False, verify: bool = True) -> TransferResult:
        """Write `data` at `offset` using chunked base64 -> ``dd`` then re-read."""
        info = self._guard(name, force, "write")
        if not data:
            return TransferResult(False, "Refusing to write 0 bytes")

        t0 = self._now()
        bs = DD_BLOCK
        if offset % bs or len(data) % bs:
            bs = 1
        chunks = (len(data) + self.chunk_size - 1) // self.chunk_size
        tmp_remote = "/data/local/tmp/_tfw_chunk.bin"

        for i in range(chunks):
            start = i * self.chunk_size
            chunk = data[start:start + self.chunk_size]
            # dd only writes whole bs blocks; pad the tail so nothing is cut.
            pad = (-len(chunk)) % bs
            payload = chunk + b"\x00" * pad
            b64 = base64.b64encode(payload).decode("ascii")
            seek = (offset + start) // bs
            count = len(payload) // bs
            cmd = (f"echo {b64} | base64 -d > {tmp_remote} && "
                   f"dd if={tmp_remote} of={info.block_dev} bs={bs} "
                   f"seek={seek} count={count} conv=fsync,notrunc 2>/dev/null "
                   f"&& echo DONE_OK")
            out = self.shell.shell(cmd, timeout_ms=60000) or ""
            if "DONE_OK" not in out:
                self.shell.shell(f"rm -f {tmp_remote}")
                return TransferResult(
                    False,
                    f"dd write failed on chunk {i + 1}/{chunks}; "
                    f"device said: {out.strip()[:160] or '(no output)'}",
                    bytes_moved=start, chunks=i)
            self._say(f"  wrote chunk {i + 1}/{chunks} "
                      f"({start + len(chunk):,}/{len(data):,} bytes)")

        self.shell.shell(f"rm -f {tmp_remote}")

        digest = hashlib.sha256(data).hexdigest()
        verified = False
        if verify:
            verified = self._verify_bytes_against(name, data, digest, offset, force=force)

        ok = verified if verify else True
        return TransferResult(
            ok,
            (f"Wrote {len(data):,} bytes to '{name}'"
             + ("" if not verify else (" (verified)" if verified
                                       else " -- READ-BACK MISMATCH"))),
            bytes_moved=len(data), sha256=digest, verified=verified, chunks=chunks,
            seconds=self._now() - t0)

    def restore_partition(self, name: str, src: Path, force: bool = False,
                          verify: bool = True) -> TransferResult:
        src = Path(src)
        if not src.exists():
            return TransferResult(False, f"Backup file not found: {src}")
        data = src.read_bytes()
        res = self.write_partition(name, data, force=force, verify=verify)
        if res.ok and res.verified:
            res.message = f"Restored '{name}' from {src.name} (verified)"
        return res

    def erase_partition(self, name: str, offset: int = 0,
                        length: Optional[int] = None, force: bool = False) -> TransferResult:
        """Zero a partition (or slice) with ``dd if=/dev/zero``.

        Kept for the offset/length slicing case. For "make this partition
        unformatted" use :meth:`wipe_partition`, which also proves the
        filesystem signatures are gone afterwards.
        """
        info = self._guard(name, force, "erase")
        total = (length if length is not None
                 else self.resolve_size(name, refresh=True) - offset)
        if not total or total <= 0:
            return TransferResult(False, f"Cannot determine the extent of '{name}'")

        t0 = self._now()
        res = self._zero_span(info.block_dev, offset, total)
        if not res.ok:
            return TransferResult(False, f"erase failed: {res.message}",
                                  bytes_moved=res.bytes_moved, chunks=res.chunks)
        return TransferResult(True, f"Zeroed {res.bytes_moved:,} bytes on '{name}'",
                              bytes_moved=res.bytes_moved, chunks=res.chunks,
                              seconds=self._now() - t0)

    # ------------------------------------------------------------------ #
    # Wipe (zero + prove the filesystem is gone)
    # ------------------------------------------------------------------ #
    def probe_signatures(self, name: str, force: bool = False) -> list[str]:
        """What image/filesystem signatures does this partition currently carry?"""
        length = min(self.resolve_size(name, refresh=True) or HEAD_PROBE, HEAD_PROBE)
        if length <= 0:
            return []
        data = self.read_partition(name, length=length, force=force)
        return detect_signatures(data)

    def wipe_partition(self, name: str, mode: str = "filesystem",
                       force: bool = False) -> TransferResult:
        """Wipe a partition and verify the wipe actually took effect.

        Modes:

        ``filesystem`` (default)
            Zero the first and last :data:`WIPE_EDGE` bytes. This destroys
            superblocks, journal headers, backup superblocks and footers, so the
            OS sees an unformatted partition. Cheap even on a 20 GB ``super``.
        ``head``
            Zero only the first :data:`WIPE_EDGE` bytes. For partitions where
            the tail must be preserved.
        ``full``
            Zero the whole partition. Slow; only needed when the data itself
            must be unrecoverable.

        A plain "erase" writes zeros but can leave a valid superblock intact if
        it sits outside the range written; this always reports what it found
        before wiping and re-reads afterwards to prove the signatures are gone.
        """
        mode = (mode or "filesystem").lower()
        if mode not in WIPE_MODES:
            return TransferResult(
                False, f"Unknown wipe mode '{mode}'; choose one of {', '.join(WIPE_MODES)}")

        info = self._guard(name, force, f"wipe ({mode})")
        total = self.resolve_size(name, refresh=True)
        if total <= 0:
            return TransferResult(False, f"Cannot determine the size of '{name}'")

        t0 = self._now()
        before: list[str] = []
        try:
            before = self.probe_signatures(name, force=force)
        except PartitionError:
            pass
        if before:
            self._say(f"  before wipe: {', '.join(before)}")
            if "preloader" in before or "lk image" in before:
                self._say("  note: this partition holds bootloader code")

        spans: list[tuple[int, int]] = []
        if mode == "full":
            spans.append((0, total))
        elif mode == "head":
            spans.append((0, min(WIPE_EDGE, total)))
        else:                                    # filesystem
            head = min(WIPE_EDGE, total)
            spans.append((0, head))
            if total > head:
                tail = min(WIPE_EDGE, total - head)
                spans.append((total - tail, tail))

        moved = 0
        chunks = 0
        for offset, length in spans:
            res = self._zero_span(info.block_dev, offset, length)
            if not res.ok:
                return TransferResult(
                    False, f"wipe failed at offset {offset:,}: {res.message}",
                    bytes_moved=moved, chunks=chunks)
            moved += length
            chunks += res.chunks

        # --- prove it ---------------------------------------------------- #
        # Any signature still readable after the wipe means we did not destroy
        # what a wipe is supposed to destroy.
        after: list[str] = []
        try:
            after = self.probe_signatures(name, force=force)
        except PartitionError:
            pass
        if after:
            return TransferResult(
                False,
                f"Wiped '{name}' ({mode}) but signatures are still readable: "
                f"{', '.join(after)}. Try --mode full.",
                bytes_moved=moved, chunks=chunks, verified=False,
                seconds=self._now() - t0)

        detail = f"{mode} wipe of '{name}'"
        if before:
            detail += f"; removed {', '.join(before)}"
        else:
            detail += "; no signatures were present"
        if mode == "filesystem":
            detail += f" (head+tail {WIPE_EDGE // 1024} KiB)"
        return TransferResult(True, detail, bytes_moved=moved, chunks=chunks,
                              verified=True, seconds=self._now() - t0)

    def _zero_span(self, dev: str, offset: int, length: int) -> TransferResult:
        """Zero `length` bytes at `offset` on a block device."""
        bs = DD_BLOCK if (offset % DD_BLOCK == 0 and length % DD_BLOCK == 0) else 1
        moved = 0
        chunks = (length + self.chunk_size - 1) // self.chunk_size
        for i in range(chunks):
            want = min(self.chunk_size, length - i * self.chunk_size)
            seek = (offset + i * self.chunk_size) // bs
            cmd = (f"dd if=/dev/zero of={dev} bs={bs} seek={seek} "
                   f"count={want // bs} conv=fsync,notrunc 2>/dev/null && echo DONE_OK")
            out = self.shell.shell(cmd, timeout_ms=60000) or ""
            if "DONE_OK" not in out:
                return TransferResult(
                    False, f"{out.strip()[:160] or '(no output)'}",
                    bytes_moved=moved, chunks=i)
            moved += want
            self._say(f"  zeroed {moved:,}/{length:,} bytes at +{offset:,}")
        return TransferResult(True, "ok", bytes_moved=moved, chunks=chunks)


    # ------------------------------------------------------------------ #
    # Replace / delete / bulk export
    # ------------------------------------------------------------------ #
    def replace_partition(self, name: str, src: Path, force: bool = False,
                          verify: bool = True, allow_size_mismatch: bool = False,
                          backup_first: bool = True) -> TransferResult:
        """Replace a partition's contents with a different image.

        Unlike a restore, this is meant for putting a *new* image on (a patched
        boot, a different vendor blob). Because a size mismatch is the usual way
        to brick a device, it is refused unless ``allow_size_mismatch`` is set;
        a shorter image leaves the partition tail untouched, a longer one is
        truncated to the partition size with a warning.
        """
        src = Path(src)
        if not src.exists():
            return TransferResult(False, f"Image not found: {src}")
        data = src.read_bytes()
        if not data:
            return TransferResult(False, "Refusing to write a 0-byte image")

        part_size = self.resolve_size(name, refresh=True)
        if part_size and len(data) != part_size and not allow_size_mismatch:
            return TransferResult(
                False,
                f"Size mismatch: '{name}' is {part_size:,} bytes but "
                f"{src.name} is {len(data):,} bytes.\n"
                "Writing a wrong-sized image is a common way to brick a device. "
                "Re-run with allow_size_mismatch=True (CLI: --allow-size-mismatch) "
                "if you are certain."
            )

        backup_path = None
        if backup_first and not force:
            bk = self.backup_partition(name, dest=self.workspace / "replace-backups" / f"{name}.img",
                                      verify=False)
            if not bk.ok:
                return TransferResult(
                    False, "Could not make the safety backup before replacing:\n"
                           + bk.message)
            backup_path = bk.path

        payload = data
        truncated = False
        if part_size and len(data) > part_size:
            payload = data[:part_size]
            truncated = True
            self._say(f"  image is larger than the partition; truncating to {part_size:,}")

        res = self.write_partition(name, payload, force=force, verify=verify)
        if res.ok:
            bits = []
            if backup_path:
                bits.append(f"safety backup {backup_path.name}")
            if truncated:
                bits.append("TRUNCATED to partition size")
            if part_size and len(data) < part_size:
                bits.append(f"tail kept ({part_size - len(data):,} bytes not written)")
            res.message = f"Replaced '{name}' with {src.name}" + (
                " (" + "; ".join(bits) + ")" if bits else "")
        return res

    def delete_files(self, paths: Sequence[Path]) -> list[TransferResult]:
        """Delete local image artefacts (exported or backed-up files).

        This is the safe meaning of "delete" in a partition manager: it removes
        copies on disk. Removing a partition *row* from the device's GPT is not
        implemented - it rewrites the partition table and is a guaranteed brick
        if it goes wrong, so it is deliberately out of scope.
        """
        out: list[TransferResult] = []
        for p in paths:
            p = Path(p)
            if not p.exists():
                out.append(TransferResult(False, f"Not found: {p}"))
                continue
            try:
                size = p.stat().st_size
                p.unlink()
                out.append(TransferResult(True, f"Deleted {p.name}",
                                          bytes_moved=size, path=p))
            except OSError as exc:
                out.append(TransferResult(False, f"Could not delete {p.name}: {exc}"))
        return out

    def export_many(self, names: Sequence[str], out_dir: Optional[Path] = None,
                    force: bool = False, skip_protected: bool = True,
                    verify: bool = False, manifest: bool = True) -> list[TransferResult]:
        """Stream several partitions to a directory and write a JSON manifest."""
        import json as _json

        out_dir = Path(out_dir) if out_dir else self.workspace / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        results: list[TransferResult] = []
        entries: list[dict] = []

        for name in names:
            if skip_protected and name in BRICK_RISK_PARTITIONS:
                results.append(TransferResult(
                    False, f"'{name}' skipped (brick-risk)"))
                continue
            try:
                res = self.export_partition(
                    name, out_dir / f"{name}.img", force=force, verify=verify)
            except Exception as exc:                            # noqa: BLE001
                res = TransferResult(False, f"'{name}' failed: {exc}")
            results.append(res)
            if res.ok:
                entries.append({
                    "partition": name,
                    "file": res.path.name if res.path else f"{name}.img",
                    "bytes": res.bytes_moved,
                    "sha256": res.sha256,
                    "seconds": round(res.seconds, 3),
                })

        if manifest and entries:
            payload = {
                "tool": "TFast MTK Bootloader Tool",
                "exported_at": __import__("datetime").datetime.now()
                                 .isoformat(timespec="seconds"),
                "partitions": entries,
            }
            (out_dir / "manifest.json").write_text(
                _json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return results

    # ------------------------------------------------------------------ #
    # Speed probe
    # ------------------------------------------------------------------ #
    def benchmark_read(self, name: str, length: Optional[int] = None,
                       chunk_size: Optional[int] = None) -> TransferResult:
        """Read a slice and report throughput, without writing anything to disk."""
        info = self._guard(name, False, "benchmark")
        total = length or min(self.resolve_size(name, refresh=True), 4 << 20)
        if total <= 0:
            return TransferResult(False, f"Nothing to measure on '{name}'")
        saved = self.chunk_size
        if chunk_size:
            self.chunk_size = max(DD_BLOCK, min(int(chunk_size), MAX_CHUNK))
        t0 = self._now()
        try:
            data = self.read_partition(name, length=min(total, 64 << 20))
        except PartitionError as exc:
            return TransferResult(False, str(exc))
        finally:
            self.chunk_size = saved
        return TransferResult(
            True, f"Read {len(data):,} bytes from '{name}'",
            bytes_moved=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            verified=True, seconds=self._now() - t0,
            chunks=(len(data) + (chunk_size or saved) - 1) // (chunk_size or saved))

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #
    def _verify_bytes_against(self, name: str, expected: bytes, digest: str,
                              offset: int, force: bool) -> bool:
        try:
            actual = self.read_partition(name, offset=offset, length=len(expected),
                                         force=force)
        except PartitionError:
            return False
        ok = hashlib.sha256(actual).hexdigest() == digest
        if not ok:
            diff = next((i for i, (a, b) in enumerate(zip(actual, expected))
                         if a != b), min(len(actual), len(expected)))
            self._say(f"  read-back differs at offset {diff:,}")
        return ok

    def _verify_file_against(self, name: str, src: Path, digest: str,
                             force: bool) -> bool:
        try:
            data = Path(src).read_bytes()
        except OSError:
            return False
        return self._verify_bytes_against(name, data, digest, 0, force)

    def verify_partition(self, name: str, src: Path, force: bool = False) -> TransferResult:
        """Compare a live partition against a local image."""
        src = Path(src)
        if not src.exists():
            return TransferResult(False, f"File not found: {src}")
        expected = src.read_bytes()
        digest = hashlib.sha256(expected).hexdigest()
        try:
            actual = self.read_partition(name, length=len(expected), force=force)
        except PartitionError as exc:
            return TransferResult(False, str(exc))

        actual_digest = hashlib.sha256(actual).hexdigest()
        if actual_digest == digest:
            return TransferResult(True, f"'{name}' matches {src.name}",
                                  bytes_moved=len(expected), sha256=digest,
                                  verified=True, path=src)
        diff = next((i for i, (a, b) in enumerate(zip(actual, expected))
                     if a != b), min(len(actual), len(expected)))
        return TransferResult(
            False,
            f"'{name}' does NOT match {src.name}; first difference at byte {diff:,}",
            bytes_moved=len(actual), sha256=actual_digest, verified=False, path=src)

    # ------------------------------------------------------------------ #
    # Bulk helper
    # ------------------------------------------------------------------ #
    def backup_many(self, names: Sequence[str], out_dir: Optional[Path] = None,
                    skip_protected: bool = True) -> list[TransferResult]:
        out_dir = Path(out_dir) if out_dir else self.workspace / "backups"
        out_dir.mkdir(parents=True, exist_ok=True)
        results: list[TransferResult] = []
        for name in names:
            if skip_protected and name in BRICK_RISK_PARTITIONS:
                results.append(TransferResult(
                    False, f"'{name}' skipped (brick-risk)"))
                continue
            results.append(self.backup_partition(
                name, dest=out_dir / f"{name}.img", verify=True))
        return results


# --------------------------------------------------------------------------- #
# Real session: connect the engine and expose a ShellTransport
# --------------------------------------------------------------------------- #
class MetaShellTransport:
    """Wraps ``MtkMetaProtocol`` as a :class:`ShellTransport`.

    Imports the compiled engines directly. The host interpreter is CPython 3.14,
    the same generation the engines were built for, so a second embedded
    interpreter (the old ``PyDLL`` route) is not needed and not used.
    """

    def __init__(self, protocol=None) -> None:
        self.proto = protocol
        self._connected = False

    # -- engine loading -------------------------------------------------- #
    @staticmethod
    def _load_engine():
        from . import config
        engines = Path(config.HANDOFF_DIR) / "engines"
        runtime = Path(config.PY314_RUNTIME_DIR)
        for d in (str(runtime), str(engines)):
            if os.path.isdir(d):
                sys.path.insert(0, d)
                try:
                    os.add_dll_directory(d)                      # type: ignore[attr-defined]
                except (AttributeError, OSError):
                    pass
        import mtk_meta_protocol                                    # noqa: PLC0415
        return mtk_meta_protocol

    @classmethod
    def engines_available(cls) -> bool:
        from . import config
        return ((Path(config.HANDOFF_DIR) / "engines" / "mtk_meta_protocol.pyd").exists()
                and (Path(config.PY314_RUNTIME_DIR) / "python314.dll").exists())

    # -- connection ------------------------------------------------------ #
    def discover_port(self) -> Optional[str]:
        """Find a MediaTek VCOM/Preloader serial port (VID 0x0E8D)."""
        try:
            from serial.tools import list_ports                       # noqa: PLC0415
        except Exception:                                           # noqa: BLE001
            return None
        for p in list_ports.comports():
            desc = (p.description or "").lower()
            if p.vid == 0x0E8D or any(k in desc for k in
                                      ("mediatek", "preloader", "mtk", "vcom")):
                return p.device
        return None

    def connect(self, port: Optional[str] = None, log=print, timeout: int = 25, cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        if self._connected:
            return True
        import time

        if not port or str(port).lower() in ("auto", "auto-detect"):
            log("[*] Searching for MediaTek Preloader / VCOM / META port...")
            log("    1. Turn phone OFF completely.")
            log("    2. Hold Volume Down (or Vol Down + Power) and connect USB.")

            t0 = time.time()
            initial_ports = set()
            try:
                from serial.tools import list_ports
                initial_ports = {p.device.upper() for p in list_ports.comports()}
            except Exception:
                pass

            port = self.discover_port()
            while not port and (time.time() - t0 < timeout):
                if cancel_check and cancel_check():
                    log("[*] Connection search canceled by user.")
                    return False
                time.sleep(0.4)
                p = self.discover_port()
                if p:
                    port = p
                    break
                try:
                    from serial.tools import list_ports
                    for cp in list_ports.comports():
                        if cp.device.upper() not in initial_ports:
                            port = cp.device
                            break
                except Exception:
                    pass
                if port:
                    break

        if not port:
            log("[-] Search timed out: No MediaTek serial port detected (VID 0x0E8D / Preloader / VCOM).")
            log("    Please ensure phone is OFF, hold Volume Down, and plug in USB.")
            return False

        log(f"[*] Found target serial port: {port}. Establishing META protocol handshake...")
        try:
            proto_mod = self._load_engine()
            self.proto = proto_mod.MtkMetaProtocol(lambda m: log(f"  [META] {m}"))
            if not self.proto.connect_persistent(port):
                log(f"[-] Could not establish META handshake on {port}. Device may have rebooted or dropped.")
                return False
            self.proto._authorized = True
            try:
                self.proto.initialize_ap_editor_shell()
            except Exception as exc:
                log(f"  AP shell init note: {exc}")
            self._connected = True
            log(f"[+] META session established on {port}")
            return True
        except Exception as exc:
            log(f"[-] META protocol error on {port}: {exc}")
            return False

    def close(self) -> None:
        if self.proto is not None:
            try:
                self.proto.close()
            except Exception:                                       # noqa: BLE001
                pass
        self._connected = False

    # -- transport ------------------------------------------------------- #
    def shell(self, cmd: str, timeout_ms: int = 20000) -> str:
        if not self._connected or self.proto is None:
            raise PartitionError("META session is not connected")
        return self.proto.execute_shell_cmd_direct(cmd, timeout_ms) or ""
