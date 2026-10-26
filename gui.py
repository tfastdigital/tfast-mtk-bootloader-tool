#!/usr/bin/env python3
# @brand tfast-digital
# TFast Digital - https://tfastdigital.com/
"""
TFast MTK Bootloader Tool - Pro Desktop Edition (GUI)
=====================================================
Professional graphical workstation for the ``bl_core`` MediaTek & Transsion
bootloader unlock, patch, META partition manager, and recovery suite.

Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.
Built by TFast Digital Agency.

    Website  : https://tfastdigital.com/
    GitHub   : https://github.com/tfastdigital
    Telegram : https://t.me/tfasthub
    WhatsApp : https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a

Features:
- Dedicated Right-Side Shared Activity Logs Panel across all workstation pages
- Guided 5-stage unlock pipeline wizard with live pre-flight checks
- Real-time device snapshot (fastboot & META mode detection)
- Instant search & filter across models catalog and META partitions
- In-place Little Kernel (LK) binary analyzer and 4-byte unlock patcher
- High-performance chunked META partition backup, export, restore & wiping
- Transsion anti-tamper guard overlay cleaner (tr_product, tr_vendor, tr_system)
- Intelligent error diagnosis with actionable step-by-step troubleshooting
- High-contrast, sleek pro tech dark theme with toast notifications

@brand tfast-digital
"""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------- #
# Path bootstrap: make ``bl_core`` and bundled runtime libs importable.
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

_RUNTIME_LIB = BASE_DIR / "py314_runtime" / "lib"
if _RUNTIME_LIB.is_dir() and str(_RUNTIME_LIB) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_LIB))

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --------------------------------------------------------------------------- #
# Back end imports (report friendly UI error instead of raw traceback)
# --------------------------------------------------------------------------- #
BACKEND_IMPORT_ERROR: Exception | None = None
try:
    import bl as bl_cli
    from bl_core import branding
    from bl_core import config
    from bl_core import lk_image
    from bl_core import meta_partitions
    from bl_core import tfast_brand  # noqa: F401
    from bl_core import tfast_guard
    from bl_core.api import SmartToolApi
    from bl_core.cleaner import PartitionCleaner  # noqa: F401
    from bl_core.fastboot import FastbootClient
    from bl_core.flasher import FirmwareFlasher  # noqa: F401
    from bl_core.meta import MetaUnlockEngine  # noqa: F401
    from bl_core.models import ModelManager
    from bl_core.patcher import BootloaderPatcher
except Exception as _exc:  # pragma: no cover
    BACKEND_IMPORT_ERROR = _exc
    bl_cli = None  # type: ignore[assignment]
    branding = None  # type: ignore[assignment]
    config = None  # type: ignore[assignment]
    lk_image = None  # type: ignore[assignment]
    meta_partitions = None  # type: ignore[assignment]
    tfast_guard = None  # type: ignore[assignment]

APP_NAME = branding.PRODUCT if branding else "TFast MTK Bootloader Tool"
APP_TITLE = branding.WINDOW_TITLE if branding else "TFast MTK Bootloader Tool - Desktop Edition"
APP_VERSION = branding.PRODUCT_VERSION if branding else "2.0.0"
AGENCY = branding.AGENCY_LONG if branding else "TFast Digital Agency"

ASSETS_DIR = BASE_DIR / "assets"
ICON_ICO = ASSETS_DIR / "tfast.ico"
ICON_PNG = ASSETS_DIR / "tfast_256.png"

MIN_W = 1120
MIN_H = 700


# --------------------------------------------------------------------------- #
# Pro Palette & Typography
# --------------------------------------------------------------------------- #
class C:
    # Canvas & Structure
    BG = "#080c14"             # Ultra-deep midnight background
    BG_PAGE = "#0a101d"        # Elevated page canvas
    SIDEBAR = "#0c1322"        # Slate navy sidebar
    SIDEBAR_SUB = "#090f1c"    # Subtle sidebar secondary
    CARD = "#111a2d"           # Elevated card surface
    CARD_2 = "#16223b"         # Secondary card / input surface
    CARD_HOVER = "#1b2a47"     # Interactive hover surface
    BORDER = "#1f2e4d"         # Crisp border definition
    BORDER_SUBTLE = "#141e33"  # Soft divider border
    BORDER_FOCUS = "#3b82f6"   # Active focus blue glow

    # Vibrant Accents
    ACCENT = "#2563eb"         # Royal Electric Blue primary
    ACCENT_H = "#1d4ed8"       # Primary hover
    ACCENT_LIGHT = "#3b82f6"   # Highlight cyan-blue
    ACCENT_SUBTLE = "#172554"  # Background tint

    # Tech Cyan
    CYAN = "#06b6d4"           # Technical / Fastboot cyan
    CYAN_H = "#0891b2"
    CYAN_BG = "#082f49"

    # Status / Semantics
    OK = "#10b981"             # Emerald success
    OK_BG = "#064e3b"          # Emerald dark container
    OK_H = "#059669"
    OK_BORDER = "#047857"

    WARN = "#f59e0b"           # Amber warning
    WARN_BG = "#451a03"        # Amber dark container
    WARN_H = "#d97706"
    WARN_BORDER = "#78350f"

    DANGER = "#dc2626"         # Crimson red danger
    DANGER_BG = "#450a0a"      # Crimson dark container
    DANGER_H = "#b91c1c"
    DANGER_BORDER = "#7f1d1d"

    # Debug / Diagnostics
    DEBUG = "#a855f7"          # Technical purple / violet
    DEBUG_BG = "#2e1065"       # Dark violet container
    DEBUG_H = "#9333ea"        # Hover violet
    DEBUG_LIGHT = "#c084fc"    # Electric lilac text / highlight
    DEBUG_BORDER = "#6b21a8"   # Border definition

    # Typography
    TEXT = "#f8fafc"           # Crisp white-slate
    TEXT_MUTED = "#94a3b8"     # Secondary silver-slate
    TEXT_DIM = "#64748b"       # Muted subtle
    WHITE = "#ffffff"


FONT = "Segoe UI"
MONO = "Consolas"


# --------------------------------------------------------------------------- #
# Technical Diagnostic & Persistent Debug Logger
# --------------------------------------------------------------------------- #
class DebugLogger:
    """Thread-safe persistent session logger capturing operational telemetry,
    hardware handshakes, commands, and diagnostics for technical improvements."""

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        session_id = time.strftime("%Y%m%d_%H%M%S")
        self.session_file = self.logs_dir / f"tfast_debug_{session_id}.log"
        self.latest_file = self.logs_dir / "tfast_latest_debug.log"
        self._lock = threading.Lock()
        self._write_header()

    def _write_header(self) -> None:
        header = [
            "=" * 84,
            "TFast MTK Bootloader Tool - Technical Diagnostic & Debug Session Log",
            f"Product        : {branding.PRODUCT if branding else 'TFast MTK Tool'} v{branding.PRODUCT_VERSION if branding else '2.0.0'} ({branding.PRODUCT_EDITION if branding else 'Desktop'})",
            f"Copyright      : {branding.COPYRIGHT_LINE if branding else '© 2025-2026 TFast Digital Agency'}",
            f"Developer      : {AGENCY}  ·  https://tfastdigital.com/",
            f"Session Start  : {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"Python Runtime : {sys.version.splitlines()[0]}",
            f"OS Platform    : {sys.platform} ({os.name}) | PID: {os.getpid()}",
            f"Fastboot Path  : {config.FASTBOOT_PATH if config else 'N/A'}",
            f"Workspace Path : {config.WORKSPACE_DIR if config else 'N/A'}",
            "=" * 84,
            "",
        ]
        text = "\n".join(header) + "\n"
        with self._lock:
            try:
                self.session_file.write_text(text, encoding="utf-8")
                self.latest_file.write_text(text, encoding="utf-8")
            except Exception:
                pass

    def log(self, category: str, message: str, level: str = "INFO") -> None:
        t_str = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        t_name = threading.current_thread().name
        entry = f"[{t_str}] [{level:5s}] [{t_name:15s}] [{category:10s}] {message}\n"
        with self._lock:
            try:
                with open(self.session_file, "a", encoding="utf-8", errors="replace") as f:
                    f.write(entry)
                with open(self.latest_file, "a", encoding="utf-8", errors="replace") as f:
                    f.write(entry)
            except Exception:
                pass

    def record_raw_log(self, text: str) -> None:
        """Record raw line from stdout/stderr directly into session log."""
        t_str = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        t_name = threading.current_thread().name
        entry = f"[{t_str}] [RAW  ] [{t_name:15s}] {text}\n"
        with self._lock:
            try:
                with open(self.session_file, "a", encoding="utf-8", errors="replace") as f:
                    f.write(entry)
                with open(self.latest_file, "a", encoding="utf-8", errors="replace") as f:
                    f.write(entry)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Event Plumbing (Thread-safe stdout / stderr capture + UI message queue)
# --------------------------------------------------------------------------- #
EVENTS: "queue.Queue[tuple[str, object]]" = queue.Queue()


class QueueStream(io.TextIOBase):
    """Line-buffering stream that forwards complete lines to the UI queue and debug logger."""

    def __init__(
        self,
        q: "queue.Queue[tuple[str, object]]",
        logger_getter: Callable[[], DebugLogger | None] | None = None,
    ) -> None:
        super().__init__()
        self.q = q
        self.logger_getter = logger_getter
        self._buf = ""
        self._lock = threading.Lock()

    def write(self, s: str) -> int:  # type: ignore[override]
        if not s:
            return 0
        with self._lock:
            self._buf += s
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self.q.put(("log", line))
                if self.logger_getter:
                    try:
                        logger = self.logger_getter()
                        if logger:
                            logger.record_raw_log(line)
                    except Exception:
                        pass
        return len(s)

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        with self._lock:
            if self._buf:
                line = self._buf
                self._buf = ""
                self.q.put(("log", line))
                if self.logger_getter:
                    try:
                        logger = self.logger_getter()
                        if logger:
                            logger.record_raw_log(line)
                    except Exception:
                        pass

    def close(self) -> None:  # type: ignore[override]
        self.flush()
        super().close()

    def isatty(self) -> bool:
        return False


# --------------------------------------------------------------------------- #
# Smart Error Diagnostics Engine
# --------------------------------------------------------------------------- #
class ErrorDiagnostics:
    """Translates cryptic hardware/fastboot/serial errors into actionable advice."""

    PATTERNS = [
        (
            re.compile(r"not allowed in locked state|locked state|device is locked", re.I),
            "Bootloader Write Lockout",
            "The stock Little Kernel (LK) rejected the command because the bootloader is locked.\n\n"
            "Resolution steps:\n"
            "1. Run the 'Automated Unlock Pipeline' on the Unlock page.\n"
            "2. If the stock LK rejects fastboot writes, use 'Hardware META Unlock' to clear seccfg in NVRAM.\n"
            "3. Ensure OEM Unlocking is toggled ON in Android Developer Options.",
        ),
        (
            re.compile(r"oem unlock is not allowed|flashing unlock is not allowed|prohibit", re.I),
            "OEM Unlocking Is Disabled In Android Settings",
            "The device rejected the unlock handshake because OEM Unlocking is turned off in Android OS.\n\n"
            "Resolution steps:\n"
            "1. Boot the phone normally into Android.\n"
            "2. Open Settings > About Phone > Tap 'Build Number' 7 times to enable Developer Options.\n"
            "3. Go to System > Developer Options > Toggle ON 'OEM Unlocking'.\n"
            "4. Connect phone via USB, enable USB Debugging, and run 'adb reboot bootloader'.",
        ),
        (
            re.compile(r"< waiting for any device >|no devices/emulators found|device not found", re.I),
            "Fastboot Communication Timeout",
            "No device was detected over the Android Fastboot USB interface.\n\n"
            "Resolution steps:\n"
            "1. Check your USB cable and connect directly to a rear motherboard USB port (avoid USB hubs).\n"
            "2. Power the device off completely. Hold Volume Down (or Vol Down + Power) until Fastboot mode appears.\n"
            "3. Open Windows Device Manager and verify 'Android Bootloader Interface' is listed without error.\n"
            "4. Press F5 or click 'Refresh Status' in the top bar to re-probe.",
        ),
        (
            re.compile(r"permission denied|access is denied|could not open port", re.I),
            "COM Port Locked Or Access Denied",
            "The serial / Preloader port is locked by another program or missing permissions.\n\n"
            "Resolution steps:\n"
            "1. Close any running instances of SP Flash Tool, MTK Client, ModemMeta, or serial monitors.\n"
            "2. Unplug and replug the USB cable.\n"
            "3. On the META page, click 'Scan' to refresh available COM ports.",
        ),
        (
            re.compile(r"partition doesn't exist|unknown partition", re.I),
            "Target Partition Not Found On Device",
            "The bootloader does not report this partition name. On A/B devices, a slot suffix (_a or _b) may be required.\n\n"
            "Resolution steps:\n"
            "1. Refresh device status on the Dashboard to confirm the active slot.\n"
            "2. Check 'Partitions reported' in the device snapshot to verify supported targets.",
        ),
        (
            re.compile(r"wrong size|size mismatch|image too large", re.I),
            "Partition Image Size Mismatch",
            "The image file size does not match the physical partition size on the device.\n\n"
            "Resolution steps:\n"
            "1. Do not force-write mismatched images as this may cause a hard-brick.\n"
            "2. Ensure the dump or backup image matches your exact model and software build.",
        ),
        (
            re.compile(r"no mediatek serial port found|preloader / vcom|could not establish a meta session|cannot open com port|meta.*timed? out", re.I),
            "MediaTek META / Preloader Port Not Detected",
            "The computer could not detect or establish a serial link with a MediaTek device.\n\n"
            "How to enter MediaTek META / Preloader mode:\n"
            "1. Unplug the USB cable from the phone completely.\n"
            "2. Power the phone OFF and wait 5 seconds until the screen is fully black.\n"
            "3. Press and hold Volume Down (or Volume Up on select Helio/Dimensity models).\n"
            "4. While holding the button, plug the USB cable into the PC.\n"
            "5. Click 'Connect META Port' or 'Execute Hardware META Unlock' immediately.\n"
            "6. In Windows Device Manager, verify 'MediaTek PreLoader USB VCOM Port' appears under Ports (COM & LPT).",
        ),
    ]

    @classmethod
    def diagnose(cls, text: str) -> tuple[str, str] | None:
        if not text:
            return None
        for pattern, title, advice in cls.PATTERNS:
            if pattern.search(text):
                return title, advice
        return None


# --------------------------------------------------------------------------- #
# Backend Facade
# --------------------------------------------------------------------------- #
class Backend:
    """High-level backend interface wrapping bl_core modules and caching state."""

    def __init__(self) -> None:
        self.fb = FastbootClient()
        self.mm = ModelManager()
        self.patcher = BootloaderPatcher()
        self.api = SmartToolApi()

    def readiness(self) -> dict:
        repo = config.OFFLINE_REPO_DIR
        engines = config.HANDOFF_DIR / "engines"
        bins = sorted(p.name for p in repo.glob("*.bin")) if repo.is_dir() else []
        ws = config.WORKSPACE_DIR
        staged = sorted(p.name for p in ws.glob("*") if p.is_file()) if ws.is_dir() else []
        return {
            "fastboot_path": config.FASTBOOT_PATH,
            "fastboot": os.path.exists(config.FASTBOOT_PATH),
            "offline_count": len(bins),
            "offline_bins": bins,
            "meta_protocol": (engines / "mtk_meta_protocol.pyd").exists(),
            "meta_exploit": (engines / "mtk_exploit.pyd").exists(),
            "py314": (config.PY314_RUNTIME_DIR / "python314.dll").exists(),
            "workspace": str(ws),
            "staged": staged,
            "trash_partitions": list(config.TRASH_PARTITIONS),
        }

    def device_snapshot(self) -> dict:
        """Fast read-only snapshot using a single fastboot getvar all probe."""
        snap = {
            "connected": False,
            "serial": "",
            "mode": "",
            "slot": None,
            "unlocked": None,
            "lock_msg": "",
            "partitions": 0,
            "key_parts": [],
            "guards": [],
            "product": "",
            "hardware": "",
            "error": None,
        }
        try:
            devices = self.fb.get_devices(timeout=8)
        except Exception as exc:
            snap["error"] = str(exc)
            return snap

        if not devices:
            return snap

        snap["connected"] = True
        snap["serial"], snap["mode"] = devices[0]

        code, out = self.fb.run(["getvar", "all"], timeout=40)
        low = (out or "").lower()

        # Slot detection
        slot = "_a"
        m_slot = re.search(r"current-slot:\s*([a-zA-Z0-9_-]+)", out or "", re.I)
        if m_slot and m_slot.group(1).strip().lower() in ("b", "_b"):
            slot = "_b"
        snap["slot"] = slot

        # Product / Hardware detection
        m_prod = re.search(r"product:\s*([^\r\n]+)", out or "", re.I)
        if m_prod:
            snap["product"] = m_prod.group(1).strip()
        m_hw = re.search(r"hardware:\s*([^\r\n]+)", out or "", re.I)
        if m_hw:
            snap["hardware"] = m_hw.group(1).strip()

        # Unlock status
        if "unlocked: yes" in low:
            snap["unlocked"] = True
            snap["lock_msg"] = "unlocked: yes"
        elif "unlocked: no" in low:
            snap["unlocked"] = False
            snap["lock_msg"] = "unlocked: no"
        else:
            snap["unlocked"] = None
            snap["lock_msg"] = "unknown (not reported by bootloader)"

        # Partitions
        parts = {
            mm.group(1).strip().lower()
            for mm in re.finditer(r"partition-type:([a-zA-Z0-9_\-]+):", out or "", re.I)
        }
        snap["partitions"] = len(parts)
        self.fb.cached_partitions = parts
        self.fb.active_slot = slot

        keys = ["lk", "lk_a", "lk_b", "vbmeta", "vbmeta_a", "vbmeta_b", "boot", "system", "super"]
        snap["key_parts"] = [k for k in keys if k in parts]

        guards: list[str] = []
        for base in config.TRASH_PARTITIONS:
            for cand in (base, f"{base}{slot}"):
                if cand.lower() in parts:
                    guards.append(cand.lower())
        snap["guards"] = sorted(set(guards))
        return snap

    def device_connected(self) -> tuple[bool, str]:
        devices = self.fb.get_devices(timeout=6)
        if not devices:
            return False, ""
        serial, mode = devices[0]
        return True, f"{serial} ({mode})"

    def offline_models(self) -> tuple[list[str], dict]:
        path = config.OFFLINE_REPO_DIR / "models.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data = data.get("data", data)
                if isinstance(data, dict) and "models" in data and "lookup" in data:
                    return list(data["models"]), dict(data["lookup"])
            except Exception:
                traceback.print_exc()
        return list(config.FALLBACK_MODELS), dict(config.FALLBACK_LOOKUP)


