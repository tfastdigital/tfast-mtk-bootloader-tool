# Terms of Use, EULA and Hardware Risk Disclaimer

**Product:** TFast MTK Bootloader Tool (Desktop & CLI Editions)  
**Version:** 2.0.0  
**Brand ID:** `tfast-digital`  
**Copyright:** &copy; 2025–2026 TFast Digital Agency. All rights reserved.  
**Website:** [https://tfastdigital.com/](https://tfastdigital.com/)  
**GitHub:** [https://github.com/tfastdigital](https://github.com/tfastdigital)  
**Effective Date:** October 26, 2026  

---

## IMPORTANT LEGAL NOTICE — READ CAREFULLY

THIS IS A BINDING LEGAL AGREEMENT BETWEEN YOU (EITHER AN INDIVIDUAL OR A LEGAL ENTITY, HEREINAFTER REFERRED TO AS "YOU", "USER", OR "LICENSEE") AND **TFAST DIGITAL AGENCY** (HEREINAFTER REFERRED TO AS "TFAST DIGITAL", "WE", "US", OR "LICENSOR").

BY DOWNLOADING, CLONING, INSTALLING, RUNNING, COMPILING, DISTRIBUTING, OR OTHERWISE USING ANY PART OF THE **TFAST MTK BOOTLOADER TOOL** (INCLUDING BOTH THE GRAPHICAL USER INTERFACE AND COMMAND-LINE INTERFACE, ASSOCIATED SCRIPTS, PYTHON MODULES, CONFIGURATIONS, BINARIES, ASSETS, AND DOCUMENTATION, COLLECTIVELY THE "SOFTWARE"), YOU EXPLICITLY AND UNCONDITIONALLY AGREE TO BE BOUND BY THE TERMS AND CONDITIONS OF THIS DOCUMENT ("TERMS OF USE" / "AGREEMENT").

IF YOU DO NOT AGREE TO THESE TERMS, DO NOT DOWNLOAD, INSTALL, EXECUTE, OR USE THIS SOFTWARE. IMMEDIATELY DELETE ALL COPIES IN YOUR POSSESSION.

---

## 1. Definitions

1. **"Software"**: The TFast MTK Bootloader Tool suite, comprising `bl.py`, `gui.py`, all modules under `bl_core/`, bundled launchers (`tfast-gui.bat`, `tfast-cli.bat`), assets, configuration templates, and operational documentation.
2. **"Hardware" or "Device"**: Any smartphone, tablet, development board, IoT terminal, or computing device powered by a MediaTek (MTK) System-on-Chip (SoC) connected via USB to the host computer.
3. **"Bootloader"**: The low-level initial program load firmware (`lk`, `lk2`, `preloader`, `bootloader`) executing on the hardware device prior to the Android OS kernel initialization.
4. **"Fastboot Mode"**: The Android standard protocol and bootloader execution state allowing host machines to query device status, OEM lock states, and flash partition images via USB.
5. **"META Mode"**: The MediaTek Engineering Testing Architecture state enabling direct low-level partition read, write, dump, and NVRAM access via virtual COM/serial handshake.
6. **"NVRAM / NVDATA"**: Critical flash partitions holding persistent device-specific hardware calibration data, RF calibration tables, MAC addresses, and International Mobile Station Equipment Identity (IMEI) data.
7. **"Tamper-Evident Brand Guard"**: The cryptographic verification mechanism implemented in `bl_core/tfast_guard.py`, `tfast-brand.json`, and associated watermarks that verifies the authenticity and licensing attribution of this Software.

---

## 2. End-User License Agreement (EULA)

### 2.1 License Grant
Subject to the strict compliance with this Agreement and applicable laws, TFast Digital Agency grants you a limited, non-exclusive, revocable, non-transferable, and non-sublicensable license to:
- Execute and operate the Software on your personal or workshop computers for lawful hardware diagnostics, servicing, flashing, repair, and authorized firmware deployment.
- Inspect and modify the source code solely for personal research, debugging, and lawful operational tailoring within your local environment.

### 2.2 Proprietary Ownership & Intellectual Property
The Software is licensed, not sold. All rights, title, and interest in and to the Software—including without limitation all copyrights, trademarks, brand names, visual logos, interface designs, algorithms, code structures, documentation, and the name "TFast Digital"—are and shall remain the exclusive property of TFast Digital Agency.

### 2.3 Mandatory Attribution Requirements
In accordance with [`tfast-NOTICE.txt`](tfast-NOTICE.txt):
1. **Preservation of Notices**: All copyright notices, legal attributions, and author watermarks (`# @brand tfast-digital`) embedded within the source files, UI dialogues, CLI banners, and documentation must remain intact, unaltered, and conspicuously visible in all distributions, forks, or derivative copies.
2. **Integrity Enforcement**: You shall not bypass, strip, defeat, or manipulate the cryptographic hash verification system (`tools/tfast_seal.py`, `tfast-brand.json`, `bl_core/tfast_guard.py`) designed to confirm authentic attribution.
3. **White-Labeling Prohibited**: Presenting, selling, or distributing this Software or any derivative thereof under another commercial trade name or claiming primary authorship is strictly prohibited and constitutes an actionable infringement under applicable copyright and unfair trade practice laws.

---

## 3. Acceptable Use Policy (AUP) & Ethical Guidelines

This Software is a specialized hardware diagnostic and engineering suite created for legitimate device servicing, academic security research, and OEM firmware recovery. You represent, warrant, and covenant that you will use this Software strictly in accordance with ethical standards and all applicable local, national, and international laws.

### 3.1 Permitted Uses
- Diagnostic querying and unlocking of bootloaders on hardware owned by you or for which you have received express, written, verifiable authorization from the legal owner to service.
- Restoring official manufacturer stock firmware (ROMs) to unbrick malfunctioning devices.
- Flashing lawful open-source operating systems, aftermarket recoveries (TWRP/OrangeFox), and legitimate custom Android kernels.
- Creating forensic safety backups of partitions (`nvram`, `nvdata`, `boot`, `recovery`, `vbmeta`) prior to firmware upgrades.
- Academic hardware and security research in controlled laboratory environments.

### 3.2 Strictly Prohibited Activities
You expressly agree NOT to use the Software for:
1. **Lost, Stolen, or Unauthorized Devices**: Performing bootloader unlocking, partition erasing, or security state manipulation on devices reported lost, stolen, or obtained without lawful owner consent.
2. **Illicit Security Bypass**: Bypassing, circumventing, or defeating Anti-Theft systems, Factory Reset Protection (FRP), carrier locks, or mobile device management (MDM) policies for fraudulent or unlawful purposes.
3. **Telecommunications Fraud & Identity Tampering**: Modifying, rewriting, spoofing, erasing, or cloning IMEI, MEID, or hardware serial numbers in contravention of telecommunications statutory laws (e.g., US Mobile Device Theft Prevention legislation, EU regulations, and local frequency management laws).
4. **Malicious Distribution**: Bundling or deploying the Software alongside spyware, adware, trojans, ransomware, or malicious payloads designed to compromise host computers or target mobile hardware.
5. **Re-Packaging as AI-Generated or Unbranded Clones**: Stripping TFast Digital Agency attribution to falsely misrepresent the engineering origin of this application.

Violation of this Acceptable Use Policy results in the immediate, automatic termination of your license and may expose you to civil liabilities and criminal prosecution under applicable laws.

---

## 4. Hardware Risks & Assumption of Risk

> [!CAUTION]
> **FLASHING AND BOOTLOADER OPERATIONS CARRY INHERENT RISK OF PERMANENT HARDWARE DAMAGE.**

You acknowledge and agree that low-level hardware servicing involves significant technical risks. By initiating any unlock, flash, erase, or partition operation, you voluntarily assume full responsibility for any and all outcomes:

### 4.1 Permanent Hardware Brick Risks
- **Preloader & Bootloader Disruption**: Corrupting or mismatching the `preloader`, `lk`, `lk2`, or partition table (`pgpt`, `gpt`) can cause the device to enter an unrecoverable "hard-brick" state where USB enumeration fails, requiring physical test-point (EDL/BROM) probing or chip-off reprogramming.
- **Anti-Rollback (ARB) Traps**: Certain OEMs (including Xiaomi, Motorola, Transsion, and others) embed hardware-fused Anti-Rollback counters in eFuses or RPMB. Flashing firmware with an older security patch level may permanently blow hardware fuses or lock the device into a non-bootable state.
- **Power Failure Hazards**: Any power loss, host system freeze, or loose USB connection during critical partition writes (especially `preloader`, `boot`, or `vbmeta`) can leave the NAND/UFS flash memory in a corrupt state.

### 4.2 Security State & DRM Attestation Downgrades
Unlocking a device bootloader inherently:
- Trips hardware integrity flags (e.g., eFuse triggers, knox/warranty bits).
- Permanently voids or limits manufacturer warranties.
- Revokes Widevine DRM Level 1 certifications, downgrading media streaming playback to Standard Definition (Widevine L3).
- Invalidates Google SafetyNet / Android Play Integrity hardware-backed attestation, disabling banking, financial, and digital wallet applications.
- Clears hardware-backed cryptographic keys stored in the TrustZone / TEE / Keystore.

### 4.3 Calibration & Radio Data Loss Warning
- **Mandatory NV Backup**: The partitions `nvram`, `nvdata`, `protect1`, `protect2`, `nvcfg`, and `sec1` store device-unique RF calibration tables, network band calibrations, and IMEI information.
- Erasing or flashing generic images over these partitions causes immediate cellular signal failure (No Service / Invalid IMEI).
- **You are solely responsible for creating and safely storing verifiable backups of these partitions before attempting any write or unlock procedure.**

---

## 5. Disclaimer of Warranties

TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW:

1. **"AS IS" AND "AS AVAILABLE"**: THE SOFTWARE IS PROVIDED ON AN "AS IS" AND "AS AVAILABLE" BASIS, WITH ALL FAULTS, DEFECTS, AND ERRORS, AND WITHOUT WARRANTY OF ANY KIND.
2. **NO IMPLIED WARRANTIES**: TFAST DIGITAL AGENCY AND ITS AFFILIATES, OFFICERS, EMPLOYEES, AND CONTRIBUTORS HEREBY EXPRESSLY DISCLAIM ALL WARRANTIES, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE, INCLUDING BUT NOT LIMITED TO:
   - IMPLIED WARRANTIES OF MERCHANTABILITY, SATISFACTORY QUALITY, FITNESS FOR A PARTICULAR PURPOSE, AND WORKMANLIKE EFFORT;
   - WARRANTIES OF TITLE, QUIET ENJOYMENT, AND NON-INFRINGEMENT OF THIRD-PARTY RIGHTS;
   - WARRANTIES ARISING FROM ANY COURSE OF DEALING, USAGE, OR TRADE PRACTICE.
3. **NO OPERATIONAL GUARANTEE**: LICENSOR DOES NOT WARRANT THAT:
   - THE FUNCTIONS CONTAINED IN THE SOFTWARE WILL MEET YOUR SPECIFIC WORKSHOP OR TECHNICAL REQUIREMENTS;
   - THE OPERATION OF THE SOFTWARE WILL BE UNINTERRUPTED, BUG-FREE, OR ERROR-FREE;
   - ANY DEFECTS IN TARGET HARDWARE, FASTBOOT PROTOCOLS, OR USB CONTROLLERS WILL BE RECOVERED OR REPAIRED;
   - THE SOFTWARE WILL BE COMPATIBLE WITH EVERY MEDIATEK SOC CHIPSET, VARIANT, OR FUTURE SECURITY PATCH LEVEL RELEASED BY DEVICE MANUFACTURERS.

---

## 6. Limitation of Liability

TO THE FULLEST EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL **TFAST DIGITAL AGENCY**, ITS DEVELOPERS, DIRECTORS, AGENTS, SUPPLIERS, OR LICENSORS BE LIABLE TO YOU OR ANY THIRD PARTY FOR:

1. **ANY SPECIAL, INCIDENTAL, INDIRECT, PUNITIVE, OR CONSEQUENTIAL DAMAGES WHATSOEVER**;
2. **ANY PHYSICAL HARDWARE DAMAGES**, INCLUDING BUT NOT LIMITED TO PERMANENTLY BRICKED SMARTPHONES, DAMAGED USB CONTROLLERS, BURNED EMMC/UFS CHIPS, OR TRIPPED HARDWARE EFUSES;
3. **ANY LOSS OF DATA**, CORRUPTION OF PARTITIONS, ACCIDENTAL DELETION OF USER FILES, OR LOSS OF NVRAM CALIBRATION DATA;
4. **LOSS OF BUSINESS PROFITS**, REVENUE, BUSINESS INTERRUPTION, LOSS OF COMMERCIAL REPUTATION, OR WORKSHOP DOWNTIME;
5. **COSTS OF PROCUREMENT OF SUBSTITUTE GOODS OR REPAIR SERVICES**;
6. **ANY THIRD-PARTY CLAIMS** BROUGHT AGAINST YOU BY CUSTOMERS, CARRIERS, OR LAW ENFORCEMENT BODIES.

THESE LIMITATIONS APPLY REGARDLESS OF THE THEORY OF LIABILITY (WHETHER BASED IN CONTRACT, TORT, NEGLIGENCE, STRICT LIABILITY, OR OTHERWISE), EVEN IF TFAST DIGITAL AGENCY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES, AND EVEN IF A REMEDY FAILS OF ITS ESSENTIAL PURPOSE.

IN NO EVENT SHALL TFAST DIGITAL AGENCY'S AGGREGATE LIABILITY ARISING OUT OF OR RELATED TO THIS AGREEMENT OR THE SOFTWARE EXCEED THE ACTUAL AMOUNT PAID BY YOU (IF ANY) TO TFAST DIGITAL AGENCY SPECIFICALLY FOR THE SOFTWARE LICENSE IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM, OR FIFTY UNITED STATES DOLLARS ($50.00 USD), WHICHEVER IS LESS.

---

## 7. Indemnification

You agree to defend, indemnify, and hold harmless TFast Digital Agency, its owners, developers, contributors, and affiliates from and against any and all claims, liabilities, damages, losses, costs, and expenses (including reasonable attorneys' fees and legal costs) arising out of or related to:
1. Your download, installation, use, or misuse of the Software;
2. Your violation of any provision of this Agreement or the Acceptable Use Policy;
3. Your servicing, flashing, or modification of hardware not owned by you without proper customer consent;
4. Any violation of applicable telecommunications, intellectual property, or export laws committed by you in connection with your use of this Software.

---

## 8. Third-Party Components & Open-Source Acknowledgments

The Software incorporates or bundles certain third-party software components, each governed by its respective open-source license:

| Component | Source / Author | License | Description |
|:---|:---|:---|:---|
| **Android Fastboot & ADB Binaries** | Google LLC / Android Open Source Project | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | `fastboot.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` |
| **PySerial** | Chris Liechti | [BSD 3-Clause](https://github.com/pyserial/pyserial/blob/master/LICENSE.txt) | Serial port communication library for META mode |
| **Requests Suite** | Kenneth Reitz / PSF | [Apache License 2.0](https://requests.readthedocs.io/en/latest/) | HTTP client libraries (`urllib3`, `certifi`, `idna`, `charset-normalizer`) |
| **Pillow (PIL)** | Jeffrey A. Clark / Clark Development | [Historical Permission Notice (HPND)](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | Image handling and icon processing |
| **Python Runtime** | Python Software Foundation | [PSF License](https://docs.python.org/3/license.html) | Embedded CPython 3.14 execution environment |

Nothing in this Agreement diminishes, limits, or supersedes your rights or obligations under the terms of those respective open-source licenses.

---

## 9. Export Controls & Telecommunications Compliance

You acknowledge that this Software and the hardware it modifies may be subject to export control laws and regulations of various jurisdictions. You agree that you will not export, re-export, or transfer the Software or any associated technical data directly or indirectly to any country, entity, or person prohibited by applicable trade sanctions, embargoes, or export control regulations.

Furthermore, you are solely responsible for ensuring that all radio frequency parameters, IMEI records, and telecommunications configurations on devices you service comply with the regulatory frameworks established by the competent telecommunications authority in your jurisdiction (e.g., FCC, CE, TRA, etc.).

---

## 10. Termination

This Agreement is effective until terminated. Your rights under this Agreement terminate automatically without notice from TFast Digital Agency if you fail to comply with any of its terms. Upon termination:
- You must cease all use of the Software;
- You must immediately destroy and purge all copies of the Software, whether in whole or in part, from your computer systems and storage media;
- Provisions regarding proprietary rights, disclaimers, limitation of liability, indemnification, and governing law shall survive termination.

---

## 11. Governing Law & Dispute Resolution

This Agreement shall be governed by and construed in accordance with the substantive laws applicable to TFast Digital Agency's registered operations, without giving effect to any principles of conflicts of law. 

Any dispute, controversy, or claim arising out of or relating to this Agreement, or the breach, termination, or invalidity thereof, shall be resolved through good-faith direct consultation between the parties. If unresolved, such dispute shall be submitted to the competent commercial courts having jurisdiction over the registered domicile of TFast Digital Agency.

---

## 12. Severability & Entire Agreement

If any provision of this Agreement is held to be invalid, illegal, or unenforceable under applicable law:
- That provision shall be reformed to the minimum extent necessary to make it valid and enforceable while preserving the original intent;
- The remaining provisions of this Agreement shall remain in full force and effect.

This Agreement, together with [`tfast-NOTICE.txt`](tfast-NOTICE.txt) and the embedded brand manifest [`tfast-brand.json`](tfast-brand.json), constitutes the complete and exclusive statement of the agreement between you and TFast Digital Agency regarding the Software and supersedes all prior or contemporaneous understandings, proposals, or communications.

---

## 13. Official Contact Information & Inquiries

For legal licensing inquiries, partnership requests, enterprise servicing agreements, or vulnerability reporting, please contact TFast Digital Agency via official channels:

- **Official Website:** [https://tfastdigital.com/](https://tfastdigital.com/)
- **Legal & Compliance:** `legal@tfastdigital.com`
- **General Support:** `contact@tfastdigital.com`
- **Official GitHub:** [https://github.com/tfastdigital](https://github.com/tfastdigital)
- **Telegram Channel:** [https://t.me/tfasthub](https://t.me/tfasthub)
- **WhatsApp Community:** [https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a](https://whatsapp.com/channel/0029VaAYznPK5cDIXJa9nW1a)

---
*TFast Digital Agency &mdash; Engineering Precision Mobile Servicing Tools.*
