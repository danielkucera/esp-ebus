"""Map tsp IR to our internal IR and group into profiles/commands."""
from __future__ import annotations

import re
from typing import Dict, Any, List, Optional

try:
    from .model import FieldIR, ProfileIR, CommandIR, FamilyIR, profile_key_from_fields
    from .convlog import NULL_LOG, ConversionLog
except ImportError:
    from model import FieldIR, ProfileIR, CommandIR, FamilyIR, profile_key_from_fields
    from convlog import NULL_LOG, ConversionLog


# Mapping from eBUS TypeSpec base types to our datatypes
# These are the base types from ebus-typespec/lib/types.tsp
TYPE_MAP: Dict[str, str] = {
    # 1 byte types
    "UCH": "UINT8",
    "SCH": "INT8",
    "D1B": "DATA1B",   # 1-byte signed fixed-point (ebus::DataType::data1b)
    "D1C": "DATA1C",   # 1-byte unsigned fixed-point /2 (ebus::DataType::data1c)
    "BCD": "BCD",
    "HCD": "UINT8",    # 1-byte HCD: no native library type, treat as raw UINT8
    "BI0": "UINT8", "BI1": "UINT8", "BI2": "UINT8", "BI3": "UINT8",
    "BI4": "UINT8", "BI5": "UINT8", "BI6": "UINT8", "BI7": "UINT8",
    "BI0_6": "UINT8", "BI0_7": "UINT8",
    "U1L": "UINT8",
    "S1L": "INT8",
    "INT8": "INT8",
    "UINT8": "UINT8",
    # 2 byte types
    "PIN": "UINT16",   # 2-byte BCD reversed; no native PIN type, raw UINT16
    "UIN": "UINT16",
    "UIR": "UINT16R",
    "U2L": "UINT16",
    "U2B": "UINT16R",
    "SIN": "INT16",
    "SIR": "INT16R",
    "S2L": "INT16",
    "S2B": "INT16R",
    "BCD2": "UINT16",  # 2-byte BCD; no native type, raw UINT16
    "HCD2": "UINT16",  # 2-byte HCD; no native type, raw UINT16
    "D2B": "DATA2B",   # 2-byte signed fixed-point /256 (ebus::DataType::data2b)
    "D2C": "DATA2C",   # 2-byte signed fixed-point /16 (ebus::DataType::data2c)
    "FLT": "INT16",    # 2-byte /1000 — INT16; no dedicated FLT type
    "FLR": "INT16R",   # same, big-endian
    "INT16": "INT16",
    "UINT16": "UINT16",
    # 3 byte types — U3N/S3N families have native 24-bit DataTypes;
    # BCD3/HCD3 and the no-sentinel U3L/U3B/S3L/S3B variants do not
    "BCD3": "CHAR3",   # 3-byte BCD (cntstarts, cnthours): no native type yet
    "HCD3": "CHAR3",   # 3-byte HCD: no native type yet
    "U3N": "UINT24",
    "U3R": "UINT24R",
    "U3L": "CHAR3",
    "U3B": "CHAR3",
    "S3N": "INT24",
    "S3R": "INT24R",
    "S3L": "CHAR3",
    "S3B": "CHAR3",
    "INT32": "INT32",
    "UINT32": "UINT32",
    # 4 byte types
    "ULG": "UINT32",
    "ULR": "UINT32R",
    "U4L": "UINT32",
    "U4B": "UINT32R",
    "SLG": "INT32",
    "SLR": "INT32R",
    "S4L": "INT32",
    "S4B": "INT32R",
    "BCD4": "UINT32",  # 4-byte BCD/HCD: no native type, raw UINT32
    "HCD4": "UINT32",
    "EXP": "FLOAT4",
    "EXR": "FLOAT4R",
    "FLOAT4": "FLOAT4",
    "FLOAT4R": "FLOAT4R",
    # String types — @maxLength handled by _map_type(); fallback CHAR1/HEX1
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
    "CHAR9": "CHAR9",
    "CHAR10": "CHAR10",
    "CHAR11": "CHAR11",
    "CHAR12": "CHAR12",
    "CHAR13": "CHAR13",
    "CHAR14": "CHAR14",
    "CHAR15": "CHAR15",
    "CHAR16": "CHAR16",
    "HEX1": "HEX1",
    "HEX2": "HEX2",
    "HEX3": "HEX3",
    "HEX4": "HEX4",
    "HEX5": "HEX5",
    "HEX6": "HEX6",
    "HEX7": "HEX7",
    "HEX8": "HEX8",
    "HEX9": "HEX9",
    "HEX10": "HEX10",
    "HEX11": "HEX11",
    "HEX12": "HEX12",
    "HEX13": "HEX13",
    "HEX14": "HEX14",
    "HEX15": "HEX15",
    "HEX16": "HEX16",
    # Boolean/bit — no native BOOL DataType; boolean → UINT8
    "boolean": "UINT8",
    "BOOL": "UINT8",
    # Date/time types — no native semantic DataType; store as raw bytes
    "BTI": "CHAR3",    # 3-byte BCD time (seconds-first, reversed)
    "HTI": "CHAR3",    # 3-byte decimal time
    "VTI": "CHAR3",    # 3-byte decimal time [Vaillant]
    "BTM": "UINT16",   # 2-byte BCD time hh:mm
    "HTM": "UINT16",   # 2-byte decimal time hh:mm
    "VTM": "UINT16R",  # 2-byte decimal time hh:mm [Vaillant, reversed]
    "MIN": "UINT16",   # 2-byte minutes since midnight
    "TTM": "UINT8",    # 1-byte truncated time (/10 min)
    "TTH": "UINT8",    # 6-bit truncated time (/30 min)
    "TTQ": "UINT8",    # 7-bit truncated time (/15 min)
    "BDA": "CHAR4",    # 4-byte BCD date with weekday
    "HDA": "CHAR4",    # 4-byte decimal date with weekday
    "BDA3": "CHAR3",   # 3-byte BCD date
    "HDA3": "CHAR3",   # 3-byte decimal date
    "BDZ": "CHAR4",    # 4-byte BCD date with zero-based weekday
    "DAY": "UINT16",   # 2-byte days since 1900-01-01
    "DTM": "UINT32",   # 4-byte minutes since 2009-01-01
    "BDY": "UINT8",    # 1-byte weekday (Mon=0)
    "HDY": "UINT8",    # 1-byte weekday [Vaillant] (Mon=1)
}

