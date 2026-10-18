"""Map tsp IR to our internal IR and group into profiles/commands."""
from __future__ import annotations

import re
from typing import Dict, Any, List, Optional

try:
    from .model import FieldIR, ProfileIR, CommandIR, FamilyIR, profile_key_from_fields
except ImportError:
    from model import FieldIR, ProfileIR, CommandIR, FamilyIR, profile_key_from_fields


# Mapping from eBUS TypeSpec base types to our datatypes
# These are the base types from ebus-typespec/lib/types.tsp
TYPE_MAP: Dict[str, str] = {
    # 1 byte types
    "UCH": "UINT8",
    "SCH": "INT8",
    "D1B": "INT8",
    "D1C": "UINT8",
    "BCD": "UINT8",
    "HCD": "UINT8",
    "BI0": "UINT8", "BI1": "UINT8", "BI2": "UINT8", "BI3": "UINT8",
    "BI4": "UINT8", "BI5": "UINT8", "BI6": "UINT8", "BI7": "UINT8",
    "BI0_6": "UINT8", "BI0_7": "UINT8",
    "U1L": "UINT8",
    "D1C": "UINT8",
    "INT8": "INT8",
    "UINT8": "UINT8",
    # 2 byte types
    "PIN": "UINT16",
    "UIN": "UINT16",
    "UIR": "UINT16",
    "U2L": "UINT16",
    "U2B": "UINT16",
    "SIN": "INT16",
    "SIR": "INT16",
    "S2L": "INT16",
    "S2B": "INT16",
    "BCD2": "UINT16",
    "HCD2": "UINT16",
    "D2B": "INT16",
    "D2C": "INT16",
    "FLT": "INT16",
    "FLR": "INT16",
    "INT16": "INT16",
    "UINT16": "UINT16",
    # 3 byte types
    "BCD3": "UINT32",
    "HCD3": "UINT32",
    "U3N": "UINT32",
    "U3R": "UINT32",
    "U3L": "UINT32",
    "U3B": "UINT32",
    "S3N": "INT32",
    "S3R": "INT32",
    "S3L": "INT32",
    "S3B": "INT32",
    "INT32": "INT32",
    "UINT32": "UINT32",
    # 4 byte types
    "ULG": "UINT32",
    "ULR": "UINT32",
    "U4L": "UINT32",
    "U4B": "UINT32",
    "SLG": "INT32",
    "SLR": "INT32",
    "S4L": "INT32",
    "S4B": "INT32",
    "BCD4": "UINT32",
    "HCD4": "UINT32",
    "EXP": "FLOAT4",
    "EXR": "FLOAT4",
    "FLOAT4": "FLOAT4",
    # String types
    "STR": "CHAR1",
    "NTS": "CHAR1",
    "IGN": "CHAR1",
    "HEX": "HEX1",
    "CHAR1": "CHAR1",
    "CHAR2": "CHAR2",
    "CHAR3": "CHAR3",
    "CHAR4": "CHAR4",
    "CHAR5": "CHAR5",
    "CHAR6": "CHAR6",
    "CHAR7": "CHAR7",
    "CHAR8": "CHAR8",
    "HEX1": "HEX1",
    "HEX2": "HEX2",
    "HEX3": "HEX3",
    "HEX4": "HEX4",
    "HEX5": "HEX5",
    "HEX6": "HEX6",
    "HEX7": "HEX7",
    "HEX8": "HEX8",
    # Boolean/bit
    "boolean": "UINT8",
    "BOOL": "UINT8",
    # Date/time types (map to their byte sizes)
    "BTI": "UINT16",  # 2-byte time
    "BDA": "UINT16",  # 3-byte date, but we'll use UINT16 as placeholder
    "BDY": "UINT8",   # 1-byte weekday
    "BDT": "UINT8",   # 1-byte date variant
}

