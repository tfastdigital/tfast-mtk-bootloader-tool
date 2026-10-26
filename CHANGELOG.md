# Changelog — TFast MTK Bootloader Tool

All notable changes, bug fixes, UI refinements, architectural splits, and workflow enhancements to the **TFast MTK Bootloader Tool** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-10-26 — *The Professional Workstation Release*

### Summary
Comprehensive transformation of the suite from a prototype utility into an industrial-grade desktop servicing environment. Refined user experience to eliminate amateur styling, separated UI feedback from deep forensic disk logging, stabilized the MediaTek serial protocol engine, restored native Windows chrome branding, and introduced automated hardware workflows.

---

### Added

#### Workflows & Automation
- **Guided 5-Stage Unlock Pipeline**: Linear pre-flight verification, real-time catalog model matching, automated LK stage flashing, AVB disablement (`--flags 3`), FENIX FRP handshake, post-unlock guard wipe, and automated reboot.
- **One-Click Fastboot-to-META Reboot**: Added `Reboot to META (Fastboot)` button in the META Partition Manager toolbar. Dispatches `fastboot reboot-meta` and `fastboot oem reboot-meta` directives to reboot connected fastboot devices straight into BootROM/Preloader META mode without manual hardware button timing.
- **Automated Partition Table Population**: Connecting via `Connect META Port` now immediately queries `/proc/dumchar_info` and repopulates the partition explorer table upon handshake completion, eliminating the need for a secondary manual click.
- **Live Connection Listening Window**: Implemented a 30-second polling handshake loop in `MetaShellTransport.connect()`. Gives technicians sufficient time to connect their powered-down handset with hardware buttons held down.
- **COM Port Selection & Live Scanning**: Added a dedicated **Target Port** selector (`Auto-detect` or specific COM devices) and **Scan Ports** button to Section 1 of the *META Partition Manager* page.

#### UI & Design Refinements
- **Shared Persistent Activity Log Panel**: Built a dedicated, multi-threaded drawer on the right side of the screen shared across all 11 workstation pages. Features real-time color-coded tags (`head`, `ok`, `warn`, `err`, `info`, `plain`), an autoscroll engine, and dedicated toolbar actions (`Clear`, `Copy`, `Save`, `Logs Folder`, `Debug: ON/OFF`, `Auto-scroll: ON/OFF`).
- **Compact Hardware Status Chip**: Topbar connection badge formatting `● FASTBOOT: [serial] (Slot X · STATE)` with dynamic truncation for long serials to prevent horizontal UI clipping.
- **Monospace CLI Device Specifications Banner**: Clean engineering hardware banner displaying friendly model name, chipset SoC, fastboot high-speed serial, active boot slot, verified bootloader state, mapped partition count, and detected guard overlays.
- **Actionable Diagnostic Modals**: Added intelligent pattern matching in `ErrorDiagnostics` for MediaTek Preloader / VCOM detection timeouts, linking directly to a 6-step physical troubleshooting modal with Windows Device Manager driver verification.

#### Forensic Logging Architecture
- **Dedicated Forensic Disk Logging Engine (`DebugLogger`)**: Automatically initializes a persistent, timestamped log file (`BL/logs/tfast_debug_YYYYMMDD_HHMMSS.log`) on workstation launch. Captures microsecond-accurate timings, thread identifiers, raw command payloads, subprocess standard output/error buffers, and full Python tracebacks.
- **Top Bar & Side Toolbar Debug Toggles**: Real-time synchronized switches (`DEBUG: ON` / `DEBUG: OFF`) allowing technicians to enable or pause technical disk recording at any point during a session.

---

### Fixed

#### Bug Fixes & Stability
- **Eliminated Idle Background Log Spam**: Fixed periodic `_auto_probe` timer (running every 8 seconds) from flooding the visual Activity Log with repetitive `[DEBUG] [FASTBOOT] >>> fastboot devices` entries while the workstation is idle.
- **Architectural UI/Disk Log Separation**: Completely removed raw low-level command outputs (`>>> fastboot ...`, `<<< RC=0 in ...`, `[OP-xxxxx]`) from the user-facing on-screen console. Deep technical traces are now recorded exclusively to disk log files in `BL/logs/`, keeping the UI calm, high-level, and readable.
- **Suppressed Raw Python Stack Traces in UI**: Replaced unhandled `traceback.print_exc()` calls in background workers with safe routing to `debug_logger.log("TRACEBACK", ...)`. Hardware detection timeouts and serial disconnects now render as clean warning notices rather than intimidating code dumps.
- **Restored Native Win32 Titlebar & Taskbar Icon**: Resolved an issue where Windows reverted to the default Tkinter feather/quill icon. 
  - Bound `self.iconbitmap(str(ICON_ICO))` directly to the root window.
  - Injected exact 16x16 (small/titlebar) and 32x32 (large/taskbar & Alt-Tab) native `HICON` handles via Win32 `WM_SETICON`.
  - Registered `tfast.bootloader.workstation.2.0` with Windows Shell via `SetCurrentProcessExplicitAppUserModelID` so the taskbar groups and displays the genuine TFast brand logo instead of the Python interpreter.
  - Bypassed conflicting `iconphoto(True, PhotoImage)` calls on Windows platforms.
- **Fixed Instantaneous META Connection Crash**: Resolved `PartitionError: No MediaTek serial port found` triggering in under 30ms when clicking `Connect META Port` before a phone was inserted.
- **Corrected Tkinter Geometry Pack Error**: Fixed invalid tuple `pady=(10, 3)` passed to `tk.Label` widget constructors by moving vertical padding directly to the `.pack()` layout manager.

#### Aesthetic & Styling Cleanup
- **Eliminated "AI Slop" & Consumer Emojis**: Systematically stripped consumer toy emojis (`⚡`, `📊`, `🔓`, `🧹`, `🧬`, `🗄️`, `🔌`, `📦`, `📱`, `🐞`, `📋`, `⟳`, `🚀`, `🔍`, `⚠️`) across sidebar navigation items, page headers, cards, action buttons, and modal dialogs.
- **Removed Cluttered Sidebar Footer Box**: Completely removed the redundant bottom-left sidebar panel containing social URLs, copyright lines, and duplicate version stamps. Visual space is now dedicated entirely to crisp uppercase category sections (**WORKFLOW**, **FASTBOOT CORE**, **META & HARDWARE**, **RESOURCES**). Attribution remains anchored cleanly in the bottom statusbar and top About dialog.

---

### Technical Specifications & Standards

| Parameter | Specification |
| :--- | :--- |
| **Fastboot Protocol** | Android Platform-Tools Fastboot v35.0.0+ |
| **Serial Protocol** | MediaTek BootROM / Preloader Handshake (USB VID `0x0E8D`) |
| **Data Encoding** | Chunked Base64 `dd`-over-shell with cryptographic SHA-256 verification |
| **LK Disassembly** | ARM32 / ARM64 (AArch64) in-place pattern matching & 4-byte patch injection |
| **Integrity Seal** | Six-layer tamper-evident manifest verification (`tools/tfast_seal.py`) |
| **Supported OS** | Windows 10 (x64) / Windows 11 (x64) |
| **Python Runtimes** | Python 3.11, 3.12, 3.13, 3.14 (Bundled CPython 3.14 portable harness) |
