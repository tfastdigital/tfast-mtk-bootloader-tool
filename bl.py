#!/usr/bin/env python3
# @brand tfast-digital
# TFast Digital - https://tfastdigital.com/
"""
TFast MTK Bootloader Tool - CLI Edition
MediaTek / Transsion bootloader unlock, patch and recovery suite

Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
Built by TFast Digital Agency.

    Website  : https://tfastdigital.com/
    GitHub   : https://github.com/tfastdigital
    Telegram : https://t.me/tfasthub
    WhatsApp : https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a

This software is proprietary. The copyright and attribution in
bl_core/tfast_brand.py must remain intact; removing it stops the application
from starting and is a breach of the licence terms. See tfast-NOTICE.txt.

@brand tfast-digital
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure bl_core is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _harden_stdout() -> None:
    """Keep the (c) and middle-dot glyphs safe on non-UTF-8 consoles.

    When stdout is a real Windows console Python already writes UTF-8. When it
    is piped or redirected into a file the active code page may not hold these
    characters, which raises UnicodeEncodeError and kills the tool mid-run.
    Reconfiguring to UTF-8 with replacement is the safe, non-fatal option.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_harden_stdout()

from bl_core import config
from bl_core import branding
from bl_core import tfast_brand
from bl_core import tfast_guard
from bl_core.fastboot import FastbootClient
from bl_core.models import ModelManager
from bl_core.api import SmartToolApi
from bl_core.cleaner import PartitionCleaner
from bl_core.patcher import BootloaderPatcher
from bl_core.flasher import FirmwareFlasher
from bl_core.meta import MetaUnlockEngine
from bl_core import lk_image
from bl_core import meta_partitions

# Terminal styling
class Style:
    HEADER = ""
    BLUE = ""
    CYAN = ""
    GREEN = ""
    YELLOW = ""
    RED = ""
    BOLD = ""
    DIM = ""
    RESET = ""

def banner():
    # Raw string: the block glyphs contain literal backslashes.
    art = r"""
  _____ _____        _     ____   _
 |_   _|  ___|_ _ __| |_  | __ ) | |
   | | | |_ / _` / __| __| |  _ \ | |
   | | |  _| (_| \__ \ |_  | |_) || |___
   |_| |_|  \__,_|___/\__| |____/ |_____|
"""
    print(f"\n{Style.CYAN}{Style.BOLD}{art}{Style.RESET}")
    print(f"{Style.BOLD}  {branding.PRODUCT}  (CLI Edition v{branding.PRODUCT_VERSION}){Style.RESET}")
    print(f"{Style.DIM}  {branding.TAGLINE}{Style.RESET}")
    print(f"{Style.DIM}  {branding.COPYRIGHT_LINE}{Style.RESET}")
    print(f"{Style.DIM}  Built by {branding.AGENCY_LONG}  |  {branding.URL_WEBSITE}{Style.RESET}")
    print()

def enforce_branding() -> int:
    """Refuse to run if the TFast Digital brand or copyright was stripped.

    Delegates to :func:`bl_core.tfast_guard.enforce`, which checks the
    in-memory constants, the on-disk manifest seal, the source watermarks and
    the copyright notice file.
    """
    return tfast_guard.enforce(stream=sys.stdout)

def log_info(msg: str):
    print(f"[{Style.CYAN}*{Style.RESET}] {msg}")

def log_success(msg: str):
    print(f"[{Style.GREEN}+{Style.RESET}] {Style.BOLD}{msg}{Style.RESET}")

def log_warn(msg: str):
    print(f"[{Style.YELLOW}!{Style.RESET}] {msg}")

def log_error(msg: str):
    print(f"[{Style.RED}-{Style.RESET}] {Style.BOLD}{msg}{Style.RESET}")

def print_section(title: str):
    print(f"\n{Style.BOLD}=== {title} ==={Style.RESET}")

# ----------------- CLI COMMAND HANDLERS -----------------

def cmd_devices(args, fb: FastbootClient):
    print_section("Scanning Fastboot Devices")
    devices = fb.get_devices()
    if not devices:
        log_warn("No fastboot devices detected.")
        log_info("Ensure device is in Fastboot / Bootloader mode and connected via USB.")
        return 1
    log_success(f"Detected {len(devices)} device(s):")
    for serial, status in devices:
        print(f"  - Serial: {Style.BOLD}{serial}{Style.RESET} ({status})")
    return 0

def cmd_info(args, fb: FastbootClient):
    print_section("Device Fastboot Information")
    if not fb.wait_for_device(timeout=15, prompt=True):
        log_error("No fastboot device connected!")
        return 1

    slot = fb.detect_slot()
    log_info(f"Active Boot Slot: {Style.GREEN}{Style.BOLD}{slot}{Style.RESET}")

    # Query Bootloader Lock Status
    is_unlocked, lock_msg = fb.get_lock_state()
    if is_unlocked is True:
        log_success(f"Bootloader State: UNLOCKED ({lock_msg})")
    elif is_unlocked is False:
        log_warn(f"Bootloader State: LOCKED ({lock_msg})")
    else:
        log_info(f"Bootloader State: {lock_msg}")

    partitions = fb.get_available_partitions(force_refresh=True)
    log_info(f"Discovered {len(partitions)} total partitions reported by bootloader.")

    # Check key partitions
    key_parts = ["lk", "lk_a", "lk_b", "vbmeta", "vbmeta_a", "vbmeta_b", "boot", "boot_a", "system", "super"]
    present = [p for p in key_parts if p in partitions]
    print(f"  Key boot partitions present: {Style.CYAN}{', '.join(present)}{Style.RESET}")

    # Check OEM trash/guard partitions
    detected_trash = []
    for trash in config.TRASH_PARTITIONS:
        for candidate in [trash, f"{trash}{slot}"]:
            if candidate in partitions:
                detected_trash.append(candidate)
    if detected_trash:
        log_warn(f"Detected {len(detected_trash)} OEM Anti-Tamper partitions: {Style.YELLOW}{', '.join(detected_trash)}{Style.RESET}")
    else:
        log_info("No known OEM anti-tamper partitions detected.")

    return 0

def cmd_models(args, mm: ModelManager):
    print_section("Supported Device Models")
    names, lookup = mm.fetch_models()
    log_info(f"Available model profiles ({len(names)} total):")
    for idx, name in enumerate(names, 1):
        meta = lookup[name]
        print(f"  [{idx}] {Style.BOLD}{name}{Style.RESET} (Codename: {meta.get('codename')}, Cost: {meta.get('patch_cost')} credits)")
    return 0