# Byte size per ebus-library DataType name (matches ebus::DataType enum high byte).
# Used to compute the eBUS write NN byte: NN = 3 + data_byte_count.
DATATYPE_SIZE: Dict[str, int] = {
    # 1 byte
    "BCD": 1, "UINT8": 1, "INT8": 1, "DATA1B": 1, "DATA1C": 1, "CHAR1": 1, "HEX1": 1, "BOOL": 1,
    # 2 bytes
    "UINT16": 2, "UINT16R": 2, "INT16": 2, "INT16R": 2, "DATA2B": 2, "DATA2BR": 2,
    "DATA2C": 2, "DATA2CR": 2, "CHAR2": 2, "HEX2": 2,
    # 3 bytes
    "UINT24": 3, "UINT24R": 3, "INT24": 3, "INT24R": 3, "CHAR3": 3, "HEX3": 3,
    # 4 bytes
    "UINT32": 4, "UINT32R": 4, "INT32": 4, "INT32R": 4, "FLOAT4": 4, "FLOAT4R": 4,
    "CHAR4": 4, "HEX4": 4,
    # 5-8 bytes
    "CHAR5": 5, "HEX5": 5, "CHAR6": 6, "HEX6": 6, "CHAR7": 7, "HEX7": 7, "CHAR8": 8, "HEX8": 8,
    # 9-16 bytes (ebusd defines these via @maxLength on STR/HEX). The
    # protocol caps NN at 16 data bytes (spec 5.6, max_data_bytes), so
    # nothing wider than 16 can occur on the wire — no rows beyond this.
    "CHAR9": 9, "HEX9": 9, "CHAR10": 10, "HEX10": 10, "CHAR11": 11, "HEX11": 11,
    "CHAR12": 12, "HEX12": 12, "CHAR13": 13, "HEX13": 13, "CHAR14": 14, "HEX14": 14,
    "CHAR15": 15, "HEX15": 15, "CHAR16": 16, "HEX16": 16,
}

# ebus-library native DataTypes it can actually decode/encode.
# Anything not in this set cannot be turned into a data profile.
# Source of truth: ebus::DataType enum in include/ebus/data_types.hpp.
SUPPORTED_DATATYPES: set = {
    # 1 byte
    "BCD", "UINT8", "INT8", "DATA1B", "DATA1C", "BOOL", "CHAR1", "HEX1",
    # 2 bytes
    "UINT16", "UINT16R", "INT16", "INT16R", "DATA2B", "DATA2BR",
    "DATA2C", "DATA2CR", "CHAR2", "HEX2",
    # 3 bytes
    "UINT24", "UINT24R", "INT24", "INT24R", "CHAR3", "HEX3",
    # 4 bytes
    "UINT32", "UINT32R", "INT32", "INT32R", "FLOAT4", "FLOAT4R",
    "CHAR4", "HEX4",
    # 5-8 bytes
    "CHAR5", "HEX5", "CHAR6", "HEX6", "CHAR7", "HEX7", "CHAR8", "HEX8",
    # 9-16 bytes
    "CHAR9", "HEX9", "CHAR10", "HEX10", "CHAR11", "HEX11",
    "CHAR12", "HEX12", "CHAR13", "HEX13", "CHAR14", "HEX14",
    "CHAR15", "HEX15", "CHAR16", "HEX16",
}

