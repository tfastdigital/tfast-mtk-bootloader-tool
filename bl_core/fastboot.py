import os
import re
import shutil
import subprocess
import sys
import time
from typing import List, Optional, Set, Tuple

from . import config

class FastbootClient:
    def __init__(self, fastboot_path: Optional[str] = None):
        self.fastboot_path = fastboot_path or self._find_fastboot()
        self.active_slot: Optional[str] = None
        self.cached_partitions: Optional[Set[str]] = None

    def _find_fastboot(self) -> str:
        """Find fastboot in bin directory or system PATH."""
        if os.path.exists(config.FASTBOOT_PATH):
            return config.FASTBOOT_PATH
        local_bin = os.path.join(os.getcwd(), 'bin', 'fastboot.exe')
        if os.path.exists(local_bin):
            return local_bin
        which_fb = shutil.which('fastboot')
        if which_fb:
            return which_fb
        return 'fastboot'

    def run(self, args: List[str], timeout: int = 60, check: bool = False, silent: bool = True) -> Tuple[int, str]:
        """Run fastboot command with hidden console window on Windows."""
        cmd = [self.fastboot_path] + args
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                timeout=timeout
            )
            combined = (proc.stdout or '') + (proc.stderr or '')
            if check and proc.returncode != 0:
                raise RuntimeError(f"Fastboot error ({proc.returncode}): {combined.strip()}")
            return proc.returncode, combined.strip()
        except subprocess.TimeoutExpired:
            return -1, "Command timed out"
        except FileNotFoundError:
            return -2, f"Fastboot binary not found at: {self.fastboot_path}"

    def get_devices(self, timeout: int = 10) -> List[Tuple[str, str]]:
        """Return list of (serial, status) tuples.

        Ignores fastboot's status banners (``< waiting for any device >``) which
        would otherwise parse as a device with serial ``<``.
        """
        code, out = self.run(['devices'], timeout=timeout)
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith('<') or line.startswith('*'):
                continue
            parts = line.split()
            if not parts or '<' in parts[0] or '>' in parts[0]:
                continue
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
            else:
                devices.append((parts[0], 'fastboot'))
        return devices

    def is_connected(self) -> bool:
        """Check if at least one fastboot device is responding."""
        devices = self.get_devices(timeout=5)
        return len(devices) > 0

    def wait_for_device(self, timeout: int = 30, prompt: bool = True) -> bool:
        """Poll and wait for a fastboot device to connect."""
        if self.is_connected():
            return True
        if prompt:
            print(f"[*] Waiting for Fastboot device (timeout {timeout}s)...")
            print("    Ensure device is in Fastboot mode and connected via USB. (Ctrl+C to abort)")
        start = time.time()
        try:
            while time.time() - start < timeout:
                if self.is_connected():
                    print("[+] Fastboot device connected!")
                    return True
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n[!] Device wait canceled by user.")
            return False
        return False

    def detect_slot(self) -> str:
        """Detect current active boot slot (_a or _b)."""
        code, out = self.run(['getvar', 'current-slot'], timeout=15)
        match = re.search(r'current-slot:\s*([a-zA-Z0-9_-]+)', out, re.IGNORECASE)
        if match:
            slot_val = match.group(1).strip().lower()
            if slot_val in ('a', '_a'):
                self.active_slot = '_a'
                return '_a'
            if slot_val in ('b', '_b'):
                self.active_slot = '_b'
                return '_b'

        # Fallback to getvar all
        code, all_out = self.run(['getvar', 'all'], timeout=25)
        fallback_match = re.search(r'current-slot:\s*([a-zA-Z0-9_-]+)', all_out, re.IGNORECASE)
        if fallback_match:
            slot_val = fallback_match.group(1).strip().lower()
            if slot_val in ('b', '_b'):
                self.active_slot = '_b'
                return '_b'

        self.active_slot = '_a'
        return '_a'

    def get_available_partitions(self, force_refresh: bool = False) -> Set[str]:
        """Query all partition-type tags from getvar all."""
        if self.cached_partitions is not None and not force_refresh:
            return self.cached_partitions

        code, out = self.run(['getvar', 'all'], timeout=30)
        found = set()
        for match in re.finditer(r'partition-type:([a-zA-Z0-9_\-]+):', out, re.IGNORECASE):
            found.add(match.group(1).strip().lower())

        self.cached_partitions = found
        return found

    def resolve_partition_name(self, base_names: List[str], slot: Optional[str] = None) -> Optional[str]:
        """Resolve the physical slotted or unslotted partition name."""
        slot = slot or self.detect_slot()
        available = self.get_available_partitions()

        for base in base_names:
            slotted = f"{base}{slot}".lower()
            if slotted in available:
                return slotted
            if base.lower() in available:
                return base.lower()
        return None

    def erase(self, partition: str) -> Tuple[bool, str]:
        """Erase target partition."""
        code, out = self.run(['erase', partition], timeout=30)
        return (code == 0, out)

    def flash(self, partition: str, image_path: str, disable_verity: bool = False) -> Tuple[bool, str]:
        """Flash image to target partition."""
        args = []
        if disable_verity:
            args.extend(['--disable-verity', '--disable-verification'])
        args.extend(['flash', partition, image_path])
        code, out = self.run(args, timeout=120)
        return (code == 0, out)

    def reboot(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """Reboot device to normal system, bootloader, recovery, or fastbootd."""
        args = ['reboot']
        if target:
            args.append(target)
        code, out = self.run(args, timeout=15)
        return (code == 0, out)

    def enter_fastbootd(self) -> Tuple[bool, str]:
        """Enter fastbootd mode (userspace fastboot)."""
        return self.reboot('fastboot')

    def get_lock_state(self) -> Tuple[Optional[bool], str]:
        """Query bootloader lock status (unlocked: yes/no)."""
        code, out = self.run(['getvar', 'unlocked'], timeout=15)
        out_lower = out.lower()
        if "unlocked: yes" in out_lower:
            return True, "unlocked: yes"
        if "unlocked: no" in out_lower:
            return False, "unlocked: no"

        # Check getvar all
        code_all, out_all = self.run(['getvar', 'all'], timeout=20)
        out_all_lower = out_all.lower()
        if "unlocked: yes" in out_all_lower:
            return True, "unlocked: yes"
        if "unlocked: no" in out_all_lower:
            return False, "unlocked: no"

        return None, out.strip() or "Unknown"

    def flashing_unlock_critical(self) -> Tuple[bool, str]:
        """Send `fastboot flashing unlock_critical` (lock-control prerequisite)."""
        code, out = self.run(['flashing', 'unlock_critical'], timeout=30)
        low = (out or "").lower()
        if code == 0 and "unrecognized" not in low and "unknown" not in low:
            return (True, out)
        return (False, out)

    def flashing_unlock(self) -> Tuple[bool, str]:
        """Send `fastboot flashing unlock`. Some MTK LK builds then show an
        "Unlock bootloader?" prompt and expect physical Volume UP confirmation.
        """
        code, out = self.run(['flashing', 'unlock'], timeout=30)
        low = (out or "").lower()
        if "unrecognized" in low or "unknown command" in low:
            return (False, out)
        return (code == 0, out)