def _ensure_unlocked(cleaner: PartitionCleaner, purpose: str = "wipe the guard partitions") -> bool:
    """Required precondition: the bootloader must report UNLOCKED.

    The stock MTK LK gates partition writes behind lock control, so a locked
    device rejects every erase. Refuse to attempt the wipe unless the
    bootloader positively reports ``unlocked: yes`` - an unknown state is not
    good enough.
    """
    allowed, state, msg = cleaner.check_unlocked()
    if allowed:
        log_success(f"Bootloader confirmed UNLOCKED ({msg}) - proceeding.")
        return True
    if state is False:
        log_error(f"Bootloader is LOCKED ({msg}).")
        log_error(f"Partition writes are gated by lock control, so you cannot {purpose} yet.")
        log_info("Unlock the bootloader first (`bl.py unlock -m <model>` or menu option 4),")
        log_info("then re-run this command on the unlocked device.")
    else:
        log_warn(f"Bootloader lock state could not be confirmed ({msg}).")
        log_error(f"Refusing to {purpose} without a confirmed unlocked bootloader.")
        log_info("Re-check with `bl.py info`, or reboot the device into fastboot and retry.")
    return False


def cmd_wipe_trash(args, fb: FastbootClient):
    print_section("Erasing OEM Anti-Tamper & Guard Partitions")
    if not fb.wait_for_device(timeout=15, prompt=True):
        log_error("No fastboot device connected!")
        return 1

    cleaner = PartitionCleaner(fb)

    # Precondition: unlocked bootloader. Nothing is erased before this passes.
    if not _ensure_unlocked(cleaner):
        return 1

    include_system = not bool(getattr(args, "guard_only", False))
    slot = fb.detect_slot()
    log_info(f"Targeting active slot: {slot}")

    if include_system:
        log_info("Wiping guard overlays + real system partitions: "
                 + ", ".join(config.GUARD_WIPE_PARTITIONS))
        log_warn("The device will NOT boot until firmware is reflashed.")
    else:
        log_info("Wiping guard overlays only: " + ", ".join(config.TRASH_PARTITIONS))

    results = cleaner.clean_trash_partitions(slot, include_system=include_system)
    if not results:
        log_info("No anti-tamper partitions found on device.")
        return 0

    success_count = 0
    for part, ok, out in results:
        if ok:
            log_success(f"Erased partition: {part}")
            success_count += 1
        else:
            log_warn(f"Failed to erase {part}: {out}")

    log_success(f"Completed: erased {success_count}/{len(results)} guard partitions.")
    return 0

def resolve_model(mm: ModelManager, model_name: str):
    """Resolve a model name against the full catalog and warn on fuzzy matches.

    Without ``load_offline()`` the manager only knows the three hardcoded
    fallback models, so most of the bundled catalog was previously unreachable
    from the CLI and a partial name could resolve to the wrong device.
    """
    mm.load_offline()
    info = mm.get_model_info(model_name)
    if info and getattr(mm, "last_match_kind", None) == "substring":
        resolved = getattr(mm, "last_match_key", None) or info.get("model")
        log_warn(f"'{model_name}' is not an exact model name; matched '{resolved}'.")
        log_warn("Verify this is your device before continuing.")
    return info


# ----------------- IN-PLACE LK PATCHING (research model) -----------------

def cmd_lk_analyze(args):
    """Statically analyse an LK image. Read-only; never touches a device."""
    print_section("LK Image Analysis")
    path = args.image
    if not path:
        log_error("--image <file> is required.")
        return 1
    if not os.path.exists(path):
        log_error(f"Image not found: {path}")
        return 1

    try:
        analysis = lk_image.analyze(open(path, "rb").read())
    except Exception as exc:                                   # noqa: BLE001
        log_error(f"Analysis failed: {exc}")
        return 1

    for line in analysis.summary_lines():
        print(f"  {line}")

    print()
    if analysis.state == lk_image.State.ALREADY_PATCHED:
        log_success("This image already carries the unlock patch.")
    elif analysis.patchable:
        log_success("Image is Ready - the lock-state stub can be applied in place.")
        try:
            plan = lk_image.plan_patch(analysis, args.value)
            for line in plan.lines():
                print(f"  {line}")
        except ValueError as exc:
            log_warn(str(exc))
    elif analysis.state == lk_image.State.MIXED:
        log_warn("Image is partially patched (stock and patched sites coexist).")
    else:
        log_warn(f"Image is not patchable in its current state ({analysis.state}).")
        log_info("Use `python bl.py lk-profiles` to see which profiles are implemented.")

    log_warn("Static analysis cannot prove the patch unlocks a device; verify on hardware.")
    return 0


def cmd_lk_patch(args):
    """Patch an LK image in place: analyse, back up, apply the stub, verify."""
    print_section("In-Place LK Patch")
    patcher = BootloaderPatcher()

    if args.image:
        image = args.image
        if not os.path.exists(image):
            log_error(f"Image not found: {image}")
            return 1
        log_info(f"Source image: {image}")
        ok, msg, backup = patcher.patch_image_in_place(
            image, value=args.value, dry_run=args.dry_run, backup=not args.no_backup)
        for line in msg.splitlines():
            print(f"  {line}")
        if backup:
            log_success(f"Original backed up: {backup}")
        if not ok:
            return 1
        if args.dry_run:
            log_info("Dry run complete; nothing was written.")
            return 0

        if args.write:
            log_info("Flashing the patched image back to the device...")
            if not patcher.workspace:
                log_error("Workspace unavailable.")
                return 1
            part = args.partition or "lk_a"
            wok, wmsg = patcher.write_back_to_device(image, part)
            for line in (wmsg or "").splitlines():
                print(f"  {line}")
            if not wok:
                log_error("Write-back failed.")
                return 1
            log_success(f"Wrote patched LK back to {part}.")
        else:
            log_info("Run again with --write to flash it back to the origin partition.")
        return 0

    # No --image: attempt the full device pipeline.
    log_info("No --image given; attempting to read LK from the connected device...")
    ok, msg = patcher.patch_device_lk(
        partition=args.partition, value=args.value,
        dry_run=args.dry_run, write_back=not args.no_write_back)
    for line in msg.splitlines():
        print(f"  {line}")
    if ok:
        log_success("In-place LK patch pipeline completed.")
        return 0
    log_error("In-place LK patch pipeline did not complete.")
    return 1


def cmd_lk_profiles(args):
    print_section("LK Device Profiles")
    for block in lk_image.describe_profiles():
        print()
        for line in block.splitlines():
            print(f"  {line}")
    print()
    log_warn("Only the implemented profiles can be patched; the rest are analysis-only.")
    return 0


# ----------------- META PARTITION MANAGER -----------------

_META_SESSION = None


def _meta_manager(args):
    """Open (once) a META session and return a MetaPartitionManager.

    Returns ``(manager, None)`` on success or ``(None, message)`` on failure.
    """
    global _META_SESSION
    from bl_core import meta_partitions as mp

    if not mp.MetaShellTransport.engines_available():
        return None, ("META engines are missing (handoff_secure/engines or "
                      "py314_runtime). Reinstall the tool.")
    try:
        if _META_SESSION is None:
            transport = mp.MetaShellTransport()
            transport.connect(getattr(args, "port", None), log=log_info)
            _META_SESSION = transport
        return mp.MetaPartitionManager(
            _META_SESSION, config.WORKSPACE_DIR / "partitions",
            progress=lambda m: print(f"  {m}")), None
    except Exception as exc:                                    # noqa: BLE001
        return None, str(exc)


