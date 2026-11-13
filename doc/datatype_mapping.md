<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# eBUS DataType and App Data Profile Mapping

This document describes how eBUS wire types map to the library's native
`ebus::DataType` values and how the firmware's data profiles add display and
validation metadata. The profile JSON files are the source of truth for the
profile inventory; see [`profiles/README.md`](../profiles/README.md) for profile
authoring and user overlays.

## ebus library native DataTypes

Defined in `include/ebus/data_types.hpp`.
Multi-byte numeric types use little-endian byte order by default; types ending
in `R` reverse that byte order. `DATA2B` and `DATA2C` are signed fixed-point
types with factors of 1/256 and 1/16, respectively. Date/time/PIN types bake
their byte layout into the format (the `Endian` argument is ignored) and
decode to formatted strings, not numbers.

| ebus library DataType | Size | Endianness | Notes |
|---|---|---|---|
| BCD8 | 1 byte | N/A | Packed decimal (2 digits); `0xff` → null |
| UINT8 / INT8 | 1 byte | N/A | Unsigned / signed integer |
| DATA1B / DATA1C | 1 byte | N/A | eBUS 1-byte data encodings |
| CHAR1 / HEX1 | 1 byte | N/A | Character / hexadecimal data |
| TIME_TRUNC10 | 1 byte | N/A | Truncated time, 10-minute steps; renders `HH:mm` |
| TIME_TRUNC15 | 1 byte | N/A | Truncated time, 15-minute steps; renders `HH:mm` |
| TIME_TRUNC30 | 1 byte | N/A | Truncated time, 30-minute steps; renders `HH:mm` |
| UINT16 / INT16 | 2 bytes | Little-endian | |
| UINT16R / INT16R | 2 bytes | Big-endian | Reversed byte order |
| DATA2B / DATA2C | 2 bytes | Little-endian | Signed fixed-point: factors 1/256 / 1/16 |
| DATA2BR / DATA2CR | 2 bytes | Big-endian | Reversed-byte-order DATA2B / DATA2C |
| CHAR2 / HEX2 | 2 bytes | N/A | Character / hexadecimal data |
| BCD16 | 2 bytes | Little-endian pairs | Packed decimal (4 digits); `0xff` byte → null |
| PIN2 | 2 bytes | N/A | BCD PIN; renders `0000` (4-digit string) |
| TIME_BIN2R | 2 bytes | N/A | `HH:mm`, wire `MM HH` |
| TIME_MIN2 | 2 bytes | Little-endian | Minutes since midnight; renders `HH:mm` |
| TIME_BIN2 | 2 bytes | N/A | `HH:mm`, wire `HH MM` |
| TIME_BCD2R | 2 bytes | N/A | BCD time, wire `MM HH`; renders `HH:mm` |
| DATE_DAY2 | 2 bytes | Little-endian | Days since 01.01.1900; renders `dd.MM.yyyy` |
| UINT24 / INT24 | 3 bytes | Little-endian | |
| UINT24R / INT24R | 3 bytes | Big-endian | Reversed byte order |
| CHAR3 / HEX3 | 3 bytes | N/A | Character / hexadecimal data |
| BCD24 | 3 bytes | Little-endian pairs | Packed decimal (6 digits); `0xff` byte → null |
| DATE_BIN3 | 3 bytes | N/A | Plain date `DD MM YY`; renders `dd.MM.yyyy` |
| TIME_BCD3R | 3 bytes | N/A | BCD time, wire `SS MM HH`; renders `HH:mm:ss` |
| TIME_BIN3R | 3 bytes | N/A | Plain time, wire `SS MM HH`; renders `HH:mm:ss` |
| TIME_BIN3 | 3 bytes | N/A | Plain time, wire `HH MM SS`; renders `HH:mm:ss` |
| DATE_BCD3 | 3 bytes | N/A | BCD date, wire `DD MM YY`; renders `dd.MM.yyyy` |
| UINT32 / INT32 | 4 bytes | Little-endian | |
| UINT32R / INT32R | 4 bytes | Big-endian | Reversed byte order |
| FLOAT32 / FLOAT32R | 4 bytes | Little-endian / big-endian | IEEE 754 |
| DATE_BCD4 | 4 bytes | N/A | BCD date + weekday byte (`DD MM WW YY`); renders `dd.MM.yyyy`, weekday computed on write |
| DATE_BCD4Z | 4 bytes | N/A | BCD date + zero-based weekday (`DD MM WZ YY`); renders `dd.MM.yyyy` |
| DATE_BIN4 | 4 bytes | N/A | Plain date + weekday (`DD MM WW YY`); renders `dd.MM.yyyy` |
| DATETIME_MIN4 | 4 bytes | Little-endian | Minutes since 01.01.2009; renders `dd.MM.yyyy HH:mm` |
| BCD32 | 4 bytes | Little-endian pairs | Packed decimal (8 digits); `0xff` byte → null |
| CHAR4-8 / HEX4-8 | 4-8 bytes | N/A | Character / hexadecimal data |