# Mapping from ebusd-configuration scalar names to our datatypes
# These are from _templates.tsp and device-specific includes
SCALAR_TYPE_MAP: Dict[str, str] = {
    # Counter types
    "cntstarts": "UINT32",      # BCD3 -> 3 bytes
    "cntminutes": "UINT8",      # BCD -> 1 byte
    "cnthours": "UINT32",       # BCD3 -> 3 bytes
    "cntfuel": "UINT32",        # BCD4 -> 4 bytes
    # Temperature types
    "temp": "DATA2C",           # D2C -> 2-byte signed with special handling
    "temp0": "UINT8",          # UCH -> 1 byte unsigned
    "temp1": "DATA1C",         # D1C -> 1-byte signed with special handling
    "temp2": "DATA2B",         # D2B -> 2-byte signed with special handling
    "tempsensor": "DATA2C",    # typically D2C
    "desiredtemp": "UINT8",    # UCH
    "outsidetemp": "INT8",      # SCH
    # Pressure types
    "press": "DATA2B",         # D2B
    "presssensor": "DATA2B",   # typically D2B
    # Percentage types
    "percent": "DATA2C",       # D2C with % unit
    "percent0": "UINT8",       # UCH with % unit
    "percent1": "DATA1C",      # D1C with % unit
    "percent2": "DATA2B",      # D2B with % unit
    "percents": "INT8",        # SCH with % unit
    # Status/on-off types
    "onoff": "UINT8",
    "yesno": "UINT8",
    "errorok": "UINT8",
    "phase": "UINT8",
    # Energy types
    "energy4": "UINT32",       # typically ULG
    "integral": "UINT32",
    # Unit/string types
    "unit": "UINT8",
    "fueltype": "UINT8",
    "countertype": "UINT8",
    "opdatacyclic": "UINT8",
    "opdatatransfer": "UINT8",
    "opdataheat": "UINT8",
    "opdataaction": "UINT8",
    # Skip/ignore
    "skip": "UINT8",
    "version": "UINT16",
    # String types
    "IGN": "CHAR1",
}

# Known enum types that map to UINT8
ENUM_TYPES: Dict[str, str] = {
    "Values_unit": "UINT8",
    "Values_fueltype": "UINT8",
    "Values_countertype": "UINT8",
    "Values_opdatacyclic": "UINT8",
    "Values_opdatatransfer": "UINT8",
    "Values_opdataheat": "UINT8",
    "Values_opdataaction": "UINT8",
}

# Single-field template models and their field names
_SINGLE_FIELD_TEMPLATES = {
    "ReadonlyRegister",
    "ReadonlyUpdateRegister",
    "WriteRegister",
    "InstallRegister",
    "ServiceCommandRegister",
}

_TWO_FIELD_TEMPLATES = {
    "ServiceUpdateRegister",
}


def _strip_qualified(ebus_type: str) -> str:
    """Strip namespace qualification from a type name (Ebus.Num.UCH -> UCH)."""
    t = (ebus_type or "").strip()
    if "." in t:
        t = t.split(".")[-1]
    return t


def _map_type(ebus_type: str) -> str:
    """Map an eBUS TypeSpec type to our datatype string."""
    # First try the direct type map
    mapped = TYPE_MAP.get(_strip_qualified(ebus_type))
    if mapped:
        return mapped
    # Try scalar type map (for named scalars like tempsensor, cntstarts, etc.)
    return SCALAR_TYPE_MAP.get(_strip_qualified(ebus_type), ebus_type.upper() if ebus_type else "")


