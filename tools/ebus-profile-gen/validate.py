"""Validate emitted structures against our constraints."""
from __future__ import annotations

from typing import List, Any, Dict


def check_no_trailing_underscores(obj: Any, path: str = "") -> List[str]:
    issues: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_"):
                issues.append(f"trailing underscore in key: {path}.{k}")
            issues.extend(check_no_trailing_underscores(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            issues.extend(check_no_trailing_underscores(v, f"{path}[{i}]"))
    elif isinstance(obj, str):
        if obj.endswith("_"):
            issues.append(f"trailing underscore in string value at {path}")
    return issues


def check_profile_keys_short(obj: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    profs = obj.get("profiles") or {}
    if isinstance(profs, dict):
        for k in profs:
            if len(k) > 24:
                issues.append(f"profile key too long (>24): {k}")
    return issues


def check_write_cmd_semantics(obj: Dict[str, Any]) -> List[str]:
    # TODO: enforce write_cmd present where rw indicates writable
    return []
