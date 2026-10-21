"""Minimal TypeSpec (.tsp) subset parser for ebusd-configuration files.

Parses eBUS TypeSpec files used by ebusd-configuration and extracts registers
(commands), fields, types, enums, and aliases into a raw IR dict consumed by
the mapper.

Supported constructs:
  * decorators: @zz(0x08), @base(MF, 0x09, 0x29), @ext(0xa8, 0), @id(...),
                @write, @passive, @auth(...), @poll(...), @unit("..."),
                @divisor(N), @factor(N), @step(N), @values(Enum),
                @maxLength(N), @condition(...)
  * alias: alias MF = 0xb5;
  * scalar: scalar Name extends Type;
  * enum: enum Name { Key: value, ... }
  * model: model Name { field: Type; ... }
  * model template: model Name is ReadonlyRegister<Type>;
  * comments: // line, /** ... */ block
  * imports: import "..."; using ...; (skipped)
  * namespace: namespace ...; (skipped)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from .convlog import NULL_LOG, ConversionLog
except ImportError:  # script-style execution
    from convlog import NULL_LOG, ConversionLog


# Matches a decorator line: @name(args) or @name
_DECORATOR_RE = re.compile(r"^\s*@(\w+)(?:\(([^)]*)\))?\s*$")

# Matches an alias: alias Name = value;
_ALIAS_RE = re.compile(r"^\s*alias\s+(\w+)\s*=\s*(.+?)\s*;?\s*$")

# Matches a scalar: scalar Name extends Type;
_SCALAR_RE = re.compile(r"^\s*scalar\s+(\w+)\s+extends\s+([\w.]+)\s*;?\s*$")

# Matches an enum: enum Name {
_ENUM_RE = re.compile(r"^\s*enum\s+(\w+)\s*\{\s*$")

# Matches an enum entry: Key: value,
_ENUM_ENTRY_RE = re.compile(r"^\s*(\w+)\s*:\s*(0x[0-9a-fA-F]+|\d+)\s*,?\s*$")

# Matches a model: model Name { (possibly with fields on same line)
_MODEL_RE = re.compile(r"^\s*model\s+(\w+)\s*\{\s*(.*?)\s*\}\s*$")
# Matches a generic model: model Name<T> { ... }
_MODEL_GENERIC_RE = re.compile(r"^\s*model\s+(\w+)\s*<(\w+)>\s*\{\s*(.*?)\s*\}\s*$")
# Matches a generic model open declaration: model Name<T> {
_MODEL_GENERIC_OPEN_RE = re.compile(r"^\s*model\s+(\w+)\s*<(\w+)>\s*\{\s*$")
_MODEL_OPEN_RE = re.compile(r"^\s*model\s+(\w+)\s*\{\s*$")

# Matches a model template: model Name is Template<Type>;
_MODEL_TEMPLATE_RE = re.compile(
    r"^\s*model\s+(\w+)\s+is\s+(\w+)<([\w.]+)>\s*;?\s*$"
)

# Matches a field: fieldName: Type;
_FIELD_RE = re.compile(r"^\s*(\w+)\s*:\s*([\w.]+)\s*;?\s*$")

# Matches closing brace
_CLOSE_BRACE_RE = re.compile(r"^\s*\}\s*$")

# Hex number
_HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")

# Decimal number
_INT_RE = re.compile(r"^\d+$")

# Template model names known to have a single "value" field
_SINGLE_FIELD_TEMPLATES = {
    "ReadonlyRegister",
    "ReadonlyUpdateRegister",
    "WriteRegister",
    "InstallRegister",
    "ServiceCommandRegister",
}

# Template models with value + service fields
_TWO_FIELD_TEMPLATES = {
    "ServiceUpdateRegister",
}


class SourceLines:
    """Comment-stripped source lines that remember their original line numbers.

    ``lines[i]`` returns the stripped text (so existing code keeps working),
    while ``lines.lineno(i)`` returns the 1-based source line for logging.
    """

    def __init__(self, items: List[Tuple[int, str]]):
        self._items = items

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> str:
        return self._items[index][1]

    def lineno(self, index: int) -> int:
        return self._items[index][0]

    def raw(self, index: int) -> Tuple[int, str]:
        return self._items[index]


def _strip_comments(lines: List[str]) -> SourceLines:
    """Remove // line comments and /** ... */ block comments.

    Returns a :class:`SourceLines` preserving the original 1-based line numbers.
    """
    result: List[Tuple[int, str]] = []
    in_block = False
    for lineno, line in enumerate(lines, start=1):
        if in_block:
            end = line.find("*/")
            if end != -1:
                in_block = False
                line = line[end + 2:]
            else:
                continue
        idx = line.find("//")
        if idx != -1:
            line = line[:idx]
        if "/**" in line:
            start = line.find("/**")
            end = line.find("*/", start)
            if end != -1:
                line = line[:start] + line[end + 2:]
            else:
                in_block = True
                line = line[:start]
        stripped = line.strip()
        if stripped:
            result.append((lineno, stripped))
    return SourceLines(result)


_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)\s*(\{)?\s*;?\s*$")


def _namespace_map(lines: SourceLines) -> Dict[int, str]:
    """Map each source line number to its fully-qualified namespace path.

    Tracks ``namespace X;`` (file-level) and ``namespace X { ... }`` (block)
    declarations with a brace-depth stack. The result lets the parser attach
    namespace context to models/fields for logging and de-duplication.
    """
    ns_map: Dict[int, str] = {}
    # Stack of (namespace_name, brace_depth_at_which_it_was_opened)
    stack: List[Tuple[str, int]] = []
    file_ns = ""
    depth = 0

    def current() -> str:
        parts = [file_ns] if file_ns else []
        parts.extend(name for name, _ in stack)
        return ".".join(p for p in parts if p)

    for i in range(len(lines)):
        line = lines[i]
        lineno = lines.lineno(i)
        m = _NAMESPACE_RE.match(line)
        if m:
            name = m.group(1)
            has_brace = bool(m.group(2))
            if has_brace:
                stack.append((name, depth))
                depth += 1
            else:
                file_ns = name
        else:
            opens = line.count("{")
            closes = line.count("}")
            if opens:
                depth += opens
            if closes:
                depth -= closes
                while stack and depth < stack[-1][1] + 1:
                    stack.pop()
        ns_map[lineno] = current()
    return ns_map


def _parse_hex_or_int(s: str) -> Optional[int]:
    """Parse a hex (0x..) or decimal string to int."""
    s = s.strip()
    if _HEX_RE.match(s):
        return int(s, 16)
    if _INT_RE.match(s):
        return int(s)
    return None


def _parse_float(s: str) -> Optional[float]:
    """Parse a float string."""
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def _short_path(path: str) -> str:
    """Return a readable path for logs (relative to CWD when possible)."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return os.path.basename(path)


