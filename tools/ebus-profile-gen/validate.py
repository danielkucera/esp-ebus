"""Validate emitted structures against our constraints.

Validation is derived from two sources:

* the structured conversion log (:func:`validate_log`), which records every
  decision (type classification, profile selection, skips, collisions), and
* the emitted JSON entries (:func:`check_no_trailing_underscores`).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


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


def validate_log(
    records: Iterable[Dict[str, Any]],
    profiles_entries: List[Dict[str, Any]] = None,  # type: ignore[assignment]
    commands_entries: List[Dict[str, Any]] = None,  # type: ignore[assignment]
) -> List[str]:
    """Turn conversion-log records into a list of human-readable issues.

    Any record that indicates the output is not ready to use becomes an issue:
    defaulted/unsupported type mappings, emitted template definitions, skipped
    inherited bases, and read_cmd collisions. When profile and command entries
    are supplied, referenced profile names are cross-checked for existence.
    """
    issues: List[str] = []
    records = list(records)

    for rec in records:
        stage = rec.get("stage", "")
        reason = rec.get("reason", "")
        severity = rec.get("severity", "")

        if severity == "error":
            issues.append(f"[{stage}] {reason}")

        classification = rec.get("classification")
        if classification == "defaulted":
            issues.append(
                f"[{stage}] defaulted type mapping: "
                f"{rec.get('input_type')!r} -> {rec.get('datatype')!r}"
            )
        elif classification == "unsupported":
            issues.append(
                f"[{stage}] unsupported type (no native DataType): "
                f"{rec.get('input_type')!r}"
            )

        action = rec.get("action")
        if action == "emitted_template_definition":
            issues.append(
                f"[{stage}] template definition emitted as a command: "
                f"{rec.get('name')!r}"
            )

        if action == "emitted" and rec.get("rw") == "write" and not rec.get("write_cmd"):
            issues.append(
                f"[{stage}] writable command has no write_cmd: {rec.get('name')!r}"
            )

    if profiles_entries is not None and commands_entries is not None:
        known = {p.get("name") for p in profiles_entries}
        for cmd in commands_entries:
            for field in cmd.get("fields", []):
                profile = field.get("profile")
                if profile and profile not in known:
                    issues.append(
                        f"[command] {cmd.get('key')} field {field.get('name')!r} "
                        f"references unknown profile {profile!r}"
                    )

    return issues