### ebusd TypeSpec → ebus library mapping

Representative mappings from ebusd's base `_templates.tsp` and Vaillant
`vaillant/_templates.tsp` definitions:

#### Supported natively by ebus library

| ebusd TypeSpec | ebus library DataType | Source file | Notes |
|---|---|---|---|
| UCH | UINT8 | _templates.tsp | Unsigned char |
| SCH | INT8 | _templates.tsp | Signed char |
| D1B | DATA1B | _templates.tsp | 1-byte data |
| D1C | DATA1C | _templates.tsp | 1-byte complement |
| D2B | DATA2B | _templates.tsp | 2-byte signed fixed-point (factor 1/256) |
| D2C | DATA2C | _templates.tsp | 2-byte fixed-point (scale 1:16) |
| INT16 | INT16 | _templates.tsp | 16-bit signed |
| UINT16 | UINT16 | _templates.tsp | 16-bit unsigned |
| INT32 | INT32 | _templates.tsp | 32-bit signed |
| UINT32 | UINT32 | _templates.tsp | 32-bit unsigned |
| FLT / FLOAT | FLOAT32 | _templates.tsp | 32-bit IEEE 754 float |
| STR | CHAR1-16 | _templates.tsp | String data, fixed-size CHAR via `@maxLength`; widths >16 (e.g. 21-byte serial numbers) stay unsupported — the protocol caps data at 16 bytes (spec 5.6) |
| IGN | (skip) | _templates.tsp | Ignore field |
| UIN | UINT16 | vaillant/_templates.tsp | Little-endian unsigned int |
| SIN | INT16 | vaillant/_templates.tsp | Little-endian signed int |
| UIR | UINT16R | vaillant/_templates.tsp | Big-endian unsigned int (reversed of UIN) |
| U3N / U3R | UINT24 / UINT24R | ebus-typespec/lib/types.tsp | 24-bit unsigned, LE / BE |
| S3N / S3R | INT24 / INT24R | ebus-typespec/lib/types.tsp | 24-bit signed, LE / BE |
| ULG | UINT32 | vaillant/_templates.tsp | Little-endian unsigned long |
| EXP / EXR | FLOAT32 / FLOAT32R | vaillant/_templates.tsp | IEEE 754 binary32 (EXR reversed byte order) |
| BCD | BCD8 | _templates.tsp | Single-byte BCD |
| BCD2 | BCD16 | — (no vendored tsp usage) | 2-byte BCD (4 digits), LE digit pairs |
| BCD3 | BCD24 | _templates.tsp (`cntstarts`, `cnthours`) | 3-byte BCD (6 digits), LE digit pairs |
| BCD4 | BCD32 | _templates.tsp (`cntfuel`) | 4-byte BCD (8 digits), LE digit pairs |
| HCD | UINT8 | ebus-typespec/lib/types.tsp | 1-byte hex-coded decimal 0-99 (0x00-0x63); the byte value is the value |
| BTI | TIME_BCD3R | _templates.tsp (`btime`) | 3-byte BCD time, wire `SS MM HH`; `HH:mm:ss` |
| BDA | DATE_BCD4 | _templates.tsp (`bdate`) | 4-byte BCD date with weekday, wire `DD MM WW YY`; `dd.MM.yyyy` |
| HDA3 | DATE_BIN3 | vaillant/_templates.tsp (`date`, `hfrom`/`hto`) | Plain 3-byte date `DD MM YY`; `dd.MM.yyyy` |
| VTI | TIME_BIN3R | vaillant/_templates.tsp (`time`) | Plain time, wire `SS MM HH`; `HH:mm:ss` |
| VTM | TIME_BIN2R | vaillant/_templates.tsp (`time2`) | Plain `hh:mm`, wire `MM HH` |
| TTM | TIME_TRUNC10 | vaillant/_templates.tsp (`from`/`to`) | 10-minute steps; `HH:mm` |
| MIN | TIME_MIN2 | tem/_templates.tsp (`min_time`/`max_time`) | Minutes since midnight (LE); `HH:mm` |
| HTI | TIME_BIN3 | 15.700 / bai.emm_inc (`value: HTI`) | Plain 3-byte time, wire `HH MM SS`; `HH:mm:ss` |
| BTM | TIME_BCD2R | 15.ctlv2 (`errorHistoryEntry.time`) | BCD time, wire `MM HH`; `HH:mm` |
| HTM | TIME_BIN2 | vaillant/_templates.tsp (`slotTimeFrame.htm`) | Plain time, wire `HH MM`; `HH:mm` |
| HDA | DATE_BIN4 | bai.*_inc (`DCFTimeDate.hda`) | Plain date + weekday, wire `DD MM WW YY`; `dd.MM.yyyy` |
| BDA3 | DATE_BCD3 | 15.ctlv2 (`errorHistoryEntry.date`) | BCD 3-byte date, wire `DD MM YY`; `dd.MM.yyyy` |
| BDZ | DATE_BCD4Z | — (no vendored tsp usage) | BCD date + zero-based weekday; `dd.MM.yyyy` |
| DAY | DATE_DAY2 | tem/15 (`Date.date`) | Days since 01.01.1900 (LE); `dd.MM.yyyy` |
| DTM | DATETIME_MIN4 | 15.e7c (`VacationStartTime`, `TimeDate`, …) | Minutes since 01.01.2009 (LE); `dd.MM.yyyy HH:mm` |
| TTH | TIME_TRUNC30 | vaillant/quick_inc (`Save.value`) | 30-minute steps; `HH:mm` |
| TTQ | TIME_TRUNC15 | — (no vendored tsp usage) | 15-minute steps; `HH:mm` |
| PIN | PIN2 | vaillant/_templates.tsp (`code`), _templates.tsp (`version`) | BCD PIN; `0000` (4-digit string) |
| BDY / HDY | UINT8 | vaillant/_templates.tsp (`day`) | Weekday number (BDY Mon=0, HDY Mon=1); Mon–Sun text via `select_enum_weekday_mon0` / `select_enum_weekday_mon1` HA profiles |

