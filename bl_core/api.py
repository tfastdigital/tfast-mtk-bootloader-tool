import requests
from typing import Optional, Tuple

from . import config

class SmartToolApi:
    def __init__(self, api_key: str = config.API_KEY_CLIENT):
        self.api_key = api_key

    def check_credits(self, cost: int = config.DEFAULT_PATCH_COST) -> Tuple[bool, int, str]:
        """Check the user's credit balance with the backend.

        Returns ``(has_enough, credits, message)``. When the server answers with
        a balance that is honoured; only a genuine network/protocol failure falls
        back to the offline unlimited mode so the tool keeps working.
        """
        try:
            payload = {"action": "check_credits", "cost": cost}
            headers = {"X-API-Key": self.api_key}
            resp = requests.post(config.API_BASE_URL, json=payload, headers=headers, timeout=6)
        except Exception:
            return True, 999, "Offline mode (unlimited credits)"

        if resp.status_code != 200:
            return True, 999, f"Credit service HTTP {resp.status_code} (offline mode)"

        try:
            data = resp.json()
        except Exception:
            return True, 999, "Credit service returned an invalid response (offline mode)"

        if not isinstance(data, dict) or data.get("credits") is None:
            return True, 999, "Credit service did not report a balance (offline mode)"

        try:
            credits = int(data["credits"])
        except (TypeError, ValueError):
            return True, 999, "Credit service returned a non-numeric balance (offline mode)"

        enough = credits >= cost
        if enough:
            return True, credits, f"{credits} credit(s) available ({cost} required)"
        return False, credits, f"Insufficient credits: {credits} available, {cost} required"

    def deduct_credits(self, cost: int = config.DEFAULT_PATCH_COST, operation: str = "bootloader_unlock",
                       model_name: str = "", files_patched: str = "") -> Tuple[bool, str]:
        """Post credit deduction to the server.

        Returns ``(ok, message)``. A server rejection is reported as a failure;
        only a transport-level failure falls back to offline mode.
        """
        try:
            payload = {
                "action": "deduct",
                "cost": cost,
                "operation": operation,
                "model": model_name,
                "files_patched": files_patched
            }
            headers = {"X-API-Key": self.api_key}
            resp = requests.post(config.DEDUCT_URL, json=payload, headers=headers, timeout=8)
        except Exception:
            return True, "Deduction bypassed (offline mode)"

        if resp.status_code != 200:
            return False, f"Deduction failed: HTTP {resp.status_code}"

        try:
            data = resp.json()
        except Exception:
            return False, "Deduction failed: invalid server response"

        if isinstance(data, dict) and (data.get("status") == "success" or data.get("ok")):
            return True, "Credits deducted successfully"

        reason = ""
        if isinstance(data, dict):
            reason = str(data.get("message") or data.get("error") or "")
        return False, f"Deduction rejected by server{': ' + reason if reason else ''}"
