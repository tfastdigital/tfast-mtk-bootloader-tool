from typing import List, Optional, Tuple
from .fastboot import FastbootClient

class FirmwareFlasher:
    def __init__(self, fb: FastbootClient):
        self.fb = fb

    def flash_bootloader(self, lk_a_path: Optional[str], lk_b_path: Optional[str]) -> List[Tuple[str, bool, str]]:
        """Flash patched LK bootloader to target slots."""
        results = []
        available = self.fb.get_available_partitions()

        if lk_a_path:
            target = "lk_a" if "lk_a" in available else ("lk" if "lk" in available else None)
            if target:
                ok, out = self.fb.flash(target, lk_a_path)
                results.append((target, ok, out))

        if lk_b_path:
            target = "lk_b" if "lk_b" in available else None
            if target:
                ok, out = self.fb.flash(target, lk_b_path)
                results.append((target, ok, out))

        return results

    def flash_vbmeta(self, vbmeta_path: str) -> List[Tuple[str, bool, str]]:
        """Flash vbmeta with AVB verification and verity disabled."""
        results = []
        slot = self.fb.detect_slot()
        available = self.fb.get_available_partitions()

        # Try active slot vbmeta
        slotted_target = f"vbmeta{slot}".lower()
        if slotted_target in available:
            ok, out = self.fb.flash(slotted_target, vbmeta_path, disable_verity=True)
            results.append((slotted_target, ok, out))

        # Always flash generic vbmeta if present
        if "vbmeta" in available:
            ok, out = self.fb.flash("vbmeta", vbmeta_path, disable_verity=True)
            results.append(("vbmeta", ok, out))

        # If neither was in getvar, flash vbmeta directly
        if not results:
            ok, out = self.fb.flash("vbmeta", vbmeta_path, disable_verity=True)
            results.append(("vbmeta", ok, out))

        return results

    def flash_custom_system(self, system_path: str, allow_unknown: bool = False) -> Tuple[bool, str]:
        """Flash custom system image to the active system partition.

        Refuses to guess: flashing to a partition the bootloader never reported
        can write over the wrong target. ``allow_unknown=True`` restores the old
        blind behaviour for callers that deliberately want it.
        """
        slot = self.fb.detect_slot()
        available = self.fb.get_available_partitions()
        for target in (f"system{slot}".lower(), "system"):
            if target in available:
                return self.fb.flash(target, system_path)

        if allow_unknown:
            return self.fb.flash("system", system_path)

        if not available:
            return False, (
                "No partition table was reported by the bootloader, so the system "
                "partition cannot be identified. Refusing to flash blindly."
            )
        return False, (
            f"No system partition found (looked for system{slot} and system). "
            "Refusing to flash blindly."
        )