> Endianness verified against the vendored ebusd 26.1 sources:
> `UIR`, `SIR`, `ULR`, `EXR` carry the `REV` flag — "reverted binary
> representation (most significant byte first)" — while `UIN`, `SIN`,
> `ULG`, `EXP` do not. `ebus-typespec/lib/types.tsp` agrees
> (`@Internal.reverse` on the `UIR`/`ULR`/`EXR` scalars).

#### No direct native DataType equivalent

| ebusd TypeSpec | Description | Action |
|---|---|---|
| HCD2 / HCD3 / HCD4 | Hex-coded decimal, each byte 0x00-0x63 | No native HCD decode — mapped to HEX2/HEX3/HEX4 (raw hex passthrough; a binary/char read would be wrong) |
| U3L / U3B / S3L / S3B | 24-bit integers without a null sentinel | No native "no replacement" DataType — mapped to raw HEX3 |
| U1L / U2L / U4L / S1L / S2L / S4L | eBUS `REQ` numbers (ebusd: no replacement value — extreme value is a normal reading) | Mapped to the sentinel-bearing UINT8/16/32 and INT8/16/32: the extreme value (`0xFF`, `0xFFFF`, `0xFFFF'FFFF`, `0x80`, …) renders `null` instead of the raw number. Accepted edge case — no no-sentinel variants are planned |
| HCL / VA | Not defined in vendored ebusd 26.1 (`datatype.cpp`) or any vendored TypeSpec | Stale entries — confirm origin before mapping |
| CHAR17+ / HEX17+ (e.g. CHAR21, HEX18) | `@maxLength` >16 on STR/HEX — needs more than 16 data bytes; NN caps the payload at 16 (spec 5.6). Corpus never emits them | Kept skipped — impossible on the wire; mapper flags the width `unsupported`, no code |
| BI0-BI7 / boolean | Bit extraction | BI runs collapse into one UINT8 field with a per-bit `bits` map; plain boolean/BOOL commands are gated — no `ebus::DataType` BOOL exists |