def _close_meta():
    global _META_SESSION
    if _META_SESSION is not None:
        _META_SESSION.close()
        _META_SESSION = None


def cmd_meta_parts(args):
    print_section("META Partition Table")
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        log_info("Put the phone in Preloader/META mode (power off, hold a volume key, plug in).")
        return 1
    try:
        parts = mgr.list_partitions(refresh=True)
        if not parts:
            log_warn("The device reported no partitions.")
            return 1
        log_success(f"{len(parts)} partition(s) reported:")
        width = max(len(p.name) for p in parts)
        for p in parts:
            flag = "  [PROTECTED]" if p.protected else ""
            print(f"  {p.name:<{width}}  {p.size_human:>12}  {p.source}{flag}")
        print()
        log_info("Protected partitions require --force for any write or erase.")
        return 0
    finally:
        _close_meta()


def cmd_meta_backup(args):
    print_section("META Partition Backup")
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        out_dir = config.WORKSPACE_DIR / "partitions" / "backups"
        names = args.names or []
        if not names:
            log_error("Name at least one partition (e.g. `meta-backup lk boot`).")
            return 1
        results = mgr.backup_many(names, out_dir=out_dir,
                                  skip_protected=not args.force)
        bad = 0
        for res in results:
            if res.ok:
                log_success(res.message)
                for line in res.lines()[1:]:
                    print(f"    {line}")
            else:
                log_error(res.message)
                bad += 1
        print()
        if bad:
            log_warn(f"{bad} of {len(results)} backup(s) did not complete.")
            return 1
        log_success(f"All {len(results)} backup(s) written to {out_dir}")
        return 0
    finally:
        _close_meta()


def cmd_meta_read(args):
    print_section("META Partition Read")
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        dest = Path(args.out) if args.out else (
            config.WORKSPACE_DIR / "partitions" / f"{args.partition}.img")
        res = mgr.backup_partition(args.partition, dest=dest,
                                   force=args.force, verify=not args.no_verify)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(res.message)
        for line in res.lines()[1:]:
            print(f"    {line}")
        return 0
    finally:
        _close_meta()


def cmd_meta_write(args):
    print_section("META Partition Write")
    src = Path(args.file)
    if not src.exists():
        log_error(f"File not found: {src}")
        return 1
    if args.partition in meta_partitions.BRICK_RISK_PARTITIONS and not args.force:
        log_error(f"'{args.partition}' is a brick-risk partition.")
        log_info("Pass --force only with a verified backup in hand.")
        return 1
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        data = src.read_bytes()
        log_info(f"Writing {len(data):,} bytes from {src.name} to '{args.partition}'"
                 f" at offset {args.offset:,}...")
        res = mgr.write_partition(args.partition, data, offset=args.offset,
                                  force=args.force, verify=not args.no_verify)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(res.message)
        for line in res.lines()[1:]:
            print(f"    {line}")
        return 0
    finally:
        _close_meta()


def cmd_meta_wipe(args):
    print_section("META Partition Wipe")
    mode = getattr(args, "mode", "filesystem")
    if args.partition in meta_partitions.BRICK_RISK_PARTITIONS and not args.force:
        log_error(f"'{args.partition}' is a brick-risk partition; refusing to wipe.")
        log_info("Pass --force only with a verified backup in hand.")
        return 1

    explain = {
        "filesystem": ("Zeroes the first and last 1 MiB. Destroys superblocks, journal "
                       "headers and footers so the partition reads as unformatted, "
                       "without rewriting a huge partition."),
        "head": "Zeroes only the first 1 MiB. The tail is left as-is.",
        "full": "Zeroes the entire partition. Slow, and only needed when the data "
                "itself must be unrecoverable.",
    }
    log_info(f"Wipe mode: {mode} - {explain.get(mode, '')}")
    log_warn("The device will not boot if you wipe the wrong partition.")

    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        _apply_speed(mgr, args)
        if getattr(args, "probe_only", False):
            sigs = mgr.probe_signatures(args.partition, force=args.force)
            if sigs:
                log_info(f"'{args.partition}' currently holds: {', '.join(sigs)}")
            else:
                log_info(f"'{args.partition}' has no recognised signatures "
                         "(blank, or an unknown format).")
            return 0

        res = mgr.wipe_partition(args.partition, mode=mode, force=args.force)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(res.message)
        for line in res.lines()[1:]:
            print(f"    {line}")
        return 0
    finally:
        _close_meta()


def cmd_meta_erase(args):
    print_section("META Partition Erase (zero-fill)")
    if args.partition in meta_partitions.BRICK_RISK_PARTITIONS and not args.force:
        log_error(f"'{args.partition}' is a brick-risk partition; refusing to erase.")
        return 1
    log_warn("Erasing zeroes the partition. The device will not boot if this is wrong.")
    log_info("To make a partition unformatted and prove it, use `meta-wipe` instead.")
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        res = mgr.erase_partition(args.partition, offset=args.offset,
                                  length=args.length, force=args.force)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(res.message)
        return 0
    finally:
        _close_meta()


def cmd_meta_verify(args):
    print_section("META Partition Verify")
    src = Path(args.file)
    if not src.exists():
        log_error(f"File not found: {src}")
        return 1
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        res = mgr.verify_partition(args.partition, src, force=args.force)
        if res.ok:
            log_success(res.message)
            return 0
        log_error(res.message)
        return 1
    finally:
        _close_meta()


def cmd_meta_restore(args):
    print_section("META Partition Restore")
    src = Path(args.file)
    if not src.exists():
        log_error(f"Backup file not found: {src}")
        return 1
    if args.partition in meta_partitions.BRICK_RISK_PARTITIONS and not args.force:
        log_error(f"'{args.partition}' is a brick-risk partition.")
        log_info("Pass --force only when restoring a backup you trust.")
        return 1
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        res = mgr.restore_partition(args.partition, src,
                                    force=args.force, verify=not args.no_verify)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(res.message)
        for line in res.lines()[1:]:
            print(f"    {line}")
        return 0
    finally:
        _close_meta()


def _apply_speed(mgr, args) -> None:
    speed = getattr(args, "speed", None)
    if speed:
        size = mgr.set_speed(speed)
        log_info(f"Transfer profile: {speed} ({size // 1024} KiB per chunk)")


def cmd_meta_export(args):
    print_section("META Partition Export")
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        _apply_speed(mgr, args)
        out_dir = Path(args.dir) if args.dir else (
            config.WORKSPACE_DIR / "partitions" / "exports")
        results = mgr.export_many(
            args.names, out_dir=out_dir, force=args.force,
            skip_protected=not args.force, verify=not args.no_verify)
        bad = 0
        total = 0
        for res in results:
            if res.ok:
                total += res.bytes_moved
                log_success(res.message + (f"  [{res.throughput}]" if res.throughput else ""))
                for line in res.lines()[1:]:
                    print(f"    {line}")
            else:
                log_error(res.message)
                bad += 1
        print()
        if bad:
            log_warn(f"{bad} of {len(results)} export(s) did not complete.")
            return 1
        log_success(f"Exported {len(results)} partition(s), {total:,} bytes "
                    f"to {out_dir}")
        if (out_dir / "manifest.json").exists():
            log_info(f"Manifest: {out_dir / 'manifest.json'}")
        return 0
    finally:
        _close_meta()