# --------------------------------------------------------------------------- #
# Pro UI Widget Helpers
# --------------------------------------------------------------------------- #
def make_button(
    parent,
    text: str,
    command,
    kind: str = "accent",
    register: list | None = None,
    width: int | None = None,
    padx: int = 14,
    pady: int = 7,
    font_size: int = 9,
):
    """Generates a modern styled button with clean hover transitions."""
    palette = {
        "accent": (C.ACCENT, C.WHITE, C.ACCENT_H),
        "cyan": (C.CYAN, C.BG, C.CYAN_H),
        "danger": (C.DANGER, C.WHITE, C.DANGER_H),
        "ok": (C.OK_BG, C.WHITE, C.OK_H),
        "ghost": (C.CARD_2, C.TEXT, C.CARD_HOVER),
        "subtle": (C.SIDEBAR, C.TEXT_MUTED, C.CARD_2),
    }
    bg, fg, hov = palette.get(kind, palette["ghost"])
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hov,
        activeforeground=fg,
        disabledforeground=C.TEXT_DIM,
        relief="flat",
        bd=0,
        highlightthickness=0,
        font=(FONT, font_size, "bold"),
        cursor="hand2",
        padx=padx,
        pady=pady,
    )
    if width:
        btn.configure(width=width)

    def on_enter(e):
        if btn["state"] != "disabled":
            btn.configure(bg=hov)

    def on_leave(e):
        if btn["state"] != "disabled":
            btn.configure(bg=bg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

    if register is not None:
        register.append(btn)
    return btn


def autowrap(label: tk.Label, container: tk.Widget, pad: int = 36, minimum: int = 180):
    """Keep a label's wraplength dynamically synchronized with parent width."""
    state = {"w": None}

    def _resize(event):
        width = max(minimum, event.width - pad)
        if state["w"] == width:
            return
        state["w"] = width
        try:
            label.configure(wraplength=width)
        except tk.TclError:
            pass

    container.bind("<Configure>", _resize, add="+")
    return label


def card(parent, title: str | None = None, subtitle: str | None = None, icon: str = "", wrap: int = 480):
    """Produces an elevated dark glass container with distinct borders and header."""
    outer = tk.Frame(parent, bg=C.CARD, highlightthickness=1, highlightbackground=C.BORDER)
    inner = tk.Frame(outer, bg=C.CARD, padx=16, pady=12)
    inner.pack(fill="both", expand=True)

    if title:
        header_row = tk.Frame(inner, bg=C.CARD)
        header_row.pack(fill="x", pady=(0, 2))
        if icon:
            tk.Label(header_row, text=icon, bg=C.CARD, fg=C.ACCENT_LIGHT, font=(FONT, 11, "bold")).pack(
                side="left", padx=(0, 6)
            )
        tk.Label(
            header_row, text=title, bg=C.CARD, fg=C.WHITE, font=(FONT, 11, "bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True)

    if subtitle:
        lbl = tk.Label(
            inner,
            text=subtitle,
            bg=C.CARD,
            fg=C.TEXT_MUTED,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=wrap,
        )
        lbl.pack(fill="x", pady=(2, 8))
        autowrap(lbl, inner, pad=36)

    return outer, inner


def kv_row(parent, key: str, value: str = "--", wrap: int = 320, mono: bool = False, val_color: str = C.TEXT):
    """Two-column key-value widget with styled labels and auto-wrap."""
    row = tk.Frame(parent, bg=C.CARD)
    row.pack(fill="x", pady=2)
    tk.Label(row, text=key, bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w", width=20).pack(
        side="left"
    )
    val = tk.Label(
        row,
        text=value,
        bg=C.CARD,
        fg=val_color,
        font=(MONO if mono else FONT, 9, "bold"),
        anchor="w",
        justify="left",
        wraplength=wrap,
    )
    val.pack(side="left", fill="x", expand=True)
    return val


def entry(parent, textvar: tk.StringVar | None = None, width: int = 38, placeholder: str = ""):
    """Modern input box with active focus highlight."""
    e = tk.Entry(
        parent,
        textvariable=textvar,
        bg=C.CARD_2,
        fg=C.TEXT,
        insertbackground=C.TEXT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=C.BORDER,
        highlightcolor=C.BORDER_FOCUS,
        font=(FONT, 9),
        width=width,
    )
    return e


def note(parent, text: str, colour: str = C.TEXT_MUTED, wrap: int = 380, kind: str = "info"):
    """Styled banner alert card for informative, warning, or danger tips."""
    bg_map = {"info": C.CARD_2, "warn": C.WARN_BG, "danger": C.DANGER_BG}
    border_map = {"info": C.BORDER, "warn": C.WARN_BORDER, "danger": C.DANGER_BORDER}
    fg_map = {"info": C.TEXT, "warn": C.WARN, "danger": C.DANGER}

    frame = tk.Frame(
        parent,
        bg=bg_map.get(kind, C.CARD_2),
        highlightthickness=1,
        highlightbackground=border_map.get(kind, C.BORDER),
        padx=12,
        pady=8,
    )
    lbl = tk.Label(
        frame,
        text=text,
        bg=bg_map.get(kind, C.CARD_2),
        fg=fg_map.get(kind, colour),
        font=(FONT, 9),
        anchor="w",
        justify="left",
        wraplength=wrap,
    )
    lbl.pack(fill="x")
    autowrap(lbl, frame, pad=28)
    return frame


def chip(parent, text: str, bg: str = C.CARD_2, fg: str = C.TEXT, border: str = C.BORDER):
    """Badge pill for status chips and tags."""
    lbl = tk.Label(
        parent,
        text=f"  {text}  ",
        bg=bg,
        fg=fg,
        font=(MONO, 8, "bold"),
        padx=6,
        pady=3,
        highlightthickness=1,
        highlightbackground=border,
    )
    return lbl


class ScrollPage(tk.Frame):
    """Vertically scrollable page canvas with smooth mouse wheel navigation."""

    def __init__(self, master, bg: str = C.BG_PAGE):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.body.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width)
        )
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class NavButton(tk.Frame):
    """Sidebar navigation tab with left accent strip and hover feedback."""

    def __init__(self, master, text: str, command: Callable, icon: str = ""):
        super().__init__(master, bg=C.SIDEBAR, cursor="hand2")
        self._command = command
        self._active = False

        self.bar = tk.Frame(self, bg=C.SIDEBAR, width=3)
        self.bar.pack(side="left", fill="y")

        display_text = f"  {text.strip()}"
        self.lbl = tk.Label(
            self,
            text=display_text,
            bg=C.SIDEBAR,
            fg=C.TEXT_MUTED,
            font=(FONT, 9),
            anchor="w",
            padx=10,
            pady=8,
        )
        self.lbl.pack(side="left", fill="both", expand=True)

        for w in (self, self.lbl, self.bar):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _click(self, _=None):
        self._command()

    def _enter(self, _=None):
        if not self._active:
            self.configure(bg=C.CARD_HOVER)
            self.lbl.configure(bg=C.CARD_HOVER, fg=C.TEXT)
            self.bar.configure(bg=C.BORDER_FOCUS)

    def _leave(self, _=None):
        if not self._active:
            self.configure(bg=C.SIDEBAR)
            self.lbl.configure(bg=C.SIDEBAR, fg=C.TEXT_MUTED)
            self.bar.configure(bg=C.SIDEBAR)

    def set_active(self, active: bool) -> None:
        self._active = active
        bg = C.CARD if active else C.SIDEBAR
        self.configure(bg=bg)
        self.lbl.configure(bg=bg, fg=C.WHITE if active else C.TEXT_MUTED)
        self.bar.configure(bg=C.BORDER_FOCUS if active else bg)


# --------------------------------------------------------------------------- #
# Main Desktop Application
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    """TFast MTK Bootloader Desktop Workstation."""

    PAGES = [
        ("wizard", "Guided Unlock Wizard", ""),
        ("dashboard", "Hardware Dashboard", ""),
        ("unlock", "Bootloader Unlock", ""),
        ("wipe", "OEM Guard Wipe", ""),
        ("flash", "Flash Custom", ""),
        ("reboot", "Reboot Targets", ""),
        ("lk", "LK Patch & Analysis", ""),
        ("parts", "META Partitions", ""),
        ("meta", "META Hardware Unlock", ""),
        ("patch", "Patch Bundle Builder", ""),
        ("models", "Supported Models", ""),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        self.backend = Backend()
        self.debug_mode = True  # Starts ON by default for all operations
        self.debug_logger = DebugLogger(BASE_DIR / "logs")

        # Instrument fastboot runner for deep diagnostic capture
        self._orig_fb_run = self.backend.fb.run
        self.backend.fb.run = self._instrumented_fb_run

        self._busy = False
        self._probe_running = False
        self._manual_scan = False
        self._action_buttons: list[tk.Button] = []
        self._nav: dict[str, NavButton] = {}
        self._page_frames: dict[str, ScrollPage] = {}
        self._model_names: list[str] = []
        self._model_lookup: dict = {}
        self._current_page = "wizard"

        # Partition search cache
        self._cached_parts: list = []
        self._cached_models: list = []
        self._auto_scroll_enabled = True
        self._last_logged_device_sig: str | None = None

        self.title(APP_TITLE)
        self.configure(bg=C.BG)
        self.minsize(MIN_W, MIN_H)
        self._apply_icon()
        self._place_window()

        self._init_style()
        self._build_topbar()
        self._build_body()
        self._build_statusbar()

        self._load_models_fast()
        self._show_page("wizard")

        # Route every backend print() into the UI console queue and persistent session log file
        sys.stdout = QueueStream(EVENTS, lambda: getattr(self, "debug_logger", None))  # type: ignore[assignment]
        sys.stderr = QueueStream(EVENTS, lambda: getattr(self, "debug_logger", None))  # type: ignore[assignment]

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda e: self._probe(force_log=True))
        self.bind("<Control-l>", lambda e: self._clear_console())

        # Runtime integrity watch
        self._guard_watch = tfast_guard.GuardWatch(interval_seconds=45.0)
        self._guard_failed = False

        self._timer_ids: set[str] = set()
        self._schedule(80, self._pump)
        self._schedule(120, self._boot)
        self._schedule(1500, self._auto_probe)
        self._schedule(20000, self._guard_tick)

        self._log_line(f"{branding.PRODUCT} v{branding.PRODUCT_VERSION} — {branding.PRODUCT_EDITION}", "head")
        self._log_line(branding.COPYRIGHT_LINE, "plain")
        self._log_line(f"Built by {AGENCY}  ·  {branding.URL_WEBSITE}", "plain")
        self._log_line(f"Python {sys.version.split()[0]}  |  Fastboot: {config.FASTBOOT_PATH}", "plain")
        self._log_line(f"[*] Diagnostic session log: logs/{self.debug_logger.session_file.name}", "info")
        self._log_line("[*] Workstation initialized. Ready for device connection.", "info")

    # -- Window & Timers --------------------------------------------------- #
    def _schedule(self, delay_ms: int, fn) -> None:
        def run():
            self._timer_ids.discard(tid)
            try:
                fn()
            except tk.TclError:
                pass

        tid = self.after(delay_ms, run)
        self._timer_ids.add(tid)

    def _cancel_timers(self) -> None:
        for tid in list(self._timer_ids):
            try:
                self.after_cancel(tid)
            except Exception:
                pass
        self._timer_ids.clear()

    def _place_window(self) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if sw <= 1400 or sh <= 900:
            try:
                self.state("zoomed")
                return
            except tk.TclError:
                pass
        w = max(MIN_W, min(1280, sw - 80))
        h = max(MIN_H, min(840, sh - 80))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Dark theme scrollbars (kills the bright white native trough)
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background=C.BORDER,
            darkcolor=C.BORDER,
            lightcolor=C.BORDER,
            troughcolor=C.CARD_2,
            bordercolor=C.CARD_2,
            arrowcolor=C.TEXT_MUTED,
            arrowsize=12,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", C.ACCENT), ("disabled", C.BORDER_SUBTLE)],
            troughcolor=[("active", C.CARD_2), ("disabled", C.BG)],
        )

        style.configure(
            "TCombobox",
            fieldbackground=C.CARD_2,
            background=C.CARD_2,
            foreground=C.TEXT,
            arrowcolor=C.TEXT_MUTED,
            bordercolor=C.BORDER,
            lightcolor=C.BORDER,
            darkcolor=C.BORDER,
            insertcolor=C.TEXT,
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", C.CARD_2), ("disabled", C.CARD)],
            foreground=[("readonly", C.TEXT), ("disabled", C.TEXT_DIM)],
            selectbackground=[("readonly", C.CARD_2)],
            selectforeground=[("readonly", C.TEXT)],
        )
        style.configure(
            "TCheckbutton",
            background=C.CARD,
            foreground=C.TEXT,
            font=(FONT, 9),
            focuscolor=C.CARD,
            indicatormargin=5,
        )
        style.map(
            "TCheckbutton",
            background=[("active", C.CARD)],
            foreground=[("active", C.TEXT)],
        )
        style.configure(
            "TRadiobutton",
            background=C.CARD,
            foreground=C.TEXT,
            font=(FONT, 9),
            focuscolor=C.CARD,
            indicatormargin=5,
        )
        style.map(
            "TRadiobutton",
            background=[("active", C.CARD)],
            foreground=[("active", C.TEXT)],
        )
        style.configure(
            "Treeview",
            background=C.CARD,
            fieldbackground=C.CARD,
            foreground=C.TEXT,
            rowheight=26,
            borderwidth=0,
            font=(FONT, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=C.CARD_2,
            foreground=C.TEXT_MUTED,
            relief="flat",
            font=(FONT, 9, "bold"),
            padding=5,
        )
        style.map(
            "Treeview",
            background=[("selected", C.ACCENT)],
            foreground=[("selected", C.WHITE)],
        )

        self.option_add("*TCombobox*Listbox.background", C.CARD_2)
        self.option_add("*TCombobox*Listbox.foreground", C.TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", C.ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", C.WHITE)
        self.option_add("*TCombobox*Listbox.font", f"{{{FONT}}} 9")

    def _apply_icon(self) -> None:
        applied = False

        # Set explicit AppUserModelID so Windows Taskbar pins and groups under the TFast icon
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tfast.bootloader.workstation.2.0")
        except Exception:
            pass

        # 1. Native Windows ICO (direct on root + default for dialogs)
        if ICON_ICO.exists():
            try:
                self.iconbitmap(str(ICON_ICO))
                self.iconbitmap(default=str(ICON_ICO))
                applied = True
            except Exception:
                pass

            # Deep Win32 handle injection for titlebar and Alt-Tab switcher
            try:
                self.update_idletasks()
                hwnd = self.winfo_id()
                top_hwnd = ctypes.windll.user32.GetParent(hwnd) or hwnd
                LR_LOADFROMFILE = 0x00000010
                IMAGE_ICON = 1
                WM_SETICON = 0x0080
                hicon_sm = ctypes.windll.user32.LoadImageW(None, str(ICON_ICO), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                hicon_lg = ctypes.windll.user32.LoadImageW(None, str(ICON_ICO), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                if hicon_sm:
                    ctypes.windll.user32.SendMessageW(top_hwnd, WM_SETICON, 0, hicon_sm)
                if hicon_lg:
                    ctypes.windll.user32.SendMessageW(top_hwnd, WM_SETICON, 1, hicon_lg)
                applied = True
            except Exception:
                pass

        # 2. Non-Windows or fallback: only use iconphoto if native iconbitmap wasn't applied
        if not applied:
            for candidate in (ASSETS_DIR / "tfast_64.png", ICON_PNG):
                if not candidate.exists():
                    continue
                try:
                    self._icon_photo = tk.PhotoImage(file=str(candidate))
                    self.iconphoto(True, self._icon_photo)
                    applied = True
                    break
                except tk.TclError:
                    continue

        if not applied:
            self._log_line("[!] Icon assets not found in assets/", "warn")

    # -- Top Chrome & Notifications ---------------------------------------- #
    def _build_topbar(self) -> None:
        top = tk.Frame(self, bg=C.SIDEBAR, height=52, highlightthickness=1, highlightbackground=C.BORDER)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        # Brand mark
        if (ASSETS_DIR / "tfast_64.png").exists():
            try:
                self._bar_icon = tk.PhotoImage(file=str(ASSETS_DIR / "tfast_64.png"))
                tk.Label(top, image=self._bar_icon, bg=C.SIDEBAR).pack(side="left", padx=(14, 8), pady=9)
            except tk.TclError:
                pass

        tk.Label(top, text="TFast", bg=C.SIDEBAR, fg=C.ACCENT_LIGHT, font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(top, text=" MTK Tool", bg=C.SIDEBAR, fg=C.TEXT, font=(FONT, 13)).pack(side="left")

        # Pro Badge
        tk.Label(
            top,
            text=f" PRO v{APP_VERSION} ",
            bg=C.CARD_2,
            fg=C.ACCENT_LIGHT,
            font=(FONT, 8, "bold"),
            padx=6,
            pady=2,
            highlightthickness=1,
            highlightbackground=C.BORDER,
        ).pack(side="left", padx=(10, 16))

        # Active page title breadcrumb
        self.page_title = tk.Label(top, text="Guided Unlock Wizard", bg=C.SIDEBAR, fg=C.WHITE, font=(FONT, 11, "bold"))
        self.page_title.pack(side="left", padx=(10, 0))

        # Right side items
        make_button(top, "About", self._show_about, "subtle", padx=10, pady=4).pack(side="right", padx=(6, 14))
        self.top_log_btn = make_button(top, "Activity Logs", self._toggle_console, "ghost", padx=10, pady=4)
        self.top_log_btn.pack(side="right", padx=4)

        # Technical Debug Mode Toggle
        self.top_debug_btn = tk.Button(
            top,
            text="DEBUG: ON",
            command=self._toggle_debug_mode,
            bg=C.CARD_2,
            fg=C.ACCENT_LIGHT,
            activebackground=C.CARD_HOVER,
            activeforeground=C.WHITE,
            relief="flat",
            bd=0,
            font=(FONT, 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=C.BORDER,
        )
        self.top_debug_btn.pack(side="right", padx=4)

        make_button(top, "Scan (F5)", lambda: self._probe(force_log=True), "ghost", padx=10, pady=4).pack(side="right", padx=4)

        # Dynamic Connection Status Pill
        self.device_pill = tk.Label(
            top,
            text="  DEVICE: OFFLINE  ",
            bg=C.CARD_2,
            fg=C.TEXT_MUTED,
            font=(MONO, 8, "bold"),
            padx=10,
            pady=5,
            highlightthickness=1,
            highlightbackground=C.BORDER,
        )
        self.device_pill.pack(side="right", padx=8)

        # Pulse / Activity indicator bar (thin strip beneath topbar)
        self.pulse_bar = tk.Frame(self, bg=C.SIDEBAR, height=2)
        self.pulse_bar.pack(fill="x", side="top")
        self.pulse_glow = tk.Frame(self.pulse_bar, bg=C.BORDER, height=2, width=1)
        self.pulse_glow.place(x=0, y=0, relheight=1.0)
        self._pulse_pos = 0

    # -- Body & 3-Column Layout (Nav Left | Center Page | Shared Logs Right) - #
    def _build_body(self) -> None:
        body = tk.Frame(self, bg=C.BG)
        body.pack(fill="both", expand=True)

        # 1. Left Sidebar: Navigation
        sidebar = tk.Frame(body, bg=C.SIDEBAR, width=190, highlightthickness=1, highlightbackground=C.BORDER)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Categorized Nav Items (Refined, no toy emojis)
        categories = [
            ("WORKFLOW", [("wizard", "Guided Wizard"), ("dashboard", "Dashboard")]),
            (
                "FASTBOOT CORE",
                [
                    ("unlock", "Unlock Pipeline"),
                    ("wipe", "OEM Guard Wipe"),
                    ("flash", "Flash Custom"),
                    ("reboot", "Reboot Tools"),
                ],
            ),
            (
                "META & HARDWARE",
                [
                    ("lk", "LK Patch & Analysis"),
                    ("parts", "META Partitions"),
                    ("meta", "META Hardware Unlock"),
                ],
            ),
            (
                "RESOURCES",
                [
                    ("patch", "Patch Bundle"),
                    ("models", "Supported Models"),
                ],
            ),
        ]

        for cat_name, pages in categories:
            tk.Label(
                sidebar,
                text=cat_name,
                bg=C.SIDEBAR,
                fg=C.TEXT_DIM,
                font=(FONT, 7, "bold"),
                anchor="w",
                padx=14,
            ).pack(fill="x", pady=(10, 3))
            for key, label in pages:
                btn = NavButton(sidebar, label, lambda k=key: self._show_page(k))
                btn.pack(fill="x")
                self._nav[key] = btn

        # 2. Right Side: Shared Activity Logs Panel (Shared across all pages!)
        self._build_side_console(body)

        # 3. Center Container: Page Host + Toast Banner
        self.center_container = tk.Frame(body, bg=C.BG)
        self.center_container.pack(side="left", fill="both", expand=True)

        # Toast Banner (Packed at top of center container, above page host)
        self._build_toast_banner(self.center_container)

        self.page_host = tk.Frame(self.center_container, bg=C.BG_PAGE)
        self.page_host.pack(fill="both", expand=True, padx=12, pady=(8, 8))

        for key, _label, _icon in self.PAGES:
            page = ScrollPage(self.page_host, bg=C.BG_PAGE)
            page.grid(row=0, column=0, sticky="nsew")
            self._page_frames[key] = page
        self.page_host.rowconfigure(0, weight=1)
        self.page_host.columnconfigure(0, weight=1)

        # Build Page Views
        self._build_page_wizard(self._page_frames["wizard"].body)
        self._build_page_dashboard(self._page_frames["dashboard"].body)
        self._build_page_unlock(self._page_frames["unlock"].body)
        self._build_page_lk(self._page_frames["lk"].body)
        self._build_page_parts(self._page_frames["parts"].body)
        self._build_page_patch(self._page_frames["patch"].body)
        self._build_page_wipe(self._page_frames["wipe"].body)
        self._build_page_flash(self._page_frames["flash"].body)
        self._build_page_meta(self._page_frames["meta"].body)
        self._build_page_models(self._page_frames["models"].body)
        self._build_page_reboot(self._page_frames["reboot"].body)

    # -- Shared Right-Side Activity Logs Panel ----------------------------- #
    def _build_side_console(self, parent) -> None:
        """Constructs the dedicated, persistent right-side logs panel."""
        self.console_wrap = tk.Frame(
            parent,
            bg=C.SIDEBAR,
            width=330,
            highlightthickness=1,
            highlightbackground=C.BORDER,
        )
        self.console_wrap.pack(side="right", fill="y")
        self.console_wrap.pack_propagate(False)

        # 1. Header Bar
        head = tk.Frame(self.console_wrap, bg=C.SIDEBAR, height=44)
        head.pack(fill="x")
        head.pack_propagate(False)

        tk.Label(
            head,
            text="Activity Log",
            bg=C.SIDEBAR,
            fg=C.WHITE,
            font=(FONT, 10, "bold"),
            anchor="w",
        ).pack(side="left", padx=(12, 6))

        self.log_count_lbl = tk.Label(
            head,
            text="0 lines",
            bg=C.CARD_2,
            fg=C.ACCENT_LIGHT,
            font=(MONO, 8, "bold"),
            padx=6,
            pady=2,
            highlightthickness=1,
            highlightbackground=C.BORDER,
        )
        self.log_count_lbl.pack(side="left")

        # Collapse Button
        tk.Button(
            head,
            text="›",
            command=self._toggle_console,
            bg=C.SIDEBAR,
            fg=C.TEXT_MUTED,
            activebackground=C.CARD_2,
            activeforeground=C.WHITE,
            relief="flat",
            bd=0,
            font=(FONT, 10, "bold"),
            cursor="hand2",
            padx=8,
            pady=4,
        ).pack(side="right", padx=(0, 8))

        # 2. Action Toolbar
        toolbar = tk.Frame(self.console_wrap, bg=C.CARD_2, height=32, highlightthickness=1, highlightbackground=C.BORDER)
        toolbar.pack(fill="x", padx=8, pady=(0, 6))
        toolbar.pack_propagate(False)

        make_button(toolbar, "Clear", self._clear_console, "ghost", padx=6, pady=2, font_size=8).pack(side="left", padx=1)
        make_button(toolbar, "Copy", self._copy_console, "ghost", padx=6, pady=2, font_size=8).pack(side="left", padx=1)
        make_button(toolbar, "Save", self._save_log, "ghost", padx=6, pady=2, font_size=8).pack(side="left", padx=1)
        make_button(toolbar, "Logs Folder", self._open_logs_dir, "ghost", padx=6, pady=2, font_size=8).pack(side="left", padx=1)

        self.side_debug_btn = tk.Button(
            toolbar,
            text="Debug: ON",
            command=self._toggle_debug_mode,
            bg=C.CARD_2,
            fg=C.ACCENT_LIGHT,
            activebackground=C.CARD_HOVER,
            activeforeground=C.WHITE,
            relief="flat",
            bd=0,
            font=(FONT, 7, "bold"),
            cursor="hand2",
            padx=3,
        )
        self.side_debug_btn.pack(side="left", padx=1)

        self.autoscroll_btn = tk.Button(
            toolbar,
            text="Auto-scroll: ON",
            command=self._toggle_autoscroll,
            bg=C.CARD_2,
            fg=C.OK,
            activebackground=C.CARD_HOVER,
            activeforeground=C.WHITE,
            relief="flat",
            bd=0,
            font=(FONT, 7, "bold"),
            cursor="hand2",
            padx=4,
        )
        self.autoscroll_btn.pack(side="right", padx=2)

        # 3. Terminal Text Widget Holder
        self.console_holder = tk.Frame(self.console_wrap, bg=C.SIDEBAR)
        self.console_holder.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.console = tk.Text(
            self.console_holder,
            bg="#060910",
            fg=C.TEXT,
            bd=0,
            relief="flat",
            font=(MONO, 8),
            wrap="word",
            insertbackground=C.TEXT,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=C.BORDER,
        )
        vsb = ttk.Scrollbar(self.console_holder, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=vsb.set)
        self.console.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Color tags
        self.console.tag_configure("ok", foreground=C.OK)
        self.console.tag_configure("warn", foreground=C.WARN)
        self.console.tag_configure("err", foreground=C.DANGER)
        self.console.tag_configure("info", foreground=C.ACCENT_LIGHT)
        self.console.tag_configure("head", foreground=C.WHITE, font=(MONO, 8, "bold"))
        self.console.tag_configure("cmd", foreground=C.CYAN)
        self.console.tag_configure("debug", foreground=C.DEBUG_LIGHT, font=(MONO, 8))
        self.console.tag_configure("plain", foreground=C.TEXT)
        self.console.configure(state="disabled")

        # 4. Bottom Status Line
        bot = tk.Frame(self.console_wrap, bg=C.SIDEBAR, height=22)
        bot.pack(fill="x", padx=10, pady=(0, 6))
        bot.pack_propagate(False)

        tk.Label(
            bot,
            text="● Shared Activity Stream",
            bg=C.SIDEBAR,
            fg=C.TEXT_DIM,
            font=(FONT, 7),
            anchor="w",
        ).pack(side="left")

        self.side_debug_status = tk.Label(
            bot,
            text="DEBUG: ON",
            bg=C.SIDEBAR,
            fg=C.ACCENT_LIGHT,
            font=(FONT, 7, "bold"),
            anchor="e",
        )
        self.side_debug_status.pack(side="right")

        self._console_visible = True
        self._line_counter = 0

    def _toggle_debug_mode(self) -> None:
        """Toggles deep diagnostic telemetry capture to disk logs."""
        self.debug_mode = not self.debug_mode
        self._update_debug_ui()
        state = "ON" if self.debug_mode else "OFF"
        self._log_line(
            f"[*] Debug Mode switched {state}. Detailed operational telemetry {'recording to disk (logs/)' if self.debug_mode else 'paused'}.",
            "info",
        )
        if hasattr(self, "debug_logger"):
            self.debug_logger.log("SYSTEM", f"Debug mode toggled to {state} by user", "INFO")
        self.show_toast(
            "info" if self.debug_mode else "warning",
            f"Debug Mode is now {state}. Technical telemetry {'saving to logs/' if self.debug_mode else 'paused'}.",
        )

    def _update_debug_ui(self) -> None:
        """Synchronizes all Debug Mode buttons and status labels."""
        if self.debug_mode:
            if hasattr(self, "top_debug_btn"):
                self.top_debug_btn.configure(
                    text="DEBUG: ON",
                    bg=C.CARD_2,
                    fg=C.ACCENT_LIGHT,
                    activebackground=C.CARD_HOVER,
                    activeforeground=C.WHITE,
                    highlightbackground=C.BORDER_FOCUS,
                )
            if hasattr(self, "side_debug_btn"):
                self.side_debug_btn.configure(
                    text="Debug: ON",
                    fg=C.ACCENT_LIGHT,
                )
            if hasattr(self, "side_debug_status"):
                self.side_debug_status.configure(
                    text="DEBUG: ON",
                    fg=C.ACCENT_LIGHT,
                )
        else:
            if hasattr(self, "top_debug_btn"):
                self.top_debug_btn.configure(
                    text="DEBUG: OFF",
                    bg=C.SIDEBAR,
                    fg=C.TEXT_MUTED,
                    activebackground=C.CARD_2,
                    activeforeground=C.TEXT,
                    highlightbackground=C.BORDER,
                )
            if hasattr(self, "side_debug_btn"):
                self.side_debug_btn.configure(
                    text="Debug: OFF",
                    fg=C.TEXT_MUTED,
                )
            if hasattr(self, "side_debug_status"):
                self.side_debug_status.configure(
                    text="DEBUG: OFF",
                    fg=C.TEXT_DIM,
                )

    def _open_logs_dir(self) -> None:
        """Opens the persistent debug logs folder in Windows Explorer or OS file manager."""
        try:
            p = str(self.debug_logger.logs_dir.resolve())
            if sys.platform == "win32" and hasattr(os, "startfile"):
                os.startfile(p)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", p])
            self.show_toast("info", f"Opened logs folder: {Path(p).name}")
            self.debug_logger.log("UI", f"Opened logs directory in explorer: {p}", "INFO")
        except Exception as exc:
            self.show_toast("error", f"Could not open logs folder: {exc}")

    def _toggle_console(self) -> None:
        """Toggles the right-side shared logs panel."""
        if self._console_visible:
            self.console_wrap.pack_forget()
            self._console_visible = False
            self.top_log_btn.configure(text="Show Logs", bg=C.SIDEBAR, fg=C.TEXT_MUTED)
        else:
            self.console_wrap.pack(side="right", fill="y", before=self.center_container)
            self._console_visible = True
            self.top_log_btn.configure(text="Hide Logs", bg=C.CARD_2, fg=C.ACCENT_LIGHT)

    def _toggle_autoscroll(self) -> None:
        self._auto_scroll_enabled = not self._auto_scroll_enabled
        if self._auto_scroll_enabled:
            self.autoscroll_btn.configure(text="Auto-scroll: ON", fg=C.OK)
            self.console.see("end")
        else:
            self.autoscroll_btn.configure(text="Auto-scroll: OFF", fg=C.TEXT_MUTED)

    def _build_toast_banner(self, parent) -> None:
        """Top alert banner for real-time feedback (success, warning, error)."""
        self.toast_frame = tk.Frame(parent, bg=C.CARD_2, highlightthickness=1, highlightbackground=C.BORDER)

        self.toast_icon = tk.Label(self.toast_frame, text="ℹ", bg=C.CARD_2, fg=C.ACCENT_LIGHT, font=(FONT, 11, "bold"))
        self.toast_icon.pack(side="left", padx=(14, 8), pady=6)

        self.toast_text = tk.Label(
            self.toast_frame,
            text="",
            bg=C.CARD_2,
            fg=C.TEXT,
            font=(FONT, 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.toast_text.pack(side="left", fill="x", expand=True, pady=6)

        self.toast_action_btn = tk.Button(
            self.toast_frame,
            text="",
            command=lambda: None,
            bg=C.ACCENT,
            fg=C.WHITE,
            activebackground=C.ACCENT_H,
            activeforeground=C.WHITE,
            relief="flat",
            bd=0,
            font=(FONT, 8, "bold"),
            padx=10,
            pady=3,
            cursor="hand2",
        )

        tk.Button(
            self.toast_frame,
            text="✕",
            command=self._hide_toast,
            bg=C.CARD_2,
            fg=C.TEXT_MUTED,
            activebackground=C.CARD_2,
            activeforeground=C.WHITE,
            relief="flat",
            bd=0,
            font=(FONT, 9, "bold"),
            cursor="hand2",
            padx=10,
        ).pack(side="right", padx=(4, 8))

    def show_toast(
        self,
        kind: str,
        message: str,
        action_text: str = "",
        action_cmd: Callable | None = None,
        duration_ms: int = 7000,
    ) -> None:
        """Display an actionable feedback banner directly above the active page."""
        colors = {
            "success": (C.OK_BG, C.OK, "✔"),
            "error": (C.DANGER_BG, C.DANGER, "✖"),
            "warning": (C.WARN_BG, C.WARN, "⚠"),
            "info": (C.CARD_2, C.ACCENT_LIGHT, "ℹ"),
        }
        bg, fg, glyph = colors.get(kind, colors["info"])

        self.toast_frame.configure(bg=bg, highlightbackground=fg)
        self.toast_icon.configure(bg=bg, fg=fg, text=glyph)
        self.toast_text.configure(bg=bg, fg=C.WHITE, text=message)

        if action_text and callable(action_cmd):
            self.toast_action_btn.configure(
                text=action_text,
                command=lambda: (action_cmd(), self._hide_toast()),
                bg=fg,
                activebackground=C.CARD_HOVER,
            )
            self.toast_action_btn.pack(side="right", padx=6)
        else:
            self.toast_action_btn.pack_forget()

        self.toast_frame.pack(fill="x", side="top", padx=12, pady=(6, 4), before=self.page_host)

        if duration_ms > 0 and kind != "error":
            self._schedule(duration_ms, self._hide_toast)

    def _hide_toast(self) -> None:
        self.toast_frame.pack_forget()

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=C.SIDEBAR, height=26, highlightthickness=1, highlightbackground=C.BORDER)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.status = tk.Label(bar, text="Ready", bg=C.SIDEBAR, fg=C.TEXT_MUTED, font=(FONT, 8), anchor="w", padx=14)
        self.status.pack(side="left", fill="y")

        credit = tk.Label(
            bar,
            text=f"© {branding.COPYRIGHT_YEARS} {AGENCY}  ·  tfastdigital.com",
            bg=C.SIDEBAR,
            fg=C.TEXT_DIM,
            font=(FONT, 8),
            anchor="e",
            padx=14,
            cursor="hand2",
        )
        credit.pack(side="right", fill="y")
        credit.bind("<Button-1>", lambda e: self._open_url(branding.URL_WEBSITE))
        credit.bind("<Enter>", lambda e: credit.configure(fg=C.ACCENT_LIGHT))
        credit.bind("<Leave>", lambda e: credit.configure(fg=C.TEXT_DIM))

    # -- Page Header Helper ------------------------------------------------ #
    def _page_header(self, parent, title: str, subtitle: str | None = None, icon: str = ""):
        hdr = tk.Frame(parent, bg=C.BG_PAGE)
        hdr.pack(fill="x", pady=(0, 8))

        title_row = tk.Frame(hdr, bg=C.BG_PAGE)
        title_row.pack(fill="x")
        if icon:
            tk.Label(title_row, text=icon, bg=C.BG_PAGE, fg=C.ACCENT_LIGHT, font=(FONT, 14, "bold")).pack(
                side="left", padx=(0, 6)
            )
        tk.Label(title_row, text=title, bg=C.BG_PAGE, fg=C.WHITE, font=(FONT, 14, "bold"), anchor="w").pack(
            side="left", fill="x", expand=True
        )

        if subtitle:
            lbl = tk.Label(
                hdr,
                text=subtitle,
                bg=C.BG_PAGE,
                fg=C.TEXT_MUTED,
                font=(FONT, 9),
                anchor="w",
                justify="left",
                wraplength=620,
            )
            lbl.pack(fill="x", pady=(2, 2))
            autowrap(lbl, hdr, pad=20)

    # ---------------------------------------------------------------------- #
    # PAGE 1: GUIDED UNLOCK WIZARD (The All-In-One Foolproof Flow)
    # ---------------------------------------------------------------------- #
    def _build_page_wizard(self, parent) -> None:
        self._page_header(
            parent,
            "Guided Unlock Wizard",
            "Foolproof step-by-step pipeline for MediaTek and Transsion devices: auto-detects hardware, "
            "selects verified LK stages, runs the FENIX FRP handshake, unlocks bootloader, and wipes anti-tamper overlays.",
        )

        # Stage Progress Stepper
        step_box = tk.Frame(parent, bg=C.CARD, highlightthickness=1, highlightbackground=C.BORDER, padx=12, pady=8)
        step_box.pack(fill="x", pady=(0, 10))

        self.w_steps = []
        step_labels = [
            ("1. Connect Phone", "Fastboot Link"),
            ("2. Target Model", "Verified LK"),
            ("3. Execute Unlock", "Pipeline"),
            ("4. Anti-Tamper Wipe", "Clean Overlays"),
            ("5. Reboot System", "Finished"),
        ]
        step_row = tk.Frame(step_box, bg=C.CARD)
        step_row.pack(fill="x")

        for i, (stitle, ssub) in enumerate(step_labels):
            sf = tk.Frame(step_row, bg=C.CARD)
            sf.pack(side="left", fill="x", expand=True)

            num_lbl = tk.Label(
                sf,
                text=f" {i+1} ",
                bg=C.CARD_2,
                fg=C.TEXT_MUTED,
                font=(FONT, 8, "bold"),
                highlightthickness=1,
                highlightbackground=C.BORDER,
                padx=2,
            )
            num_lbl.pack(side="left", padx=(0, 5))

            txt_f = tk.Frame(sf, bg=C.CARD)
            txt_f.pack(side="left")
            t_lbl = tk.Label(txt_f, text=stitle, bg=C.CARD, fg=C.TEXT, font=(FONT, 8, "bold"), anchor="w")
            t_lbl.pack(anchor="w")
            sub_lbl = tk.Label(txt_f, text=ssub, bg=C.CARD, fg=C.TEXT_DIM, font=(FONT, 7), anchor="w")
            sub_lbl.pack(anchor="w")

            if i < len(step_labels) - 1:
                tk.Label(sf, text="→", bg=C.CARD, fg=C.BORDER, font=(FONT, 9)).pack(side="right", padx=2)

            self.w_steps.append((num_lbl, t_lbl, sub_lbl))

        # Card 1: Device Pre-Flight Check
        c1, in1 = card(
            parent,
            "Stage 1: Device Pre-Flight Verification",
            "Checks live USB communication and fastboot bootloader status.",
        )
        c1.pack(fill="x", pady=(0, 10))

        self.w_dev_status = kv_row(in1, "Hardware Link", "Checking…")
        self.w_dev_slot = kv_row(in1, "Active Slot", "--")
        self.w_dev_lock = kv_row(in1, "Lock Status", "--")
        self.w_dev_chip = kv_row(in1, "Detected Model", "--")

        w_btn_row = tk.Frame(in1, bg=C.CARD)
        w_btn_row.pack(fill="x", pady=(8, 0))
        make_button(w_btn_row, "Probe Device (F5)", lambda: self._probe(force_log=True), "ghost", self._action_buttons).pack(side="left")
        make_button(w_btn_row, "Reboot to Bootloader", lambda: self._quick_reboot("bootloader"), "ghost", self._action_buttons).pack(
            side="left", padx=6
        )

        note(
            in1,
            "Tip: Turn phone OFF completely. Hold Volume Down (or Vol Down + Power) and plug in USB "
            "until Fastboot mode appears on screen.",
            wrap=620,
        ).pack(fill="x", pady=(8, 0))

        # Card 2: Target Model Selection with Instant Search
        c2, in2 = card(
            parent,
            "Stage 2: Model & Patched Binary Selection",
            "Type your model or codename to filter the verified offline catalog instantly.",
        )
        c2.pack(fill="x", pady=(0, 10))

        sel_row = tk.Frame(in2, bg=C.CARD)
        sel_row.pack(fill="x", pady=(0, 6))

        tk.Label(sel_row, text="Filter:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=7, anchor="w").pack(side="left")
        self.w_model_filter = tk.StringVar()
        self.w_model_filter.trace_add("write", lambda *_: self._filter_wizard_models())
        w_entry = entry(sel_row, self.w_model_filter, width=22)
        w_entry.pack(side="left", padx=(0, 8))

        tk.Label(sel_row, text="Target:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=7, anchor="w").pack(side="left")
        self.w_model_combo = ttk.Combobox(sel_row, state="readonly", font=(FONT, 9))
        self.w_model_combo.pack(side="left", fill="x", expand=True)
        self.w_model_combo.bind("<<ComboboxSelected>>", self._on_wizard_model_selected)

        self.w_model_info = tk.Label(
            in2, text="Select a model to view offline binary readiness.", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9)
        )
        self.w_model_info.pack(anchor="w", pady=(2, 4))

        # Card 3: Execute Unlock Pipeline
        c3, in3 = card(
            parent,
            "Stage 3: Automated Unlock Execution",
            "Flashes verified LK stages, zeroes FRP flags, and executes the unlock handshake.",
        )
        c3.pack(fill="x", pady=(0, 10))

        self.w_reboot_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            in3,
            text="Keep device in fastboot mode after unlock (Recommended: allows immediate Guard Wipe)",
            variable=self.w_reboot_var,
        ).pack(anchor="w", pady=(0, 6))

        w_exec_btn = make_button(
            in3,
            "Execute Unlock Pipeline",
            self._do_wizard_unlock,
            "danger",
            self._action_buttons,
            padx=18,
            pady=8,
        )
        w_exec_btn.pack(fill="x")

        # Card 4: Post-Unlock Guard Wipe
        c4, in4 = card(
            parent,
            "Stage 4: OEM Anti-Tamper Guard Wipe",
            "Neutralizes Transsion guard overlays (tr_product, tr_vendor, tr_system) to eliminate red-state panics and bootloops.",
        )
        c4.pack(fill="x", pady=(0, 10))

        self.w_wipe_status = kv_row(in4, "Prerequisite", "Bootloader must be unlocked")
        make_button(
            in4,
            "Wipe Guard Partitions",
            self._do_wipe,
            "accent",
            self._action_buttons,
            padx=16,
            pady=7,
        ).pack(anchor="w", pady=(6, 0))

        # Card 5: Finish & Reboot
        c5, in5 = card(parent, "Stage 5: Final Reboot", "Return the device to normal system mode.")
        c5.pack(fill="x")
        r_row = tk.Frame(in5, bg=C.CARD)
        r_row.pack(fill="x")
        make_button(r_row, "Normal Reboot (System)", lambda: self._quick_reboot("system"), "ok", self._action_buttons).pack(
            side="left"
        )
        make_button(r_row, "Reboot to Recovery", lambda: self._quick_reboot("recovery"), "ghost", self._action_buttons).pack(
            side="left", padx=8
        )

    # ---------------------------------------------------------------------- #
    # PAGE 2: DASHBOARD
    # ---------------------------------------------------------------------- #
    def _build_page_dashboard(self, parent) -> None:
        self._page_header(
            parent,
            "Hardware Dashboard",
            "Real-time device snapshot, partition table inspection, and local environment readiness.",
        )

        dev_card, dev_in = card(
            parent, "Device Status & Hardware Registers", "Read directly from fastboot getvar probe."
        )
        dev_card.pack(fill="x", pady=(0, 10))

        self.d_conn = kv_row(dev_in, "Connection Link", "checking…")
        self.d_serial = kv_row(dev_in, "Serial Number", "--", mono=True)
        self.d_mode = kv_row(dev_in, "Fastboot Mode", "--")
        self.d_slot = kv_row(dev_in, "Active Slot", "--", mono=True)
        self.d_lock = kv_row(dev_in, "Bootloader Lock", "--")
        self.d_parts = kv_row(dev_in, "Reported Partitions", "--")
        self.d_guards = kv_row(dev_in, "Guard Overlays", "--")
        self.d_keys = kv_row(dev_in, "Core Boot Partitions", "--")

        row = tk.Frame(dev_in, bg=C.CARD)
        row.pack(fill="x", pady=(10, 0))
        make_button(row, "Refresh Status (F5)", lambda: self._probe(force_log=True), "accent", self._action_buttons).pack(side="left")
        make_button(row, "Copy Device Info", self._copy_device_info, "ghost", self._action_buttons).pack(
            side="left", padx=6
        )
        make_button(row, "Reboot System", lambda: self._quick_reboot("system"), "ghost", self._action_buttons).pack(
            side="left", padx=6
        )
        make_button(row, "Fastbootd", lambda: self._quick_reboot("fastboot"), "ghost", self._action_buttons).pack(
            side="left"
        )

        env_card, env_in = card(
            parent, "Environment & Offline Repository", "Local binary assets and embedded protocol engines."
        )
        env_card.pack(fill="x", pady=(0, 10))

        self.r_fastboot = kv_row(env_in, "fastboot.exe", "--")
        self.r_offline = kv_row(env_in, "Offline LK Binaries", "--")
        self.r_meta = kv_row(env_in, "META Protocol Engine", "--")
        self.r_exploit = kv_row(env_in, "META Exploit Engine", "--")
        self.r_py314 = kv_row(env_in, "Python 3.14 Runtime", "--")
        self.r_ws = kv_row(env_in, "Workspace Directory", "--")

        row2 = tk.Frame(env_in, bg=C.CARD)
        row2.pack(fill="x", pady=(10, 0))
        make_button(row2, "Refresh Readiness", self._refresh_readiness, "ghost", self._action_buttons).pack(side="left")
        make_button(row2, "Open Workspace Folder", self._open_workspace, "ghost", self._action_buttons).pack(
            side="left", padx=6
        )

        act_card, act_in = card(parent, "Quick Navigation Shortcuts")
        act_card.pack(fill="x")
        qrow = tk.Frame(act_in, bg=C.CARD)
        qrow.pack(fill="x")
        make_button(qrow, "Guided Wizard", lambda: self._show_page("wizard"), "accent").pack(side="left")
        make_button(qrow, "Unlock Pipeline", lambda: self._show_page("unlock"), "ghost").pack(side="left", padx=6)
        make_button(qrow, "Guard Wipe", lambda: self._show_page("wipe"), "ghost").pack(side="left")
        make_button(qrow, "LK Analysis", lambda: self._show_page("lk"), "ghost").pack(side="left", padx=6)
        make_button(qrow, "META Partitions", lambda: self._show_page("parts"), "ghost").pack(side="left")

    # ---------------------------------------------------------------------- #
    # PAGE 3: UNLOCK
    # ---------------------------------------------------------------------- #
    def _build_page_unlock(self, parent) -> None:
        self._page_header(
            parent,
            "Automated Bootloader Unlock",
            "Executes slot detection, LK stage patching, VBMeta flag modification (--flags 3), "
            "FENIX FRP clearance, and automated META fallback.",
        )

        cfg_card, cfg = card(parent, "Target Configuration")
        cfg_card.pack(fill="x", pady=(0, 10))

        # Search filter and combobox row
        m_row = tk.Frame(cfg, bg=C.CARD)
        m_row.pack(fill="x", pady=(0, 6))

        tk.Label(m_row, text="Filter:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=7, anchor="w").pack(side="left")
        self.unlock_filter = tk.StringVar()
        self.unlock_filter.trace_add("write", lambda *_: self._filter_unlock_models())
        entry(m_row, self.unlock_filter, width=22).pack(side="left", padx=(0, 8))

        tk.Label(m_row, text="Target Model:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=12, anchor="w").pack(side="left")
        self.unlock_model = ttk.Combobox(m_row, state="readonly", font=(FONT, 9))
        self.unlock_model.pack(side="left", fill="x", expand=True)

        tk.Label(cfg, text="Original vbmeta.img (optional — leave empty for offline auto-patch)", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(fill="x", pady=(4, 0))
        vbrow = tk.Frame(cfg, bg=C.CARD)
        vbrow.pack(fill="x", pady=(3, 8))
        self.unlock_vbmeta = tk.StringVar()
        entry(vbrow, self.unlock_vbmeta).pack(side="left", fill="x", expand=True)
        make_button(vbrow, "Browse", lambda: self._pick(self.unlock_vbmeta), "ghost").pack(side="left", padx=(6, 0))

        self.unlock_reboot = tk.BooleanVar(value=True)
        self.unlock_skip_meta = tk.BooleanVar(value=False)
        ttk.Checkbutton(cfg, text="Reboot the device when the pipeline finishes", variable=self.unlock_reboot).pack(
            anchor="w", pady=1
        )
        ttk.Checkbutton(cfg, text="Skip the automatic META fallback (flash attempts only)", variable=self.unlock_skip_meta).pack(
            anchor="w"
        )

        run_card, run = card(parent, "Execution Pipeline")
        run_card.pack(fill="x", pady=(0, 10))

        steps = [
            "1. Detect active slot (_a or _b)",
            "2. Acquire verified Little Kernel stages from offline catalog",
            "3. Patch VBMeta flags (--disable-verity --disable-verification)",
            "4. Execute FENIX FRP clear + unlock handshake",
            "5. Flash patched LK binaries to active slot",
            "6. Fall back to Preloader/META seccfg clear if lock-control gates fastboot",
        ]
        for s in steps:
            tk.Label(run, text=f"  {s}", bg=C.CARD, fg=C.TEXT, font=(FONT, 8), anchor="w").pack(fill="x", pady=1)

        tk.Frame(run, bg=C.BORDER, height=1).pack(fill="x", pady=8)

        note(
            run,
            "Device screen prompt: When the phone displays 'Unlock bootloader?', press VOLUME UP to confirm.",
            C.WARN,
            kind="warn",
        ).pack(fill="x", pady=(0, 8))

        make_button(run, "Run Full Unlock Pipeline", self._do_unlock, "danger", self._action_buttons).pack(fill="x")
        make_button(run, "Fastboot Handshake Only (FRP + Unlock)", self._do_handshake, "ghost", self._action_buttons).pack(
            fill="x", pady=(6, 0)
        )
        make_button(run, "Send `fastboot flashing unlock`", self._do_flashing_unlock, "ghost", self._action_buttons).pack(
            fill="x", pady=(6, 0)
        )

    # ---------------------------------------------------------------------- #
    # PAGE 4: LK ANALYSIS & IN-PLACE PATCH
    # ---------------------------------------------------------------------- #
    def _build_page_lk(self, parent) -> None:
        self._page_header(
            parent,
            "Little Kernel (LK) In-Place Analyzer",
            "Analyzes raw device Little Kernel images, matches against documented Transsion profiles, "
            "locates the lock-state getter stub, and applies the 4-byte unlock patch directly without changing file size.",
        )

        pick_card, pick = card(parent, "1. Target Image Source")
        pick_card.pack(fill="x", pady=(0, 10))

        note(
            pick,
            "Always patch an image dumped from THIS physical device (via mtkclient or the 'Read from device' button). "
            "Flashing foreign LK binaries from mismatched firmware revisions is the primary cause of bricking.",
            wrap=620,
        ).pack(fill="x", pady=(0, 8))

        prow = tk.Frame(pick, bg=C.CARD)
        prow.pack(fill="x", pady=(0, 6))
        self.lk_image_path = tk.StringVar()
        entry(prow, self.lk_image_path).pack(side="left", fill="x", expand=True)
        make_button(prow, "Browse", lambda: self._pick(self.lk_image_path), "ghost").pack(side="left", padx=(6, 0))

        brow = tk.Frame(pick, bg=C.CARD)
        brow.pack(fill="x")
        make_button(brow, "Read from Device (Fastboot)", self._do_lk_acquire, "ghost", self._action_buttons).pack(
            side="left"
        )
        make_button(brow, "Analyze Binary", self._do_lk_analyze, "accent", self._action_buttons).pack(
            side="left", padx=6
        )

        res_card, res = card(parent, "2. Binary Analysis Result")
        res_card.pack(fill="x", pady=(0, 10))
        self.lk_state = kv_row(res, "Lock State", "--")
        self.lk_arch = kv_row(res, "Architecture", "--")
        self.lk_profile = kv_row(res, "Matched Profile", "--")
        self.lk_sites = kv_row(res, "Lock-state Sites", "--")
        self.lk_verdict = kv_row(res, "Patchable Verdict", "--")

        patch_card, patch = card(parent, "3. Apply In-Place Patch")
        patch_card.pack(fill="x", pady=(0, 10))

        vrow = tk.Frame(patch, bg=C.CARD)
        vrow.pack(fill="x", pady=(0, 8))
        tk.Label(vrow, text="Patch Value:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=18, anchor="w").pack(
            side="left"
        )
        self.lk_value = tk.StringVar(value="3")
        for val, label in (
            ("3", "3 — LKS_UNLOCK (recommended)"),
            ("1", "1 — LKS_DEFAULT"),
            ("0", "0 — Force Zero"),
        ):
            ttk.Radiobutton(vrow, text=label, value=val, variable=self.lk_value).pack(side="left", padx=(0, 14))

        crow = tk.Frame(patch, bg=C.CARD)
        crow.pack(fill="x", pady=(0, 8))
        self.lk_write_back = tk.BooleanVar(value=False)
        ttk.Checkbutton(crow, text="Flash the patched image directly back to device (lk_a)", variable=self.lk_write_back).pack(
            anchor="w"
        )

        arow = tk.Frame(patch, bg=C.CARD)
        arow.pack(fill="x")
        make_button(arow, "Dry Run (Verify Only)", self._do_lk_patch_dry, "ghost", self._action_buttons).pack(side="left")
        make_button(arow, "Apply Patch In Place", self._do_lk_patch, "danger", self._action_buttons).pack(
            side="left", padx=6
        )

    # ---------------------------------------------------------------------- #
    # PAGE 5: META PARTITION MANAGER
    # ---------------------------------------------------------------------- #
    def _build_page_parts(self, parent) -> None:
        self._page_header(
            parent,
            "META Partition Manager",
            "Direct read, backup, restore, verify, and wipe access over the MediaTek Preloader / BootROM serial link. "
            "All transfers use chunked base64 dd with cryptographic hash re-verification.",
        )

        conn_card, conn = card(parent, "1. META Connection & Session")
        conn_card.pack(fill="x", pady=(0, 10))

        prow = tk.Frame(conn, bg=C.CARD)
        prow.pack(fill="x", pady=(0, 8))
        tk.Label(prow, text="Target Port:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=10, anchor="w").pack(side="left")
        self.parts_meta_port = ttk.Combobox(prow, state="readonly", font=(FONT, 9), width=28)
        self.parts_meta_port.pack(side="left", padx=(0, 6))
        make_button(prow, "Scan Ports", self._scan_ports, "ghost").pack(side="left")

        crow = tk.Frame(conn, bg=C.CARD)
        crow.pack(fill="x")
        make_button(crow, "Connect META Port", self._do_meta_connect, "accent", self._action_buttons).pack(side="left")
        make_button(crow, "Reboot to META (Fastboot)", self._do_reboot_to_meta, "ghost", self._action_buttons).pack(side="left", padx=6)
        make_button(crow, "Refresh Table", self._do_parts_refresh, "ghost", self._action_buttons).pack(side="left", padx=(0, 6))
        make_button(crow, "Disconnect", self._do_meta_disconnect, "ghost").pack(side="left")

        self.parts_status = kv_row(conn, "Active Session", "not connected")

        note(
            conn,
            "To connect: Turn phone OFF completely. Hold Volume Down (or Vol Down + Power) and plug in USB.",
            C.TEXT_MUTED,
            kind="info",
            wrap=640,
        ).pack(fill="x", pady=(6, 0))

        # Partition Table Explorer with Real-time Search Filter
        tbl_card, tbl = card(parent, "2. Partition Explorer")
        tbl_card.pack(fill="both", expand=True, pady=(0, 10))

        # Real-time search filter bar
        filter_bar = tk.Frame(tbl, bg=C.CARD)
        filter_bar.pack(fill="x", pady=(0, 8))
        tk.Label(filter_bar, text="Filter:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=7, anchor="w").pack(
            side="left"
        )
        self.parts_filter = tk.StringVar()
        self.parts_filter.trace_add("write", lambda *_: self._filter_parts_tree())
        entry(filter_bar, self.parts_filter, width=22).pack(side="left", padx=(0, 8))

        # Quick preset selection buttons
        make_button(filter_bar, "Critical", self._select_critical_parts, "ghost", padx=8, pady=2, font_size=8).pack(
            side="left", padx=2
        )
        make_button(filter_bar, "Guards", self._select_guard_parts, "ghost", padx=8, pady=2, font_size=8).pack(
            side="left", padx=2
        )
        make_button(filter_bar, "Safe", self._do_part_select_safe, "ghost", padx=8, pady=2, font_size=8).pack(
            side="left", padx=2
        )
        make_button(filter_bar, "All", self._do_part_select_all, "ghost", padx=8, pady=2, font_size=8).pack(
            side="left", padx=2
        )
        make_button(filter_bar, "Clear", self._do_part_clear_sel, "ghost", padx=8, pady=2, font_size=8).pack(
            side="left", padx=2
        )

        # Treeview
        self.parts_tree = ttk.Treeview(
            tbl,
            columns=("name", "size", "source", "prot"),
            show="headings",
            height=8,
            selectmode="extended",
        )
        for col, label, width, anchor in (
            ("name", "Partition Name", 220, "w"),
            ("size", "Size (Bytes / Human)", 120, "e"),
            ("source", "Detection Source", 140, "w"),
            ("prot", "Protection State", 110, "w"),
        ):
            self.parts_tree.heading(col, text=label)
            self.parts_tree.column(col, width=width, minwidth=70, anchor=anchor, stretch=True)
        self.parts_tree.pack(fill="both", expand=True)
        self.parts_tree.bind("<<TreeviewSelect>>", self._on_part_selected)

        self.parts_selinfo = tk.Label(
            tbl,
            text="0 selected  (Connect in META mode or click 'Refresh Table' to populate)",
            bg=C.CARD,
            fg=C.TEXT_MUTED,
            font=(FONT, 8),
            anchor="w",
        )
        self.parts_selinfo.pack(fill="x", pady=(4, 0))

        # Operations
        act_card, act = card(parent, "3. Partition Operations")
        act_card.pack(fill="x", pady=(0, 10))

        self.part_sel = kv_row(act, "Target Partition(s)", "(none)", val_color=C.ACCENT_LIGHT)

        frow = tk.Frame(act, bg=C.CARD)
        frow.pack(fill="x", pady=(4, 6))
        tk.Label(frow, text="File / Output Folder:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=18, anchor="w").pack(
            side="left"
        )
        self.part_file = tk.StringVar()
        entry(frow, self.part_file).pack(side="left", fill="x", expand=True)
        make_button(frow, "File", lambda: self._pick(self.part_file), "ghost").pack(side="left", padx=(6, 2))
        make_button(frow, "Folder", self._pick_folder, "ghost").pack(side="left", padx=2)
        make_button(frow, "Open Folder", self._open_part_folder, "ghost").pack(side="left", padx=2)

        optrow = tk.Frame(act, bg=C.CARD)
        optrow.pack(fill="x", pady=(0, 6))
        tk.Label(optrow, text="Transfer Speed:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=18, anchor="w").pack(
            side="left"
        )
        self.parts_speed = tk.StringVar(value="fast")
        for name in ("safe", "balanced", "fast", "turbo"):
            ttk.Radiobutton(optrow, text=name.title(), value=name, variable=self.parts_speed).pack(side="left", padx=(0, 12))
        make_button(optrow, "Measure Benchmark", self._do_part_bench, "ghost").pack(side="left", padx=(8, 0))

        self.part_force = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            act,
            text="Override protection on critical partitions (preloader, pgpt, nvram, seccfg)",
            variable=self.part_force,
        ).pack(anchor="w", pady=(0, 6))

        wrow = tk.Frame(act, bg=C.CARD)
        wrow.pack(fill="x", pady=(0, 8))
        tk.Label(wrow, text="Wipe Algorithm:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=18, anchor="w").pack(
            side="left"
        )
        self.wipe_mode = tk.StringVar(value="filesystem")
        for value, label in (
            ("filesystem", "Filesystem (Head + Tail 1MB)"),
            ("head", "Head Only"),
            ("full", "Full Raw Zero-Fill"),
        ):
            ttk.Radiobutton(wrow, text=label, value=value, variable=self.wipe_mode).pack(side="left", padx=(0, 10))
        make_button(wrow, "Probe Signature", self._do_part_probe, "ghost").pack(side="left", padx=(6, 0))

        brow = tk.Frame(act, bg=C.CARD)
        brow.pack(fill="x")
        make_button(brow, "Export (Dump)", self._do_part_export, "accent", self._action_buttons).pack(side="left")
        make_button(brow, "Back Up", self._do_part_backup, "accent", self._action_buttons).pack(side="left", padx=6)
        make_button(brow, "Replace (Write)", self._do_part_replace, "danger", self._action_buttons).pack(side="left")
        make_button(brow, "Restore", self._do_part_restore, "danger", self._action_buttons).pack(side="left", padx=6)
        make_button(brow, "Verify", self._do_part_verify, "ghost", self._action_buttons).pack(side="left")
        make_button(brow, "Wipe Partition", self._do_part_wipe, "danger", self._action_buttons).pack(
            side="left", padx=6
        )

    # ---------------------------------------------------------------------- #
    # PAGE 6: GUARD WIPE
    # ---------------------------------------------------------------------- #
    def _build_page_wipe(self, parent) -> None:
        self._page_header(
            parent,
            "OEM Anti-Tamper Guard Wipe",
            "Cleans Transsion overlay partitions (tr_product, tr_vendor, tr_system) that trigger bootloops "
            "and re-arm verification after bootloader unlock. Mirrors CLI `wipe-trash`.",
        )

        gate_card, gate = card(parent, "Precondition: Unlocked Bootloader")
        gate_card.pack(fill="x", pady=(0, 10))

        note(
            gate,
            "Stock MTK Little Kernel gates partition writes behind lock control. This operation queries "
            "getvar first and will refuse to execute unless the device reports `unlocked: yes`.",
            wrap=620,
        ).pack(fill="x")
        self.wipe_lock_state = kv_row(gate, "Bootloader Verification", "not checked")

        wrap, inner = card(parent, "Partitions Targeted for Wipe")
        wrap.pack(fill="x", pady=(0, 10))

        chips = tk.Frame(inner, bg=C.CARD)
        chips.pack(fill="x", pady=(0, 8))
        for name in config.TRASH_PARTITIONS:
            chip(chips, name, bg=C.CARD_2, fg=C.TEXT).pack(side="left", padx=(0, 8))

        chips2 = tk.Frame(inner, bg=C.CARD)
        chips2.pack(fill="x", pady=(0, 12))
        for name in config.EXTRA_SYSTEM_PARTITIONS:
            chip(chips2, name, bg=C.WARN_BG, fg=C.WARN, border=C.WARN_BORDER).pack(side="left", padx=(0, 8))

        self.wipe_include_system = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            inner,
            text="Also erase product and system_ext (Required post-unlock to purge guard overlays)",
            variable=self.wipe_include_system,
        ).pack(anchor="w")

        note(
            inner,
            "Clearing product / system_ext requires re-flashing clean firmware or GSI afterwards. "
            "Untick to erase only the tr_* overlays.",
            C.WARN,
            kind="warn",
            wrap=620,
        ).pack(fill="x", pady=(4, 12))

        make_button(inner, "Wipe OEM Guard Partitions Now", self._do_wipe, "danger", self._action_buttons).pack(anchor="w")

        det, det_in = card(parent, "Detected Overlays on Active Device")
        det.pack(fill="x")
        self.wipe_detected = kv_row(det_in, "Active Overlays", "--")
        make_button(det_in, "Re-Scan Device", self._probe, "ghost", self._action_buttons).pack(anchor="w", pady=(10, 0))

    # ---------------------------------------------------------------------- #
    # PAGE 7: FLASH CUSTOM
    # ---------------------------------------------------------------------- #
    def _build_page_flash(self, parent) -> None:
        self._page_header(
            parent,
            "Flash Custom Firmware",
            "Slot-aware flashing of vbmeta.img (with verification disabled) and optional custom system/GSI images.",
        )

        wrap, inner = card(parent, "Target Images")
        wrap.pack(fill="x", pady=(0, 10))

        tk.Label(inner, text="vbmeta.img (AVB disabled)", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(
            fill="x"
        )
        r1 = tk.Frame(inner, bg=C.CARD)
        r1.pack(fill="x", pady=(4, 12))
        self.flash_vbmeta = tk.StringVar()
        entry(r1, self.flash_vbmeta).pack(side="left", fill="x", expand=True)
        make_button(r1, "Browse", lambda: self._pick(self.flash_vbmeta), "ghost").pack(side="left", padx=(6, 0))

        tk.Label(inner, text="custom system image (optional)", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(
            fill="x"
        )
        r2 = tk.Frame(inner, bg=C.CARD)
        r2.pack(fill="x", pady=(4, 12))
        self.flash_system = tk.StringVar()
        entry(r2, self.flash_system).pack(side="left", fill="x", expand=True)
        make_button(r2, "Browse", lambda: self._pick(self.flash_system), "ghost").pack(side="left", padx=(6, 0))

        self.flash_reboot = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Reboot device automatically when flashing finishes", variable=self.flash_reboot).pack(
            anchor="w", pady=(0, 12)
        )

        make_button(inner, "Flash Images to Active Slot", self._do_flash, "danger", self._action_buttons).pack(anchor="w")

        warn, warn_in = card(parent, "Safety Advisory")
        warn.pack(fill="x")
        note(
            warn_in,
            "Flashing vbmeta with flags disabled removes Android Verified Boot 2.0 enforcement. "
            "Ensure the image matches your device build exactly.",
            C.WARN,
            kind="warn",
            wrap=620,
        ).pack(fill="x")

    # ---------------------------------------------------------------------- #
    # PAGE 8: META MODE HARDWARE UNLOCK
    # ---------------------------------------------------------------------- #
    def _build_page_meta(self, parent) -> None:
        self._page_header(
            parent,
            "Hardware META Mode Unlock",
            "Direct Preloader / BootROM serial communication to clear the hardware seccfg lock in NVRAM. "
            "Used when fastboot writes are strictly rejected by OEM lock-control.",
        )

        port_card, port = card(parent, "Preloader Serial Connection")
        port_card.pack(fill="x", pady=(0, 10))

        tk.Label(port, text="Serial COM Port:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(fill="x")
        prow = tk.Frame(port, bg=C.CARD)
        prow.pack(fill="x", pady=(4, 12))
        self.meta_port = ttk.Combobox(prow, state="readonly", font=(FONT, 9))
        self.meta_port.pack(side="left", fill="x", expand=True)
        make_button(prow, "Scan Ports", self._scan_ports, "ghost").pack(side="left", padx=(6, 0))

        self.meta_engine = kv_row(port, "META Engine", "--")
        self.meta_py314 = kv_row(port, "Python 3.14 Runtime", "--")

        make_button(port, "Execute Hardware META Unlock", self._do_meta, "danger", self._action_buttons).pack(
            anchor="w", pady=(12, 0)
        )

        steps_card, steps = card(parent, "How to Enter MTK Preloader Mode")
        steps_card.pack(fill="x")
        steps_text = [
            "1. Unplug the USB cable from the phone completely.",
            "2. Power the device off and wait 5 seconds.",
            "3. Hold the Volume Down button (or Volume Up on select Dimensity chipsets).",
            "4. Connect the USB cable while continuing to hold the volume key.",
            "5. Click 'Scan Ports' once the PC chimes; the tool will lock onto the MTK VCOM port (VID 0x0E8D).",
        ]
        for s in steps_text:
            tk.Label(steps, text=f"  {s}", bg=C.CARD, fg=C.TEXT, font=(FONT, 9), anchor="w").pack(fill="x", pady=2)

    # ---------------------------------------------------------------------- #
    # PAGE 9: PATCH BUNDLE BUILDER
    # ---------------------------------------------------------------------- #
    def _build_page_patch(self, parent) -> None:
        self._page_header(
            parent,
            "Patch Bundle Builder",
            "Prepares offline Little Kernel binaries and patches custom vbmeta images into the workspace directory. "
            "No device interaction required.",
        )

        wrap, inner = card(parent, "Bundle Parameters")
        wrap.pack(fill="x", pady=(0, 10))

        tk.Label(inner, text="Target Model:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(fill="x")
        self.patch_model = ttk.Combobox(inner, state="readonly", font=(FONT, 9))
        self.patch_model.pack(fill="x", pady=(4, 12))

        tk.Label(inner, text="Original vbmeta.img (optional):", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(
            fill="x"
        )
        prow = tk.Frame(inner, bg=C.CARD)
        prow.pack(fill="x", pady=(4, 12))
        self.patch_vbmeta = tk.StringVar()
        entry(prow, self.patch_vbmeta).pack(side="left", fill="x", expand=True)
        make_button(prow, "Browse", lambda: self._pick(self.patch_vbmeta), "ghost").pack(side="left", padx=(6, 0))

        make_button(inner, "Prepare Patch Bundle", self._do_patch, "accent", self._action_buttons).pack(anchor="w")

        info, info_in = card(parent, "Workspace Staged Assets")
        info.pack(fill="both", expand=True)

        self.ws_tree = ttk.Treeview(info_in, columns=("file", "size"), show="headings", height=7)
        self.ws_tree.heading("file", text="Staged Binary Name")
        self.ws_tree.heading("size", text="File Size")
        self.ws_tree.column("file", width=440, anchor="w")
        self.ws_tree.column("size", width=140, anchor="e")
        self.ws_tree.pack(fill="both", expand=True)

        w_btns = tk.Frame(info_in, bg=C.CARD)
        w_btns.pack(fill="x", pady=(10, 0))
        make_button(w_btns, "Refresh List", self._refresh_workspace, "ghost").pack(side="left")
        make_button(w_btns, "Open Workspace", self._open_workspace, "ghost").pack(side="left", padx=6)

    # ---------------------------------------------------------------------- #
    # PAGE 10: SUPPORTED MODELS CATALOG
    # ---------------------------------------------------------------------- #
    def _build_page_models(self, parent) -> None:
        self._page_header(
            parent,
            "Supported Models Catalog",
            "Comprehensive database of verified Transsion & MTK models with automatic offline fallback.",
        )

        wrap, inner = card(parent, "Catalog Explorer")
        wrap.pack(fill="both", expand=True)

        # Real-time search filter
        srow = tk.Frame(inner, bg=C.CARD)
        srow.pack(fill="x", pady=(0, 8))
        tk.Label(srow, text="Filter:", bg=C.CARD, fg=C.TEXT_MUTED, font=(FONT, 9), width=7, anchor="w").pack(
            side="left"
        )
        self.models_filter = tk.StringVar()
        self.models_filter.trace_add("write", lambda *_: self._filter_models_tree())
        entry(srow, self.models_filter, width=32).pack(side="left", fill="x", expand=True)

        self.models_tree = ttk.Treeview(
            inner,
            columns=("model", "codename", "chipset", "cost", "lk_a", "lk_b"),
            show="headings",
            height=10,
        )
        for col, label, width, anchor in (
            ("model", "Device Model", 230, "w"),
            ("codename", "Codename", 130, "w"),
            ("chipset", "Chipset", 100, "w"),
            ("cost", "Cost", 60, "e"),
            ("lk_a", "LK A Binary", 90, "w"),
            ("lk_b", "LK B Binary", 90, "w"),
        ):
            self.models_tree.heading(col, text=label)
            self.models_tree.column(col, width=width, minwidth=50, anchor=anchor, stretch=True)
        self.models_tree.pack(fill="both", expand=True)

        row = tk.Frame(inner, bg=C.CARD)
        row.pack(fill="x", pady=(10, 0))
        make_button(row, "Reload Catalog", self._reload_models, "accent", self._action_buttons).pack(side="left")
        make_button(row, "Check API Balance", self._do_credits, "ghost").pack(side="left", padx=6)

    # ---------------------------------------------------------------------- #
    # PAGE 11: REBOOT TOOLS (Interactive Selection Tiles)
    # ---------------------------------------------------------------------- #
    def _build_page_reboot(self, parent) -> None:
        self._page_header(
            parent,
            "Reboot & Diagnostic Targets",
            "Send target reboot directives directly to connected fastboot bootloaders.",
        )

        wrap, inner = card(parent, "Select Reboot Target Directive")
        wrap.pack(fill="x")

        self.reboot_target = tk.StringVar(value="system")

        targets = [
            ("system", "Normal Android System Boot", "Boots the phone normally into full Android OS environment."),
            ("bootloader", "Fastboot Bootloader Mode", "Reboots into stock bootloader for flashing and partition maintenance."),
            ("fastboot", "Fastbootd (Userspace Recovery)", "Boots into userspace fastbootd for super / dynamic partition operations."),
            ("recovery", "Stock / Custom Recovery", "Reboots into recovery mode (TWRP, OrangeFox, or stock recovery)."),
        ]

        for val, title, desc in targets:
            tile = tk.Frame(inner, bg=C.CARD_2, highlightthickness=1, highlightbackground=C.BORDER, padx=12, pady=8)
            tile.pack(fill="x", pady=3)

            r_btn = ttk.Radiobutton(tile, text="", value=val, variable=self.reboot_target)
            r_btn.pack(side="left", padx=(0, 8))

            tf = tk.Frame(tile, bg=C.CARD_2)
            tf.pack(side="left", fill="x", expand=True)
            tk.Label(tf, text=title, bg=C.CARD_2, fg=C.WHITE, font=(FONT, 9, "bold"), anchor="w").pack(anchor="w")
            tk.Label(tf, text=desc, bg=C.CARD_2, fg=C.TEXT_MUTED, font=(FONT, 8), anchor="w").pack(anchor="w")

            make_button(tile, "Reboot Now", lambda v=val: (self.reboot_target.set(v), self._do_reboot()), "ghost", padx=10, pady=4).pack(side="right")

    # ---------------------------------------------------------------------- #
    # Navigation & View Switching
    # ---------------------------------------------------------------------- #
    def _show_page(self, key: str) -> None:
        self._current_page = key
        for k, btn in self._nav.items():
            btn.set_active(k == key)
        if key in self._page_frames:
            self._page_frames[key].tkraise()

        title_map = {k: (lbl, ico) for k, lbl, ico in self.PAGES}
        lbl, ico = title_map.get(key, (key, ""))
        self.page_title.configure(text=f"{ico} {lbl}")

        if key == "models":
            self._render_models_tree()
        elif key == "patch":
            self._refresh_workspace()
        elif key == "meta":
            self._scan_ports()

    # ---------------------------------------------------------------------- #
    # Background Worker Plumbing
    # ---------------------------------------------------------------------- #
    def _pump(self) -> None:
        """Process queued thread-safe UI events."""
        try:
            while True:
                try:
                    kind, payload = EVENTS.get_nowait()
                except queue.Empty:
                    break

                try:
                    if kind == "log":
                        self._log_line(str(payload))
                    elif kind == "device":
                        self._apply_snapshot(payload)  # type: ignore[arg-type]
                    elif kind == "models":
                        names, lookup = payload  # type: ignore[misc]
                        self._set_models(names, lookup)
                    elif kind == "done":
                        self._on_done(payload)  # type: ignore[arg-type]
                    elif kind == "ui":
                        payload()  # type: ignore[operator]
                except Exception:
                    try:
                        traceback.print_exc(file=self._orig_stderr or sys.__stderr__)
                    except Exception:
                        pass
        finally:
            self._schedule(60, self._pump)

    # ---------------------------------------------------------------------- #
    # Deep Fastboot Instrumentation & Diagnostic Telemetry
    # ---------------------------------------------------------------------- #
    def _instrumented_fb_run(
        self,
        args: list[str],
        timeout: int = 60,
        check: bool = False,
        silent: bool = True,
    ) -> tuple[int, str]:
        cmd_str = " ".join(str(a) for a in args)
        t0 = time.perf_counter()

        # Deep diagnostic capture to persistent disk log when Debug Mode is ON
        if getattr(self, "debug_mode", True) and hasattr(self, "debug_logger"):
            self.debug_logger.log("FASTBOOT", f">>> fastboot {cmd_str}", "DEBUG")

        rc, out = self._orig_fb_run(args, timeout=timeout, check=check, silent=silent)
        duration_ms = (time.perf_counter() - t0) * 1000

        if getattr(self, "debug_mode", True) and hasattr(self, "debug_logger"):
            self.debug_logger.log(
                "FASTBOOT",
                f"<<< RC={rc} ({duration_ms:.1f}ms) | Output: {out.strip() if out else '(empty)'}",
                "DEBUG" if rc == 0 else "WARN",
            )
        return rc, out

    def run_async(self, label: str, fn: Callable, refresh: bool = False, after: Callable | None = None) -> None:
        if self._busy:
            self.show_toast("warning", "An operation is currently in progress. Please wait.")
            return
        self._busy = True
        self._set_busy(True)
        self._set_status(f"Working: {label}…")
        self._log_line(f"[*] {label}", "info")
        self._animate_pulse(True)

        op_id = f"OP-{int(time.time() * 1000) % 100000:05d}"
        start_time = time.perf_counter()
        if getattr(self, "debug_mode", True) and hasattr(self, "debug_logger"):
            self.debug_logger.log(
                "OP_START",
                f"[{op_id}] Label: '{label}' | Thread: {threading.current_thread().name}",
                "INFO",
            )

        # Auto-expand the side logs panel when an action starts
        if not self._console_visible:
            self._toggle_console()

        def worker():
            rc = 0
            err_output = ""
            try:
                result = fn()
                if isinstance(result, bool):
                    rc = 0 if result else 1
                elif isinstance(result, int):
                    rc = result
                elif result is None:
                    rc = 0
            except SystemExit as exc:
                rc = int(exc.code or 0)
            except Exception as exc:
                if hasattr(self, "debug_logger"):
                    self.debug_logger.log("TRACEBACK", traceback.format_exc(), "ERROR")
                err_output = str(exc)
                rc = 1
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                if getattr(self, "debug_mode", True) and hasattr(self, "debug_logger"):
                    self.debug_logger.log(
                        "OP_END",
                        f"[{op_id}] '{label}' -> ExitCode: {rc} ({duration_ms:.1f}ms)",
                        "INFO" if rc == 0 else "ERROR",
                    )
                    if rc != 0 and err_output:
                        self.debug_logger.log("OP_TRACE", f"[{op_id}] '{label}' Error details: {err_output}", "ERROR")
                EVENTS.put(("done", (label, rc, refresh, after, err_output)))

        threading.Thread(target=worker, daemon=True).start()

    def run_device_task(self, label: str, fn: Callable) -> None:
        def wrapped():
            connected, info = self.backend.device_connected()
            if not connected:
                print("[-] No fastboot device detected. Connect device in Fastboot mode via USB.")
                if getattr(self, "debug_mode", True) and hasattr(self, "debug_logger"):
                    self.debug_logger.log("DEVICE", f"run_device_task aborted: '{label}' (No device connected)", "WARN")
                return 1
            print(f"[+] Device Link: {info}")
            if getattr(self, "debug_mode", True) and hasattr(self, "debug_logger"):
                self.debug_logger.log("DEVICE", f"run_device_task link verified: {info}", "DEBUG")
            return fn()

        self.run_async(label, wrapped, refresh=True)

    def _on_done(self, payload: tuple) -> None:
        label, rc, refresh, after, err_output = payload
        self._busy = False
        self._set_busy(False)
        self._animate_pulse(False)

        if rc == 0:
            self._log_line(f"[+] Succeeded: {label}", "ok")
            self._set_status(f"Completed: {label}")
            if hasattr(self, "debug_logger"):
                self.debug_logger.log("STATUS", f"Operation succeeded: '{label}'", "INFO")
            if "unlock" in label.lower():
                self.show_toast(
                    "success",
                    "Bootloader unlocked! Next: Wipe OEM guard partitions to prevent bootloops.",
                    "Go to Guard Wipe →",
                    lambda: self._show_page("wipe"),
                )
            else:
                self.show_toast("success", f"Operation '{label}' completed successfully.")
        else:
            self._log_line(f"[-] Failed: {label} (exit code {rc})", "err")
            self._set_status(f"Failed: {label} (error {rc})")
            if hasattr(self, "debug_logger"):
                self.debug_logger.log("STATUS", f"Operation failed: '{label}' (ExitCode: {rc})", "ERROR")

            # Diagnose errors
            diag = ErrorDiagnostics.diagnose(err_output)
            if not diag:
                diag = ErrorDiagnostics.diagnose(self._last_log_snippet())

            if diag:
                d_title, d_advice = diag
                toast_kind = "warning" if "not detected" in d_title.lower() or "timeout" in d_title.lower() else "error"
                self.show_toast(
                    toast_kind,
                    f"{label}: {d_title}",
                    "View Fix Guide",
                    lambda: self._show_troubleshoot_modal(d_title, d_advice),
                )
            else:
                self.show_toast("error", f"Operation '{label}' encountered an error.")

        if callable(after):
            try:
                after()
            except Exception:
                traceback.print_exc()
        if refresh:
            self._probe()

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            try:
                btn.configure(state=state)
            except tk.TclError:
                pass

    def _animate_pulse(self, active: bool) -> None:
        if not active:
            self.pulse_glow.place_forget()
            return
        self.pulse_glow.configure(bg=C.ACCENT_LIGHT, width=120)
        self.pulse_glow.place(x=self._pulse_pos, y=0, relheight=1.0)
        self._pulse_pos = (self._pulse_pos + 15) % max(1, self.winfo_width())
        if self._busy:
            self.after(30, lambda: self._animate_pulse(True))

    def _boot(self) -> None:
        self._refresh_readiness()
        self._probe()
        self._scan_ports()
        self._refresh_workspace()
        threading.Thread(target=self._fetch_models_bg, daemon=True).start()

    def _auto_probe(self) -> None:
        if not self._busy and not self._probe_running:
            self._probe()
        self._schedule(8000, self._auto_probe)

    def _guard_tick(self) -> None:
        if not self._guard_failed:
            try:
                healthy, report = self._guard_watch.poll(time.monotonic())
            except Exception:
                healthy, report = True, ""
            if not healthy:
                self._guard_failed = True
                self._on_brand_failure(report)
                return
        self._schedule(15000, self._guard_tick)

    def _on_brand_failure(self, report: str) -> None:
        self._log_line("[-] BRAND INTEGRITY FAILURE", "err")
        for line in report.splitlines():
            if line.strip():
                self._log_line(line, "err")
        self._set_status("Brand integrity check failed")
        self._set_busy(True)
        messagebox.showerror(f"{APP_NAME} — Integrity Violation", report, parent=self)
        self._close_now()

    def _close_now(self) -> None:
        self._cancel_timers()
        if hasattr(self, "debug_logger"):
            self.debug_logger.log("SYSTEM", "Workstation session closed by user.", "INFO")
        try:
            sys.stdout = self._orig_stdout
            sys.stderr = self._orig_stderr
        except Exception:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    # -- Device Snapshot & View Updates ------------------------------------ #
    def _log_pro_device_details(self, snap: dict) -> None:
        """Outputs clear, professional device specifications to the Activity Log panel,
        strictly omitting raw security hex codes, internal tokens, or cryptic codes."""
        serial = snap.get("serial") or "Detected"
        raw_prod = snap.get("product") or ""
        raw_hw = snap.get("hardware") or ""
        slot_raw = snap.get("slot") or "_a"
        slot_display = "Slot B (Active Boot Slot)" if slot_raw in ("b", "_b") else "Slot A (Active Boot Slot)"

        # 1. Resolve Friendly Model & Marketing Name
        model_display = raw_prod or "MediaTek Handset"
        chipset_display = raw_hw or "MediaTek MTK Platform"

        # Check in offline/remote model catalog
        meta_match = None
        if hasattr(self.backend, "mm"):
            meta_match = self.backend.mm.get_model_info(raw_prod)
            if not meta_match and self._model_names:
                for m in self._model_names:
                    if raw_prod and raw_prod.lower() in m.lower():
                        meta_match = self._model_lookup.get(m)
                        if meta_match:
                            break

        if meta_match:
            base_model = meta_match.get("model") or model_display
            code = meta_match.get("codename") or ""
            model_display = f"{base_model} ({code})" if code and code not in base_model else base_model
            chip = meta_match.get("chipset")
            if chip:
                chipset_display = f"MediaTek {chip} (64-bit)"
        elif raw_prod:
            model_display = f"{raw_prod.upper()} (Transsion/MTK)"

        # 2. Clean, Professional Status (NO cryptic hex codes like 0x01, NO raw tokens)
        unlocked = snap.get("unlocked")
        if unlocked is True:
            boot_state = "UNLOCKED — Custom binary flashing permitted"
            boot_tag = "ok"
        elif unlocked is False:
            boot_state = "LOCKED — Standard OEM bootloader security active"
            boot_tag = "warn"
        else:
            boot_state = "READY — Fastboot communication verified"
            boot_tag = "info"

        parts_count = snap.get("partitions") or 0
        parts_text = f"{parts_count} partitions mapped" if parts_count else "Standard MTK partition layout"

        guards = snap.get("guards") or []
        if guards:
            guards_text = f"Detected ({', '.join(guards)}) — Ready for cleanup"
        else:
            guards_text = "Clean (No vendor anti-tamper overlays detected)"

        # 3. Output clean, authentic engineering hardware banner
        self._log_line("----------------------------------------------------------------------", "head")
        self._log_line(f"DEVICE IDENTIFIED : {model_display}", "ok")
        self._log_line(f"  Platform SoC    : {chipset_display}", "plain")
        self._log_line(f"  USB Interface   : Fastboot High-Speed (Serial: {serial})", "plain")
        self._log_line(f"  Active Slot     : {slot_display}", "info")
        self._log_line(f"  Boot State      : {boot_state}", boot_tag)
        self._log_line(f"  Partitions      : {parts_text}", "plain")
        self._log_line(f"  Guard Overlays  : {guards_text}", "warn" if guards else "plain")
        self._log_line("----------------------------------------------------------------------", "head")

    def _probe(self, force_log: bool = False) -> None:
        if self._probe_running:
            return
        self._probe_running = True
        self._manual_scan = bool(force_log)
        if force_log:
            self._last_logged_device_sig = None
            self._log_line("[*] Scanning for connected Fastboot devices...", "info")

        def worker():
            t0 = time.perf_counter()
            manual = getattr(self, "_manual_scan", False)
            if hasattr(self, "debug_logger") and manual:
                self.debug_logger.log("PROBE", "Probing USB devices and fastboot connection...", "DEBUG")
            try:
                snap = self.backend.device_snapshot()
            except Exception as exc:
                traceback.print_exc()
                if hasattr(self, "debug_logger"):
                    self.debug_logger.log("PROBE", f"Probe error: {exc}", "ERROR")
                snap = {"connected": False, "error": str(exc)}
            finally:
                duration_ms = (time.perf_counter() - t0) * 1000
                if hasattr(self, "debug_logger") and (manual or snap.get("connected")):
                    self.debug_logger.log(
                        "PROBE",
                        f"Probe completed in {duration_ms:.1f}ms (connected={snap.get('connected')}, slot={snap.get('slot')}, serial={snap.get('serial')})",
                        "INFO",
                    )
                if manual and not snap.get("connected"):
                    self._log_line("[-] No fastboot devices detected. Check USB connection and mode.", "warn")
                self._manual_scan = False
                EVENTS.put(("device", snap))
                self._probe_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _apply_snapshot(self, snap: dict) -> None:
        connected = bool(snap.get("connected"))
        if connected:
            slot = snap.get("slot") or "_a"
            serial = snap.get("serial") or "--"
            unlocked = snap.get("unlocked")
            lock_text = "UNLOCKED" if unlocked is True else "LOCKED" if unlocked is False else "UNKNOWN"

            # Check if device signature changed or if force re-log requested
            sig = f"{serial}:{slot}:{unlocked}:{snap.get('product')}:{snap.get('partitions')}"
            if getattr(self, "_last_logged_device_sig", None) != sig:
                self._last_logged_device_sig = sig
                self._log_pro_device_details(snap)

            # Topbar badge
            short_ser = serial if len(serial) <= 12 else serial[:10] + "…"
            self.device_pill.configure(
                text=f"  ● FASTBOOT: {short_ser} (Slot {slot[-1].upper()} · {lock_text})  ",
                bg=C.OK_BG,
                fg=C.WHITE,
                highlightbackground=C.OK,
            )

            # Dashboard card
            self.d_conn.configure(text="Connected (Fastboot)", fg=C.OK)
            self.d_serial.configure(text=serial)
            self.d_mode.configure(text=snap.get("mode") or "--")
            self.d_slot.configure(text=slot, fg=C.ACCENT_LIGHT)

            # Wizard card
            self.w_dev_status.configure(text=f"Online ({serial})", fg=C.OK)
            self.w_dev_slot.configure(text=slot, fg=C.ACCENT_LIGHT)
            self.w_dev_chip.configure(
                text=snap.get("product") or snap.get("hardware") or "(Generic MediaTek)",
                fg=C.TEXT,
            )

            if unlocked is True:
                self.d_lock.configure(text="UNLOCKED (Writes Permitted)", fg=C.OK)
                self.wipe_lock_state.configure(text="UNLOCKED — Guard wipe permitted", fg=C.OK)
                self.w_dev_lock.configure(text="UNLOCKED", fg=C.OK)
                self.w_wipe_status.configure(text="UNLOCKED — Ready for wipe", fg=C.OK)
            elif unlocked is False:
                self.d_lock.configure(text="LOCKED", fg=C.WARN)
                self.wipe_lock_state.configure(text="LOCKED — Unlock bootloader first", fg=C.DANGER)
                self.w_dev_lock.configure(text="LOCKED (Unlock Required)", fg=C.WARN)
                self.w_wipe_status.configure(text="LOCKED — Unlock first", fg=C.WARN)
            else:
                self.d_lock.configure(text=snap.get("lock_msg") or "unknown", fg=C.TEXT_MUTED)
                self.wipe_lock_state.configure(text="Unconfirmed — Unlock first", fg=C.TEXT_MUTED)
                self.w_dev_lock.configure(text="Unconfirmed", fg=C.TEXT_MUTED)
                self.w_wipe_status.configure(text="Unconfirmed", fg=C.TEXT_MUTED)

            self.d_parts.configure(text=str(snap.get("partitions") or 0))
            guards = snap.get("guards") or []
            self.d_guards.configure(
                text=", ".join(guards) if guards else "none detected",
                fg=C.WARN if guards else C.TEXT_MUTED,
            )
            keys = snap.get("key_parts") or []
            self.d_keys.configure(text=", ".join(keys) if keys else "--", fg=C.TEXT)
            self.wipe_detected.configure(
                text=", ".join(guards) if guards else "none detected",
                fg=C.WARN if guards else C.TEXT_MUTED,
            )

            # Highlight wizard steps
            self.w_steps[0][0].configure(bg=C.OK_BG, fg=C.WHITE, highlightbackground=C.OK)
            self.w_steps[0][1].configure(fg=C.OK)

            # Auto-suggest model if matched
            prod = (snap.get("product") or "").lower()
            if prod and self._model_names:
                for m in self._model_names:
                    if prod in m.lower():
                        self.w_model_combo.set(m)
                        self._on_wizard_model_selected()
                        break
        else:
            if getattr(self, "_last_logged_device_sig", None) is not None:
                self._last_logged_device_sig = None
                self._log_line("[*] USB Fastboot link disconnected. Waiting for device connection...", "info")

            self.device_pill.configure(
                text="  ○ DEVICE: OFFLINE (Connect USB)  ",
                bg=C.CARD_2,
                fg=C.TEXT_MUTED,
                highlightbackground=C.BORDER,
            )
            for lbl in (self.d_serial, self.d_mode, self.d_slot, self.d_lock, self.d_parts, self.d_guards, self.d_keys):
                lbl.configure(text="--", fg=C.TEXT)
            self.d_conn.configure(text="Not detected", fg=C.TEXT_MUTED)
            self.wipe_detected.configure(text="--", fg=C.TEXT)
            self.wipe_lock_state.configure(text="No device detected", fg=C.TEXT_MUTED)

            self.w_dev_status.configure(text="Offline (Connect USB in Fastboot mode)", fg=C.TEXT_MUTED)
            self.w_dev_slot.configure(text="--", fg=C.TEXT)
            self.w_dev_lock.configure(text="--", fg=C.TEXT)
            self.w_dev_chip.configure(text="--", fg=C.TEXT)
            self.w_wipe_status.configure(text="No device detected", fg=C.TEXT_MUTED)

            self.w_steps[0][0].configure(bg=C.CARD_2, fg=C.TEXT_MUTED, highlightbackground=C.BORDER)
            self.w_steps[0][1].configure(fg=C.TEXT)

    def _refresh_readiness(self) -> None:
        info = self.backend.readiness()

        def mark(label, ok: bool, good_text: str, bad_text: str):
            label.configure(text=good_text if ok else bad_text, fg=C.OK if ok else C.WARN)

        mark(self.r_fastboot, info["fastboot"], "Available (fastboot.exe)", "Missing")
        mark(
            self.r_offline,
            info["offline_count"] > 0,
            f"{info['offline_count']} binaries ready offline",
            "Empty",
        )
        mark(self.r_meta, info["meta_protocol"], "Ready", "Missing")
        mark(self.r_exploit, info["meta_exploit"], "Ready", "Missing")
        mark(self.r_py314, info["py314"], "Embedded Python 3.14 OK", "Missing")
        self.r_ws.configure(text=info["workspace"], fg=C.TEXT)

    def _open_workspace(self) -> None:
        path = str(config.WORKSPACE_DIR)
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except Exception:
            self._log_line(f"[!] Cannot open directory: {path}", "warn")

    def _open_part_folder(self) -> None:
        path = str(self._export_dir_from_field())
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except Exception:
            self._log_line(f"[!] Cannot open folder: {path}", "warn")

    def _copy_device_info(self) -> None:
        snap = self.backend.device_snapshot()
        if not snap.get("connected"):
            self.show_toast("warning", "No device connected to copy specs.")
            return
        specs = (
            f"Device Serial: {snap.get('serial')}\n"
            f"Mode: {snap.get('mode')}\n"
            f"Active Slot: {snap.get('slot')}\n"
            f"Lock State: {snap.get('lock_msg')}\n"
            f"Partitions: {snap.get('partitions')}\n"
            f"Guards: {', '.join(snap.get('guards') or [])}\n"
        )
        self.clipboard_clear()
        self.clipboard_append(specs)
        self.show_toast("success", "Device specifications copied to clipboard.")

    # -- Models Handling & Search Filters ---------------------------------- #
    def _load_models_fast(self) -> None:
        try:
            names, lookup = self.backend.offline_models()
        except Exception:
            traceback.print_exc()
            names, lookup = [], {}
        self._set_models(names, lookup)

    def _fetch_models_bg(self) -> None:
        try:
            names, lookup = self.backend.mm.fetch_models()
            EVENTS.put(("models", (names, lookup)))
        except Exception:
            traceback.print_exc()

    def _set_models(self, names: list, lookup: dict) -> None:
        names = list(names or [])
        lookup = dict(lookup or {})
        if not names:
            return
        self._model_names = names
        self._model_lookup = lookup
        self._cached_models = names[:]

        for combo in (self.unlock_model, self.patch_model, self.w_model_combo):
            current = combo.get()
            combo.configure(values=names)
            if current in names:
                combo.set(current)
            elif names:
                combo.current(0)

        self._render_models_tree()
        self._on_wizard_model_selected()

    def _filter_wizard_models(self) -> None:
        q = self.w_model_filter.get().strip().lower()
        filtered = [m for m in self._model_names if q in m.lower()] if q else self._model_names
        self.w_model_combo.configure(values=filtered)
        if filtered:
            self.w_model_combo.current(0)
            self._on_wizard_model_selected()

    def _filter_unlock_models(self) -> None:
        q = self.unlock_filter.get().strip().lower()
        filtered = [m for m in self._model_names if q in m.lower()] if q else self._model_names
        self.unlock_model.configure(values=filtered)
        if filtered:
            self.unlock_model.current(0)

    def _filter_models_tree(self) -> None:
        q = self.models_filter.get().strip().lower()
        filtered = [m for m in self._model_names if q in m.lower()] if q else self._model_names
        self._render_models_tree(filtered)

    def _on_wizard_model_selected(self, _event=None) -> None:
        name = self.w_model_combo.get().strip()
        if not name or name not in self._model_lookup:
            return
        meta = self._model_lookup[name]
        codename = meta.get("codename", "--")
        chipset = meta.get("chipset", "--")
        lk_a = meta.get("lk_a_filename", "--")
        lk_b = meta.get("lk_b_filename", "--")
        cost = meta.get("patch_cost", "--")
        self.w_model_info.configure(
            text=f"Codename: {codename}  |  Chipset: {chipset}  |  LK Stages: {lk_a}, {lk_b}  |  Cost: {cost} credits",
            fg=C.ACCENT_LIGHT,
        )

    def _render_models_tree(self, names_subset: list | None = None) -> None:
        if not hasattr(self, "models_tree"):
            return
        tree = self.models_tree
        for item in tree.get_children():
            tree.delete(item)
        target_list = names_subset if names_subset is not None else self._model_names
        for name in target_list:
            meta = self._model_lookup.get(name, {})
            tree.insert(
                "",
                "end",
                values=(
                    name,
                    meta.get("codename", "--"),
                    meta.get("chipset", "--"),
                    meta.get("patch_cost", "--"),
                    meta.get("lk_a_filename", "--"),
                    meta.get("lk_b_filename", "--"),
                ),
            )

    def _reload_models(self) -> None:
        self.run_async("Reload Model Catalog", self._reload_models_task)

    def _reload_models_task(self) -> int:
        names, lookup = self.backend.mm.fetch_models()
        EVENTS.put(("models", (names, lookup)))
        print(f"[+] Catalog reloaded: {len(names)} models verified.")
        return 0

    # -- Workspace Listing ------------------------------------------------- #
    def _refresh_workspace(self) -> None:
        if not hasattr(self, "ws_tree"):
            return
        tree = self.ws_tree
        for item in tree.get_children():
            tree.delete(item)
        ws = config.WORKSPACE_DIR
        if not ws.is_dir():
            return
        for path in sorted(ws.glob("*"), key=lambda p: p.name.lower()):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            human = f"{size / (1024 * 1024):.2f} MB" if size >= 1024 * 1024 else f"{size} B"
            tree.insert("", "end", values=(path.name, human))

    # -- Serial Ports ------------------------------------------------------ #
    def _scan_ports(self) -> None:
        ports = ["Auto-detect"]
        try:
            from serial.tools import list_ports

            for p in list_ports.comports():
                label = f"{p.device} — {p.description}" if p.description else p.device
                ports.append(label)
        except Exception:
            pass

        if hasattr(self, "meta_port"):
            current = self.meta_port.get()
            self.meta_port.configure(values=ports)
            if current in ports:
                self.meta_port.set(current)
            else:
                self.meta_port.set(ports[0])

        if hasattr(self, "parts_meta_port"):
            current = self.parts_meta_port.get()
            self.parts_meta_port.configure(values=ports)
            if current in ports:
                self.parts_meta_port.set(current)
            else:
                self.parts_meta_port.set(ports[0])

        info = self.backend.readiness()
        if hasattr(self, "meta_engine"):
            ok = info["meta_protocol"] and info["meta_exploit"]
            self.meta_engine.configure(
                text="Ready" if ok else "Missing drivers/engines",
                fg=C.OK if ok else C.DANGER,
            )
            self.meta_py314.configure(
                text="Embedded 3.14 OK" if info["py314"] else "Missing",
                fg=C.OK if info["py314"] else C.DANGER,
            )

    # -- Console Logging --------------------------------------------------- #
    def _log_line(self, line: str, tag: str | None = None) -> None:
        if not hasattr(self, "console"):
            return
        if threading.current_thread() is not threading.main_thread():
            EVENTS.put(("log", line))
            return

        if tag is None:
            s = line.lstrip()
            if s.startswith("[+]"):
                tag = "ok"
            elif s.startswith("[!]"):
                tag = "warn"
            elif s.startswith("[-]"):
                tag = "err"
            elif s.startswith("[*]"):
                tag = "info"
            elif s.startswith("[DEBUG]"):
                tag = "debug"
            elif s.startswith("==="):
                tag = "head"
            elif s.startswith(">>>"):
                tag = "cmd"
            else:
                tag = "plain"

        # If debug mode is toggled OFF, suppress verbose [DEBUG] lines from polluting UI
        if tag == "debug" and not getattr(self, "debug_mode", True):
            return

        widget = self.console
        widget.configure(state="normal")
        widget.insert("end", line + "\n", tag)
        widget.configure(state="disabled")

        if getattr(self, "_auto_scroll_enabled", True):
            widget.see("end")

        self._line_counter += 1
        if hasattr(self, "log_count_lbl"):
            self.log_count_lbl.configure(text=f"{self._line_counter} lines")

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        self._line_counter = 0
        if hasattr(self, "log_count_lbl"):
            self.log_count_lbl.configure(text="0 lines")

    def _copy_console(self) -> None:
        content = self.console.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.show_toast("info", "Activity log copied to clipboard.")

    def _save_log(self) -> None:
        content = self.console.get("1.0", "end").strip()
        path = filedialog.asksaveasfilename(
            title="Save Activity Log",
            defaultextension=".log",
            filetypes=[("Log file", "*.log"), ("Text file", "*.txt")],
            initialfile="tfast-mtk-tool.log",
        )
        if not path:
            return
        footer = (
            "\n" + "-" * 72 + "\n"
            + f"{branding.PRODUCT} v{branding.PRODUCT_VERSION}\n"
            + f"{branding.COPYRIGHT_LINE}\n"
            + f"Built by {AGENCY}\n"
            + "\n".join(f"  {label}: {url}" for label, url in branding.LINKS)
            + "\n" + "-" * 72 + "\n"
        )
        try:
            Path(path).write_text(content + footer, encoding="utf-8")
            self._set_status(f"Log saved: {path}")
            self.show_toast("success", f"Log saved to {Path(path).name}")
        except Exception as exc:
            self._log_line(f"[-] Could not save log: {exc}", "err")

    def _last_log_snippet(self, max_lines: int = 15) -> str:
        try:
            content = self.console.get("1.0", "end")
            lines = content.strip().splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception:
            return ""

    def _set_status(self, text: str) -> None:
        if hasattr(self, "status"):
            self.status.configure(text=text)

    # ---------------------------------------------------------------------- #
    # Action Dialogs & Modals
    # ---------------------------------------------------------------------- #
    def _confirm(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message, icon="warning", parent=self)

    def _show_troubleshoot_modal(self, title: str, advice: str) -> None:
        win = tk.Toplevel(self)
        win.title(f"Diagnostic Guide: {title}")
        win.configure(bg=C.BG)
        win.transient(self)
        win.resizable(False, False)

        head = tk.Frame(win, bg=C.SIDEBAR, padx=18, pady=14)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=C.SIDEBAR, fg=C.WARN, font=(FONT, 12, "bold")).pack(anchor="w")

        body = tk.Frame(win, bg=C.BG, padx=18, pady=16)
        body.pack(fill="both", expand=True)

        lbl = tk.Label(
            body,
            text=advice,
            bg=C.BG,
            fg=C.TEXT,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=480,
        )
        lbl.pack(fill="x", pady=(0, 14))

        btns = tk.Frame(body, bg=C.BG)
        btns.pack(fill="x")
        make_button(btns, "Got It / Close", win.destroy, "accent").pack(side="right")

        win.update_idletasks()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        win.grab_set()

    def _pick(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Android Binaries", "*.img *.bin"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def _selected_model(self, combo: ttk.Combobox) -> str | None:
        name = combo.get().strip()
        if not name:
            self.show_toast("warning", "Please select a target model first.")
            return None
        return name

    # ---------------------------------------------------------------------- #
    # Action Handlers: Unlock
    # ---------------------------------------------------------------------- #
    def _do_wizard_unlock(self) -> None:
        model = self.w_model_combo.get().strip()
        if not model:
            self.show_toast("warning", "Select a target device model in Stage 2 first.")
            return

        meta = self.backend.mm.get_model_info(model) or {}
        if not self._confirm(
            "Execute Unlock Pipeline",
            f"Run automated unlock pipeline for:\n\n{model}\n"
            f"Codename: {meta.get('codename', '?')}\n\n"
            "This will flash verified LK stages and AVB-disabled VBMeta to the active slot.\n"
            "Device user data will be wiped. Proceed?",
        ):
            return

        ns = argparse.Namespace(
            model=model,
            vbmeta=None,
            reboot=not bool(self.w_reboot_var.get()),
            no_meta_fallback=False,
        )
        self.run_device_task(
            "Automated Unlock Pipeline",
            lambda: bl_cli.cmd_unlock(ns, self.backend.fb, self.backend.mm, self.backend.patcher, self.backend.api),
        )

    def _do_unlock(self) -> None:
        model = self._selected_model(self.unlock_model)
        if not model:
            return
        meta = self.backend.mm.get_model_info(model) or {}
        if not self._confirm(
            "Run Automated Unlock",
            f"Run the full unlock pipeline for:\n\n{model}\n"
            f"Codename: {meta.get('codename', '?')}\n\n"
            "This wipes user data and rewrites little-kernel / vbmeta partitions. Continue?",
        ):
            return

        vbmeta = self.unlock_vbmeta.get().strip() or None
        if vbmeta and not os.path.exists(vbmeta):
            self._log_line(f"[-] vbmeta not found: {vbmeta}", "err")
            return

        ns = argparse.Namespace(
            model=model,
            vbmeta=vbmeta,
            reboot=bool(self.unlock_reboot.get()),
            no_meta_fallback=bool(self.unlock_skip_meta.get()),
        )
        self.run_device_task(
            "Automated Unlock Pipeline",
            lambda: bl_cli.cmd_unlock(ns, self.backend.fb, self.backend.mm, self.backend.patcher, self.backend.api),
        )

    def _do_handshake(self) -> None:
        if not self._confirm(
            "Fastboot Handshake",
            "Flash zeroed FRP image, send unlock_critical, then `fastboot flashing unlock`.\n\n"
            "Watch phone screen and press VOLUME UP when prompted.\n\nProceed?",
        ):
            return
        self.run_device_task(
            "FENIX FRP + Unlock Handshake",
            lambda: bl_cli.cmd_unlock_handshake(None, self.backend.fb),
        )

    def _do_flashing_unlock(self) -> None:
        if not self._confirm(
            "Send Flashing Unlock",
            "Send `fastboot flashing unlock` to connected device.\n\n"
            "OEM Unlocking must be enabled in Developer Options.\n\nProceed?",
        ):
            return

        def task():
            ok, out = self.backend.fb.flashing_unlock()
            print(out.strip() or "(no output)")
            if ok and "prohibit" not in (out or "").lower():
                print("[+] Command accepted by device.")
                return 0
            if "prohibit" in (out or "").lower():
                print("[!] Rejected: OEM Unlocking is disabled in Android Developer Options.")
            return 1

        self.run_device_task("fastboot flashing unlock", task)

    # ---------------------------------------------------------------------- #
    # Action Handlers: LK Analysis & Patch
    # ---------------------------------------------------------------------- #
    def _lk_selected_image(self) -> str | None:
        path = self.lk_image_path.get().strip()
        if not path:
            self.show_toast("warning", "Select an LK image first (Browse or Read from device).")
            return None
        if not os.path.exists(path):
            self._log_line(f"[-] Image not found: {path}", "err")
            return None
        return path

    def _render_lk_analysis(self, analysis) -> None:
        state = analysis.state
        colour = (
            C.OK
            if state == lk_image.State.ALREADY_PATCHED
            else C.ACCENT_LIGHT
            if analysis.patchable
            else C.WARN
            if state == lk_image.State.MIXED
            else C.DANGER
        )
        self.lk_state.configure(text=state, fg=colour)
        self.lk_arch.configure(text=f"{analysis.arch}  {analysis.arch_counts}", fg=C.TEXT)
        self.lk_profile.configure(
            text=(f"{analysis.profile.key} - {analysis.profile.name}" if analysis.profile else "None matched"),
            fg=C.TEXT if analysis.profile else C.DANGER,
        )
        self.lk_sites.configure(
            text=f"{len(analysis.sites)} found (stock: {analysis.stock_site_count}, patched: {len(analysis.sites) - analysis.stock_site_count})",
            fg=C.TEXT,
        )
        if analysis.patchable:
            self.lk_verdict.configure(text="YES — Stub can be applied in-place", fg=C.OK)
        elif state == lk_image.State.ALREADY_PATCHED:
            self.lk_verdict.configure(text="Already Patched", fg=C.OK)
        else:
            self.lk_verdict.configure(text=f"NO — {state}", fg=C.DANGER if analysis.problems else C.WARN)

    def _do_lk_acquire(self) -> None:
        def task():
            acquired = self.backend.patcher.acquire_device_lk(fastboot_path=self.backend.fb.fastboot_path)
            print(f"[+] Read {acquired.partition} via {acquired.transport} ({acquired.size:,} bytes)")
            path = str(acquired.path)
            self._ui(lambda: self.lk_image_path.set(path))
            return 0

        self.run_async("Read LK from Device", task)

    def _do_lk_analyze(self) -> None:
        path = self._lk_selected_image()
        if not path:
            return

        def task():
            analysis = self.backend.patcher.analyze_image(path)
            for line in analysis.summary_lines():
                print(line)
            self._ui(lambda: self._render_lk_analysis(analysis))
            if analysis.state == lk_image.State.ALREADY_PATCHED:
                print("[+] This image already carries the unlock patch.")
            elif analysis.patchable:
                print("[+] Image is Ready — unlock stub can be applied in place.")
            else:
                print(f"[!] Not patchable in its current state ({analysis.state}).")
            return 0 if (analysis.patchable or analysis.state == lk_image.State.ALREADY_PATCHED) else 1

        self.run_async("Analyze LK Image", task)

    def _lk_patch_common(self, dry_run: bool) -> None:
        path = self._lk_selected_image()
        if not path:
            return
        value = int(self.lk_value.get())
        write_back = bool(self.lk_write_back.get())

        if not dry_run:
            msg = (
                f"Patch this Little Kernel image in place?\n\n{path}\n\n"
                f"Stub {lk_image.STUB_NAMES[value]} writing {lk_image.STUB_VALUES[value]} at every stock site.\n"
                "Original will be backed up first and size will remain unchanged."
            )
            if write_back:
                msg += "\n\nThe patched binary WILL be flashed back to device (lk_a)."
            if not self._confirm("Patch LK in place", msg):
                return

        def task():
            ok, message, backup = self.backend.patcher.patch_image_in_place(path, value=value, dry_run=dry_run)
            for line in message.splitlines():
                print(("[+] " if ok else "[-] ") + line)
            if backup:
                print(f"[+] Original backed up to {backup}")
            if not ok:
                return 1
            if dry_run:
                print("[*] Dry run complete; no bytes modified.")
                return 0

            analysis = self.backend.patcher.analyze_image(path)
            self._ui(lambda: self._render_lk_analysis(analysis))

            if write_back:
                print("[*] Flashing back to device lk_a…")
                wok, wmsg = self.backend.patcher.write_back_to_device(path, "lk_a")
                for line in (wmsg or "").splitlines():
                    print(("[+] " if wok else "[-] ") + line)
                return 0 if wok else 1
            return 0

        self.run_async("Dry Run LK Patch" if dry_run else "Patch LK In Place", task)

    def _do_lk_patch_dry(self) -> None:
        self._lk_patch_common(dry_run=True)

    def _do_lk_patch(self) -> None:
        self._lk_patch_common(dry_run=False)

    # ---------------------------------------------------------------------- #
    # Action Handlers: META Partition Manager
    # ---------------------------------------------------------------------- #
    def _part_mgr(self):
        if not meta_partitions.MetaShellTransport.engines_available():
            self._log_line("[-] META engines missing from handoff_secure/engines or py314_runtime.", "err")
            return None
        if getattr(self, "_meta_transport", None) is None:
            self._meta_transport = meta_partitions.MetaShellTransport()
        if getattr(self, "_part_mgr_obj", None) is None:
            self._part_mgr_obj = meta_partitions.MetaPartitionManager(
                self._meta_transport,
                config.WORKSPACE_DIR / "partitions",
                progress=lambda m: print(f"  {m}"),
            )
        return self._part_mgr_obj

    def _do_meta_connect(self) -> None:
        if getattr(self, "_meta_transport", None) is None:
            self._meta_transport = meta_partitions.MetaShellTransport()

        sel = self.parts_meta_port.get().strip() if hasattr(self, "parts_meta_port") else ""
        chosen_port = None if (not sel or "auto" in sel.lower()) else sel.split("—")[0].split("-")[0].strip()

        def task():
            ok = self._meta_transport.connect(port=chosen_port, log=print)
            if not ok:
                return 1
            active_p = getattr(getattr(self._meta_transport, "proto", None), "port", "Active Session")
            self._ui(lambda: self.parts_status.configure(text=f"Connected ({active_p})", fg=C.OK))

            # Auto-populate partition tree immediately upon successful link
            mgr = self._part_mgr()
            if mgr:
                try:
                    parts = mgr.list_partitions(refresh=True)
                    if parts:
                        self._ui(lambda: self._render_parts(parts))
                except Exception as ex:
                    print(f"  Note: partition listing deferred: {ex}")
            return 0

        self.run_async("Connect META Port", task)

    def _do_reboot_to_meta(self) -> None:
        def task():
            print("[*] Sending fastboot directive to reboot into META mode...")
            code, out = self.backend.fb.run(["reboot-meta"], timeout=10)
            if code != 0:
                code, out = self.backend.fb.run(["oem", "reboot-meta"], timeout=10)
            if code != 0:
                print(f"[-] Fastboot reboot-meta not supported by this bootloader: {out.strip() or 'rejected'}")
                print("[*] Please use manual hardware key combo instead (Power OFF, hold Vol Down + plug USB).")
                return 1
            print("[+] Reboot directive accepted! Phone is rebooting to META mode...")
            print("[*] Establishing META serial link in 3 seconds...")
            time.sleep(3.0)
            self._do_meta_connect()
            return 0

        self.run_device_task("Reboot to META Mode", task)

    def _do_meta_disconnect(self) -> None:
        t = getattr(self, "_meta_transport", None)
        if t is not None:
            t.close()
        self._meta_transport = None
        self._part_mgr_obj = None
        self.parts_status.configure(text="not connected", fg=C.TEXT_MUTED)
        self._log_line("[*] META session closed.", "info")

    def _render_parts(self, parts: list) -> None:
        self._cached_parts = parts
        self._filter_parts_tree()

    def _filter_parts_tree(self) -> None:
        tree = self.parts_tree
        for item in tree.get_children():
            tree.delete(item)
        q = self.parts_filter.get().strip().lower() if hasattr(self, "parts_filter") else ""
        for p in self._cached_parts:
            if q and q not in p.name.lower():
                continue
            tree.insert("", "end", values=(p.name, p.size_human, p.source, "PROTECTED" if p.protected else "UNPROTECTED"))
        if hasattr(self, "parts_selinfo"):
            total = len(self._cached_parts)
            shown = len(tree.get_children())
            self.parts_selinfo.configure(text=f"Showing {shown} of {total} partitions")

    def _do_parts_refresh(self) -> None:
        mgr = self._part_mgr()
        if mgr is None:
            return

        def task():
            parts = mgr.list_partitions(refresh=True)
            print(f"[+] {len(parts)} partitions reported by META shell")
            self._ui(lambda: self._render_parts(parts))
            return 0 if parts else 1

        self.run_async("Refresh Partition Table", task)

    def _on_part_selected(self, _event=None) -> None:
        sel = self.parts_tree.selection()
        n = len(sel)
        if hasattr(self, "parts_selinfo"):
            self.parts_selinfo.configure(
                text=f"{n} selected (Ctrl/Shift-click for multi-selection)",
                fg=C.ACCENT_LIGHT if n else C.TEXT_MUTED,
            )
        if not sel:
            self.part_sel.configure(text="(none)", fg=C.TEXT_MUTED)
            return

        values = self.parts_tree.item(sel[0], "values")
        name = values[0]
        protected = len(values) > 3 and values[3] == "PROTECTED"
        extra = f" (+{n - 1} more)" if n > 1 else ""
        self.part_sel.configure(
            text=name + (" [PROTECTED]" if protected else "") + extra,
            fg=C.WARN if protected else C.ACCENT_LIGHT,
        )
        if not self.part_file.get().strip():
            self.part_file.set(str(config.WORKSPACE_DIR / "partitions" / f"{name}.img"))

    def _selected_partitions(self) -> list[str]:
        return [self.parts_tree.item(i, "values")[0] for i in self.parts_tree.selection()]

    def _selected_partition(self) -> str | None:
        names = self._selected_partitions()
        if not names:
            self.show_toast("warning", "Select one or more partitions from the table first.")
            return None
        return names[0]

    def _do_part_select_all(self) -> None:
        self.parts_tree.selection_set(self.parts_tree.get_children())
        self._on_part_selected()

    def _do_part_select_safe(self) -> None:
        keep = [
            i
            for i in self.parts_tree.get_children()
            if len(self.parts_tree.item(i, "values")) > 3 and self.parts_tree.item(i, "values")[3] != "PROTECTED"
        ]
        self.parts_tree.selection_set(keep)
        self._on_part_selected()

    def _select_critical_parts(self) -> None:
        critical_names = {
            "boot", "boot_a", "boot_b",
            "lk", "lk_a", "lk_b",
            "vbmeta", "vbmeta_a", "vbmeta_b",
            "recovery", "super",
        }
        keep = [i for i in self.parts_tree.get_children() if self.parts_tree.item(i, "values")[0].lower() in critical_names]
        self.parts_tree.selection_set(keep)
        self._on_part_selected()

    def _select_guard_parts(self) -> None:
        guard_names = set(config.TRASH_PARTITIONS) | set(config.EXTRA_SYSTEM_PARTITIONS)
        keep = [i for i in self.parts_tree.get_children() if self.parts_tree.item(i, "values")[0].lower() in guard_names]
        self.parts_tree.selection_set(keep)
        self._on_part_selected()

    def _do_part_clear_sel(self) -> None:
        self.parts_tree.selection_remove(self.parts_tree.get_children())
        self._on_part_selected()

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self.part_file.set(path)

    def _apply_parts_speed(self, mgr) -> None:
        name = self.parts_speed.get() if hasattr(self, "parts_speed") else "fast"
        size = mgr.set_speed(name)
        print(f"[*] Speed profile: {name} ({size // 1024} KiB chunks)")

    def _export_dir_from_field(self) -> Path:
        raw = self.part_file.get().strip()
        if not raw:
            return config.WORKSPACE_DIR / "partitions" / "exports"
        p = Path(raw)
        if p.suffix.lower() in (".img", ".bin", ".mbn", ".elf"):
            return p.parent
        return p

    def _part_op(self, label: str, fn: Callable) -> None:
        mgr = self._part_mgr()
        if mgr is None:
            return
        self._apply_parts_speed(mgr)

        def task():
            try:
                res = fn(mgr)
            except meta_partitions.PartitionError as exc:
                for line in str(exc).splitlines():
                    print("  ! " + line)
                return 1
            if isinstance(res, list):
                bad = sum(1 for r in res if not r.ok)
                for r in res:
                    for line in r.lines():
                        print(("  " if r.ok else "  ! ") + line)
                return 1 if bad else 0
            for line in res.lines():
                print(("  " if res.ok else "  ! ") + line)
            return 0 if res.ok else 1

        self.run_async(label, task)

    def _do_part_export(self) -> None:
        names = self._selected_partitions()
        if not names:
            self.show_toast("warning", "Select one or more partitions first.")
            return
        out_dir = self._export_dir_from_field()
        force = bool(self.part_force.get())
        self._part_op(
            f"Export {len(names)} partition(s)",
            lambda m: m.export_many(names, out_dir=out_dir, force=force, skip_protected=not force, verify=False),
        )

    def _do_part_backup(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        dest = self.part_file.get().strip() or str(config.WORKSPACE_DIR / "partitions" / f"{name}.img")
        force = bool(self.part_force.get())
        self._part_op(f"Back up {name}", lambda m: m.backup_partition(name, dest=Path(dest), force=force))

    def _do_part_replace(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        src = self.part_file.get().strip()
        if not src or not os.path.isfile(src):
            self.show_toast("warning", "Choose an image file to write.")
            return
        force = bool(self.part_force.get())
        if not self._confirm(
            "Replace Partition",
            f"Replace contents of '{name}' with {Path(src).name}?\n\n"
            "Safety backup will be saved first and checksum re-verified.\n"
            "Mismatched file sizes are refused. Proceed?",
        ):
            return
        self._part_op(f"Replace {name}", lambda m: m.replace_partition(name, Path(src), force=force))

    def _do_part_restore(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        src = self.part_file.get().strip()
        if not src or not os.path.exists(src):
            self.show_toast("warning", "Choose an existing backup image to restore.")
            return
        force = bool(self.part_force.get())
        if not self._confirm("Restore Partition", f"Write {Path(src).name} over '{name}'?\n\nProceed?"):
            return
        self._part_op(f"Restore {name}", lambda m: m.restore_partition(name, Path(src), force=force))

    def _do_part_verify(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        src = self.part_file.get().strip()
        if not src or not os.path.exists(src):
            self.show_toast("warning", "Choose an image to compare against.")
            return
        force = bool(self.part_force.get())
        self._part_op(f"Verify {name}", lambda m: m.verify_partition(name, Path(src), force=force))

    def _do_part_bench(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        self._part_op(f"Benchmark Read ({name})", lambda m: m.benchmark_read(name, length=4 << 20))

    def _do_part_probe(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        force = bool(self.part_force.get())
        mgr = self._part_mgr()
        if mgr is None:
            return

        def task():
            try:
                sigs = mgr.probe_signatures(name, force=force)
            except Exception as exc:
                print(f"  ! Probe failed: {exc}")
                return 1
            if sigs:
                print(f"[+] '{name}' filesystem signature: {', '.join(sigs)}")
            else:
                print(f"[*] '{name}' has no recognized signature (raw zero-filled or unknown format).")
            return 0

        self.run_async(f"Probe {name}", task)

    def _do_part_wipe(self) -> None:
        name = self._selected_partition()
        if not name:
            return
        force = bool(self.part_force.get())
        mode = self.wipe_mode.get() if hasattr(self, "wipe_mode") else "filesystem"

        if not self._confirm(
            f"Wipe Partition ({mode})",
            f"Wipe '{name}' using mode '{mode}'?\n\n"
            "This operation destroys superblocks / data. Cannot be undone. Proceed?",
        ):
            return

        def task(mgr):
            return mgr.wipe_partition(name, mode=mode, force=force)

        self._part_op(f"Wipe {name} ({mode})", task)

    # ---------------------------------------------------------------------- #
    # Action Handlers: Wipe Trash, Flash, Meta, Reboot, Credits
    # ---------------------------------------------------------------------- #
    def _do_wipe(self) -> None:
        include_system = bool(self.wipe_include_system.get())
        targets = list(config.TRASH_PARTITIONS) + (list(config.EXTRA_SYSTEM_PARTITIONS) if include_system else [])
        extra = "\n\nAlso clears product and system_ext.\nDevice will not boot until firmware is flashed." if include_system else ""
        if not self._confirm(
            "Wipe OEM Guard Partitions",
            f"Erase reported guard partitions:\n\n{', '.join(targets)}{extra}\n\nRequires unlocked bootloader. Proceed?",
        ):
            return

        def task():
            ns = argparse.Namespace(guard_only=not include_system)
            return bl_cli.cmd_wipe_trash(ns, self.backend.fb)

        self.run_device_task("Wipe OEM Guard Partitions", task)

    def _do_flash(self) -> None:
        vbmeta = self.flash_vbmeta.get().strip() or None
        system = self.flash_system.get().strip() or None
        if not vbmeta and not system:
            self.show_toast("warning", "Select at least one image to flash.")
            return

        if not self._confirm(
            "Flash Custom Images",
            f"Flash selected images to active slot?\nvbmeta: {vbmeta or '(skipped)'}\nsystem: {system or '(skipped)'}\n\nProceed?",
        ):
            return

        ns = argparse.Namespace(vbmeta=vbmeta, system=system, reboot=bool(self.flash_reboot.get()))
        self.run_device_task("Flash Custom Images", lambda: bl_cli.cmd_flash_custom(ns, self.backend.fb))

    def _do_patch(self) -> None:
        model = self._selected_model(self.patch_model)
        if not model:
            return
        vbmeta = self.patch_vbmeta.get().strip() or None
        ns = argparse.Namespace(model=model, vbmeta=vbmeta)
        self.run_async(
            "Prepare Patch Bundle",
            lambda: bl_cli.cmd_patch(ns, self.backend.fb, self.backend.mm, self.backend.patcher, self.backend.api),
            after=self._refresh_workspace,
        )

    def _do_meta(self) -> None:
        sel = self.meta_port.get().strip()
        port = None if (not sel or sel == "Auto-detect") else sel.split("—")[0].strip()

        if not self._confirm(
            "Run Hardware META Unlock",
            "Clear seccfg unlock flag via MTK Preloader serial protocol.\n\n"
            "Ensure device is powered off and ready to plug in with volume key held.\n\nProceed?",
        ):
            return

        ns = argparse.Namespace(port=port)
        self.run_async("Hardware META Mode Unlock", lambda: bl_cli.cmd_meta_unlock(ns), refresh=True)

    def _do_reboot(self) -> None:
        target = self.reboot_target.get()
        ns = argparse.Namespace(target=target)
        self.run_device_task(f"Reboot to {target}", lambda: bl_cli.cmd_reboot(ns, self.backend.fb))

    def _quick_reboot(self, target: str) -> None:
        ns = argparse.Namespace(target=target)
        self.run_device_task(f"Reboot to {target}", lambda: bl_cli.cmd_reboot(ns, self.backend.fb))

    def _do_credits(self) -> None:
        def task():
            ok, credits, msg = self.backend.api.check_credits()
            print(f"[*] API balance: {credits} credits ({msg})")
            return 0 if ok else 1

        self.run_async("Check API Credits", task)

    def _ui(self, fn: Callable) -> None:
        EVENTS.put(("ui", fn))

    # ---------------------------------------------------------------------- #
    # About Dialog & External Links
    # ---------------------------------------------------------------------- #
    def _open_url(self, url: str) -> None:
        try:
            import webbrowser

            webbrowser.open_new_tab(url)
            self._set_status(f"Opened {url}")
        except Exception as exc:
            self._log_line(f"[!] Cannot open {url}: {exc}", "warn")

    def _show_about(self) -> None:
        win = tk.Toplevel(self)
        win.title(f"About {APP_NAME}")
        win.configure(bg=C.BG)
        win.transient(self)
        win.resizable(False, False)

        head = tk.Frame(win, bg=C.SIDEBAR, padx=20, pady=16)
        head.pack(fill="x")
        if (ASSETS_DIR / "tfast_64.png").exists():
            try:
                win._logo = tk.PhotoImage(file=str(ASSETS_DIR / "tfast_64.png"))
                tk.Label(head, image=win._logo, bg=C.SIDEBAR).pack(side="left", padx=(0, 14))
            except tk.TclError:
                pass

        txt = tk.Frame(head, bg=C.SIDEBAR)
        txt.pack(side="left")
        tk.Label(txt, text=branding.PRODUCT, bg=C.SIDEBAR, fg=C.WHITE, font=(FONT, 13, "bold"), anchor="w").pack(fill="x")
        tk.Label(
            txt,
            text=f"Version {branding.PRODUCT_VERSION} · {branding.PRODUCT_EDITION}",
            bg=C.SIDEBAR,
            fg=C.ACCENT_LIGHT,
            font=(FONT, 9),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            txt,
            text=branding.TAGLINE,
            bg=C.SIDEBAR,
            fg=C.TEXT_MUTED,
            font=(FONT, 9),
            anchor="w",
            wraplength=440,
            justify="left",
        ).pack(fill="x", pady=(6, 0))

        body = tk.Frame(win, bg=C.BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=branding.COPYRIGHT_LINE, bg=C.BG, fg=C.TEXT, font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text=f"Built by {AGENCY}", bg=C.BG, fg=C.TEXT_MUTED, font=(FONT, 9), anchor="w").pack(
            fill="x", pady=(2, 14)
        )

        tk.Label(body, text="COMMUNITY & SUPPORT", bg=C.BG, fg=C.TEXT_DIM, font=(FONT, 8, "bold"), anchor="w").pack(fill="x")
        for label, url in branding.LINKS:
            row = tk.Frame(body, bg=C.BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:", bg=C.BG, fg=C.TEXT_MUTED, font=(FONT, 9), width=18, anchor="w").pack(side="left")
            lnk = tk.Label(row, text=url, bg=C.BG, fg=C.ACCENT_LIGHT, font=(FONT, 9, "underline"), anchor="w", cursor="hand2")
            lnk.pack(side="left")
            lnk.bind("<Button-1>", lambda e, u=url: self._open_url(u))
            lnk.bind("<Enter>", lambda e, w=lnk: w.configure(fg=C.WHITE))
            lnk.bind("<Leave>", lambda e, w=lnk: w.configure(fg=C.ACCENT_LIGHT))

        tk.Frame(body, bg=C.BORDER, height=1).pack(fill="x", pady=14)

        ok, msg = tfast_guard.verify()
        summary = "Brand and copyright integrity verified." if ok else msg.splitlines()[0]
        tk.Label(
            body,
            text=("✔ " if ok else "✖ ") + summary,
            bg=C.BG,
            fg=C.OK if ok else C.DANGER,
            font=(FONT, 8, "bold"),
            anchor="w",
        ).pack(fill="x")

        btns = tk.Frame(body, bg=C.BG)
        btns.pack(fill="x", pady=(16, 0))
        make_button(btns, "Close", win.destroy, "accent").pack(side="right")

        win.update_idletasks()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        win.grab_set()

    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno(
                "Operation in Progress",
                "A hardware flash or partition operation is running.\nClosing now may cause partition corruption.\n\nClose anyway?",
                icon="warning",
                parent=self,
            ):
                return
        self._close_now()


# --------------------------------------------------------------------------- #
# Entry Point & CLI Deep-Linking
# --------------------------------------------------------------------------- #
def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> int:
    enable_dpi_awareness()

    if BACKEND_IMPORT_ERROR is not None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            f"{APP_NAME} — Missing Dependencies",
            f"The back end engine failed to import:\n\n{BACKEND_IMPORT_ERROR}\n\n"
            "Run via tfast-gui.bat or install dependencies:\n    pip install requests pyserial",
        )
        root.destroy()
        return 1

    # Brand integrity verification
    ok, bmsg = tfast_guard.verify()
    if not ok:
        print(bmsg)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(f"{branding.PRODUCT} — Integrity Error", bmsg)
        root.destroy()
        return tfast_guard.EXIT_BRAND_FAILURE

    if "--about" in sys.argv:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(f"About {branding.PRODUCT}", branding.about_text())
        root.destroy()
        return 0

    app = App()

    # Deep-link support: --page=wizard or --page=unlock
    for arg in sys.argv[1:]:
        if arg.startswith("--page="):
            key = arg.split("=", 1)[1].strip()
            if key in app._page_frames:
                app._show_page(key)
            break

    if "--selftest" in sys.argv:
        app.update_idletasks()
        app.update()
        sys.stdout = app._orig_stdout
        print("SELFTEST OK")
        app.destroy()
        return 0

    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