---

## App Data Profiles (`profiles/data_profiles.json`)

The base file currently defines **83 data profiles**. At build time,
`scripts/generate_data_profiles.py` merges the optional
`profiles/data_profiles_user.json` overlay and generates
`include/app/data_profile_gen.hpp`. A user overlay can add profiles or replace
base entries with the same name, so the final compiled count can differ from
83.

### Naming Convention

Most profile names follow `{datatype}_{unit}` with optional suffixes:
- `_div{N}` — divider ≠ 1 (e.g., `uint8_kw_div10` = divider 10)
- `_d{N}` — non-standard digit precision (e.g., `uint8_d2` = 2 decimals)
Type-only profiles (such as `uint8`, `char1`, and `hex1`) are also used.

### Base profile inventory

Values below are from `profiles/data_profiles.json`. The `ebusd scalar` and
`@step` columns show known upstream associations; a dash means none is listed
here, not that the profile is unsupported by ebusd.

| Profile | Datatype | Unit | Divider | Digits | Min | Max | ebusd scalar | @step |
|---|---|---|---|---|---|---|---|---|
| `data2c_celsius` | DATA2C | °C | 1 | 1 | -50 | 180 | `temp` / `temps` | 0.5 |
| `data2b_celsius` | DATA2B | °C | 1 | 1 | -50 | 180 | `temp2` | 0.5 |
| `data1c_celsius` | DATA1C | °C | 1 | 1 | 0 | 75 | `temp1` | — |
| `int8_celsius` | INT8 | °C | 1 | 0 | -50 | 180 | — | — |
| `uint8_celsius` | UINT8 | °C | 1 | 0 | -50 | 180 | `temp0` | — |
| `data2b_bar` | DATA2B | bar | 1000 | 1 | 0 | 70 | base `press` (D2B) | 0.5 |
> Scope: base `press` only (`scalar press extends D2B`, ÷256 native).
> Vaillant `press` is `FLT`/int16 (÷1000) — using this profile there
> renders `raw/256000` (verified live: 0 for 2.4 bar); use `int16_bar`.
| `float32_bar` | FLOAT32 | bar | 1 | 1 | 0 | 70 | `press` (FLT) | 0.5 |
| `int16_bar` | INT16 | bar | 1000 | 1 | 0 | 70 | `pressm` | — |
| `int16_percent` | INT16 | % | 1 | 1 | -100 | 100 | `percents` | — |
| `uint8_percent` | UINT8 | % | 1 | 0 | 0 | 100 | `percent0` | — |
| `int8_percent_div10` | INT8 | % | 10 | 1 | -100 | 100 | `percent2` | 0.5 |
| `uint32_hour` | UINT32 | h | 1 | 0 | 0 | 0 | `hoursum` | — |
| `uint16_hour` | UINT16 | h | 1 | 0 | 0 | 0 | `hoursum2` | — |
| `uint16_min_div120` | UINT16 | min | 120 | 0 | 0 | 0 | `minutes` | — |
| `data2c_lpm` | DATA2C | L/min | 1 | 0 | 0 | 0 | — | — |
| `uint16_lph` | UINT16 | l/h | 1 | 0 | 0 | 20 | `flowrate` | — |
| `uint16_lph_div100` | UINT16 | l/h | 100 | 1 | 0 | 20 | `flowrate100` | — |
| `uint16_m3h` | UINT16 | m3/h | 1 | 0 | 0 | 400 | `airflowrate` | — |
| `uint16_rpm` | UINT16 | rpm | 1 | 0 | 0 | 1000 | `fanspeed` | — |
| `uint8` | UINT8 | — | 1 | 0 | 0 | 0 | `UCH` | — |
| `uint16` | UINT16 | — | 1 | 0 | 0 | 0 | `UINT16` | — |
| `uint32` | UINT32 | — | 1 | 0 | 0 | 0 | `UINT32` | — |
| `uint32_kwh` | UINT32 | kWh | 1 | 2 | 0 | 0 | `energy` | — |
| `uint8_kw` | UINT8 | kW | 1 | 1 | 0 | 0 | `power` | — |
| `uint8_kw_div10` | UINT8 | kW | 10 | 1 | 0 | 0 | — | — |
| `uint16_kw_div10` | UINT16 | kW | 10 | 1 | 0 | 0 | — | — |
| `uint8_d2` | UINT8 | — | 1 | 2 | 0 | 0 | — | — |
| `char1` | CHAR1 | — | 1 | 0 | 0 | 0 | `CHAR1` | — |
| `char2` | CHAR2 | — | 1 | 0 | 0 | 0 | — | — |
| `char3` | CHAR3 | — | 1 | 0 | 0 | 0 | — | — |
| `char4` | CHAR4 | — | 1 | 0 | 0 | 0 | — | — |
| `char5` | CHAR5 | — | 1 | 0 | 0 | 0 | — | — |
| `char6` | CHAR6 | — | 1 | 0 | 0 | 0 | — | — |
| `char7` | CHAR7 | — | 1 | 0 | 0 | 0 | — | — |
| `char8` | CHAR8 | — | 1 | 0 | 0 | 0 | — | — |
| `char9` | CHAR9 | — | 1 | 0 | 0 | 0 | — | — |
| `char10` | CHAR10 | — | 1 | 0 | 0 | 0 | — | — |
| `char11` | CHAR11 | — | 1 | 0 | 0 | 0 | — | — |
| `char12` | CHAR12 | — | 1 | 0 | 0 | 0 | — | — |
| `char13` | CHAR13 | — | 1 | 0 | 0 | 0 | — | — |
| `char14` | CHAR14 | — | 1 | 0 | 0 | 0 | — | — |
| `char15` | CHAR15 | — | 1 | 0 | 0 | 0 | — | — |
| `char16` | CHAR16 | — | 1 | 0 | 0 | 0 | — | — |
| `hex1` | HEX1 | — | 1 | 0 | 0 | 0 | — | — |
| `hex2` | HEX2 | — | 1 | 0 | 0 | 0 | — | — |
| `hex3` | HEX3 | — | 1 | 0 | 0 | 0 | — | — |
| `hex4` | HEX4 | — | 1 | 0 | 0 | 0 | — | — |
| `hex5` | HEX5 | — | 1 | 0 | 0 | 0 | — | — |
| `hex6` | HEX6 | — | 1 | 0 | 0 | 0 | — | — |
| `hex7` | HEX7 | — | 1 | 0 | 0 | 0 | — | — |
| `hex8` | HEX8 | — | 1 | 0 | 0 | 0 | — | — |
| `hex9` | HEX9 | — | 1 | 0 | 0 | 0 | — | — |
| `hex10` | HEX10 | — | 1 | 0 | 0 | 0 | — | — |
| `hex11` | HEX11 | — | 1 | 0 | 0 | 0 | — | — |
| `hex12` | HEX12 | — | 1 | 0 | 0 | 0 | — | — |
| `hex13` | HEX13 | — | 1 | 0 | 0 | 0 | — | — |
| `hex14` | HEX14 | — | 1 | 0 | 0 | 0 | — | — |
| `hex15` | HEX15 | — | 1 | 0 | 0 | 0 | — | — |
| `hex16` | HEX16 | — | 1 | 0 | 0 | 0 | — | — |
| `int16_celsius_div10` | INT16 | °C | 10 | 1 | -50 | 180 | — | — |
| `uint16_celsius` | UINT16 | °C | 1 | 0 | 0 | 180 | — | — |
| `date_bcd3` | DATE_BCD3 | — | 1 | 0 | 0 | 0 | `errorHistoryEntry.date` (BDA3) | — |
| `date_bcd4` | DATE_BCD4 | — | 1 | 0 | 0 | 0 | `bdate` (BDA) | — |
| `date_bcd4z` | DATE_BCD4Z | — | 1 | 0 | 0 | 0 | — | — |
| `date_bin3` | DATE_BIN3 | — | 1 | 0 | 0 | 0 | `date` (HDA3) | — |
| `date_bin4` | DATE_BIN4 | — | 1 | 0 | 0 | 0 | `DCFTimeDate.hda` (HDA) | — |
| `date_day2` | DATE_DAY2 | — | 1 | 0 | 0 | 0 | `Date.date` (DAY) | — |
| `datetime_min4` | DATETIME_MIN4 | — | 1 | 0 | 0 | 0 | `VacationStartTime` (DTM) | — |
| `time_bcd2r` | TIME_BCD2R | — | 1 | 0 | 0 | 0 | `errorHistoryEntry.time` (BTM) | — |
| `time_bcd3r` | TIME_BCD3R | — | 1 | 0 | 0 | 0 | `btime` (BTI) | — |
| `time_bin2` | TIME_BIN2 | — | 1 | 0 | 0 | 0 | `slotTimeFrame.htm` (HTM) | — |
| `time_bin2r` | TIME_BIN2R | — | 1 | 0 | 0 | 0 | `time2` (VTM) | — |
| `time_bin3` | TIME_BIN3 | — | 1 | 0 | 0 | 0 | `value` (HTI) | — |
| `time_bin3r` | TIME_BIN3R | — | 1 | 0 | 0 | 0 | `time` (VTI) | — |
| `time_min2` | TIME_MIN2 | — | 1 | 0 | 0 | 0 | `min_time`/`max_time` (MIN) | — |
| `time_trunc10` | TIME_TRUNC10 | — | 1 | 0 | 0 | 0 | `from`/`to` (TTM) | — |
| `time_trunc15` | TIME_TRUNC15 | — | 1 | 0 | 0 | 0 | — | — |
| `time_trunc30` | TIME_TRUNC30 | — | 1 | 0 | 0 | 0 | `Save.value` (TTH) | — |
| `pin2` | PIN2 | — | 1 | 0 | 0 | 0 | `code` (PIN) | — |
| `bcd16` | BCD16 | — | 1 | 0 | 0 | 0 | — | — |
| `bcd24` | BCD24 | — | 1 | 0 | 0 | 0 | `cntstarts` / `cnthours` | — |
| `bcd32` | BCD32 | — | 1 | 0 | 0 | 0 | `cntfuel` | — |
| `bcd8` | BCD8 | — | 1 | 0 | 0 | 0 | `cntminutes` | — |

