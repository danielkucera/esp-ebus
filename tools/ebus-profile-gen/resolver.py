"""Include/template resolution for .tsp files."""
from __future__ import annotations

import os
import re
from typing import List, Optional, Set

_IMPORT_RE = re.compile(r'^\s*import\s+"([^"]+)"\s*;?\s*$', re.MULTILINE)

# Local TypeSpec library package providing constants (BROADCAST, ...) and
# base scalars; mapped to its lib/types.tsp (no imports of its own).
_TYPESPEC_IMPORT = "@ebusd/ebus-typespec"


class IncludeResolver:
    def __init__(self, ebusd_root: str, typespec_root: Optional[str] = None):
        self.ebusd_root = os.path.abspath(ebusd_root)
        self.typespec_root = (
            os.path.abspath(typespec_root) if typespec_root else None
        )

    def resolve(self, tsp_path: str) -> List[str]:
        """Resolve tsp_path and its transitive includes relative to ebusd_root.

        Returns list of absolute file paths in order (entry first, then includes).
        """
        entry = self._abs(tsp_path)
        seen: Set[str] = set()
        order: List[str] = []
        self._walk(entry, seen, order)
        return order

    def _abs(self, p: str) -> str:
        if os.path.isabs(p):
            return os.path.abspath(p)
        # If the path exists as-is (relative to CWD), use it directly.
        # Otherwise resolve relative to ebusd_root.
        if os.path.exists(p):
            return os.path.abspath(p)
        return os.path.abspath(os.path.join(self.ebusd_root, p))

    def _walk(self, path: str, seen: Set[str], order: List[str]) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        ap = os.path.abspath(path)
        if ap in seen:
            return
        seen.add(ap)
        order.append(ap)

        # Parse imports from file content and resolve them recursively
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            return

        file_dir = os.path.dirname(ap)
        for m in _IMPORT_RE.finditer(content):
            import_path = m.group(1)
            # Skip @library imports (not file paths)
            if import_path.startswith("@"):
                if import_path == _TYPESPEC_IMPORT and self.typespec_root:
                    self._walk(
                        os.path.join(self.typespec_root, "lib", "types.tsp"),
                        seen,
                        order,
                    )
                continue
            # Resolve import relative to the including file's directory
            abs_import = os.path.normpath(os.path.join(file_dir, import_path))
            if not os.path.exists(abs_import):
                # Try relative to ebusd_root
                abs_import = os.path.normpath(
                    os.path.join(self.ebusd_root, import_path)
                )
            self._walk(abs_import, seen, order)
