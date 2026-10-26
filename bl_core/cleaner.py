from typing import List, Tuple
from .fastboot import FastbootClient
from . import config

class PartitionCleaner:
    def __init__(self, fb: FastbootClient):
        self.fb = fb

    def clean_trash_partitions(self, slot: str = None,
                               include_system: bool = True) -> List[Tuple[str, bool, str]]:
        """
        Detect and wipe Transsion / OEM anti-tamper and verification guard
        partitions, plus the ``product`` / ``system_ext`` partitions the guard
        overlays point back at. This is the step that runs after a successful
        bootloader unlock.

        The caller MUST confirm the bootloader is unlocked first: the stock LK
        gates partition writes, so on a locked device every erase is rejected.
        ``cleaner.assert_unlocked()`` does that check.

        Set ``include_system=False`` to erase only the ``tr_*`` overlays and
        leave the real system partitions intact.
        """
        slot = slot or self.fb.detect_slot()
        available = self.fb.get_available_partitions(force_refresh=True)
        results = []

        targets = list(config.TRASH_PARTITIONS)
        if include_system:
            targets += list(config.EXTRA_SYSTEM_PARTITIONS)

        seen = set()
        for base in targets:
            for target in (f"{base}{slot}".lower(), base.lower()):
                if target in available and target not in seen:
                    seen.add(target)
                    ok, out = self.fb.erase(target)
                    results.append((target, ok, out))

        return results

    def check_unlocked(self) -> Tuple[bool, bool, str]:
        """Confirm the bootloader is unlocked before any guard wipe.

        Returns ``(allowed, state, message)`` where ``state`` is ``True``
        (unlocked), ``False`` (locked) or ``None`` (bootloader did not report).
        Only a positive ``unlocked: yes`` reports from the bootloader is
        accepted; an unknown state is treated as not-allowed.
        """
        unlocked, msg = self.fb.get_lock_state()
        if unlocked is True:
            return True, True, msg or "unlocked: yes"
        if unlocked is False:
            return False, False, msg or "unlocked: no"
        return False, None, msg or "unknown"
