"""Structured conversion log for ebus-profile-gen.

Emits one JSON object per line (JSONL) describing every decision the
generator makes while turning a TypeSpec (.tsp) file into data profiles and
commands. The log is the debugging surface: it records what was converted,
how it was classified, and why something was skipped or defaulted.

Stages:
    parse     - raw constructs read from the .tsp (models, fields, scalars)
    resolve   - alias/scalar chain resolution and datatype mapping
    template  - template model expansion
    profile   - data-profile entry emission and profile-name selection
    command   - command entry emission (key, addressing, duplicates)
    emit      - output file writing

Classifications (for type resolution):
    native      - ebusd type maps directly to an ebus-library DataType
    profile     - supported type that needs unit/scaling metadata
    unsupported - no native DataType equivalent (needs explicit decoding)
    defaulted   - unknown type; mapped by guessing (a bug, surfaced loudly)
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

STAGES = ("parse", "resolve", "template", "profile", "command", "emit")
SEVERITIES = ("debug", "info", "warn", "error")

_LEVELS = {"debug": 0, "info": 1, "warn": 2, "error": 3}


class ConversionLog:
    """Collects structured records and writes them as JSONL."""

    def __init__(self, path: Optional[str] = None, level: str = "info"):
        self.path = path
        self.level = level if level in _LEVELS else "info"
        self.records: List[Dict[str, Any]] = []
        self._counts: Dict[str, int] = {s: 0 for s in SEVERITIES}

    def enabled(self, severity: str) -> bool:
        return _LEVELS.get(severity, 1) >= _LEVELS[self.level]

    def log(self, stage: str, severity: str, reason: str = "", **fields: Any) -> None:
        if stage not in STAGES:
            stage = "parse"
        if severity not in SEVERITIES:
            severity = "info"
        rec: Dict[str, Any] = {"stage": stage, "severity": severity, "reason": reason}
        rec.update(fields)
        self.records.append(rec)
        self._counts[severity] += 1

    def debug(self, stage: str, reason: str = "", **fields: Any) -> None:
        self.log(stage, "debug", reason, **fields)

    def info(self, stage: str, reason: str = "", **fields: Any) -> None:
        self.log(stage, "info", reason, **fields)

    def warn(self, stage: str, reason: str = "", **fields: Any) -> None:
        self.log(stage, "warn", reason, **fields)

    def error(self, stage: str, reason: str = "", **fields: Any) -> None:
        self.log(stage, "error", reason, **fields)

    def write(self) -> None:
        if not self.path:
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for rec in self.records:
                if not self.enabled(rec.get("severity", "info")):
                    continue
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True))
                fh.write("\n")

    def summary(self) -> Dict[str, Any]:
        by_stage: Dict[str, int] = {}
        by_classification: Dict[str, int] = {}
        for rec in self.records:
            by_stage[rec["stage"]] = by_stage.get(rec["stage"], 0) + 1
            classification = rec.get("classification")
            if classification:
                by_classification[classification] = (
                    by_classification.get(classification, 0) + 1
                )
        return {
            "total": len(self.records),
            "by_severity": dict(self._counts),
            "by_stage": by_stage,
            "by_classification": by_classification,
        }


class NullLog:
    """No-op logger; safe to use when logging is disabled."""

    def __getattr__(self, name: str):
        def _noop(*_args: Any, **_kwargs: Any) -> None:
            return None

        return _noop


NULL_LOG = NullLog()