# Mapping from ebusd-configuration scalar names to our datatypes
# These are from _templates.tsp and device-specific includes
SCALAR_TYPE_MAP: Dict[str, str] = {
    # Counter types
    "cntstarts": "CHAR3",      # BCD3 -> 3-byte raw (no native BCD3 DataType yet)
    "cntstarts2": "UINT16",    # UIN -> 2-byte unsigned
    "cntminutes": "BCD",       # BCD -> 1 byte
    "cnthours": "CHAR3",       # BCD3 -> 3 bytes
    "cntfuel": "UINT32",       # BCD4 -> 4 bytes
    # Temperature types
    "temp": "DATA2C",           # D2C -> 2-byte signed with special handling
    "temp0": "UINT8",          # UCH -> 1 byte unsigned
    "temp1": "DATA1C",         # D1C -> 1-byte signed with special handling
    "temp2": "DATA2B",         # D2B -> 2-byte signed with special handling
    "tempsensor": "DATA2C",    # typically D2C
    "tempmirrorsensor": "UINT16",  # UIN
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
    "onoff2": "UINT8",
    "yesno": "UINT8",
    "yesno2": "UINT8",
    "errorok": "UINT8",
    "phase": "UINT8",
    "phaseok": "UINT8",
    "dcfstate": "UINT8",
    # Energy types
    "energy4": "UINT32",       # typically ULG
    "energy": "UINT16",        # UIN
    "integral": "INT16",       # SIN
    # Flow / speed
    "fanspeed": "UINT16",      # UIN
    "fanspeedoffset": "INT16", # SIN
    "flowrate": "UINT16",      # UIN
    "flowrate100": "UINT16",   # UIN
    "airflowrate": "UINT16",   # UIN
    "speed": "UINT16",         # UIN
    # Time
    "hoursum": "UINT32",       # ULG -> 4 bytes
    "hoursum2": "UINT16",      # UIN -> 2 bytes
    "hours": "UINT8",          # HCD / UCH -> 1 byte
    "hours1": "DATA1C",        # D1C -> 1 byte / 2
    "minutes": "UINT16",       # UIN
    "minutes0": "UINT8",       # UCH
    "minutes2": "UINT16",      # UIN
    "seconds": "UINT32",       # ULG
    "seconds0": "UINT8",       # UCH
    "seconds2": "UINT16",      # UIN
    "seconds4": "UINT32",      # ULG
    # Unit/string types
    "unit": "UINT8",
    "fueltype": "UINT8",
    "countertype": "UINT8",
    "opdatacyclic": "UINT8",
    "opdatatransfer": "UINT8",
    "opdataheat": "UINT8",
    "opdataaction": "UINT8",
    "mcmode": "UINT8",
    "power": "UINT8",
    # Calibration
    "calibration": "DATA2C",   # D2C
    "calibration0": "UINT8",   # UCH
    "calibration1": "DATA1C",  # D1C
    "calibrations": "INT8",    # SCH
    # Misc numeric
    "uin100": "UINT16",        # UIN
    "version": "UINT16",
    "pressm2": "UINT16",       # UIN
    "curve": "UINT16",         # UIN
    "frequency": "UINT16",     # UIN
    # Skip/ignore
    "skip": "UINT8",
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

# Template models whose instances are writable on the eBUS bus (respond to
# write commands, NN=0x04) unless explicitly marked @passive.
_WRITABLE_TEMPLATES = {
    "WriteRegister",
    "InstallRegister",
    "ServiceCommandRegister",
    "UpdateRegister",
    "InstallUpdateRegister",
    "ServiceUpdateRegister",
}

# eBUS bitfield types: BI0..BI7 are individual bits (ebus-typespec
# `scalar BI0 extends boolean`), phase1..3 extend them, and plain boolean
# fields are bit payloads too. The firmware command writer packs at most
# 4 bytes per field and cannot emit these wire payloads faithfully, so any
# command carrying one is dropped (resolved type "boolean"/"BOOL" as well
# as the raw scalar names when the typespec library is not loaded).
_BIT_GATED_EBUS_TYPES = frozenset(
    {"boolean", "BOOL"}
    | {f"BI{i}" for i in range(8)}
    | {"phase1", "phase2", "phase3"}
)


def _bit_index(ebus_type: str) -> Optional[int]:
    """Bit number of a BI0..BI7 type, else None."""
    t = _strip_qualified(ebus_type)
    if t.startswith("BI") and t[2:].isdigit():
        n = int(t[2:])
        if n <= 7:
            return n
    return None


def _merge_bit_runs(fields: List[FieldIR]) -> List[FieldIR]:
    """Collapse each consecutive BI0..BI7 run into one byte-wide UINT8 field.

    The bits of a run share a single wire byte, which byte-positioned fields
    cannot represent individually: keep the first member's name, carry the
    whole run as a `bits` name->bit-index map in meta, and count it as one
    UINT8 byte for positions and NN.
    """
    merged: List[FieldIR] = []
    i = 0
    while i < len(fields):
        if _bit_index(fields[i].ebus_type) is None:
            merged.append(fields[i])
            i += 1
            continue
        run: List[FieldIR] = []
        while i < len(fields) and _bit_index(fields[i].ebus_type) is not None:
            run.append(fields[i])
            i += 1
        head = run[0]
        merged.append(
            FieldIR(
                name=head.name,
                ebus_type="UINT8",
                unit=head.unit,
                factor=head.factor,
                offset=head.offset,
                length=1,
                signed=head.signed,
                big_endian=head.big_endian,
                bitfield=True,
                bitpos=0,
                bitlen=8,
                mask=head.mask,
                our_datatype="UINT8",
                meta={**head.meta, "bits": {f.name: _bit_index(f.ebus_type) for f in run}},
            )
        )
    return merged


def _strip_qualified(ebus_type: str) -> str:
    """Strip namespace qualification from a type name (Ebus.Num.UCH -> UCH)."""
    t = (ebus_type or "").strip()
    if "." in t:
        t = t.split(".")[-1]
    return t


def _map_type(ebus_type: str, max_length: Optional[int] = None) -> str:
    """Map an eBUS TypeSpec type to our datatype string.

    For STR/HEX types the @maxLength decorator selects the exact CHAR/HEX
    width (e.g. STR + maxLength(21) → CHAR21). The protocol allows at most
    16 data bytes (spec 5.6, max_data_bytes) and the ebus-library implements
    CHAR1-16 / HEX1-16; wider types are flagged as unsupported by the caller.
    """
    t = _strip_qualified(ebus_type)
    mapped = TYPE_MAP.get(t)
    if mapped:
        if t in ("STR", "HEX") and max_length:
            base = "CHAR" if t == "STR" else "HEX"
            return f"{base}{max_length}"
        return mapped
    # Try scalar type map (for named scalars like tempsensor, cntstarts, etc.)
    return SCALAR_TYPE_MAP.get(t, ebus_type.upper() if ebus_type else "")


def _classify_type(ebus_type: str, datatype: str, enums: Optional[Dict[str, Any]] = None) -> str:
    """Classify an ebusd TypeSpec type for the conversion log.

    Returns one of: native, profile, unsupported, defaulted.

    Classification is based on the mapped ebus-library datatype; CHAR/HEX
    types wider than 16 bytes are unsupported because the protocol allows
    at most 16 data bytes (spec 5.6, max_data_bytes) — CHAR17+ cannot
    occur on the wire.
    """
    t = _strip_qualified(ebus_type)
    d = _strip_qualified(datatype)
    # CHAR/HEX width check on the mapped datatype (STR/HEX with @maxLength)
    if d.startswith(("CHAR", "HEX")):
        try:
            prefix = "CHAR" if d.startswith("CHAR") else "HEX"
            width = int(d[len(prefix):])
        except ValueError:
            width = 0
        if width > 16:
            return "unsupported"
    if t in TYPE_MAP:
        return "native"
    if t in SCALAR_TYPE_MAP:
        return "profile"
    if enums and t in enums:
        # Enum types resolve to UINT8 (native), not "unsupported".
        # They decode correctly on the wire; flag as native so validation
        # doesn't reject them.
        return "native"
    return "defaulted"


def _map_profile_name(ebus_type: str, unit: str, max_length: Optional[int] = None) -> str:
    """Map a field's ebus_type and unit to a profile name in data_profiles.json.
    
    This uses the datatype and unit to determine the appropriate profile name.
    """
    # Get the mapped datatype
    datatype = _map_type(ebus_type, max_length)
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
        "UINT24": "uint24",
        "UINT32": "uint32",
        "INT8": "int8",
        "INT16": "int16",
        "INT24": "int24",
        "INT32": "int32",
        "FLOAT4": "float4",
        "UINT16R": "uint16r",
        "UINT24R": "uint24r",
        "INT16R": "int16r",
        "INT24R": "int24r",
        "UINT32R": "uint32r",
        "INT32R": "int32r",
        "FLOAT4R": "float4r",
        "BCD": "bcd",
        "BOOL": "bool",
        "DATA2BR": "data2br",
        "DATA2CR": "data2cr",
        "CHAR1": "char1",
        "CHAR2": "char2",
        "CHAR3": "char3",
        "CHAR4": "char4",
        "CHAR5": "char5",
        "CHAR6": "char6",
        "CHAR7": "char7",
        "CHAR8": "char8",
        "CHAR9": "char9",
        "CHAR10": "char10",
        "CHAR11": "char11",
        "CHAR12": "char12",
        "CHAR13": "char13",
        "CHAR14": "char14",
        "CHAR15": "char15",
        "CHAR16": "char16",
        "HEX1": "hex1",
        "HEX2": "hex2",
        "HEX3": "hex3",
        "HEX4": "hex4",
        "HEX5": "hex5",
        "HEX6": "hex6",
        "HEX7": "hex7",
        "HEX8": "hex8",
        "HEX9": "hex9",
        "HEX10": "hex10",
        "HEX11": "hex11",
        "HEX12": "hex12",
        "HEX13": "hex13",
        "HEX14": "hex14",
        "HEX15": "hex15",
        "HEX16": "hex16",
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


def _max_length_from_meta(meta: Optional[Dict[str, Any]]) -> Optional[int]:
    """Parse @maxLength from field/scalar metadata (stored as a string)."""
    if not meta:
        return None
    v = meta.get("max_length")
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
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


def profiles_to_flat_entries(
    fam: FamilyIR, log: Any = None
) -> List[Dict[str, Any]]:
    """Convert FamilyIR commands to flat data_profiles.json schema entries.

    Each unique field profile becomes one flat entry:
    {name, datatype, unit, divider, digits, min, max}

    Entries are named canonically via _map_profile_name so that command
    field references (which use the same mapping) resolve to existing
    profiles. Deduplication is by (datatype, unit, divider) so that two
    fields with identical semantics share one profile entry.
    """
    log = log if log is not None else NULL_LOG
    entries: List[Dict[str, Any]] = []
    seen: set = set()
    used_names: set = set()

    for cmd in fam.commands:
        for f in cmd.fields:
            datatype = f.our_datatype or _map_type(
                f.ebus_type, _max_length_from_meta(f.meta)
            )
            unit = f.unit or ""

            # Skip datatypes the ebus-library cannot decode/encode.
            # (e.g. CHAR17+, HEX17+, ERRORHISTORY, POWER, etc.)
            if datatype not in SUPPORTED_DATATYPES:
                log.warn(
                    "profile",
                    "profile entry skipped: datatype not supported by ebus-library",
                    action="skipped_unsupported_datatype",
                    name=f.name,
                    input_type=f.ebus_type,
                    datatype=datatype,
                    classification=_classify_type(f.ebus_type, datatype),
                )
                continue

            # Deduplicate by profile identity (datatype, unit, divider)
            try:
                divider = float(f.factor) if f.factor else 1.0
            except ValueError:
                divider = 1.0
            dedup_key = (datatype, unit, divider)
            if dedup_key in seen:
                log.debug(
                    "profile",
                    "profile entry deduplicated",
                    action="deduplicated",
                    name=f.name,
                    datatype=datatype,
                    unit=unit,
                )
                continue
            seen.add(dedup_key)

            # Canonical profile name (same mapping commands use for references)
            profile_name = _map_profile_name(f.ebus_type, unit, _max_length_from_meta(f.meta))

            # Disambiguate name collisions
            original_name = profile_name
            suffix = 1
            while profile_name in used_names:
                profile_name = f"{original_name}_{suffix}"
                suffix += 1
            used_names.add(profile_name)

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

            entry = {
                "name": profile_name,
                "datatype": datatype,
                "unit": unit,
                "divider": divider if divider != 1.0 else 1,
                "digits": digits,
                "min": min_val,
                "max": max_val,
            }
            entries.append(entry)

            log.info(
                "profile",
                "data profile entry emitted",
                action="emitted",
                name=profile_name,
                datatype=datatype,
                unit=unit,
                divider=entry["divider"],
                digits=digits,
                classification=_classify_type(f.ebus_type, datatype),
            )

    return entries


def commands_to_flat_entries(
    fam: FamilyIR,
    key_prefix: str = "",
    aliases: Optional[Dict[str, str]] = None,
    log: Any = None,
) -> List[Dict[str, Any]]:
    """Convert FamilyIR commands to config/simulation.json schema entries.

    {key, name, zz, pbsb, [dx], [nn], wpbsb, [wdx], interval, master,
     fields: [{name, profile, position, ha_profile, [bits]}]}

    Split addressing: the read id is pbsb + dx (write id = wpbsb + wdx);
    pbsb is always present (empty for write-only commands) while the dx/wdx
    tails appear only when they carry bytes. NN stays runtime-derived
    (len(d) + value), with nn only for wire quirks.
    """
    log = log if log is not None else NULL_LOG
    entries: List[Dict[str, Any]] = []
    seen_read_id: Dict[str, str] = {}
    
    # Try to get MF from aliases if not in meta
    default_mf = 0x00
    if aliases and "MF" in aliases:
        try:
            default_mf = int(aliases["MF"], 16)
        except ValueError:
            default_mf = 0x00
    
    for idx, c in enumerate(fam.commands, start=1):
        meta = c.meta or {}
        namespace = meta.get("namespace", "")
        
        # Get addressing from meta.
        # Command layout: ZZ + id, where id = PB SB D... (2..6 bytes).
        # The D tail comes from the parser-resolved read_tail/write_tail
        # (@base D bytes + inherited ancestors, never a fabricated 0x0d)
        # followed by the model's own @ext bytes.
        zz = meta.get("zz", 0x08)  # Default ZZ
        mf = meta.get("mf", default_mf)  # Default MF (PB byte, e.g. 0xb5)
        pb = meta.get("pb", 0x09)  # Default SB

        read_tail = meta.get("read_tail")
        write_tail = meta.get("write_tail")
        ext_bytes = list(meta.get("ext") or [])

        def _hex(bs: List[int]) -> str:
            return "".join(f"{b:02x}" for b in bs)

        # NN bytes: ZZ PB SB NN D... [data...]
        #   read  NN typically 0x03 (no data)
        #   write NN = 3 + sum of datatype sizes of the writable field(s).
        nn_read = meta.get("read_nn", 0x03)

        data_byte_count = 0
        if c.fields:
            for f in c.fields:
                dt = f.our_datatype or f.ebus_type.upper()
                if dt in SUPPORTED_DATATYPES:
                    data_byte_count += DATATYPE_SIZE.get(dt, 0)
        nn_write = meta.get("write_nn", 3 + data_byte_count)

        # Split schema: zz + pbsb/dx (read) / wpbsb/wdx (write); NN is
        # derived at the runtime from the dx length (plus the value length
        # for writes). The halves are empty when the command has no
        # read/write side (write-only commands carry wpbsb/wdx only).
        # The SB byte (pb) is per-direction: read and write parents may
        # use different PBSB (e.g. *r B504 19 / *w B505 2e).
        zz_hex = f"{zz:02x}"
        mf_hex = f"{mf:02x}"
        read_prefix = f"{mf_hex}{meta.get('read_pb', pb):02x}"
        write_prefix = f"{mf_hex}{meta.get('write_pb', pb):02x}"
        id_hex = (
            read_prefix + _hex(read_tail) + _hex(ext_bytes)
            if read_tail is not None
            else ""
        )
        wid_hex = (
            write_prefix + _hex(write_tail) + _hex(ext_bytes)
            if write_tail is not None
            else ""
        )
        # Explicit read NN only when it differs from the derived len(id)-2
        # and the command actually has a read side.
        nn_hex = f"{nn_read:02x}" if (nn_read != 3 and id_hex) else ""
    
        if c.rw == "write" and "write_nn" not in meta:
            log.debug(
                "command",
                "write NN computed from datatype size",
                action="write_cmd_nn_from_datatype",
                name=c.name,
                key=f"{idx:03d}",
                namespace=namespace,
                nn_write=nn_write,
                data_byte_count=data_byte_count,
                fields=[(f.name, f.our_datatype or f.ebus_type) for f in c.fields],
            )

        log.debug(
            "command",
            "write id generated" if wid_hex else "no write command (read-only)",
            action="write_cmd_generated" if wid_hex else "read_only",
            name=c.name,
            zz=zz_hex,
            id=id_hex,
            wid=wid_hex,
            rw=c.rw,
        )
        
        # Determine key
        # Use sequential numbering with 3-digit zero-padding by default
        # This matches the working commands.json format ("01", "02", etc.)
        key = f"{idx:03d}"
        
        # Override with prefix if provided
        if key_prefix:
            key = f"{key_prefix}{key}"
        
        # Build fields with 1-based byte positions: position = 1 + cumulative
        # byte offset of preceding datatype sizes (firmware uses
        # field_pos = position - 1 to index into the data part).
        fields: List[Dict[str, Any]] = []
        byte_offset = 0
        for f in c.fields:
            # Get the profile name based on type and unit
            profile = _map_profile_name(f.ebus_type, f.unit or "", _max_length_from_meta(f.meta))
            
            # Get min/max overrides from field meta
            min_val = f.meta.get("min") if f.meta.get("min") is not None else None
            max_val = f.meta.get("max") if f.meta.get("max") is not None else None
            
            field_entry = {
                "name": f.name,
                "profile": profile,
                "position": byte_offset + 1,
                # Bits fields are read-only bit rows in HA: one
                # binary_sensor per bit (values payload expands the byte).
                "ha_profile": "binary_sensor" if f.meta.get("bits") else "",
            }
            
            # Add min/max if present
            if min_val is not None:
                field_entry["min"] = min_val
            if max_val is not None:
                field_entry["max"] = max_val
            if f.meta.get("bits"):
                field_entry["bits"] = f.meta["bits"]
            
            fields.append(field_entry)
            
            datatype = f.our_datatype or _map_type(
                f.ebus_type, _max_length_from_meta(f.meta)
            )
            if datatype in DATATYPE_SIZE:
                byte_offset += DATATYPE_SIZE[datatype]
            else:
                log.warn(
                    "command",
                    "datatype size unknown; positions after this field may be wrong",
                    action="unknown_datatype_size",
                    name=f.name,
                    input_type=f.ebus_type,
                    datatype=datatype,
                )
            log.debug(
                "profile",
                "command field profile selected",
                action="profile_selected",
                name=f.name,
                input_type=f.ebus_type,
                datatype=f.our_datatype or _map_type(f.ebus_type, _max_length_from_meta(f.meta)),
                unit=f.unit or "",
                profile=profile,
                classification=_classify_type(
                    f.ebus_type,
                    f.our_datatype or _map_type(f.ebus_type, _max_length_from_meta(f.meta)),
                ),
            )

        command_name = _format_command_name(c.name, namespace)
        # Split schema keys: read id = pbsb + dx, write id = wpbsb + wdx.
        # id_hex/wid_hex are always PB SB + tail (>= 4 hex chars) when set.
        entry: Dict[str, Any] = {
            "key": key,
            "name": command_name,
            "zz": zz_hex,
            "pbsb": id_hex[:4] if id_hex else "",
        }
        if len(id_hex) > 4:
            entry["dx"] = id_hex[4:]
        if nn_hex:
            entry["nn"] = nn_hex
        if wid_hex:
            entry["wpbsb"] = wid_hex[:4]
            if len(wid_hex) > 4:
                entry["wdx"] = wid_hex[4:]
        entry["interval"] = 0  # Default to passive only
        entry["master"] = False  # Default
        entry["fields"] = fields

        # Deduplicate namespace collisions: same model in multiple namespaces
        # produces identical zz+id + fields. Keep all variants but log them
        # so the user can curate by hardware/software version. Write-only
        # commands carry no id, so fall back to wid for the key.
        read_key = zz_hex + (id_hex or wid_hex)
        duplicate = seen_read_id.get(read_key)
        if duplicate is not None:
            log.debug(
                "command",
                "namespace collision: same zz+id in another variant",
                action="namespace_collision",
                key=key,
                name=command_name,
                namespace=namespace,
                zz=zz_hex,
                id=id_hex,
                wid=wid_hex,
                collides_with=duplicate,
            )
        else:
            seen_read_id[read_key] = key
        entries.append(entry)

        log.info(
            "command",
            "command entry emitted",
            action="emitted",
            key=key,
            name=command_name,
            namespace=namespace,
            zz=zz_hex,
            id=id_hex,
            wid=wid_hex,
            rw=c.rw,
            fields=len(fields),
        )
    
    return entries


def build_profiles_and_commands(
    raw: Dict[str, Any], manufacturer: int = 0x00, log: Any = None
) -> FamilyIR:
    """Build FamilyIR from raw tsp parser IR.

    Converts parser-extracted registers (commands) and fields into
    FamilyIR with ProfileIR grouping and CommandIR entries.
    """
    log = log if log is not None else NULL_LOG
    fam = FamilyIR()

    registers: List[Dict[str, Any]] = raw.get("registers", [])
    enums: Dict[str, Any] = raw.get("enums", {})
    scalars: Dict[str, Any] = raw.get("scalars", {})
    aliases: Dict[str, Any] = raw.get("aliases", {})
    models: Dict[str, Any] = raw.get("models", {})

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
            if scalar.get("unit"):
                meta["unit"] = scalar["unit"]
            if scalar.get("factor"):
                meta["factor"] = scalar["factor"]
            if scalar.get("digits"):
                meta["digits"] = scalar["digits"]
            if scalar.get("min") is not None:
                meta["min"] = scalar["min"]
            if scalar.get("max") is not None:
                meta["max"] = scalar["max"]
            if scalar.get("values_enum"):
                meta["values_enum"] = scalar["values_enum"]
            if scalar.get("max_length"):
                meta["max_length"] = scalar["max_length"]
            
            t = _strip_qualified(scalar.get("base_type", ""))
        
        # Check if it's an enum
        if t in enums:
            meta["values_enum"] = t
            meta["values"] = enums[t].get("entries", [])
        
        datatype = _map_type(t)
        classification = _classify_type(t_orig, datatype, enums)
        if classification == "defaulted":
            log.warn(
                "resolve",
                "type has no ebusd→library mapping; using raw name",
                action="defaulted",
                input_type=t_orig,
                resolved_type=t,
                datatype=datatype,
            )
        elif classification == "unsupported":
            log.warn(
                "resolve",
                "type has no native ebus-library DataType equivalent",
                action="unsupported",
                input_type=t_orig,
                resolved_type=t,
                datatype=datatype,
            )
        else:
            log.debug(
                "resolve",
                "type resolved",
                action="resolved",
                input_type=t_orig,
                resolved_type=t,
                datatype=datatype,
                classification=classification,
                unit=meta.get("unit", ""),
            )
        return t, meta

    def expand_composite_field(
        parent_name: str, type_name: str, path: List[str], depth: int
    ) -> List[FieldIR]:
        """Expand a composite (plain-model) field into leaf FieldIRs.

        Leaf names are the full field-name path joined with '_' prefixed by
        the parent field name, with repeated underscores collapsed:
        value: timer -> value_slot1_slot_from, value_daysel. Leaves resolve
        through the normal type machinery, so profiles, write NN, and byte
        positions follow automatically.
        """
        if depth > 8:
            log.warn(
                "template",
                "composite expansion depth exceeded",
                action="expansion_depth_exceeded",
                name=parent_name,
                input_type=type_name,
            )
            return []
        leaves: List[FieldIR] = []
        model = models.get(type_name) or {}
        for child in model.get("fields", []):
            child_name = str(child.get("name", ""))
            child_type = _strip_qualified(str(child.get("type", "")))
            if child_type in models and child_type not in TYPE_MAP:
                leaves.extend(
                    expand_composite_field(
                        parent_name, child_type, path + [child_name], depth + 1
                    )
                )
                continue
            resolved_type, type_meta = resolve_type_and_meta(child_type)
            merged_meta = dict(type_meta)
            leaf_name = "_".join([parent_name] + path + [child_name])
            while "__" in leaf_name:
                leaf_name = leaf_name.replace("__", "_")
            factor_str = merged_meta.get("factor", merged_meta.get("divisor", ""))
            factor_val = _parse_factor(factor_str) if factor_str else None
            leaves.append(
                FieldIR(
                    name=leaf_name,
                    ebus_type=resolved_type or child_type,
                    unit=merged_meta.get("unit", ""),
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=resolved_type.startswith(("S", "s")),
                    big_endian="R" in resolved_type
                    or ("B" in resolved_type and "L" not in resolved_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=_map_type(
                        resolved_type or child_type,
                        _max_length_from_meta(merged_meta),
                    ),
                    meta=merged_meta,
                )
            )
        return leaves

    def _service_field_ir() -> FieldIR:
        """UINT8 service companion of two-field template instances."""
        return FieldIR(
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
            # Composite template argument (e.g. Timer<timer>): expand into
            # positioned leaf sub-fields. Mapped arguments (e.g. phase) are
            # excluded by the TYPE_MAP gate; the service companion of
            # two-field templates is preserved.
            tt = _strip_qualified(template_type)
            composite_leaves: List[FieldIR] = []
            if tt in models and tt not in TYPE_MAP:
                composite_leaves = expand_composite_field("value", tt, [], 0)
            if composite_leaves:
                log.debug(
                    "template",
                    "composite field expanded",
                    action="composite_expanded",
                    name="value",
                    input_type=tt,
                    leaves=[fi.name for fi in composite_leaves],
                )
                field_irs.extend(composite_leaves)
                if template_name in _TWO_FIELD_TEMPLATES:
                    field_irs.append(_service_field_ir())
            # Handle template models
            elif template_name in _SINGLE_FIELD_TEMPLATES:
                # Single field template: the type is template_type
                resolved_type, type_meta = resolve_type_and_meta(template_type)
                
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(f_ebus_type, _max_length_from_meta(type_meta))
                
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
                f_our_datatype = _map_type(f_ebus_type, _max_length_from_meta(type_meta))
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
                field_irs.append(_service_field_ir())
            else:
                # Unknown template: assume single value field
                resolved_type, type_meta = resolve_type_and_meta(template_type)
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(f_ebus_type, _max_length_from_meta(type_meta))
                
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
                
                # Composite field: plain model without a library mapping of
                # its own (mapped types like phase are never expanded) →
                # emit positioned leaf sub-fields instead of the raw type.
                leaf_type = _strip_qualified(f_ebus_type)
                if leaf_type in models and leaf_type not in TYPE_MAP:
                    leaves = expand_composite_field(f_name, leaf_type, [], 0)
                    if leaves:
                        log.debug(
                            "template",
                            "composite field expanded",
                            action="composite_expanded",
                            name=f_name,
                            input_type=leaf_type,
                            leaves=[fi.name for fi in leaves],
                        )
                        field_irs.extend(leaves)
                        continue
                
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
                    our_datatype=_map_type(resolved_type or f_ebus_type, _max_length_from_meta(merged_meta)),
                    meta=merged_meta,
                )
                field_irs.append(field_ir)

        # Determine the command's direction from the parser-resolved id
        # tails: a write side exists when write_tail was seeded/inherited,
        # a read side when read_tail was. Decorator/template rules only
        # remain as a fallback for registers with no resolved sides.
        read_tail = meta.get("read_tail")
        write_tail = meta.get("write_tail")
        if write_tail is not None:
            rw = "write"
        elif read_tail is not None:
            rw = "read"
        else:
            rw = reg.get("rw", "read")

        unsupported = False
        unsupported_reason = ""

        if reg.get("unsupported"):
            unsupported = True
            unsupported_reason = reg.get(
                "unsupported_reason", "unsupported register"
            )

        if rw not in ("read", "write"):
            unsupported = True
            unsupported_reason = f"unknown rw direction: {rw}"

        # BI bitfield children (BI0..BI7) share one wire byte: collapse each
        # consecutive run into a single UINT8 field with a `bits` name->bit
        # map first; anything still gated (boolean/BOOL, raw bitfield names)
        # drops the whole command.
        field_irs = _merge_bit_runs(field_irs)
        for f in field_irs:
            if f.ebus_type in _BIT_GATED_EBUS_TYPES:
                unsupported = True
                unsupported_reason = (
                    f"BI bitfield field {f.name!r} (type {f.ebus_type!r})"
                )
                break

        writable = rw == "write"
        log.debug(
            "command",
            "writability determined",
            action="writable" if writable else "read_only",
            name=reg_name,
            namespace=reg.get("namespace", ""),
            rw=rw,
            template=template_name,
            explicit_write=bool(meta.get("explicit_write")),
            explicit_passive=bool(meta.get("explicit_passive")),
        )

        cmd_ir = CommandIR(
            name=reg_name,
            profile_key=None,
            register=reg_str,
            rw=rw,
            fields=field_irs,
            unsupported=unsupported,
            unsupported_reason=unsupported_reason,
            meta=meta,
        )
        # Determine kind of register
        if template_name is None and template_type is not None:
            kind = "template_definition"
        elif reg_name in inherited_model_names:
            kind = "inherited_base"
        else:
            kind = "register"

        # Only concrete registers become commands; skip template definitions,
        # inherited base models, and registers the merge/BI gate marked
        # unsupported (no id/wid side or bitfield payload).
        if kind == "register" and not unsupported:
            fam.commands.append(cmd_ir)

        # Log what happened to this register.
        if kind == "register" and unsupported:
            log.warn(
                "command",
                "register skipped: unsupported",
                action="skipped_unsupported",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
                cause=unsupported_reason,
            )
        elif kind == "template_definition":
            log.warn(
                "command",
                "template definition skipped (only instantiations become commands)",
                action="skipped_template_definition",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
            )
        elif kind == "inherited_base":
            log.warn(
                "command",
                "register skipped because it is referenced via @inherit",
                action="skipped",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
                cause="inherited_base_model",
            )
        else:
            log.debug(
                "command",
                "register converted to command",
                action="converted",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
                fields=len(field_irs),
            )

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
                key = key[:24].rstrip("_")

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
