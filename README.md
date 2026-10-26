# TFast MTK Bootloader Tool — Pro Desktop & CLI Suite

**Version 2.0.0** · *Industrial-Grade MediaTek (MTK) & Transsion Bootloader Unlock, Little Kernel (LK) Binary Patcher, and META Partition Engineering Suite.*

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://tfastdigital.com/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20x64-0078d7.svg)](https://tfastdigital.com/)
[![Runtime](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-green.svg)](https://python.org/)
[![Brand](https://img.shields.io/badge/brand-TFast%20Digital-7c3aed.svg)](https://tfastdigital.com/)

> **Copyright © 2025-2026 [TFast Digital Agency](https://tfastdigital.com/). All rights reserved.**  
> Built and maintained by TFast Digital Agency.
>
> | Resource | Destination |
> | :--- | :--- |
> | **Website** | [https://tfastdigital.com/](https://tfastdigital.com/) |
> | **GitHub Organization** | [https://github.com/tfastdigital](https://github.com/tfastdigital) |
> | **Telegram Channel** | [https://t.me/tfasthub](https://t.me/tfasthub) |
> | **WhatsApp Channel** | [https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a](https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a) |

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [How It Works (Under the Hood)](#how-it-works-under-the-hood)
   - [Fastboot Core Pipeline & FENIX Handshake](#1-fastboot-core-pipeline--fenix-handshake)
   - [Little Kernel (LK) 4-Byte Binary Patcher](#2-little-kernel-lk-4-byte-binary-patcher)
   - [Transsion Anti-Tamper Guard Neutralization](#3-transsion-anti-tamper-guard-neutralization)
   - [MediaTek Preloader / BootROM META Protocol](#4-mediatek-preloader--bootrom-meta-protocol)
3. [Comprehensive GUI Reference & Button Guide](#comprehensive-gui-reference--button-guide)
   - [Top Navigation Chrome & Activity Console Toolbar](#top-navigation-chrome--activity-console-toolbar)
   - [Page 1: Guided Unlock Wizard](#page-1-guided-unlock-wizard)
   - [Page 2: Hardware Dashboard](#page-2-hardware-dashboard)
   - [Page 3: Bootloader Unlock](#page-3-bootloader-unlock)
   - [Page 4: OEM Guard Wipe](#page-4-oem-guard-wipe)
   - [Page 5: Flash Custom Firmware](#page-5-flash-custom-firmware)
   - [Page 6: Reboot & Diagnostic Targets](#page-6-reboot--diagnostic-targets)
   - [Page 7: Little Kernel (LK) Patch & Analysis](#page-7-little-kernel-lk-patch--analysis)
   - [Page 8: META Partition Manager](#page-8-meta-partition-manager)
   - [Page 9: Hardware META Mode Unlock](#page-9-hardware-meta-mode-unlock)
   - [Page 10: Patch Bundle Builder](#page-10-patch-bundle-builder)
   - [Page 11: Supported Models Catalog](#page-11-supported-models-catalog)
4. [Command-Line Interface (CLI) Reference](#command-line-interface-cli-reference)
5. [Operational Risks & Safety Protocols](#operational-risks--safety-protocols)
6. [Prerequisites & Quick Start](#prerequisites--quick-start)
7. [Attribution, Security Seal & Integrity Verification](#attribution-security-seal--integrity-verification)
8. [License & Third-Party Notices](#license--third-party-notices)

---

## Project Overview

**TFast MTK Bootloader Tool** is an engineering-grade workstation designed specifically for servicing, unlocking, and repairing modern MediaTek (MTK) smartphones and tablets, with specialized support for Transsion platforms (**Tecno**, **Infinix**, **itel**).

Modern Transsion devices enforce aggressive multi-layer security protections:
- **Fastboot Lockouts**: Stock Little Kernel (LK) images gate all flashing operations behind hardware lock control and reject standard OEM unlock commands (`flashing unlock`).
- **Anti-Tamper Guard Overlays**: Hidden partitions (`tr_product`, `tr_vendor`, `tr_system`) monitor system integrity at boot. If unsigned binaries are detected, the device triggers bootloops, NVRAM corruption, or "Red State" verification halts.
- **AVB 2.0 & dm-verity**: Android Verified Boot checks cryptographically enforce signature chains across `vbmeta`, `boot`, and `super` partitions.

This suite provides both an **interactive desktop GUI** (built on Tkinter with native Win32 window chrome and real-time telemetry) and a **scriptable CLI**, providing complete coverage for:
1. Fastboot-level Little Kernel stage injection and unlock handshakes.
2. Complete neutralization of OEM guard partitions.
3. In-place binary disassembly, pattern matching, and 4-byte unlock patching for raw Little Kernel (`lk.bin`) files.
4. Preloader / BootROM serial communication over the MediaTek META protocol for hardware `seccfg` unlocking and chunked partition reading, writing, and wiping.

---

## How It Works (Under the Hood)

### 1. Fastboot Core Pipeline & FENIX Handshake
When unlocking a device through Fastboot, the tool executes an automated 5-stage pre-flight pipeline:
1. **Hardware Link Probing**: Sends `fastboot getvar all` to extract real-time hardware variables (`current-slot`, `product`, `hardware`, `unlocked`, partition maps).
2. **FRP Zeroing**: Zeroes out Google Factory Reset Protection (`frp`) flags to prevent device lockout post-wipe.
3. **AVB Flag Mutation**: Patches the target `vbmeta` flags to `--flags 3` (`AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED | AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED`), completely disabling DM-verity and hash-tree verification.
4. **FENIX Handshake**: Transmits proprietary OEM handshake sequences recognized by Transsion MediaTek bootloaders when standard commands are rejected.
5. **Patched LK Injection**: Flashes unlocked Little Kernel stages (`lk_a.unlocked.bin`, `lk_b.unlocked.bin`) into active and inactive slots to permanently remove fastboot flashing restrictions.

### 2. Little Kernel (LK) 4-Byte Binary Patcher
The offline patcher (`BootloaderPatcher`) disassembles raw ARM32/ARM64 Little Kernel binaries in-place:
- Scans for proprietary fastboot lock gating logic:
  - Branch conditional instructions evaluating lock flags (`CBZ`, `CBNZ`, `TBZ`, `TBNZ`, `B.NE`, `B.EQ`).
  - Fastboot command lookup tables (`fastboot:flash`, `fastboot:erase`, `fastboot:unlock`).
- Applies verified 4-byte ARM patch sequences (replacing branch instructions with `NOP` `0x1F2003D5` on AArch64 or immediate unconditionals) that force the LK engine to treat all fastboot commands as authorized.
- Performs dry-run hash verification and creates a `.bak` copy before modifying a single byte on disk.

### 3. Transsion Anti-Tamper Guard Neutralization
Transsion implements custom protection overlays known as `trash` partitions:
- `tr_product`: Enforces product-level partition mounting restrictions.
- `tr_vendor`: Validates vendor hardware signatures against bootloader tokens.
- `tr_system`: Mounts read-only integrity overlays on `/system`.

The **OEM Guard Wipe** engine wipes these partitions cleanly once the bootloader is unlocked. By formatting both the header and footer blocks and re-verifying the empty state, it guarantees the phone will boot cleanly without triggering "Red State" hardware verification panics.

### 4. MediaTek Preloader / BootROM META Protocol
When fastboot commands are completely disabled by hardware security fuses:
- Interfaces with the MediaTek Preloader / BootROM serial COM port (USB VID `0x0E8D`).
- Executes chunked Base64 `dd`-over-shell commands over the serial transport (`mtk_meta_protocol`).
- Directly clears the `seccfg` (Security Configuration) block in NVRAM storage, flipping the hardware bootloader lock bit at the silicon level.

---

## Comprehensive GUI Reference & Button Guide

Below is the definitive reference for every button, control, and display element across all 11 pages of the Desktop Edition:

### Top Navigation Chrome & Activity Console Toolbar

| Control | Type | Purpose & Action |
| :--- | :--- | :--- |
| **Connection Pill** | Display Badge | Displays live device state: `FASTBOOT: [serial] (Slot X · LOCKED/UNLOCKED)` in green when connected, or `DEVICE: OFFLINE (Connect USB)` in dark slate when disconnected. |
| **Scan (F5)** | Button | Triggers an immediate hardware probe across USB fastboot interfaces. Updates active slot, serial, lock status, and logs a clean scan summary. |
| **DEBUG: ON / DEBUG: OFF** | Button | Toggles technical diagnostic mode. When ON, all fastboot commands, timings, thread IDs, and exit codes are recorded to disk in `BL/logs/`. The visual UI remains clean. |
| **Activity Logs** | Button | Expands or collapses the shared persistent right-side Activity Log drawer. |
| **About** | Button | Displays official legal copyright, brand registration, runtime diagnostics, and TFast Digital Agency web links. |
| **Clear** | Log Toolbar Button | Clears the visible Activity Log screen buffer (Keyboard shortcut: `Ctrl+L`). |
| **Copy** | Log Toolbar Button | Copies the entire contents of the Activity Log to the Windows clipboard. |
| **Save** | Log Toolbar Button | Prompts a save dialog to export the activity log to a custom `.txt` or `.log` file. |
| **Logs Folder** | Log Toolbar Button | Opens Windows Explorer directly at `BL/logs/` where deep forensic session logs are stored. |
| **Auto-scroll: ON/OFF** | Log Toolbar Button | Toggles automatic scrolling to the latest log line as events occur. |

---

### Page 1: Guided Unlock Wizard
*A linear, foolproof 5-stage pipeline guiding technicians through the full unlock procedure.*

- **Stage 1: Pre-Flight Verification**:
  - `Probe Device (F5)`: Manually queries the connected phone to verify Fastboot communication and display slot/lock attributes.
  - `Reboot to Bootloader`: Sends a fastboot directive to ensure the phone is firmly halted in Bootloader mode.
- **Stage 2: Model & Patched Binary Selection**:
  - `Filter`: Text search box that filters the verified offline/remote handset catalog in real time.
  - `Target`: Dropdown selection box containing matched model profiles and LK stage requirements.
- **Stage 3: Automated Unlock Execution**:
  - `Keep device in fastboot mode after unlock`: Checkbox (Checked by default). Prevents the device from booting Android immediately post-unlock, allowing seamless transition to Stage 4.
  - `Execute Unlock Pipeline`: Initiates the automated unlock workflow (FRP zeroing, LK stage flashing, AVB disable, and unlock handshake).
- **Stage 4: OEM Anti-Tamper Guard Wipe**:
  - `Wipe Guard Partitions`: Wipes `tr_product`, `tr_vendor`, `tr_system` overlays to prevent red state bootloops.
- **Stage 5: Final Reboot**:
  - `Normal Reboot (System)`: Reboots the handset normally into the Android operating system.
  - `Reboot to Recovery`: Boots into recovery mode (TWRP, OrangeFox, or stock recovery) for GSI flashing or data wipes.

---

### Page 2: Hardware Dashboard
*Comprehensive real-time telemetry center for connected devices.*

- **Telemetry Cards**:
  - Displays Hardware Link state, Serial Number, Fastboot Protocol Mode, Active Slot (`a` or `b`), Bootloader Lock Status, Mapped Partition Count, Detected Guard Overlays, and Critical Boot Partition availability.
- **Action Buttons**:
  - `Refresh Status (F5)`: Executes deep `fastboot getvar all` query to refresh all hardware status cards.
  - `Copy Device Info`: Formats all detected hardware specifications into a clean table and copies it to your clipboard.

---

### Page 3: Bootloader Unlock
*Direct standalone access to the LK injection and FENIX unlock pipeline.*

- `Keep device in fastboot mode after unlock`: Toggles whether the phone reboots or remains in bootloader mode.
- `Execute Unlock Pipeline`: Executes the full unlock sequence directly.

---

### Page 4: OEM Guard Wipe
*Post-unlock cleanup to purge vendor anti-tamper overlays.*

- `Partitions Targeted for Wipe`: Visual chips showing detected guard partitions (`tr_product`, `tr_vendor`, `tr_system`).
- `Also erase product and system_ext`: Checkbox. When enabled, also purges `product` and `system_ext` partitions referenced by the guard overlays. *(Required if installing Generic System Images / GSI).*
- `Wipe Guard Partitions`: Executes verified zero-fill wipes on the targeted guard partitions. Gated behind unlock verification (will refuse to run on locked devices).
- `Re-Scan Device`: Re-probes partition layout to confirm successful erasure.

---

### Page 5: Flash Custom Firmware
*Slot-aware firmware flasher with automated verification bypass.*

- `vbmeta.img (AVB disabled)` + `Browse`: Selects a clean or AVB-disabled vbmeta binary.
- `custom system image` + `Browse`: Selects an optional custom Android GSI or system binary (`system.img`).
- `Reboot device automatically when flashing finishes`: Checkbox to automate system reboot post-flash.
- `Flash Images to Active Slot`: Flashes selected images to the current boot slot using `--disable-verity` and `--disable-verification` flags.

---

### Page 6: Reboot & Diagnostic Targets
*Directive dispatcher for hardware reboot sequences.*

- **Target Directives**:
  - `Normal Android System Boot`: Directs phone to boot into full Android OS.
  - `Fastboot Bootloader Mode`: Reboots back into bootloader for further maintenance.
  - `Fastbootd (Userspace Recovery)`: Reboots into userspace fastbootd mode for dynamic / `super` partition servicing.
  - `Stock / Custom Recovery`: Reboots into recovery partition.
- `Send Reboot Directive`: Transmits the selected reboot command immediately.

---

### Page 7: Little Kernel (LK) Patch & Analysis
*In-place binary analyzer and 4-byte unlock patcher for raw LK binaries.*

- `Stock LK Image` + `Browse`: Selects a local Little Kernel binary (`lk.bin`, `lk_a.bin`, `lk_b.bin`).
- `Analyze LK Binary`: Disassembles the binary, identifies the CPU architecture (ARM32 / AArch64), and searches for fastboot lock evaluation patterns.
- `Dry Run LK Patch`: Simulates the patch in memory without modifying the file. Reports exact hex offsets and replacement opcodes.
- `Patch LK In Place`: Safely patches the binary on disk and creates an automatic `.bak` copy.

---

### Page 8: META Partition Manager
*Direct read, write, backup, restore, and wipe access over the MediaTek serial protocol.*

- **Section 1: Connection & Session**:
  - `Target Port`: Dropdown list of detected serial COM ports (Defaults to `Auto-detect`).
  - `Scan Ports`: Re-scans Windows COM ports and populates the dropdown.
  - `Connect META Port`: Starts a 30-second listening window to establish a META session when the phone is plugged in with Volume Down held.
  - `Reboot to META (Fastboot)`: One-click fastboot command that tells a connected fastboot phone to reboot directly into META mode automatically.
  - `Refresh Table`: Queries the partition layout over the META shell and repopulates the explorer tree.
  - `Disconnect`: Terminates the serial session cleanly.
- **Section 2: Partition Explorer**:
  - `Filter`: Real-time text search for partition names (e.g., `boot`, `nvram`, `seccfg`).
  - Quick Filter Presets: `Critical` (boot, lk, vbmeta), `Guards` (tr_*), `Safe` (safe to backup), `All` (complete partition map), `Clear` (clears filter).
  - Partition Tree: Lists Partition Name, Size (Human-readable), Detection Source (`dumchar`/`by-name`), and Protection State (`PROTECTED` vs `UNPROTECTED`).
- **Section 3: Partition Operations**:
  - `File` / `Folder`: File selection controls for dump/restore operations.
  - `Open Folder`: Opens the workspace output folder in Windows Explorer.
  - Speed Presets: `Safe` (conservative chunking), `Balanced` (standard), `Fast` (high throughput), `Turbo` (maximum chunk rate).
  - `Measure Benchmark`: Benchmarks transfer rate against a selected partition.
  - Mode Buttons:
    - `Back up`: Dumps selected partition to `BL/workspace/partitions/`.
    - `Export`: Exports multiple selected partitions in bulk.
    - `Restore`: Restores a previously saved backup image.
    - `Replace`: Replaces partition contents with a selected image file.
    - `Wipe`: Cryptographically zeroes the partition and verifies removal of filesystem headers.
    - `Probe`: Reads head bytes and reports filesystem type (`ext4`, `erofs`, `AVB0`, `ANDROID!`).

---

### Page 9: Hardware META Mode Unlock
*Direct hardware NVRAM `seccfg` unlock for devices with locked fastboot interfaces.*

- `Serial COM Port` + `Scan Ports`: Chooses target serial port or Auto-detect.
- `Execute Hardware META Unlock`: Clears the bootloader security configuration flag in NVRAM over the serial link.
- `How to Enter MTK Preloader Mode`: Embedded physical guide detailing the exact button sequences.

---

### Page 10: Patch Bundle Builder
*Prepares automated deployment bundles for specific models.*

- `Target Model`: Selects model profile from the verified catalog.
- `Original vbmeta.img (optional)` + `Browse`: Selects stock vbmeta for patch integration.
- `Prepare Patch Bundle`: Synthesizes ready-to-flash payloads into the local workspace.
- `Refresh List` / `Open Workspace`: Manages staged artifacts in `BL/workspace/`.

---

### Page 11: Supported Models Catalog
*Filterable catalog of verified MediaTek and Transsion handsets.*

- Real-time search filter across model names, marketing designations, codenames, chipsets (e.g., `MT6789`, `MT6877`, `MT6765`), and required LK stages.
- Automatically caches data offline in `BL/offline_repo/models.json` for operations without internet access.

---

## Command-Line Interface (CLI) Reference

The tool includes a full CLI accessible via `BL\tfast-cli.bat` or `python bl.py`:

```bash
# 1. Probe connected Fastboot hardware
python bl.py scan

# 2. Execute automated bootloader unlock
python bl.py unlock --model "Tecno Spark 40 Pro" --keep-fastboot

# 3. Wipe OEM anti-tamper guard partitions
python bl.py wipe-trash                    # Wipes tr_* and product/system_ext
python bl.py wipe-trash --guard-only       # Wipes only tr_product, tr_vendor, tr_system

# 4. Slot-aware firmware flashing
python bl.py flash-custom --vbmeta vbmeta.img --system system.img --reboot

# 5. Hardware META Mode unlock (NVRAM seccfg)
python bl.py meta-unlock                   # Auto-detects Preloader port
python bl.py meta-unlock --port COM5       # Specific COM port

# 6. Analyze and patch Little Kernel (LK) binary
python bl.py lk-patch lk.bin --analyze     # Forensic scan
python bl.py lk-patch lk.bin --dry-run     # Simulate patch
python bl.py lk-patch lk.bin --in-place    # Patch on disk with .bak backup

# 7. META Partition Manager CLI
python bl.py meta-parts                    # List all partitions over serial
python bl.py meta-backup boot lk vbmeta    # Back up key partitions
python bl.py meta-wipe system              # Zero and verify wipe
python bl.py meta-bench lk                 # Benchmark transfer rate

# 8. Reboot directives
python bl.py reboot --target system        # Normal boot
python bl.py reboot --target bootloader    # Fastboot
python bl.py reboot --target recovery      # Recovery
python bl.py reboot --target fastboot      # Fastbootd
```

---

## Operational Risks & Safety Protocols

> [!CAUTION]
> **Modifying device bootloaders carries inherent risks.** Misuse or interruptions can result in soft-bricks, bootloops, or permanent device damage. Adhere strictly to the safety protocols below:

1. **Anti-Rollback Protection (ARB)**:
   Never flash Little Kernel (`lk.bin`) stages from an older major Android version than the firmware currently running on the device. MediaTek fuses hardware rollback counters in RPMB; flashing an older LK can trigger a hardware boot halt.
2. **Brick-Risk Partition Protection**:
   The META Partition Manager contains built-in safety locks refusing direct operations on critical silicon partitions:
   - `preloader`, `pgpt`, `sgpt`, `nvram`, `nvdata`, `proinfo`, `seccfg`.
   - Modifying or erasing NVRAM/NVDATA will wipe your device's unique IMEI, calibration data, and MAC addresses. The tool strictly gates these partitions behind explicit confirmation flags.
3. **Power Stability**:
   Ensure the device battery has at least **50% charge** before initiating flashing or wipe pipelines. A device powering off mid-write will corrupt the partition table.
4. **USB Connection Quality**:
   Always connect directly to a rear motherboard USB port using a high-quality USB-C/micro-USB data cable. **Do not use unpowered USB hubs or loose front-panel ports**, as serial transmission errors during META operations can interrupt critical transfers.
5. **Data Backup**:
   Unlocking the bootloader automatically enforces a factory data wipe by Android operating system specification. Back up all personal files beforehand.

---

## Prerequisites & Quick Start

### System Requirements
- **OS**: Windows 10 or Windows 11 (64-bit).
- **USB Drivers**:
  - Android Bootloader Interface (Fastboot) driver.
  - MediaTek USB VCOM / PreLoader USB driver (for META mode operations).
- **Python**: Python 3.11, 3.12, 3.13, or 3.14. *(A portable Python 3.14 runtime environment is included in `BL/py314_runtime/` for standalone operation).*

### Launching the Suite

- **Launch Desktop GUI**:
  Double-click `tfast-gui.bat` in the project root.
- **Launch Command-Line Interface (CLI)**:
  Double-click `tfast-cli.bat` or open PowerShell in the directory:
  ```powershell
  .\tfast-cli.bat --help
  ```

---

## Attribution, Security Seal & Integrity Verification

To protect brand reputation and prevent unauthorized re-branding or malicious redistribution, the suite enforces a **six-layer tamper-evident brand integrity seal**:

1. **In-Memory Constants**: Legal attribution primitives verified against canonical SHA-256 signatures.
2. **On-Disk Manifest**: [`tfast-brand.json`](tfast-brand.json) records SHA-256 cryptographic hashes of all sealed modules.
3. **Manifest Self-Seal**: The manifest seals its own metadata structure.
4. **Source Watermarks**: Explicit `@brand tfast-digital` watermarks embedded across entry files.
5. **Runtime Guard Watch**: Background watchdog (`GuardWatch`) periodically verifies memory and module pointers while the application is active.
6. **Notice File Integrity**: [`tfast-NOTICE.txt`](tfast-NOTICE.txt) must name TFast Digital Agency.

### Verifying Brand Integrity
You can verify the codebase seal at any time using the bundled verification tool:
```powershell
python tools\tfast_seal.py --check
```
*Expected Output:*
```text
[+] Brand and copyright integrity verified.
```

---

## License & Third-Party Notices

This software is proprietary software developed by **TFast Digital Agency**. All rights reserved.

- Complete licensing terms and attribution requirements are set forth in [`tfast-NOTICE.txt`](tfast-NOTICE.txt).
- Bundled third-party components (Android Fastboot binaries, `pyserial`, `requests`, Python runtime) remain licensed under their respective open-source licenses (Apache 2.0, BSD 3-Clause, PSF License).