def cmd_meta_replace(args):
    print_section("META Partition Replace")
    src = Path(args.file)
    if not src.exists():
        log_error(f"Image not found: {src}")
        return 1
    if args.partition in meta_partitions.BRICK_RISK_PARTITIONS and not args.force:
        log_error(f"'{args.partition}' is a brick-risk partition.")
        log_info("Pass --force only with a verified backup in hand.")
        return 1
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        _apply_speed(mgr, args)
        log_info(f"Replacing '{args.partition}' with {src.name} ({src.stat().st_size:,} bytes)...")
        res = mgr.replace_partition(
            args.partition, src, force=args.force,
            verify=not args.no_verify,
            allow_size_mismatch=args.allow_size_mismatch,
            backup_first=not args.no_backup)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(res.message)
        for line in res.lines()[1:]:
            print(f"    {line}")
        return 0
    finally:
        _close_meta()


def cmd_meta_delete(args):
    print_section("Delete Local Partition Images")
    targets = [Path(p) for p in args.files]
    if args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            log_error(f"Not a directory: {d}")
            return 1
        targets += sorted(d.glob("*.img"))
    if not targets:
        log_error("Nothing to delete. Give file paths, or --dir <folder>.")
        return 1

    total = sum(p.stat().st_size for p in targets if p.exists())
    log_warn(f"About to delete {len(targets)} local file(s), {total:,} bytes total:")
    for p in targets:
        print(f"  {p}")
    if not args.yes:
        confirm = input("\nType YES to delete these files: ").strip()
        if confirm != "YES":
            log_info("Cancelled. Nothing was deleted.")
            return 1

    from bl_core import meta_partitions as _mp
    results = _mp.MetaPartitionManager(
        _mp.SimulatedTransport({}), config.WORKSPACE_DIR).delete_files(targets)
    bad = 0
    for res in results:
        if res.ok:
            log_success(res.message)
        else:
            log_error(res.message)
            bad += 1
    print()
    log_info("Note: this deletes local copies only. To wipe the partition ON the "
             "device use `meta-erase`.")
    return 1 if bad else 0


def cmd_meta_bench(args):
    print_section("META Read Speed Probe")
    mgr, err = _meta_manager(args)
    if err:
        log_error(err)
        return 1
    try:
        size = args.length or (4 << 20)
        log_info(f"Reading {size:,} bytes from '{args.partition}' to measure throughput...")
        res = mgr.benchmark_read(args.partition, length=size)
        if not res.ok:
            log_error(res.message)
            return 1
        log_success(f"{res.message}  [{res.throughput}]")
        for line in res.lines()[1:]:
            print(f"    {line}")
        log_info("Try --speed fast or --speed turbo on the other commands to compare.")
        return 0
    finally:
        _close_meta()


def cmd_patch(args, fb: FastbootClient, mm: ModelManager, patcher: BootloaderPatcher, api: SmartToolApi):
    print_section("Bootloader Patch Operation (LEGACY vendor-bundle path)")
    log_warn("This path stages a PRE-MADE binary keyed only by model name.")
    log_warn("It cannot verify the firmware revision, so a mismatch can brick the device.")
    log_info("Prefer: python bl.py lk-analyze / lk-patch (in-place, revision-safe).")

    model_name = args.model
    if not model_name:
        log_error("Model name or codename is required! Use --model <name>")
        return 1

    model_info = resolve_model(mm, model_name)
    if not model_info:
        log_error(f"Unknown model: '{model_name}'. Run 'python bl.py models' to see supported list.")
        return 1

    log_info(f"Selected Model: {Style.BOLD}{model_info.get('model', model_name)}{Style.RESET} ({model_info.get('codename')})")
    cost = model_info.get("patch_cost", config.DEFAULT_PATCH_COST)

    # Credit check
    log_info(f"Verifying account credits ({cost} credits required)...")
    ok, credits, msg = api.check_credits(cost=cost)
    if not ok:
        log_error(f"Credit check failed: {msg}")
        return 1
    log_success(f"Balance verified: {credits} credits available.")

    # Download and prepare files
    log_info("Downloading unlocked Little Kernel (LK) stages and preparing bundle...")
    ok, bundle, msg = patcher.prepare_patch_bundle(model_info, vbmeta_src=args.vbmeta)
    if not ok:
        log_error(f"Patch preparation failed: {msg}")
        return 1

    log_success(f"Patched bundle staged in workspace:")
    for k, p in bundle.items():
        print(f"  - {k}: {p}")

    # Deduct credits
    patched_str = ", ".join(os.path.basename(p) for p in bundle.values())
    deducted, deduct_msg = api.deduct_credits(
        cost=cost, operation="bootloader_patch",
        model_name=model_info.get('model', model_name), files_patched=patched_str)
    if not deducted:
        log_warn(f"Credit deduction was not confirmed: {deduct_msg}")

    log_success("Patch bundle ready for flashing!")
    return 0

def cmd_flash_custom(args, fb: FastbootClient):
    print_section("Flash Custom Firmware Stages")
    if not fb.wait_for_device(timeout=15, prompt=True):
        log_error("No fastboot device connected!")
        return 1

    flasher = FirmwareFlasher(fb)
    slot = fb.detect_slot()
    log_info(f"Targeting active slot: {slot}")

    if args.vbmeta:
        if not os.path.exists(args.vbmeta):
            log_error(f"VBMeta file not found: {args.vbmeta}")
            return 1
        log_info(f"Flashing VBMeta with AVB disabled: {args.vbmeta}")
        results = flasher.flash_vbmeta(args.vbmeta)
        for part, ok, out in results:
            if ok:
                log_success(f"Flashed VBMeta to {part}")
            else:
                log_error(f"Failed flashing VBMeta to {part}: {out}")

    if args.system:
        if not os.path.exists(args.system):
            log_error(f"System image not found: {args.system}")
            return 1
        log_info(f"Flashing custom system image: {args.system}")
        ok, out = flasher.flash_custom_system(args.system)
        if ok:
            log_success(f"Flashed custom system image successfully")
        else:
            log_error(f"Failed flashing custom system: {out}")

    if args.reboot:
        log_info("Rebooting device...")
        fb.reboot()

    return 0

