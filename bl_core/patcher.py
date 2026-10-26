"""
Bootloader patching: in-place LK patching plus the legacy vbmeta helper.

The primary path is **in-place**: read the device's own LK partition, analyse it,
patch the documented lock-state stubs, back up the original and write the patched
image back to the *same* partition. Image size never changes.

This replaces, for unlock purposes, the older "download a pre-made binary from
the vendor catalog" model, which requires an exact model *and* firmware-revision
match and will brick a device when that mapping is wrong.

The vendor helpers (`download_patch_file`, `prepare_patch_bundle`) are retained
only because older call sites still use them; they are marked legacy.

HONEST SCOPE
------------
* Reading a partition requires a transport. `fastboot fetch` is tried first, then
  adb shell `dd`. Many production bootloaders disable `fetch`; when neither works
  the tool refuses with instructions instead of pretending.
* Nothing here proves a patch unlocks a phone. Only hardware can.

Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
https://tfastdigital.com/
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import requests

from . import config
from . import lk_image

# --------------------------------------------------------------------------- #
# Partition candidates, in the order the research tries them
# --------------------------------------------------------------------------- #
LK_PARTITIONS = ("lk_a", "lk_b", "lk")


class LkAcquireError(RuntimeError):
    """Raised when no transport can read the LK partition."""


@dataclass
class AcquiredImage:
    path: Path
    partition: str
    transport: str
    sha256: str
    size: int


def _run_quiet(cmd: list[str], timeout: int = 60, cwd: str | None = None):
    """Run a command with the console window hidden on Windows."""
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        timeout=timeout,
        cwd=cwd,
    )


def find_adb() -> Optional[str]:
    """Locate adb.exe: bundled bin/ first, then PATH."""
    bundled = config.BIN_DIR / "adb.exe"
    if bundled.exists():
        return str(bundled)
    return shutil.which("adb")


def find_fastboot() -> Optional[str]:
    if os.path.exists(config.FASTBOOT_PATH):
        return str(config.FASTBOOT_PATH)
    return shutil.which("fastboot")


# --------------------------------------------------------------------------- #
class BootloaderPatcher:
    def __init__(self, workspace_dir: Optional[Path] = None,
                 api_key: str = config.API_KEY_CLIENT):
        self.workspace = workspace_dir or config.WORKSPACE_DIR
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key

    # ------------------------------------------------------------------ #
    # In-place LK patching (primary path)
    # ------------------------------------------------------------------ #
    def acquire_device_lk(self, partition: Optional[str] = None,
                          fastboot_path: Optional[str] = None,
                          dest: Optional[Path] = None) -> AcquiredImage:
        """Read the device's LK partition into the workspace.

        Tries ``fastboot fetch``, then adb shell ``dd``. Raises
        :class:`LkAcquireError` with actionable guidance when neither transport
        can read the partition.
        """
        parts = [partition] if partition else list(LK_PARTITIONS)
        dest = dest or (self.workspace / "lk_device.img")
        errors: list[str] = []
        fb = fastboot_path or find_fastboot()

        # Fail fast when nothing is connected. Without this, `fastboot fetch`
        # blocks waiting for a device and the caller appears to hang.
        if fb:
            try:
                probe = _run_quiet([fb, "devices"], timeout=15)
                if not (probe.stdout or "").strip():
                    raise LkAcquireError(
                        "No fastboot device detected, so the LK partition cannot be read.\n"
                        "Put the device in Fastboot/Bootloader mode and connect it, or\n"
                        "dump `lk` yourself with mtkclient / a scatter file and use\n"
                        "  lk-analyze --image <file>\n"
                        "  lk-patch   --image <file> --write"
                    )
            except LkAcquireError:
                raise
            except Exception as exc:                            # noqa: BLE001
                errors.append(f"fastboot devices: {exc}")

        # --- transport 1: fastboot fetch -------------------------------- #
        if fb:
            for part in parts:
                if dest.exists():
                    dest.unlink()
                try:
                    proc = _run_quiet([fb, "fetch", part, str(dest)], timeout=300)
                    out = (proc.stdout or "").strip()
                except Exception as exc:                        # noqa: BLE001
                    errors.append(f"fastboot fetch {part}: {exc}")
                    continue
                if dest.exists() and dest.stat().st_size > 0:
                    return AcquiredImage(
                        path=dest, partition=part, transport="fastboot fetch",
                        sha256=lk_image.sha256_of_file(dest),
                        size=dest.stat().st_size,
                    )
                low = out.lower()
                if "unknown" in low or "not support" in low or "unsupported" in low:
                    errors.append(f"fastboot fetch {part}: bootloader does not support `fetch`")
                else:
                    errors.append(f"fastboot fetch {part}: {out[:160] or 'no data returned'}")

        # --- transport 2: adb shell dd ---------------------------------- #
        adb = find_adb()
        if adb:
            remote = "/sdcard/lk_readback.img"
            for part in parts:
                path_on_device = f"/dev/block/by-name/{part}"
                try:
                    probe = _run_quiet([adb, "shell", f"su -c 'ls -l {path_on_device}'"],
                                       timeout=25)
                    if probe.returncode != 0 or "No such file" in (probe.stdout or ""):
                        errors.append(f"adb: {path_on_device} not present")
                        continue
                    copy = _run_quiet(
                        [adb, "shell",
                         f"su -c 'dd if={path_on_device} of={remote} bs=1048576'"],
                        timeout=600,
                    )
                    if copy.returncode != 0:
                        errors.append(f"adb dd {part}: {(copy.stdout or '')[:160]}")
                        continue
                    if dest.exists():
                        dest.unlink()
                    pull = _run_quiet([adb, "pull", remote, str(dest)], timeout=600)
                    _run_quiet([adb, "shell", f"rm -f {remote}"], timeout=25)
                    if dest.exists() and dest.stat().st_size > 0:
                        return AcquiredImage(
                            path=dest, partition=part, transport="adb dd",
                            sha256=lk_image.sha256_of_file(dest),
                            size=dest.stat().st_size,
                        )
                    errors.append(f"adb pull {part}: {(pull.stdout or '')[:160]}")
                except Exception as exc:                        # noqa: BLE001
                    errors.append(f"adb dd {part}: {exc}")

        raise LkAcquireError(
            "Could not read the LK partition from the device.\n"
            "  - `fastboot fetch` is disabled on most production bootloaders.\n"
            "  - adb readback needs root (an unlocked, rooted device) and adb on PATH.\n"
            "Alternative: dump `lk` yourself with mtkclient / a scatter file, then use\n"
            "  lk-analyze --image <file>\n"
            "  lk-patch   --image <file> --write\n"
            + ("\nAttempts:\n  " + "\n  ".join(errors) if errors else "")
        )

    def analyze_image(self, path: str | Path) -> lk_image.Analysis:
        return lk_image.analyze(Path(path).read_bytes())

    def patch_image_in_place(self, path: str | Path,
                             value: int = lk_image.DEFAULT_PATCH_VALUE,
                             dry_run: bool = False,
                             backup: bool = True) -> Tuple[bool, str, Optional[Path]]:
        """Analyse, patch and (unless dry-run) overwrite ``path`` with the result.

        Returns ``(ok, message, backup_path)``. The original is backed up before
        anything is written.
        """
        path = Path(path)
        if not path.exists():
            return False, f"Image not found: {path}", None

        data = path.read_bytes()
        analysis = lk_image.analyze(data)

        if analysis.state not in (lk_image.State.READY, lk_image.State.MIXED):
            return False, (
                f"Refusing to patch: state is {analysis.state}.\n"
                + "\n".join(analysis.problems or analysis.notes)
            ), None
        if analysis.arch != "AArch64":
            return False, (
                f"Refusing to patch: image is {analysis.arch}. Only AArch64 "
                "technique-A stubs are documented; guessing bytes could brick the device."
            ), None

        try:
            plan = lk_image.plan_patch(analysis, value)
        except ValueError as exc:
            return False, str(exc), None

        patched = lk_image.apply_plan(data, plan)

        ok, problems = lk_image.verify_patch(patched, value)
        if not ok:
            return False, "Patch verification failed:\n  " + "\n  ".join(problems), None

        detail = (f"state {analysis.state}, profile {analysis.profile.key}, "
                  f"{len(plan.sites)} site(s) -> {plan.stub_name} "
                  f"[{lk_image.STUB_VALUES[value]}]")

        if dry_run:
            return True, f"DRY RUN - would patch {detail} (file unchanged)", None

        backup_path: Optional[Path] = None
        if backup:
            backup_path = lk_image.backup_path_for(path)
            shutil.copyfile(path, backup_path)

        # Write via a temp file then replace, so a failure mid-write cannot leave
        # a half-patched image on disk.
        tmp = path.with_suffix(path.suffix + ".patched.tmp")
        tmp.write_bytes(patched)
        os.replace(tmp, path)

        return True, f"Patched {detail}", backup_path

    def write_back_to_device(self, image: Path, partition: str,
                             fastboot_path: Optional[str] = None,
                             reboot_to_fastboot: bool = True) -> Tuple[bool, str]:
        """Flash a patched LK image back to the partition it came from."""
        fb = fastboot_path or find_fastboot()
        if not fb:
            return False, "fastboot binary not found"
        try:
            proc = _run_quiet([fb, "flash", partition, str(image)], timeout=300)
        except Exception as exc:                                # noqa: BLE001
            return False, f"flash failed: {exc}"
        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            low = out.lower()
            if "lock control" in low or "no support" in low:
                return False, (
                    "Bootloader rejected the write: 'lock control'. The stock LK "
                    "gates partition writes, so this path needs an already-unlocked "
                    "device (or the META route).\n" + out
                )
            return False, out
        if reboot_to_fastboot:
            _run_quiet([fb, "reboot", "bootloader"], timeout=60)
        return True, out

    def patch_device_lk(self, partition: Optional[str] = None,
                        value: int = lk_image.DEFAULT_PATCH_VALUE,
                        dry_run: bool = False,
                        write_back: bool = True,
                        fastboot_path: Optional[str] = None) -> Tuple[bool, str]:
        """Full in-place pipeline: acquire -> analyse -> patch -> write back."""
        try:
            acquired = self.acquire_device_lk(partition, fastboot_path=fastboot_path)
        except LkAcquireError as exc:
            return False, str(exc)

        head = (f"Acquired {acquired.partition} via {acquired.transport} "
                f"({acquired.size:,} bytes, sha256 {acquired.sha256[:16]}...)")
        ok, msg, backup = self.patch_image_in_place(
            acquired.path, value=value, dry_run=dry_run, backup=True)
        lines = [head, msg]
        if backup:
            lines.append(f"Original backed up to {backup}")

        if not ok or dry_run:
            return ok, "\n".join(lines)

        if not write_back:
            lines.append("Skipped write-back; patched image left in the workspace.")
            return True, "\n".join(lines)

        wok, wmsg = self.write_back_to_device(
            acquired.path, acquired.partition, fastboot_path=fastboot_path)
        lines.append(("Write-back OK: " if wok else "Write-back FAILED: ") + wmsg)
        return wok, "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Legacy vendor-catalog helpers (kept for existing call sites)
    # ------------------------------------------------------------------ #
    def download_patch_file(self, remote_name: str, dest_filename: str) -> Tuple[bool, str]:
        """LEGACY: obtain a pre-compiled unlock binary from offline repo or server.

        Prefer :meth:`patch_device_lk`; a pre-made binary must match the model
        *and* firmware revision, which nothing here verifies.
        """
        dest_path = self.workspace / dest_filename

        local_file = config.OFFLINE_REPO_DIR / remote_name
        if local_file.exists() and local_file.stat().st_size > 0:
            shutil.copyfile(local_file, dest_path)
            return True, str(dest_path)

        url = config.PATCH_FILE_BASE + remote_name
        headers = {"X-API-Key": self.api_key}
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=30)
            if resp.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                try:
                    shutil.copyfile(dest_path, local_file)
                except Exception:
                    pass
                return True, str(dest_path)
            return False, f"Server returned HTTP {resp.status_code}"
        except Exception as exc:                                # noqa: BLE001
            return False, f"Download failed: {exc}"

    def patch_vbmeta(self, source_path: str, overwrite: bool = False) -> Tuple[bool, str]:
        """Disable AVB 2.0 verification and dm-verity in a vbmeta image header.

        Sets both flag bits: HASHTREE_DISABLED (bit0, dm-verity) and
        VERIFICATION_DISABLED (bit1). Clearing verification alone leaves
        dm-verity armed, so a modified system still fails its hashtree check and
        the device boot-loops.

        Output goes to ``workspace/vbmeta.unlocked.bin``, which is refused when it
        already exists unless ``overwrite=True`` - it previously destroyed a real
        staged vbmeta dumped from the device.
        """
        dest_path = self.workspace / "vbmeta.unlocked.bin"
        if dest_path.exists() and not overwrite:
            try:
                existing = dest_path.stat().st_size
            except OSError:
                existing = -1
            return False, (
                f"{dest_path} already exists ({existing:,} bytes) and was not "
                "overwritten. Move or delete it first, or pass overwrite=True."
            )
        try:
            with open(source_path, "rb") as f:
                data = bytearray(f.read())

            if len(data) < config.AVB_FLAGS_OFFSET + 4:
                return False, "File too small for valid AVB header"

            if not data.startswith(config.AVB_MAGIC):
                return False, "Not a valid AVB 2.0 image (magic missing)"

            flags = config.AVB_DISABLE_ALL_FLAGS  # 0x03
            data[config.AVB_FLAGS_OFFSET:config.AVB_FLAGS_OFFSET + 4] = flags.to_bytes(4, "big")

            with open(dest_path, "wb") as f:
                f.write(data)

            return True, str(dest_path)
        except Exception as exc:                                # noqa: BLE001
            return False, f"VBMeta patch failed: {exc}"

    def prepare_patch_bundle(self, model_info: dict,
                             vbmeta_src: Optional[str] = None) -> Tuple[bool, dict, str]:
        """LEGACY: stage pre-made LK binaries from the offline repo / server."""
        results: dict[str, str] = {}

        lk_a_name = model_info.get("lk_a_filename")
        if lk_a_name:
            ok, path = self.download_patch_file(lk_a_name, "lk_a.unlocked.bin")
            if not ok:
                return False, {}, f"Failed to download LK_A ({lk_a_name}): {path}"
            results["lk_a"] = path

        lk_b_name = model_info.get("lk_b_filename")
        if lk_b_name:
            ok, path = self.download_patch_file(lk_b_name, "lk_b.unlocked.bin")
            if ok:
                results["lk_b"] = path
            elif "lk_a" in results:
                lk_b_dest = self.workspace / "lk_b.unlocked.bin"
                shutil.copyfile(results["lk_a"], lk_b_dest)
                results["lk_b"] = str(lk_b_dest)
            else:
                return False, {}, f"Failed to download LK_B ({lk_b_name}): {path}"

        if vbmeta_src and os.path.exists(vbmeta_src):
            ok, path = self.patch_vbmeta(vbmeta_src)
            if not ok:
                return False, {}, f"Failed to patch VBMeta: {path}"
            results["vbmeta"] = path

        return True, results, "Patch files prepared successfully"