def _parse_decorator_args(args_str: Optional[str]) -> List[str]:
    """Parse decorator arguments, splitting by comma, respecting quotes."""
    if not args_str:
        return []
    args: List[str] = []
    current = ""
    in_quote = False
    quote_char = ""
    for ch in args_str:
        if in_quote:
            current += ch
            if ch == quote_char:
                in_quote = False
        elif ch in ('"', "'"):
            in_quote = True
            quote_char = ch
            current += ch
        elif ch == ",":
            args.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        args.append(current.strip())
    return args


def _resolve_constant(name: str, aliases: Dict[str, str]) -> Optional[int]:
    """Resolve a constant name or hex/int string to an int value."""
    s = name.strip()
    if _HEX_RE.match(s):
        return int(s, 16)
    if _INT_RE.match(s):
        return int(s)
    # Look up in aliases
    if s in aliases:
        return _resolve_constant(aliases[s], aliases)
    return None


class TspParser:
    def __init__(self, files: List[str], log: Optional[ConversionLog] = None):
        self.files = [os.path.abspath(f) for f in files]
        self.log = log if log is not None else NULL_LOG

    def parse(self) -> Dict[str, Any]:
        """Parse tsp files and return a raw IR dict.

        Returns:
            dict with keys: registers, fields, types, enums, scalars, aliases, includes
        """
        # First pass: collect all aliases from all files
        aliases: Dict[str, str] = {}
        all_file_contents: List[Tuple[str, str]] = []
        for fpath in self.files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except Exception:
                continue
            all_file_contents.append((fpath, content))
            lines = _strip_comments(content.splitlines())
            for i in range(len(lines)):
                am = _ALIAS_RE.match(lines[i])
                if am:
                    alias_name = am.group(1)
                    alias_value = am.group(2).strip()
                    aliases[alias_name] = alias_value

        # Second pass: parse all files with the complete alias map
        ir: Dict[str, Any] = {
            "registers": [],
            "fields": [],
            "types": {},
            "enums": {},
            "scalars": {},
            "aliases": aliases,
            "includes": list(self.files),
        }

        for fpath, content in all_file_contents:
            lines = _strip_comments(content.splitlines())
            ns_map = _namespace_map(lines)
            self._parse_lines(lines, ir, fpath, aliases, ns_map)

        # Post-process: resolve @inherit chains
        # Build model name → register index map
        model_index: Dict[str, int] = {}
        for idx, reg in enumerate(ir["registers"]):
            model_index[reg["name"]] = idx

        def merge_meta(child: Dict[str, Any], parent: Dict[str, Any]) -> None:
            """Copy missing meta components from parent to child."""
            for k in ("zz", "mf", "pb", "sb", "ext_pb", "ext_sb"):
                if k not in child["meta"] and k in parent["meta"]:
                    child["meta"][k] = parent["meta"][k]

        # Resolve inheritance iteratively (handles chains)
        # Keep iterating until no more meta is copied (handles chains
        # where parent is defined after child in the file list)
        changed = True
        while changed:
            changed = False
            for reg in ir["registers"]:
                inherit_list = reg.get("inherit") or []
                for parent_name in inherit_list:
                    parent_idx = model_index.get(parent_name)
                    if parent_idx is None:
                        continue
                    parent = ir["registers"][parent_idx]
                    # Copy missing meta from parent
                    for k in ("zz", "mf", "pb", "sb", "ext_pb", "ext_sb"):
                        if k not in reg["meta"] and k in parent["meta"]:
                            reg["meta"][k] = parent["meta"][k]
                            changed = True

        return ir

    def _parse_lines(
        self,
        lines: SourceLines,
        ir: Dict[str, Any],
        fpath: str,
        aliases: Dict[str, str],
        ns_map: Optional[Dict[int, str]] = None,
    ) -> None:
        """Parse a list of preprocessed lines into the IR."""
        ns_map = ns_map or {}
        i = 0
        while i < len(lines):
            line = lines[i]
            lineno = lines.lineno(i)
            namespace = ns_map.get(lineno, "")

            # Skip using/import/namespace/union statements
            if (
                line.startswith("using ")
                or line.startswith('import "')
                or line.startswith("namespace ")
                or line.startswith("union ")
            ):
                i += 1
                continue

            # Skip alias declarations (already collected in first pass)
            if _ALIAS_RE.match(line):
                i += 1
                continue

            # Check for decorator
            m = _DECORATOR_RE.match(line)
            if m:
                decorators: List[Dict[str, Any]] = []
                while i < len(lines):
                    m = _DECORATOR_RE.match(lines[i])
                    if not m:
                        break
                    name = m.group(1)
                    args = _parse_decorator_args(m.group(2))
                    decorators.append({"name": name, "args": args})
                    i += 1

                if i >= len(lines):
                    break

                next_line = lines[i]

                # The declaration line (not the first decorator line) carries the
                # namespace/line context used for logging.
                lineno = lines.lineno(i)
                namespace = ns_map.get(lineno, "")

                # Model declaration with decorators
                mm = _MODEL_RE.match(next_line)
                if mm:
                    model_name = mm.group(1)
                    inline_fields = mm.group(2).strip()
                    reg = self._parse_model_inline(
                        lines,
                        i + 1,
                        decorators,
                        model_name,
                        ir,
                        fpath,
                        aliases,
                        inline_fields=inline_fields,
                        body_on_same_line=True,
                        model_line=lineno,
                        namespace=namespace,
                    )
                    i = reg["next_i"]
                    ir["registers"].append(reg["register"])
                    continue

                # Generic model declaration: model Name<T> { ... }
                mg = _MODEL_GENERIC_RE.match(next_line)
                if mg:
                    model_name = mg.group(1)
                    type_param = mg.group(2)
                    inline_fields = mg.group(3).strip()
                    reg = self._parse_model_inline(
                        lines,
                        i + 1,
                        decorators,
                        model_name,
                        ir,
                        fpath,
                        aliases,
                        inline_fields=inline_fields,
                        body_on_same_line=True,
                        model_line=lineno,
                        namespace=namespace,
                    )
                    reg["register"]["template_type"] = type_param
                    i = reg["next_i"]
                    ir["registers"].append(reg["register"])
                    continue

                # Model open declaration (body on following lines)
                mo = _MODEL_OPEN_RE.match(next_line)
                if mo:
                    model_name = mo.group(1)
                    reg = self._parse_model_inline(
                        lines,
                        i + 1,
                        decorators,
                        model_name,
                        ir,
                        fpath,
                        aliases,
                        inline_fields="",
                        body_on_same_line=False,
                        model_line=lineno,
                        namespace=namespace,
                    )
                    i = reg["next_i"]
                    ir["registers"].append(reg["register"])
                    continue

                # Generic model open declaration: model Name<T> {
                mg = _MODEL_GENERIC_OPEN_RE.match(next_line)
                if mg:
                    model_name = mg.group(1)
                    type_param = mg.group(2)
                    reg = self._parse_model_inline(
                        lines,
                        i + 1,
                        decorators,
                        model_name,
                        ir,
                        fpath,
                        aliases,
                        inline_fields="",
                        body_on_same_line=False,
                        model_line=lineno,
                        namespace=namespace,
                    )
                    reg["register"]["template_type"] = type_param
                    i = reg["next_i"]
                    ir["registers"].append(reg["register"])
                    continue

                # Model template declaration
                tm = _MODEL_TEMPLATE_RE.match(next_line)
                if tm:
                    model_name = tm.group(1)
                    template_name = tm.group(2)
                    type_param = tm.group(3)
                    reg = self._build_register_from_decorators(
                        decorators,
                        model_name,
                        ir,
                        fpath,
                        aliases,
                        model_line=lineno,
                        namespace=namespace,
                    )
                    reg['template'] = template_name
                    reg['template_type'] = type_param
                    reg['fields'] = self._template_fields(template_name, type_param, ir, aliases)
                    ir['registers'].append(reg)
                    i += 1
                    continue

                # Scalar declaration with decorators
                sm = _SCALAR_RE.match(next_line)
                if sm:
                    scalar = self._build_scalar(
                        sm.group(1), sm.group(2), decorators, ir, fpath, lineno, namespace
                    )
                    ir["scalars"][sm.group(1)] = scalar
                    i += 1
                    continue

                # Enum declaration with decorators
                em = _ENUM_RE.match(next_line)
                if em:
                    enum_entries, next_i = self._parse_enum(lines, i + 1)
                    ir["enums"][em.group(1)] = {
                        "name": em.group(1),
                        "entries": enum_entries,
                        "file": fpath,
                        "line": lineno,
                        "namespace": namespace,
                    }
                    i = next_i
                    continue

                i += 1
                continue

            # Scalar declaration
            sm = _SCALAR_RE.match(line)
            if sm:
                scalar = self._build_scalar(
                    sm.group(1), sm.group(2), [], ir, fpath, lineno, namespace
                )
                ir["scalars"][sm.group(1)] = scalar
                i += 1
                continue

            # Enum declaration
            em = _ENUM_RE.match(line)
            if em:
                enum_name = em.group(1)
                enum_entries, next_i = self._parse_enum(lines, i + 1)
                ir["enums"][enum_name] = {
                    "name": enum_name,
                    "entries": enum_entries,
                    "file": fpath,
                    "line": lineno,
                    "namespace": namespace,
                }
                i = next_i
                continue

            i += 1

    def _parse_model_inline(
        self,
        lines: SourceLines,
        start_i: int,
        model_decorators: List[Dict[str, Any]],
        model_name: str,
        ir: Dict[str, Any],
        fpath: str,
        aliases: Dict[str, str],
        inline_fields: str = "",
        body_on_same_line: bool = False,
        model_line: int = 0,
        namespace: str = "",
    ) -> Dict[str, Any]:
        """Parse a model block { field: Type; ... } and return register info."""
        i = start_i
        fields: List[Dict[str, Any]] = []
        decorators = list(model_decorators)

        # Parse inline fields from the same line (e.g. model whwc {field: Type;})
        if inline_fields:
            for token in inline_fields.split(";"):
                token = token.strip()
                if not token:
                    continue
                fm = _FIELD_RE.match(token)
                if fm:
                    field_name = fm.group(1)
                    field_type = fm.group(2)
                    field = self._build_field(
                        field_name,
                        field_type,
                        [],
                        ir,
                        fpath,
                        model=model_name,
                        namespace=namespace,
                        line_no=model_line,
                    )
                    fields.append(field)

        # If the model body is empty {} on the same line (e.g. model whwc {}),
        # do NOT consume subsequent decorators - they belong to the next model!
        if body_on_same_line and not inline_fields:
            register = self._build_register_from_decorators(
                decorators,
                model_name,
                ir,
                fpath,
                aliases,
                model_line=model_line,
                namespace=namespace,
            )
            register["fields"] = fields
            return {"register": register, "next_i": i}

        while i < len(lines):
            line = lines[i]
            lineno = lines.lineno(i)

            if _CLOSE_BRACE_RE.match(line):
                i += 1
                break

            # Decorator before a field
            dm = _DECORATOR_RE.match(line)
            if dm:
                field_decorators: List[Dict[str, Any]] = []
                while i < len(lines):
                    dm = _DECORATOR_RE.match(lines[i])
                    if not dm:
                        break
                    fname = dm.group(1)
                    fargs = _parse_decorator_args(dm.group(2))
                    field_decorators.append({"name": fname, "args": fargs})
                    i += 1

                if i < len(lines):
                    fm = _FIELD_RE.match(lines[i])
                    if fm:
                        field_name = fm.group(1)
                        field_type = fm.group(2)
                        field = self._build_field(
                            field_name,
                            field_type,
                            field_decorators,
                            ir,
                            fpath,
                            model=model_name,
                            namespace=namespace,
                            line_no=lines.lineno(i),
                        )
                        fields.append(field)
                        i += 1
                        continue
            # Model declaration without decorators
            mo = _MODEL_OPEN_RE.match(line)
            if mo:
                model_name = mo.group(1)
                reg = self._parse_model_inline(
                    lines,
                    i + 1,
                    [],
                    model_name,
                    ir,
                    fpath,
                    aliases,
                    model_line=lineno,
                    namespace=namespace,
                )
                i = reg["next_i"]
                ir["registers"].append(reg["register"])
                continue

            # Generic model declaration without decorators: model Name<T> {
            mg = _MODEL_GENERIC_OPEN_RE.match(line)
            if mg:
                model_name = mg.group(1)
                type_param = mg.group(2)
                reg = self._parse_model_inline(
                    lines,
                    i + 1,
                    [],
                    model_name,
                    ir,
                    fpath,
                    aliases,
                    inline_fields="",
                    body_on_same_line=False,
                    model_line=lineno,
                    namespace=namespace,
                )
                reg["register"]["template_type"] = type_param
                i = reg["next_i"]
                ir["registers"].append(reg["register"])
                continue

            # Model template declaration without decorators
            tm = _MODEL_TEMPLATE_RE.match(line)
            if tm:
                model_name = tm.group(1)
                template_name = tm.group(2)
                type_param = tm.group(3)
                reg = self._build_register_from_decorators(
                    [],
                    model_name,
                    ir,
                    fpath,
                    aliases,
                    model_line=lineno,
                    namespace=namespace,
                )
                reg["template"] = template_name
                reg["template_type"] = type_param
                reg["fields"] = self._template_fields(
                    template_name, type_param, ir, aliases
                )
                ir["registers"].append(reg)
                i += 1
                continue

            # Field without decorators
            fm = _FIELD_RE.match(line)
            if fm:
                field_name = fm.group(1)
                field_type = fm.group(2)
                field = self._build_field(
                    field_name,
                    field_type,
                    [],
                    ir,
                    fpath,
                    model=model_name,
                    namespace=namespace,
                    line_no=lineno,
                )
                fields.append(field)
                i += 1
                continue

            i += 1

        register = self._build_register_from_decorators(
            decorators,
            model_name,
            ir,
            fpath,
            aliases,
            model_line=model_line,
            namespace=namespace,
        )
        register["fields"] = fields

        return {"register": register, "next_i": i}

    def _parse_enum(
        self,
        lines: SourceLines,
        start_i: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Parse an enum block. Returns (entries, next_index)."""
        entries: List[Dict[str, Any]] = []
        i = start_i
        while i < len(lines):
            line = lines[i]
            if _CLOSE_BRACE_RE.match(line):
                i += 1
                break
            em = _ENUM_ENTRY_RE.match(line)
            if em:
                key = em.group(1)
                val_str = em.group(2)
                val = _parse_hex_or_int(val_str)
                if val is not None:
                    entries.append({"key": key, "value": val})
                i += 1
                continue
            i += 1
        return entries, i

    def _build_field(
        self,
        name: str,
        ebus_type: str,
        decorators: List[Dict[str, Any]],
        ir: Dict[str, Any],
        fpath: str,
        model: str = "",
        namespace: str = "",
        line_no: int = 0,
    ) -> Dict[str, Any]:
        """Build a field dict from name, type, and decorators."""
        field: Dict[str, Any] = {
            "name": name,
            "ebus_type": ebus_type,
            "unit": "",
            "factor": "",
            "offset": "",
            "length": 0,
            "signed": False,
            "big_endian": False,
            "bitfield": False,
            "bitpos": -1,
            "bitlen": 0,
            "mask": "",
            "our_datatype": "",
            "meta": {},
            "file": fpath,
            "line": line_no,
            "namespace": namespace,
        }

        for dec in decorators:
            dname = dec["name"]
            args = dec["args"]

            if dname == "unit":
                if args:
                    field["unit"] = args[0].strip('"').strip("'")
                    if len(args) > 1:
                        field["meta"]["unit_category"] = args[1].strip('"').strip("'")
            elif dname == "divisor":
                if args:
                    field["factor"] = args[0]
            elif dname == "factor":
                if args:
                    field["factor"] = args[0]
            elif dname == "step":
                if args:
                    s = args[0].strip()
                    fval = _parse_float(s)
                    if fval is not None:
                        if "." in s:
                            field["meta"]["digits"] = len(s.split(".")[1].rstrip("0"))
                        else:
                            field["meta"]["digits"] = 0
            elif dname == "values":
                if args:
                    enum_name = args[0].strip()
                    field["meta"]["values_enum"] = enum_name
                    if enum_name in ir["enums"]:
                        field["meta"]["values"] = ir["enums"][enum_name]["entries"]
            elif dname == "in":
                field["meta"]["direction"] = "in"
            elif dname == "out":
                field["meta"]["direction"] = "out"
            elif dname == "constValue":
                if args:
                    field["meta"]["const_value"] = args[0]
            elif dname == "maxLength":
                if args:
                    field["meta"]["max_length"] = args[0]

        field["our_datatype"] = self._map_type(ebus_type)
        field["signed"] = ebus_type.startswith(("S", "s"))
        field["big_endian"] = "R" in ebus_type or ("B" in ebus_type and "L" not in ebus_type)

        self.log.debug(
            "parse",
            "field parsed",
            source=_short_path(fpath),
            line=line_no,
            namespace=namespace,
            model=model,
            field=name,
            input_type=ebus_type,
        )
        return field

    def _build_register_from_decorators(
        self,
        decorators: List[Dict[str, Any]],
        name: str,
        ir: Dict[str, Any],
        fpath: str,
        aliases: Dict[str, str],
        model_line: int = 0,
        namespace: str = "",
    ) -> Dict[str, Any]:
        """Build a register (command) dict from model decorators."""
        register: Dict[str, Any] = {
            "name": name,
            "rw": "read",
            "write_cmd": "",
            "fields": [],
            "template": None,
            "template_type": None,
            "inherit": None,
            "unsupported": False,
            "unsupported_reason": "",
            "meta": {},
            "file": fpath,
            "line": model_line,
            "namespace": namespace,
        }

        aliases = ir.get("aliases", {})

        for dec in decorators:
            dname = dec["name"]
            args = dec["args"]

            if dname == "zz":
                if args:
                    val = _resolve_constant(args[0], aliases)
                    if val is not None:
                        register["meta"]["zz"] = val
            elif dname == "base":
                # base(pb, sb) or base(mf, pb, sb)
                if len(args) >= 3:
                    mf = _resolve_constant(args[0], aliases)
                    pb = _resolve_constant(args[1], aliases)
                    sb = _resolve_constant(args[2], aliases)
                    if mf is not None:
                        register["meta"]["mf"] = mf
                    if pb is not None:
                        register["meta"]["pb"] = pb
                    if sb is not None:
                        register["meta"]["sb"] = sb
                elif len(args) == 2:
                    mf = _resolve_constant(args[0], aliases)
                    pb = _resolve_constant(args[1], aliases)
                    if mf is not None:
                        register["meta"]["mf"] = mf
                    if pb is not None:
                        register["meta"]["pb"] = pb
            elif dname == "ext":
                # ext(pb, sb)
                if len(args) >= 2:
                    pb = _resolve_constant(args[0], aliases)
                    sb = _resolve_constant(args[1], aliases)
                    if pb is not None:
                        register["meta"]["ext_pb"] = pb
                    if sb is not None:
                        register["meta"]["ext_sb"] = sb
            elif dname == "inherit":
                # inherit(parent_model, ...)
                if args:
                    register["inherit"] = [a.strip() for a in args]
            elif dname == "id":
                # id(pb, sb, dd...)
                id_bytes = []
                for a in args:
                    v = _resolve_constant(a, aliases)
                    if v is not None:
                        id_bytes.append(v)
                if id_bytes:
                    register["register"] = "".join(f"{b:02x}" for b in id_bytes)
            elif dname == "write":
                register["rw"] = "write"
                register["meta"]["sb_write"] = 0x0e
                register["meta"]["explicit_write"] = True
                if args:
                    v = _resolve_constant(args[0], aliases)
                    if v is not None:
                        register["meta"]["write_nn"] = v
            elif dname == "passive":
                register["rw"] = "read"
                register["meta"]["explicit_passive"] = True
            elif dname == "poll":
                if args:
                    v = _resolve_constant(args[0], aliases)
                    if v is not None:
                        register["meta"]["poll"] = v
            elif dname == "auth":
                if args:
                    register["meta"]["auth"] = args[0].strip('"').strip("'")
            elif dname == "condition":
                if args:
                    register["meta"]["condition"] = args

        self.log.debug(
            "parse",
            "model parsed",
            source=_short_path(fpath),
            line=model_line,
            namespace=namespace,
            model=name,
            rw=register["rw"],
            template=register["template"],
        )
        return register

    def _build_scalar(
        self,
        name: str,
        base_type: str,
        decorators: List[Dict[str, Any]],
        ir: Dict[str, Any],
        fpath: str,
        line_no: int = 0,
        namespace: str = "",
    ) -> Dict[str, Any]:
        """Build a scalar dict, capturing decorator metadata (unit/min/max/...)."""
        scalar: Dict[str, Any] = {
            "name": name,
            "base_type": base_type,
            "file": fpath,
            "line": line_no,
            "namespace": namespace,
            "unit": "",
            "factor": "",
            "digits": 0,
            "min": None,
            "max": None,
            "values_enum": "",
            "max_length": "",
        }

        for dec in decorators:
            dname = dec["name"]
            args = dec["args"]
            if dname == "unit" and args:
                scalar["unit"] = args[0].strip('"').strip("'")
            elif dname in ("divisor", "factor") and args:
                scalar["factor"] = args[0]
            elif dname == "step" and args:
                s = args[0].strip()
                if "." in s:
                    scalar["digits"] = len(s.split(".")[1].rstrip("0"))
            elif dname == "minValue" and args:
                scalar["min"] = _parse_hex_or_int(args[0])
            elif dname == "maxValue" and args:
                scalar["max"] = _parse_hex_or_int(args[0])
            elif dname == "values" and args:
                scalar["values_enum"] = args[0].strip()
            elif dname == "maxLength" and args:
                scalar["max_length"] = args[0]

        existing = ir["scalars"].get(name)
        if existing is not None and existing.get("base_type") != base_type:
            self.log.warn(
                "parse",
                "scalar redefined with a different base type; last definition wins",
                source=_short_path(fpath),
                line=line_no,
                namespace=namespace,
                scalar=name,
                previous_base_type=existing.get("base_type"),
                previous_file=_short_path(existing.get("file", "")),
                new_base_type=base_type,
            )

        self.log.debug(
            "parse",
            "scalar parsed",
            source=_short_path(fpath),
            line=line_no,
            namespace=namespace,
            scalar=name,
            base_type=base_type,
            unit=scalar["unit"],
        )
        return scalar

    def _template_fields(
        self,
        template_name: str,
        type_param: str,
        ir: Dict[str, Any],
        aliases: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Build field list for a template model."""
        fields: List[Dict[str, Any]] = []

        if template_name in _SINGLE_FIELD_TEMPLATES:
            fields.append(
                {
                    "name": "value",
                    "ebus_type": type_param,
                    "unit": "",
                    "factor": "",
                    "offset": "",
                    "length": 0,
                    "signed": False,
                    "big_endian": False,
                    "bitfield": False,
                    "bitpos": -1,
                    "bitlen": 0,
                    "mask": "",
                    "our_datatype": self._map_type(type_param),
                    "meta": {},
                    "file": "template",
                }
            )
        elif template_name in _TWO_FIELD_TEMPLATES:
            fields.append(
                {
                    "name": "value",
                    "ebus_type": type_param,
                    "unit": "",
                    "factor": "",
                    "offset": "",
                    "length": 0,
                    "signed": False,
                    "big_endian": False,
                    "bitfield": False,
                    "bitpos": -1,
                    "bitlen": 0,
                    "mask": "",
                    "our_datatype": self._map_type(type_param),
                    "meta": {},
                    "file": "template",
                }
            )
            fields.append(
                {
                    "name": "service",
                    "ebus_type": "UCH",
                    "unit": "",
                    "factor": "",
                    "offset": "",
                    "length": 0,
                    "signed": False,
                    "big_endian": False,
                    "bitfield": False,
                    "bitpos": -1,
                    "bitlen": 0,
                    "mask": "",
                    "our_datatype": "UINT8",
                    "meta": {},
                    "file": "template",
                }
            )
        else:
            # Unknown template: assume single value field
            fields.append(
                {
                    "name": "value",
                    "ebus_type": type_param,
                    "unit": "",
                    "factor": "",
                    "offset": "",
                    "length": 0,
                    "signed": False,
                    "big_endian": False,
                    "bitfield": False,
                    "bitpos": -1,
                    "bitlen": 0,
                    "mask": "",
                    "our_datatype": self._map_type(type_param),
                    "meta": {},
                    "file": "template",
                }
            )

        return fields

    def _map_type(self, ebus_type: str) -> str:
        """Map an eBUS TypeSpec type to our datatype string."""
        t = ebus_type.strip()
        if "." in t:
            t = t.split(".")[-1]

        type_map = {
            # 1 byte
            "BI0": "UINT8", "BI1": "UINT8", "BI2": "UINT8", "BI3": "UINT8",
            "BI4": "UINT8", "BI5": "UINT8", "BI6": "UINT8", "BI7": "UINT8",
            "BI0_6": "UINT8", "BI0_7": "UINT8",
            "UCH": "UINT8", "U1L": "UINT8",
            "SCH": "INT8", "D1B": "INT8", "S1L": "INT8",
            "BCD": "UINT8", "HCD": "UINT8",
            "D1C": "UINT8",
            # 2 byte
            "PIN": "UINT16", "UIN": "UINT16", "UIR": "UINT16",
            "U2L": "UINT16", "U2B": "UINT16",
            "SIN": "INT16", "SIR": "INT16",
            "S2L": "INT16", "S2B": "INT16",
            "BCD2": "UINT16", "HCD2": "UINT16",
            "D2B": "INT16", "D2C": "INT16",
            "FLT": "INT16", "FLR": "INT16",
            # 3 byte
            "BCD3": "UINT32", "HCD3": "UINT32",
            "U3N": "UINT32", "U3R": "UINT32", "U3L": "UINT32", "U3B": "UINT32",
            "S3N": "INT32", "S3R": "INT32", "S3L": "INT32", "S3B": "INT32",
            # 4 byte
            "ULG": "UINT32", "ULR": "UINT32", "U4L": "UINT32", "U4B": "UINT32",
            "SLG": "INT32", "SLR": "INT32", "S4L": "INT32", "S4B": "INT32",
            "BCD4": "UINT32", "HCD4": "UINT32",
            "EXP": "FLOAT4", "EXR": "FLOAT4",
            # String
            "STR": "STRING", "NTS": "STRING", "IGN": "STRING", "HEX": "STRING",
            # Boolean
            "boolean": "BOOL",
        }
        return type_map.get(t, t.upper() if t else "")