def _map_profile_name(ebus_type: str, unit: str) -> str:
    """Map a field's ebus_type and unit to a profile name in data_profiles.json.
    
    This uses the datatype and unit to determine the appropriate profile name.
    """
    # Get the mapped datatype
    datatype = _map_type(ebus_type)
    unit_lower = (unit or "").strip().lower()
    
    # Special mappings based on type + unit combinations
    # Temperature
    if "celsius" in unit_lower or unit_lower == "°c" or unit_lower == "c":
        if datatype == "DATA2C":
            return "data2c_celsius"
        if datatype == "DATA2B":
            return "data2b_celsius"
        if datatype == "DATA1C":
            return "data1c_celsius"
        if datatype == "INT8":
            return "int8_celsius"
        if datatype == "UINT8":
            return "uint8_celsius"
    
    # Pressure
    if unit_lower == "bar":
        if datatype == "DATA2B":
            return "data2b_bar"
        if datatype == "FLOAT4":
            return "float4_bar"
        if datatype == "INT16":
            return "int16_bar"
    
    # Percentage
    if unit_lower in ("%", "percent"):
        if datatype == "INT16":
            return "int16_percent"
        if datatype == "UINT8":
            return "uint8_percent"
        if datatype == "INT8":
            return "int8_percent_div10"
    
    # Power
    if unit_lower == "kw":
        if datatype == "UINT8":
            return "uint8_kw"
        if datatype == "UINT16":
            return "uint16_kw_div10"
    
    # Energy
    if unit_lower == "kwh":
        if datatype == "UINT32":
            return "uint32_kwh"
    
    # Flow rate
    if unit_lower in ("l/min", "lpm"):
        if datatype == "DATA2C":
            return "data2c_lpm"
    if unit_lower == "l/h":
        if datatype == "UINT16":
            return "uint16_lph"
    if unit_lower == "m3/h":
        if datatype == "UINT16":
            return "uint16_m3h"
    
    # Time
    if unit_lower == "h" or unit_lower == "hour":
        if datatype == "UINT32":
            return "uint32_hour"
        if datatype == "UINT16":
            return "uint16_hour"
    
    if unit_lower == "min" or unit_lower == "minute":
        if datatype == "UINT16":
            return "uint16_min_div120"
    
    # RPM
    if unit_lower == "rpm":
        if datatype == "UINT16":
            return "uint16_rpm"
    
    # Basic type fallback
    basic_map = {
        "DATA2C": "data2c",
        "DATA2B": "data2b", 
        "DATA1C": "data1c",
        "DATA1B": "data1b",
        "UINT8": "uint8",
        "UINT16": "uint16",
        "UINT32": "uint32",
        "INT8": "int8",
        "INT16": "int16",
        "INT32": "int32",
        "FLOAT4": "float4",
        "CHAR1": "char1",
        "CHAR2": "char2",
        "CHAR3": "char3",
        "CHAR4": "char4",
        "CHAR5": "char5",
        "CHAR6": "char6",
        "CHAR7": "char7",
        "CHAR8": "char8",
        "HEX1": "hex1",
        "HEX2": "hex2",
        "HEX3": "hex3",
        "HEX4": "hex4",
        "HEX5": "hex5",
        "HEX6": "hex6",
        "HEX7": "hex7",
        "HEX8": "hex8",
    }
    return basic_map.get(datatype, "uint8")


