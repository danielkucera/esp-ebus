"""Emit raw generated JSON output (gitignored)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List


class Emitter:
    def __init__(self, profiles_out_path: str, commands_out_path: str):
        self.profiles_out_path = profiles_out_path
        self.commands_out_path = commands_out_path

    def emit_profiles(self, entries: List[Dict[str, Any]]) -> None:
        _ensure_parent_dir(self.profiles_out_path)
        with open(self.profiles_out_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
            f.write("\n")

    def emit_commands(self, commands: List[Dict[str, Any]]) -> None:
        _ensure_parent_dir(self.commands_out_path)
        with open(self.commands_out_path, "w", encoding="utf-8") as f:
            json.dump(commands, f, indent=2)
            f.write("\n")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