def cmd_unlock_handshake(args, fb: FastbootClient):
    """FENIX-style Fastboot unlock track used before LK flashing.

    Sequence reproduced from the FENIX reference (`Fenix/fenix_cli.py`,
    `Fenix/unlock.bat`):
      1. Flash a 1MB zeroed FRP image (`fastboot flash frp <img>`).
      2. Send the lock-control prerequisite (`fastboot flashing unlock_critical`).
      3. Send `fastboot flashing unlock`; watch for the physical Volume UP
         "Unlock bootloader?" screen confirmation.
      4. Re-read `getvar unlocked`.
    Returns 0 only when the bootloader reports `unlocked: yes`.
    """
    print_section("Fastboot FRP + Unlock Handshake (FENIX Track)")
    if not fb.wait_for_device(timeout=25, prompt=True):
        log_error("No fastboot device connected!")
        return 1

    log_info("Step 1: Flashing 1MB zeroed frp.img (FRP restriction clear)...")
    frp_path = None
    for p in config.WORKSPACE_DIR.glob("frp*.img"):
        frp_path = p
        break
    if not frp_path:
        frp_path = config.WORKSPACE_DIR / "frp_cleared.img"
    try:
        with open(frp_path, "wb") as f:
            f.write(b"\x00" * (1024 * 1024))
    except Exception as e:
        log_error(f"Cannot stage zeroed FRP image: {e}")
        return 1
    ok, out = fb.flash("frp", str(frp_path))
    print(out.strip() or "(no output)")
    if not ok:
        low = (out or "").lower()
        if "lock control" in low or "not support" in low or "prohibit" in low:
            log_warn("FRP flash is still gated by lock control.")
        else:
            log_warn("FRP flash rejected.")
        log_info("Re-enter fastboot and retry, or continue with the META path")
        log_info("so seccfg/FRP can be cleared over serial instead.")
        return 1
    log_success("FRP image flashed (FRP restriction cleared).")

    log_info("Step 2: Sending lock-control prerequisite (flashing unlock_critical)...")
    ok, out = fb.flashing_unlock_critical()
    print(out.strip() or "(no output)")
    if not ok:
        log_warn("unlock_critical was not accepted; continuing anyway.")

    log_info("Step 3: Sending fastboot flashing unlock...")
    print(f"{Style.YELLOW}[!] WATCH THE PHONE SCREEN NOW:{Style.RESET}")
    print("    If a black 'Unlock bootloader?' screen appears,")
    print("    press VOLUME UP within a few seconds to confirm.")
    ok, out = fb.flashing_unlock()
    print(out.strip() or "(no output)")
    if not ok:
        log_error("flashing unlock was rejected.")
        return 1

    log_info("Step 4: Verifying bootloader lock state...")
    unlocked, lock_msg = fb.get_lock_state()
    print(lock_msg)
    if unlocked is True:
        log_success("Bootloader status verified: UNLOCKED!")
        return 0
    log_warn("Bootloader still reports LOCKED.")
    return 1


def cmd_unlock(args, fb: FastbootClient, mm: ModelManager, patcher: BootloaderPatcher, api: SmartToolApi):
    """Automated End-to-End Unlock Workflow (flash-first + auto META fallback).

    Mirrors the original SmartTool sequence recovered from the deobfuscated
    string pool: there is NO `fastboot flashing unlock` handshake gate - the
    patched LK/VBMeta stages ARE the unlock and are flashed directly. If the
    stock LK rejects the write ("No support by lock control"), the hardware
    unlock flag is cleared via META/Preloader NVRAM (the original's
    `_run_meta_action('Unlock Bootloader')`) and the flash is retried.
    """
    print_section("Automated Bootloader Unlock & Patch Pipeline")
    if not fb.wait_for_device(timeout=25, prompt=True):
        log_error("No fastboot device connected!")
        return 1

    model_name = args.model
    if not model_name:
        log_error("Model name or codename is required! Use --model <name>")
        return 1

    model_info = resolve_model(mm, model_name)
    if not model_info:
        log_error(f"Unknown model: '{model_name}'.")
        return 1

    log_info(f"Target Device: {Style.BOLD}{model_info.get('model', model_name)}{Style.RESET}")

    # 1. Detect slot and partitions
    slot = fb.detect_slot()
    log_info(f"1. Active boot slot: {slot}")

    # 2. Report lock state (informational only - the stock LK gates writes
    #    with 'lock control' regardless of the reported getvar flag).
    is_unlocked, lock_msg = fb.get_lock_state()
    log_info(f"2. Current lock status: {lock_msg}")

    # 3. Prepare patched binaries first (offline repo, else server)
    log_info("3. Preparing patched bootloader and vbmeta binaries...")
    ok, bundle, msg = patcher.prepare_patch_bundle(model_info, vbmeta_src=args.vbmeta)
    if not ok:
        log_error(f"Failed: {msg}")
        return 1

    flasher = FirmwareFlasher(fb)

    def _flash_once(label):
        any_ok = False
        lock_blocked = False
        if bundle.get("lk_a") or bundle.get("lk_b"):
            log_info(f"{label} flashing patched Little Kernel (LK) stages...")
            for part, okp, out in flasher.flash_bootloader(
                    bundle.get("lk_a"), bundle.get("lk_b")):
                low = (out or "").lower()
                if "lock control" in low or "no support" in low:
                    lock_blocked = True
                    log_warn(f"Lock control blocked {part} (expected on stock LK)")
                elif okp:
                    any_ok = True
                    log_success(f"Flashed {part}")
                else:
                    log_warn(f"Notice flashing {part}: {out.strip()}")
        if "vbmeta" in bundle:
            log_info(f"{label} flashing AVB-disabled VBMeta...")
            for part, okp, out in flasher.flash_vbmeta(bundle["vbmeta"]):
                low = (out or "").lower()
                if "lock control" in low or "no support" in low:
                    lock_blocked = True
                    log_warn(f"Lock control blocked {part}")
                elif okp:
                    any_ok = True
                    log_success(f"Flashed {part}")
                else:
                    log_warn(f"Notice flashing {part}: {out.strip()}")
        return any_ok, lock_blocked

    # 4. FENIX pre-flash track on a locked device: zeroed FRP image, then
    # unlock_critical, then the on-screen confirmed flashing unlock. This is
    # the missing SmartTool/FENIX sequence that makes later LK writes legal.
    if is_unlocked is not True:
        log_info("4. Running FENIX FRP + unlock handshake before LK flash...")
        hs = argparse.Namespace()
        if cmd_unlock_handshake(hs, fb) != 0:
            log_error("Fastboot handshake did not unlock the device.")
            log_info("Continuing: META fallback can still clear seccfg/FRP over serial.")
        else:
            log_success("Fastboot handshake accepted; lock state should now permit flashing.")

    # 5. FLASH attempt only after the handshake/track above.
    log_info("5. Attempting direct LK / VBMeta flash...")
    any_ok, lock_blocked = _flash_once("Attempt 1:")

    # 6. Auto META fallback when the stock LK still gates writes
    if lock_blocked and not getattr(args, "no_meta_fallback", False):
        log_warn("5. Stock LK enforces 'lock control' - flash writes gated.")
        log_info("   Clearing the hardware unlock flag via META/Preloader NVRAM...")
        print()
        print(f"{Style.CYAN}[*] PHONE MODE SWITCH REQUIRED:{Style.RESET}")
        print("    1. Unplug the USB cable now.")
        print("    2. Power the phone off completely.")
        print("    3. Hold Volume Down (or Volume Up / one key if needed).")
        print("    4. Plug the USB cable back in while holding.")
        print("    Waiting for the MTK Preloader serial port...\n")
        meta_args = argparse.Namespace(port=None)
        meta_rc = cmd_meta_unlock(meta_args)
        if meta_rc != 0:
            log_error("META unlock did not complete. Device left untouched.")
            return 1
        log_info("META unlock complete - waiting for device in Fastboot...")
        if not fb.wait_for_device(timeout=90, prompt=True):
            log_error("Device did not return to fastboot. Re-enter and retry.")
            return 1
        time.sleep(2)
        
        # Check lock state after META seccfg wipe
        is_unl, lock_msg = fb.get_lock_state()
        log_info(f"Bootloader lock status after META wipe: {lock_msg}")
        if is_unl is not True:
            log_info("Engaging Fastboot unlock with wiped seccfg hardware flag...")
            fb.flashing_unlock_critical()
            print(f"{Style.YELLOW}[!] WATCH THE PHONE SCREEN NOW:{Style.RESET}")
            print("    If an 'Unlock bootloader?' confirmation screen appears,")
            print("    press VOLUME UP immediately to confirm.")
            ok_unl, out_unl = fb.flashing_unlock()
            print(out_unl.strip() or "(no output)")
            is_unl_after, _ = fb.get_lock_state()
            if is_unl_after is True:
                log_success("Bootloader transitioned to UNLOCKED state!")
            else:
                log_info("Continuing with LK / VBMeta stage flash...")

        log_info("Retrying LK / VBMeta flash with cleared lock flag...")
        any_ok, lock_blocked = _flash_once("Attempt 2:")

    if lock_blocked:
        log_error("Flash still gated by lock control. Recovery needed.")
        return 1
    if not any_ok:
        log_error("No flash succeeded.")
        return 1

    # 7. Verify
    final_unlocked, final_lock_msg = fb.get_lock_state()
    if final_unlocked is True:
        log_success("Bootloader status verified: UNLOCKED!")
        log_success("Automated bootloader unlock workflow completed!")
    else:
        log_warn(f"Bootloader state reports: {final_lock_msg}")

    if getattr(args, "reboot", False):
        log_info("Rebooting device...")
        fb.reboot()
    return 0