def _parse_factor(args_str: Optional[str]) -> Optional[float]:
    """Parse a numeric factor/divisor argument."""
    if not args_str:
        return None
    try:
        return float(args_str.strip())
    except ValueError:
        return None


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase or PascalCase to snake_case."""
    # Insert underscore before capital letters, then lowercase
    s1 = re.sub(r"([A-Z])", r"_\1", name)
    return s1.lower().lstrip("_")


def _format_command_name(model_name: str, namespace: str = "") -> str:
    """Format a command name from model name and namespace.
    
    Converts CamelCase to hierarchy format like Buffer/Middle_Temperature
    """
    # Split by namespace if present
    parts = []
    if namespace:
        # Convert namespace to path-like (Vaillant.Ehp -> Ehp)
        ns_parts = namespace.split(".")
        for ns in ns_parts:
            if ns and ns != "Vaillant":
                parts.append(_camel_to_snake(ns))
    
    # Add the model name
    model_snake = _camel_to_snake(model_name)
    
    # For models that look like they're in groups, split them
    # e.g., "HwcTemp" -> we might want to keep as is or split
    # But from the working commands.json, names are like:
    # "Buffer/Middle_Temperature", "Compressor/Hours"
    # So we need to understand the naming convention from ebusd-configuration
    
    # For now, just use the model name as-is in snake_case
    parts.append(model_snake)
    
    return "/".join(parts) if parts else model_snake


def tsp_type_to_datatype(tsp_type: str) -> str:
    """Map ebusd/tsp type to our datatype."""
    return _map_type(tsp_type)


def profiles_to_flat_entries(fam: FamilyIR) -> List[Dict[str, Any]]:
    """Convert FamilyIR profiles to flat data_profiles.json schema entries.

    Each unique field in each profile becomes one flat entry:
    {name, datatype, unit, divider, digits, min, max}
    
    Note: We deduplicate by (name, datatype, unit, divider) to avoid duplicates.
    """
    entries: List[Dict[str, Any]] = []
    seen: set = set()
    
    for key, p in fam.profiles.items():
        for f in p.fields:
            # Create a unique key for deduplication
            dedup_key = (f.name, f.our_datatype or f.ebus_type, f.unit, f.factor)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            
            try:
                divider = float(f.factor) if f.factor else 1.0
            except ValueError:
                divider = 1.0
            
            # Parse digits from meta
            digits = 0
            meta_digits = f.meta.get("digits")
            if isinstance(meta_digits, int):
                digits = meta_digits
            elif isinstance(meta_digits, str):
                try:
                    digits = int(meta_digits)
                except ValueError:
                    digits = 0
            
            # Get min/max from meta
            min_val = f.meta.get("min", 0)
            max_val = f.meta.get("max", 0)
            
            # Convert to int if they're whole numbers
            if isinstance(min_val, float) and min_val.is_integer():
                min_val = int(min_val)
            if isinstance(max_val, float) and max_val.is_integer():
                max_val = int(max_val)
            
            entries.append({
                "name": f.name,
                "datatype": f.our_datatype or _map_type(f.ebus_type),
                "unit": f.unit or "",
                "divider": divider if divider != 1.0 else 1,
                "digits": digits,
                "min": min_val,
                "max": max_val,
            })
    
    return entries


def commands_to_flat_entries(fam: FamilyIR, key_prefix: str = "", aliases: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Convert FamilyIR commands to config/simulation.json schema entries.

    {key, name, read_cmd, write_cmd, interval, master, 
     fields: [{name, profile, position, ha_profile}]}
    """
    entries: List[Dict[str, Any]] = []
    
    # Try to get MF from aliases if not in meta
    default_mf = 0x00
    if aliases and "MF" in aliases:
        try:
            default_mf = int(aliases["MF"], 16)
        except ValueError:
            default_mf = 0x00
    
    for idx, c in enumerate(fam.commands, start=1):
        meta = c.meta or {}
        
        # Get addressing from meta
        # Command format: ZZ PB SB NN D1 D2 D3 (7 bytes)
        # Where:
        #   ZZ = destination address (from @zz or default 0x08)
        #   PB = source address/MF (from MF alias via @base decorator)
        #   SB = primary command (from @base second arg)
        #   NN = 0x03 for read, 0x04 for write
        #   D1 = secondary command (from @base third arg or default 0x0d for read)
        #   D2 = extension PB (from @ext first arg)
        #   D3 = extension SB (from @ext second arg)
        zz = meta.get("zz", 0x08)  # Default ZZ
        mf = meta.get("mf", default_mf)  # Default MF (should come from @base decorator with MF alias)
        pb = meta.get("pb", 0x09)  # Default PB
        
        # SB values: from @base or @ext
        sb_read = meta.get("sb", 0x0d)  # Default SB for read
        sb_write = meta.get("sb_write", meta.get("sb", 0x0e))  # SB for write
        
        # Extension bytes from @ext decorator
        ext_pb = meta.get("ext_pb", 0x00)
        ext_sb = meta.get("ext_sb", 0x00)
        
        # NN: 0x03 for read, 0x04 for write
        nn_read = 0x03
        nn_write = 0x04
        
        # Build full ebus read command: ZZ PB SB NN D1 D2 D3
        # Format: lowercase hex without spaces, exactly 14 hex chars (7 bytes)
        # Example: 08b509030d9a00 where:
        #   ZZ=08 (destination), PB=b5 (source/MF), SB=09, NN=03, D1=0d, D2=9a, D3=00
        read_cmd = f"{zz:02x}{mf:02x}{pb:02x}{nn_read:02x}{sb_read:02x}{ext_pb:02x}{ext_sb:02x}"
        
        # Write command: ZZ PB SB NN D1 D2 D3 with NN=0x04
        # Only generate if rw == "write"
        write_cmd = f"{zz:02x}{mf:02x}{pb:02x}{nn_write:02x}{sb_write:02x}{ext_pb:02x}{ext_sb:02x}" if c.rw == "write" else ""
        
        # Determine key
        # Use sequential numbering with 3-digit zero-padding by default
        # This matches the working commands.json format ("01", "02", etc.)
        key = f"{idx:03d}"
        
        # Override with prefix if provided
        if key_prefix:
            key = f"{key_prefix}{key}"
        
        # Build fields with 1-based position
        fields: List[Dict[str, Any]] = []
        for pos, f in enumerate(c.fields, start=1):
            # Get the profile name based on type and unit
            profile = _map_profile_name(f.ebus_type, f.unit or "")
            
            # Get min/max overrides from field meta
            min_val = f.meta.get("min") if f.meta.get("min") is not None else None
            max_val = f.meta.get("max") if f.meta.get("max") is not None else None
            
            field_entry = {
                "name": f.name,
                "profile": profile,
                "position": pos,
                "ha_profile": "",
            }
            
            # Add min/max if present
            if min_val is not None:
                field_entry["min"] = min_val
            if max_val is not None:
                field_entry["max"] = max_val
            
            fields.append(field_entry)
        
        entries.append({
            "key": key,
            "name": _format_command_name(c.name, meta.get("namespace", "")),
            "read_cmd": read_cmd,
            "write_cmd": write_cmd,
            "interval": 0,  # Default to passive only
            "master": False,  # Default
            "fields": fields,
        })
    
    return entries