### Scaling and formatting

The profile's `divider` scales a decoded numeric value as `decoded / divider`;
`digits` controls formatted decimal precision. Upstream `@step` metadata can
inform a profile's precision, but there is no universal one-to-one rule: the
profile explicitly sets `digits` and `divider`.

### Per-Field Min/Max Override

Commands can override profile defaults per-field in `commands.json`:

```json
{
  "key": "32",
  "name": "Basement/Temperature_NightRoomSetPoint",
  "fields": [{
    "name": "value",
    "profile": "data1c_celsius",
    "position": 1,
    "min": 15,
    "max": 20
  }]
}
```

- Profile `data1c_celsius` default: min=0, max=75
- This command overrides: min=15, max=20
- Overrides are persisted to LittleFS and included in `/api/v1/app/commands` output

`min`/`max` of `0` mean **no bound** during write validation (see
[`doc/api.md`](api.md)): profiles whose upstream TypeSpec metadata was
not popped by the generator carry `max = 0` (most plain `uint8`/`uint16`
and all `char*`/`hex*` inventory rows) — those fields accept any value
the datatype can hold.

### Raw values (sentinel bypass)

Numeric datatypes map their replacement value (sentinel) to `null`:
`0xFF` for 1-byte, `0xFFFF`/`0x8000` for 2-byte, and so on. Date/time/PIN
string types carry the same rule — replacement bytes render `null` for the
whole field (a documented divergence from ebusd's partial-null strings such
as `null.05.2017`). A field can
opt out per field with `"raw": true` and always render the raw numeric
value instead:

```json
{
  "key": "48",
  "name": "Pressure",
  "fields": [{
    "name": "value",
    "profile": "int16_bar",
    "position": 1,
    "raw": true
  }]
}
```

- Default (`raw` absent or false): sentinel bytes render `null`
  (unknown in Home Assistant) — the honest reading for "no data".
- `"raw": true`: sentinel bytes render as numbers (e.g. `UINT16`
  `0xFFFF` → 65535). Opt-in only; graphs will show the extreme.
- Types without sentinels (`HEX3`–`HEX16`, `CHAR3`–`CHAR16`, `FLOAT32`,
  `FLOAT32R`) always render raw — the flag changes nothing for them.

---

Command JSON schema (keys, `read_cmd`/`write_cmd` anatomy, NN rules,
limits) is documented in [`doc/command-schema.md`](command-schema.md);
runtime interfaces (HTTP/MQTT/cron writes, MQTT payload modes, Home
Assistant discovery) in [`doc/api.md`](api.md); upload recipes in
[`doc/commands.md`](commands.md). This document focuses on wire
datatypes and the display/validation metadata attached to command
fields.