def cmd_meta_unlock(args):
    print_section("MTK BROM / Preloader META Mode Unlock")
    engine = MetaUnlockEngine()
    if not engine.is_available():
        log_error("META engine protocol components not found in handoff_secure/engines!")
        return 1

    log_info("Initiating META mode connection over USB...")
    ok, msg = engine.run_meta_unlock(com_port=args.port)
    if ok:
        log_success(f"Success: {msg}")
        return 0
    else:
        log_error(f"Failed: {msg}")
        return 1

def cmd_reboot(args, fb: FastbootClient):
    print_section("Reboot Device")
    target = args.target if args.target != "system" else None
    log_info(f"Rebooting device to: {args.target}...")
    ok, out = fb.reboot(target)
    if ok:
        log_success("Reboot command sent.")
        return 0
    else:
        log_error(f"Reboot failed: {out}")
        return 1

# ----------------- INTERACTIVE WIZARD -----------------

def interactive_menu(fb: FastbootClient, mm: ModelManager, patcher: BootloaderPatcher, api: SmartToolApi):
    while True:
        banner()
        print(f"""  {Style.BOLD}MAIN MENU:{Style.RESET}
  [{Style.CYAN}1{Style.RESET}] Scan Fastboot Devices
  [{Style.CYAN}2{Style.RESET}] Device Information & Boot Slot
  [{Style.CYAN}3{Style.RESET}] Wipe OEM Anti-Tamper Partitions (tr_product, tr_vendor, etc.)
  [{Style.CYAN}4{Style.RESET}] Automated Bootloader Unlock (Smart Fastboot -> META Auto-Switch)
  [{Style.CYAN}5{Style.RESET}] Download / Export Patched LK & VBMeta (Offline Storage)
  [{Style.CYAN}6{Style.RESET}] Flash Custom VBMeta / System Image (Fastbootd)
  [{Style.CYAN}7{Style.RESET}] Fastboot Flashing Unlock (fastboot flashing unlock)
  [{Style.CYAN}8{Style.RESET}] Hardware META-Mode Unlock (NVRAM seccfg - Direct Hardware Bypass)
  [{Style.CYAN}9{Style.RESET}] View Supported Models & Credits
  [{Style.CYAN}R{Style.RESET}] Reboot Device (System / Fastbootd / Bootloader)
  [{Style.CYAN}0{Style.RESET}] Exit
""")
        choice = input(f"{Style.BOLD}Select an option [0-9, R]: {Style.RESET}").strip().upper()

        if choice == "1":
            cmd_devices(None, fb)
        elif choice == "2":
            cmd_info(None, fb)
        elif choice == "3":
            cmd_wipe_trash(None, fb)
        elif choice == "4":
            names, lookup = mm.fetch_models()
            print("\nSelect Target Model:")
            for idx, name in enumerate(names, 1):
                print(f"  [{idx}] {name}")
            sel = input("Model number: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(names):
                target_model = names[int(sel) - 1]
                vb_path = input("Optional local vbmeta.img path (press Enter to skip): ").strip() or None
                ns = argparse.Namespace(model=target_model, vbmeta=vb_path,
                                        reboot=True, no_meta_fallback=False)
                cmd_unlock(ns, fb, mm, patcher, api)
            else:
                log_warn("Invalid model selection.")
        elif choice == "5":
            names, lookup = mm.fetch_models()
            print("\nSelect Target Model:")
            for idx, name in enumerate(names, 1):
                print(f"  [{idx}] {name}")
            sel = input("Model number: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(names):
                target_model = names[int(sel) - 1]
                vb_path = input("Optional local vbmeta.img path (press Enter to skip): ").strip() or None
                ns = argparse.Namespace(model=target_model, vbmeta=vb_path)
                cmd_patch(ns, fb, mm, patcher, api)
        elif choice == "6":
            vb_path = input("Path to vbmeta image (press Enter to skip): ").strip() or None
            sys_path = input("Path to custom system.img (press Enter to skip): ").strip() or None
            reb = input("Reboot after flashing? (y/n): ").strip().lower() == "y"
            ns = argparse.Namespace(vbmeta=vb_path, system=sys_path, reboot=reb)
            cmd_flash_custom(ns, fb)
        elif choice == "7":
            log_info("Executing fastboot flashing unlock...")
            ok, out = fb.flashing_unlock()
            if ok and "prohibit" not in out.lower():
                log_success("Command accepted!")
            else:
                log_info(out)
                if "prohibit" in out.lower():
                    log_warn("Rejected: OEM Unlocking is disabled in Android Developer Options.")
                    print(f"[{Style.CYAN}*{Style.RESET}] To unlock without Android Developer Options, use Option [8] (Hardware META-Mode).")
        elif choice == "8":
            port = input("Enter COM port (press Enter for auto-detect): ").strip() or None
            ns = argparse.Namespace(port=port)
            cmd_meta_unlock(ns)
        elif choice == "9":
            cmd_models(None, mm)
            ok, credits, msg = api.check_credits()
            log_info(f"API Balance: {credits} credits ({msg})")
        elif choice == "R":
            print("\nReboot options: [1] System, [2] Fastbootd, [3] Bootloader, [4] Recovery")
            r_sel = input("Choice: ").strip()
            target_map = {"1": "system", "2": "fastboot", "3": "bootloader", "4": "recovery"}
            target = target_map.get(r_sel, "system")
            ns = argparse.Namespace(target=target)
            cmd_reboot(ns, fb)
        elif choice == "0":
            print("\nExiting MTK Bootloader CLI. Goodbye!")
            break
        else:
            log_warn("Unknown option. Please try again.")

        input(f"\n{Style.DIM}Press Enter to return to menu...{Style.RESET}")

# ----------------- ENTRY POINT -----------------

def main():
    rc = enforce_branding()
    if rc != 0:
        sys.exit(rc)

    parser = argparse.ArgumentParser(
        description=f"{branding.PRODUCT} (MediaTek / Transsion) - {branding.AGENCY_LONG}",
        epilog=f"{branding.COPYRIGHT_LINE}  {branding.URL_WEBSITE}",
    )
    parser.add_argument("--about", action="store_true",
                        help="Show version, copyright and support links")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # devices
    subparsers.add_parser("devices", help="List connected fastboot devices")

    # info
    subparsers.add_parser("info", help="Display device slot and partition details")

    # models
    subparsers.add_parser("models", help="List supported device models")

    # wipe-trash
    wt_parser = subparsers.add_parser(
        "wipe-trash",
        help="Wipe Transsion / OEM guard partitions (requires an unlocked bootloader)",
    )
    wt_parser.add_argument("--guard-only", action="store_true",
                           help="Erase only the tr_* guard overlays, leaving product/system_ext intact")
    wt_parser.add_argument("--include-system", action="store_true",
                           help="(default) Also erase product/system_ext; accepted for compatibility")

    # lk-analyze
    la_parser = subparsers.add_parser(
        "lk-analyze",
        help="Statically analyse an LK image (read-only, no device needed)",
    )
    la_parser.add_argument("--image", "-i", help="Path to an LK image (lk.img / lk_a / *.bin)")
    la_parser.add_argument("--value", "-V", type=int, default=lk_image.DEFAULT_PATCH_VALUE,
                           choices=sorted(lk_image.PATCH_STUBS),
                           help="Patch value to plan for (1=LKS_DEFAULT, 3=LKS_UNLOCK, 0=zero)")

    # lk-patch
    lp_parser = subparsers.add_parser(
        "lk-patch",
        help="Patch LK in place (analyse, back up, apply stub, verify)",
    )
    lp_parser.add_argument("--image", "-i",
                           help="Patch this image file instead of reading the device")
    lp_parser.add_argument("--value", "-V", type=int, default=lk_image.DEFAULT_PATCH_VALUE,
                           choices=sorted(lk_image.PATCH_STUBS),
                           help="Patch value to write (default 3 = LKS_UNLOCK)")
    lp_parser.add_argument("--partition", "-p",
                           help="Partition name (default: try lk_a, lk_b, lk)")
    lp_parser.add_argument("--dry-run", action="store_true",
                           help="Analyse and plan only; write nothing")
    lp_parser.add_argument("--no-backup", action="store_true",
                           help="Skip the .original backup (not recommended)")
    lp_parser.add_argument("--write", action="store_true",
                           help="With --image: flash the patched image back to the device")
    lp_parser.add_argument("--no-write-back", action="store_true",
                           help="Without --image: patch but do not flash")

    # lk-profiles
    subparsers.add_parser("lk-profiles", help="List implemented and unpublished LK profiles")

    # ---- META partition manager ---- #
    def _meta_common(p, extra_force=True):
        p.add_argument("--port", "-p", help="COM port of the META/Preloader link (auto-detect if omitted)")
        if extra_force:
            p.add_argument("--force", action="store_true",
                           help="Allow brick-risk partitions (preloader, pgpt, nvram, ...)")

    mp_list = subparsers.add_parser(
        "meta-parts", help="List the device partition table over META")
    _meta_common(mp_list, extra_force=False)

    mp_backup = subparsers.add_parser(
        "meta-backup", help="Back up one or more partitions over META (verified)")
    _meta_common(mp_backup)
    mp_backup.add_argument("names", nargs="+", help="Partition name(s), e.g. lk boot vbmeta")

    mp_read = subparsers.add_parser("meta-read", help="Read one partition to a local image")
    _meta_common(mp_read)
    mp_read.add_argument("partition", help="Partition name")
    mp_read.add_argument("--out", "-o", help="Destination file")
    mp_read.add_argument("--no-verify", action="store_true", help="Skip the read-back check")

    mp_write = subparsers.add_parser("meta-write", help="Write a local image to a partition")
    _meta_common(mp_write)
    mp_write.add_argument("partition", help="Partition name")
    mp_write.add_argument("--file", "-f", required=True, help="Image file to write")
    mp_write.add_argument("--offset", type=int, default=0, help="Byte offset inside the partition")
    mp_write.add_argument("--no-verify", action="store_true", help="Skip the read-back check")

    mp_wipe = subparsers.add_parser(
        "meta-wipe",
        help="Wipe a partition and verify its filesystem signatures are gone")
    _meta_common(mp_wipe)
    mp_wipe.add_argument("partition", help="Partition name")
    mp_wipe.add_argument("--mode", "-M", choices=list(meta_partitions.WIPE_MODES),
                         default="filesystem",
                         help="filesystem (head+tail, default) | head | full")
    mp_wipe.add_argument("--speed", choices=sorted(meta_partitions.SPEED_PROFILES),
                         help="Transfer profile (safe/balanced/fast/turbo)")
    mp_wipe.add_argument("--probe", dest="probe_only", action="store_true",
                         help="Only report the signatures present; wipe nothing")

    mp_erase = subparsers.add_parser("meta-erase", help="Zero a partition (or a slice of it)")
    _meta_common(mp_erase)
    mp_erase.add_argument("partition", help="Partition name")
    mp_erase.add_argument("--offset", type=int, default=0, help="Byte offset")
    mp_erase.add_argument("--length", type=int, help="Bytes to zero (default: whole partition)")

    mp_verify = subparsers.add_parser("meta-verify", help="Compare a live partition to a local image")
    _meta_common(mp_verify)
    mp_verify.add_argument("partition", help="Partition name")
    mp_verify.add_argument("--file", "-f", required=True, help="Reference image")

    mp_restore = subparsers.add_parser("meta-restore", help="Restore a partition from a backup")
    _meta_common(mp_restore)
    mp_restore.add_argument("partition", help="Partition name")
    mp_restore.add_argument("--file", "-f", required=True, help="Backup image to restore")
    mp_restore.add_argument("--no-verify", action="store_true", help="Skip the read-back check")

    mp_export = subparsers.add_parser(
        "meta-export", help="Export one or more partitions to files + manifest (streaming)")
    _meta_common(mp_export)
    mp_export.add_argument("names", nargs="+", help="Partition name(s)")
    mp_export.add_argument("--dir", "-d", help="Output directory")
    mp_export.add_argument("--speed", choices=sorted(meta_partitions.SPEED_PROFILES),
                           help="Transfer profile (safe/balanced/fast/turbo)")
    mp_export.add_argument("--no-verify", action="store_true", help="Skip the read-back check")

    mp_replace = subparsers.add_parser(
        "meta-replace", help="Replace a partition's contents with a different image")
    _meta_common(mp_replace)
    mp_replace.add_argument("partition", help="Partition name")
    mp_replace.add_argument("--file", "-f", required=True, help="New image to write")
    mp_replace.add_argument("--speed", choices=sorted(meta_partitions.SPEED_PROFILES),
                            help="Transfer profile (safe/balanced/fast/turbo)")
    mp_replace.add_argument("--allow-size-mismatch", action="store_true",
                            help="Permit a differently sized image (truncates if larger)")
    mp_replace.add_argument("--no-backup", action="store_true",
                            help="Skip the automatic safety backup (not recommended)")
    mp_replace.add_argument("--no-verify", action="store_true", help="Skip the read-back check")

    mp_delete = subparsers.add_parser(
        "meta-delete", help="Delete LOCAL partition images (not device partitions)")
    mp_delete.add_argument("files", nargs="*", help="Image files to delete")
    mp_delete.add_argument("--dir", "-d", help="Delete every *.img in this folder")
    mp_delete.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")

    mp_bench = subparsers.add_parser(
        "meta-bench", help="Measure partition read throughput")
    _meta_common(mp_bench, extra_force=False)
    mp_bench.add_argument("partition", help="Partition name")
    mp_bench.add_argument("--length", type=int, help="Bytes to read (default 4 MiB)")

    mp_speed = subparsers.add_parser("meta-speeds", help="List transfer speed profiles")
    mp_speed.add_argument("--port", "-p", help="(unused)")

    # patch
    p_parser = subparsers.add_parser("patch", help="LEGACY: stage a pre-made unlock bundle")
    p_parser.add_argument("--model", "-m", required=True, help="Target model name or codename")
    p_parser.add_argument("--vbmeta", "-v", help="Path to original vbmeta.img to patch")

    # flash-custom
    f_parser = subparsers.add_parser("flash-custom", help="Flash custom vbmeta and system images")
    f_parser.add_argument("--vbmeta", "-v", help="Path to vbmeta image")
    f_parser.add_argument("--system", "-s", help="Path to custom system image")
    f_parser.add_argument("--reboot", "-r", action="store_true", help="Reboot device after flashing")

    # unlock
    u_parser = subparsers.add_parser("unlock-handshake", help="FENIX track: flash zeroed FRP, unlock_critical, flashing unlock")
    u_parser.set_defaults(func="unlock-handshake")

    # unlock (full pipeline)
    u_parser = subparsers.add_parser("unlock", help="Run automated end-to-end bootloader unlock pipeline")
    u_parser.add_argument("--model", "-m", required=True, help="Target model name or codename")
    u_parser.add_argument("--vbmeta", "-v", help="Path to original vbmeta.img")
    u_parser.add_argument("--reboot", "-r", action="store_true", help="Reboot after completion")
    u_parser.add_argument("--no-meta-fallback", action="store_true",
                          help="Flash-first attempt only; skip the automatic META unlock fallback")

    # meta-unlock
    m_parser = subparsers.add_parser("meta-unlock", help="Execute hardware META mode seccfg unlock")
    m_parser.add_argument("--port", "-p", help="Serial COM port (e.g. COM3)")

    # reboot
    r_parser = subparsers.add_parser("reboot", help="Reboot connected device")
    r_parser.add_argument("target", nargs="?", default="system", choices=["system", "bootloader", "fastboot", "recovery"])

    args = parser.parse_args()

    if args.about:
        banner()
        print(branding.about_text(edition="CLI Edition"))
        print()
        return

    fb = FastbootClient()
    mm = ModelManager()
    patcher = BootloaderPatcher()
    api = SmartToolApi()

    if not args.command:
        # No args -> Launch interactive mode
        interactive_menu(fb, mm, patcher, api)
        return

    # Direct command mode
    banner()
    if args.command == "devices":
        sys.exit(cmd_devices(args, fb))
    elif args.command == "info":
        sys.exit(cmd_info(args, fb))
    elif args.command == "models":
        sys.exit(cmd_models(args, mm))
    elif args.command == "wipe-trash":
        sys.exit(cmd_wipe_trash(args, fb))
    elif args.command == "patch":
        sys.exit(cmd_patch(args, fb, mm, patcher, api))
    elif args.command == "flash-custom":
        sys.exit(cmd_flash_custom(args, fb))
    elif args.command == "unlock":
        sys.exit(cmd_unlock(args, fb, mm, patcher, api))
    elif args.command == "unlock-handshake":
        sys.exit(cmd_unlock_handshake(args, fb))
    elif args.command == "meta-unlock":
        sys.exit(cmd_meta_unlock(args))
    elif args.command == "lk-analyze":
        sys.exit(cmd_lk_analyze(args))
    elif args.command == "lk-patch":
        sys.exit(cmd_lk_patch(args))
    elif args.command == "lk-profiles":
        sys.exit(cmd_lk_profiles(args))
    elif args.command == "meta-parts":
        sys.exit(cmd_meta_parts(args))
    elif args.command == "meta-backup":
        sys.exit(cmd_meta_backup(args))
    elif args.command == "meta-read":
        sys.exit(cmd_meta_read(args))
    elif args.command == "meta-write":
        sys.exit(cmd_meta_write(args))
    elif args.command == "meta-erase":
        sys.exit(cmd_meta_erase(args))
    elif args.command == "meta-wipe":
        sys.exit(cmd_meta_wipe(args))
    elif args.command == "meta-verify":
        sys.exit(cmd_meta_verify(args))
    elif args.command == "meta-restore":
        sys.exit(cmd_meta_restore(args))
    elif args.command == "meta-export":
        sys.exit(cmd_meta_export(args))
    elif args.command == "meta-replace":
        sys.exit(cmd_meta_replace(args))
    elif args.command == "meta-delete":
        sys.exit(cmd_meta_delete(args))
    elif args.command == "meta-bench":
        sys.exit(cmd_meta_bench(args))
    elif args.command == "meta-speeds":
        print_section("Transfer Speed Profiles")
        for name, size in meta_partitions.SPEED_PROFILES.items():
            print(f"  {name:<10} {size // 1024:>6} KiB per chunk "
                  f"({size // (1024*1024)} MiB)")
        print()
        log_info("Bigger chunks mean fewer shell round-trips, which is what limits")
        log_info("throughput here. Use `safe` on a flaky link, `turbo` on a healthy one.")
        log_info("Measure the difference with:  meta-bench <partition> --length 4194304")
        sys.exit(0)
    elif args.command == "reboot":
        sys.exit(cmd_reboot(args, fb))

if __name__ == "__main__":
    main()