def build_profiles_and_commands(raw: Dict[str, Any], manufacturer: int = 0x00) -> FamilyIR:
    """Build FamilyIR from raw tsp parser IR.

    Converts parser-extracted registers (commands) and fields into
    FamilyIR with ProfileIR grouping and CommandIR entries.
    """
    fam = FamilyIR()

    registers: List[Dict[str, Any]] = raw.get("registers", [])
    enums: Dict[str, Any] = raw.get("enums", {})
    scalars: Dict[str, Any] = raw.get("scalars", {})
    aliases: Dict[str, Any] = raw.get("aliases", {})

    # Identify base models that are only used for inheritance
    # These are models that appear in other models' @inherit decorators
    inherited_model_names: set = set()
    for reg in registers:
        inherit_list = reg.get("inherit") or []
        for parent_name in inherit_list:
            inherited_model_names.add(parent_name)

    # Build a namespace context from the file structure
    # For now, we'll extract it from the register meta if available
    
    # Resolve scalar aliases and types: if a field type is an alias or scalar,
    # follow to the base type and collect metadata
    def resolve_type_and_meta(t: str) -> tuple[str, Dict[str, Any]]:
        """Resolve a type to its base type and collect metadata (unit, min, max, etc.)"""
        t_orig = t
        t = _strip_qualified(t)
        visited: set[str] = set()
        meta: Dict[str, Any] = {}
        
        # Follow alias chain
        while t in aliases and t not in visited:
            visited.add(t)
            alias_val = aliases[t]
            # Check if alias has metadata
            if alias_val in scalars:
                scalar = scalars[alias_val]
                meta.update(scalar.get("meta", {}))
                t = _strip_qualified(scalar.get("base_type", ""))
            else:
                t = _strip_qualified(alias_val)
        
        # Follow scalar chain
        while t in scalars and t not in visited:
            visited.add(t)
            scalar = scalars[t]
            meta.update(scalar.get("meta", {}))
            # Extract decorator-based metadata from scalar
            # In TSP, scalars can have decorators like @unit("°C")
            # These are stored in the scalar's meta in our parser
            if "unit" in scalar:
                meta["unit"] = scalar["unit"]
            if "minValue" in scalar:
                meta["min"] = scalar["minValue"]
            if "maxValue" in scalar:
                meta["max"] = scalar["maxValue"]
            if "step" in scalar:
                step_val = scalar["step"]
                if isinstance(step_val, str):
                    try:
                        step_float = float(step_val)
                        if "." in step_val:
                            meta["digits"] = len(step_val.split(".")[1].rstrip("0"))
                    except ValueError:
                        pass
            if "maxLength" in scalar:
                meta["max_length"] = scalar["maxLength"]
            
            t = _strip_qualified(scalar.get("base_type", ""))
        
        # Check if it's an enum
        if t in enums:
            meta["values_enum"] = t
            meta["values"] = enums[t].get("entries", [])
        
        return t, meta

    # Process each register into commands
    for reg in registers:
        reg_name = reg.get("name", "unnamed")
        reg_str = reg.get("register", "")
        rw = reg.get("rw", "read")
        meta = dict(reg.get("meta", {}))
        reg_fields = reg.get("fields", [])
        template_name = reg.get("template")
        template_type = reg.get("template_type")
        namespace = meta.get("namespace", "")
        
        # Store namespace in meta for later use
        if namespace:
            meta["namespace"] = namespace
        
        # Build FieldIR list from raw fields
        field_irs: List[FieldIR] = []
        
        if template_name and template_type:
            # Handle template models
            if template_name in _SINGLE_FIELD_TEMPLATES:
                # Single field template: the type is template_type
                resolved_type, type_meta = resolve_type_and_meta(template_type)
                
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(f_ebus_type)
                
                # Get unit from template_type metadata or scalar
                f_unit = type_meta.get("unit", "")
                
                # Parse factor
                factor_str = type_meta.get("factor", type_meta.get("divisor", ""))
                factor_val = _parse_factor(factor_str) if factor_str else None
                
                # Determine digits
                digits = type_meta.get("digits", 0)
                if isinstance(digits, str):
                    try:
                        digits = int(digits)
                    except ValueError:
                        digits = 0
                
                # Create field IR for the value field
                field_ir = FieldIR(
                    name="value",
                    ebus_type=f_ebus_type,
                    unit=f_unit,
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=f_ebus_type.startswith(("S", "s")) or f_our_datatype.startswith("INT"),
                    big_endian="R" in f_ebus_type or ("B" in f_ebus_type and "L" not in f_ebus_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=f_our_datatype,
                    meta=type_meta,
                )
                field_irs.append(field_ir)
            
            elif template_name in _TWO_FIELD_TEMPLATES:
                # Two field template: value + service
                resolved_type, type_meta = resolve_type_and_meta(template_type)
                
                # Value field
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(f_ebus_type)
                f_unit = type_meta.get("unit", "")
                factor_str = type_meta.get("factor", type_meta.get("divisor", ""))
                factor_val = _parse_factor(factor_str) if factor_str else None
                digits = type_meta.get("digits", 0)
                if isinstance(digits, str):
                    try:
                        digits = int(digits)
                    except ValueError:
                        digits = 0
                
                field_ir = FieldIR(
                    name="value",
                    ebus_type=f_ebus_type,
                    unit=f_unit,
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=f_ebus_type.startswith(("S", "s")) or f_our_datatype.startswith("INT"),
                    big_endian="R" in f_ebus_type or ("B" in f_ebus_type and "L" not in f_ebus_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=f_our_datatype,
                    meta=type_meta,
                )
                field_irs.append(field_ir)
                
                # Service field (UINT8)
                field_ir = FieldIR(
                    name="service",
                    ebus_type="UCH",
                    unit="",
                    factor="",
                    offset="",
                    length=0,
                    signed=False,
                    big_endian=False,
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype="UINT8",
                    meta={},
                )
                field_irs.append(field_ir)
            else:
                # Unknown template: assume single value field
                resolved_type, type_meta = resolve_type_and_meta(template_type)
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(f_ebus_type)
                
                field_ir = FieldIR(
                    name="value",
                    ebus_type=f_ebus_type,
                    unit=type_meta.get("unit", ""),
                    factor=type_meta.get("factor", ""),
                    offset="",
                    length=0,
                    signed=f_ebus_type.startswith(("S", "s")) or f_our_datatype.startswith("INT"),
                    big_endian="R" in f_ebus_type or ("B" in f_ebus_type and "L" not in f_ebus_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=f_our_datatype,
                    meta=type_meta,
                )
                field_irs.append(field_ir)
        else:
            # Regular model with explicit fields
            for f in reg_fields:
                f_name = f.get("name", "")
                f_ebus_type = f.get("ebus_type", "")
                f_decorators = f.get("decorators", [])
                f_meta = f.get("meta", {})
                
                # Resolve the type and get metadata
                resolved_type, type_meta = resolve_type_and_meta(f_ebus_type)
                
                # Merge metadata
                merged_meta = {**type_meta, **f_meta}
                
                # If field has its own decorators, extract metadata from them
                for dec in f_decorators:
                    dname = dec.get("name", "")
                    args = dec.get("args", [])
                    
                    if dname == "unit" and args:
                        merged_meta["unit"] = args[0].strip('"').strip("'")
                    elif dname == "factor" and args:
                        merged_meta["factor"] = args[0]
                    elif dname == "divisor" and args:
                        merged_meta["factor"] = args[0]
                    elif dname == "step" and args:
                        s = args[0].strip()
                        try:
                            step_float = float(s)
                            if "." in s:
                                merged_meta["digits"] = len(s.split(".")[1].rstrip("0"))
                        except ValueError:
                            pass
                    elif dname == "minValue" and args:
                        try:
                            merged_meta["min"] = int(args[0])
                        except ValueError:
                            try:
                                merged_meta["min"] = float(args[0])
                            except ValueError:
                                pass
                    elif dname == "maxValue" and args:
                        try:
                            merged_meta["max"] = int(args[0])
                        except ValueError:
                            try:
                                merged_meta["max"] = float(args[0])
                            except ValueError:
                                pass
                
                # Determine signedness
                signed = resolved_type.startswith(("S", "s"))
                
                # Determine endianness
                big_endian = "R" in resolved_type or ("B" in resolved_type and "L" not in resolved_type)
                
                # Bitfield info
                bitfield = f.get("bitfield", False)
                bitpos = f.get("bitpos", -1)
                bitlen = f.get("bitlen", 0)
                mask = f.get("mask", "")
                
                # Get factor from merged metadata
                factor_str = merged_meta.get("factor", merged_meta.get("divisor", ""))
                factor_val = _parse_factor(factor_str) if factor_str else None
                
                # Get unit from merged metadata
                unit = merged_meta.get("unit", "")
                
                # Get digits
                digits = merged_meta.get("digits", 0)
                if isinstance(digits, str):
                    try:
                        digits = int(digits)
                    except ValueError:
                        digits = 0
                
                field_ir = FieldIR(
                    name=f_name,
                    ebus_type=resolved_type or f_ebus_type,
                    unit=unit,
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=signed,
                    big_endian=big_endian,
                    bitfield=bitfield,
                    bitpos=bitpos,
                    bitlen=bitlen,
                    mask=mask,
                    our_datatype=_map_type(resolved_type or f_ebus_type),
                    meta=merged_meta,
                )
                field_irs.append(field_ir)

        # Determine if command is writable
        unsupported = False
        unsupported_reason = ""
        
        if rw == "write":
            pass  # write_cmd will be generated
        elif rw == "read":
            pass  # read only
        else:
            unsupported = True
            unsupported_reason = f"unknown rw direction: {rw}"

        cmd_ir = CommandIR(
            name=reg_name,
            profile_key=None,
            register=reg_str,
            rw=rw,
            write_cmd="",  # Will be regenerated in commands_to_flat_entries
            fields=field_irs,
            unsupported=unsupported,
            unsupported_reason=unsupported_reason,
            meta=meta,
        )
        # Skip base models that are only used for inheritance
        if reg_name not in inherited_model_names:
            fam.commands.append(cmd_ir)

    # Group commands into profiles by canonical field semantics
    _group_profiles(fam)

    return fam


def _group_profiles(fam: FamilyIR) -> None:
    """Group commands into profiles by canonical field semantics.

    Groups by: datatype + unit + scaling + signedness + endianness.
    Each group becomes a ProfileIR; commands reference it via profile_key.
    """
    groups: Dict[str, List[CommandIR]] = {}

    for cmd in fam.commands:
        if not cmd.fields:
            key = "no_fields"
        else:
            # Derive profile key from first field's semantics
            f = cmd.fields[0]
            key_parts = [
                f.our_datatype or f.ebus_type or "x",
                f.unit or "",
                f.factor or "",
                "s" if f.signed else "u",
                "be" if f.big_endian else "le",
            ]
            key = "_".join(p for p in key_parts if p)
            if len(key) > 24:
                key = key[:24]

        if key not in groups:
            groups[key] = []
        groups[key].append(cmd)

    # Build ProfileIRs and assign profile_key to commands
    for key, cmds in groups.items():
        # Collect all unique fields from commands in this group
        seen_fields: Dict[str, FieldIR] = {}
        for cmd in cmds:
            for f in cmd.fields:
                if f.name not in seen_fields:
                    seen_fields[f.name] = f

        profile_fields = list(seen_fields.values())
        profile_ir = ProfileIR(key=key, fields=profile_fields, meta={})
        fam.profiles[key] = profile_ir

        # Assign profile_key to commands in this group
        for cmd in cmds:
            cmd.profile_key = key
