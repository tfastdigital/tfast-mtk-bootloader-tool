import json
import requests
from typing import Dict, List, Optional, Tuple

from . import config

class ModelManager:
    def __init__(self, api_key: str = config.API_KEY_CLIENT):
        self.api_key = api_key
        self.models_lookup: Dict[str, dict] = dict(config.FALLBACK_LOOKUP)
        self.model_names: List[str] = list(config.FALLBACK_MODELS)
        #: How the last get_model_info() call matched: 'exact', 'codename',
        #: 'ci', 'substring', or None when nothing matched.
        self.last_match_kind: Optional[str] = None
        #: Display name a 'substring' match resolved to (for warning messages).
        self.last_match_key: Optional[str] = None

    def load_offline(self) -> Tuple[List[str], Dict[str, dict]]:
        """Load the bundled offline catalog only - no network round-trip.

        Callers that need to resolve an arbitrary model name (the CLI) must use
        this first; otherwise they only see the small hardcoded fallback table
        and silently fail to find most models.
        """
        offline_json = config.OFFLINE_REPO_DIR / "models.json"
        if offline_json.exists():
            try:
                coerced = self._coerce_catalog(
                    json.loads(offline_json.read_text(encoding="utf-8")))
                if coerced:
                    self.model_names, self.models_lookup = coerced
            except Exception:
                pass
        return self.model_names, self.models_lookup

    @staticmethod
    def _coerce_catalog(data) -> Optional[Tuple[List[str], Dict[str, dict]]]:
        """Validate a catalog payload, returning (names, lookup) or None.

        Guards against a malformed server response: a non-list ``models`` value
        would otherwise become a per-character list in the UI selector.
        """
        if not isinstance(data, dict):
            return None
        if "data" in data:
            data = data["data"]
            if not isinstance(data, dict):
                return None
        raw_names = data.get("models")
        raw_lookup = data.get("lookup")
        if not isinstance(raw_names, list) or not isinstance(raw_lookup, dict):
            return None
        names = [str(n) for n in raw_names if isinstance(n, (str, int)) and str(n).strip()]
        lookup = {str(k): v for k, v in raw_lookup.items() if isinstance(v, dict)}
        if not names or not lookup:
            return None
        return names, lookup

    def fetch_models(self) -> Tuple[List[str], Dict[str, dict]]:
        """Fetch model list from remote API, falling back to local offline repository."""
        # 1. Try remote API
        try:
            headers = {"X-API-Key": self.api_key}
            resp = requests.get(config.MODEL_LIST_URL, headers=headers, timeout=5)
            if resp.status_code == 200:
                coerced = self._coerce_catalog(resp.json())
                if coerced:
                    self.model_names, self.models_lookup = coerced
                    return self.model_names, self.models_lookup
        except Exception:
            pass

        # 2. Try offline repository
        offline_json = config.OFFLINE_REPO_DIR / "models.json"
        if offline_json.exists():
            try:
                content = json.loads(offline_json.read_text(encoding="utf-8"))
                coerced = self._coerce_catalog(content)
                if coerced:
                    self.model_names, self.models_lookup = coerced
                    return self.model_names, self.models_lookup
            except Exception:
                pass

        return self.model_names, self.models_lookup

    def get_model_info(self, model_name: str) -> Optional[dict]:
        """Look up metadata for a model name or codename.

        Resolution order is exact, then case-insensitive exact, then the
        *shortest* matching display name. The shortest-match rule keeps
        "Tecno Spark 40 Pro" from resolving to "Tecno Spark 40 Pro Plus", and an
        empty or whitespace name never matches anything at all.
        """
        if not isinstance(model_name, str):
            self.last_match_kind = None
            return None
        key = model_name.strip()
        if not key:
            self.last_match_kind = None
            return None

        if key in self.models_lookup:
            self.last_match_kind = 'exact'
            return self.models_lookup[key]

        lowered = key.lower()
        for name, meta in self.models_lookup.items():
            if (meta.get("codename") or "").strip().lower() == lowered:
                self.last_match_kind = 'codename'
                return meta

        exact_ci = [m for n, m in self.models_lookup.items() if n.strip().lower() == lowered]
        if exact_ci:
            self.last_match_kind = 'ci'
            return exact_ci[0]

        candidates = [(n, m) for n, m in self.models_lookup.items() if lowered in n.lower()]
        if not candidates:
            self.last_match_kind = None
            return None
        candidates.sort(key=lambda pair: (len(pair[0]), pair[0]))
        self.last_match_kind = 'substring'
        self.last_match_key = candidates[0][0]
        return candidates[0][1]
