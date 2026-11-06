<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Configuration Files (`config/`)

This directory contains command configuration files for the eBUS adapter and virtual bus simulation.

## Command JSON Structure

Commands are defined as a JSON array of objects. Each command object specifies an eBUS command and its data fields.

### Example

```json
[
  {
    "key": "09",
    "name": "Buffer/Middle_Temperature",
    "zz": "08",
    "id": "b509290100",
    "interval": 0,
    "master": false,
    "fields": [
      {
        "name": "value",
        "profile": "data2c_celsius",
        "position": 3,
        "ha_profile": "sensor_temperature"
      },
      {
        "name": "status",
        "profile": "uint8",
        "position": 5,
        "ha_profile": "sensor_enum_sensor_state"
      }
    ]
  },
  {
    "key": "32",
    "name": "Basement/Temperature_NightRoomSetPoint",
    "zz": "50",
    "id": "b5090d3300",
    "wid": "b5090e3300",
    "interval": 60,
    "master": false,
    "fields": [
      {
        "name": "value",
        "profile": "data1c_celsius",
        "position": 1,
        "ha_profile": "number_temperature",
        "min": 15,
        "max": 20
      }
    ]
  }
]
```

### Schema Description

#### Command Properties
- **`key`** *(string)*: Unique decimal or hexadecimal identifier for the command (e.g. `"09"` or `"43"`). Used as prefix for HA `unique_id` and MQTT control topic (`ebus/<id>/set/<key>`).
- **`name`** *(string)*: Command name hierarchy using slashes and underscores (e.g. `"Buffer/Middle_Temperature"`). Generates MQTT value subtopic `ebus/<id>/values/buffer/middle_temperature`.
- **`zz`** *(hex string)*: 1-byte destination address of the telegram (e.g. `"08"`).
- **`id`** *(hex string)*: Read id `PB SB DD...` without `zz`, 2–6 bytes (e.g. `"b509290100"`). The read telegram is built as `zz id[0] id[1] NN id[2..]` with `NN = len(id) - 2` (example: `"08"` + `"b509290100"` → `08b50903290100`).
- **`nn`** *(hex string, optional)*: Explicit 1-byte read NN for the rare telegrams where it differs from the derived `len(id) - 2`.
- **`wid`** *(hex string, optional)*: Write id with the same layout as `id`. The write NN is computed at runtime as `len(wid) - 2` plus the appended value bytes. Omit for read-only commands.
- **`write_type`** *(string, optional)*: Write encoding: `"simple"` (default) appends the value to the write id frame; `"weishaupt"` opts into the WCM 5023 encoding with a two-byte value. See [Weishaupt write support](../doc/weishaupt-writes.md).
- **`interval`** *(integer)*: Automatic polling interval in seconds. `0` disables active polling (passive listening only).
- **`master`** *(boolean)*: `true` if field data is located in the master message payload; `false` if in the slave response payload.
- **`fields`** *(array)*: Array of data field definitions (max 4 per command).

#### Field Properties
- **`name`** *(string)*: Field identifier used as the key in MQTT value JSON payload (`{"middle_temperature": 49.3, "state": 85}`).
- **`profile`** *(string)*: Reference to a Data Profile in `profiles/data_profiles.json` (e.g. `"data2c_celsius"`, `"uint8"`).
- **`position`** *(integer)*: 1-based offset of the field within the eBUS message payload. No default — `0` never matches.
- **`ha_profile`** *(string, optional)*: Reference to an HA Profile in `profiles/ha_profiles.json` (e.g. `"sensor_temperature"`). If omitted or empty, no Home Assistant entity is registered for this field.
- **`min`** *(float, optional)*: Override the profile's default min value for write validation (e.g. `15` for a setpoint with profile `data1c_celsius` default min=0).
- **`max`** *(float, optional)*: Override the profile's default max value for write validation (e.g. `20` for a setpoint with profile `data1c_celsius` default max=75).

## Files
- `simulation.json`: Command definitions used when building in simulation mode (`esp32-c3-internal-simulation`).

## Weishaupt WTC example

[`weishaupt-wtc.json`](weishaupt-wtc.json) contains installation-specific read
and optional write definitions. Adapt the bus addresses before uploading.
See [Weishaupt write support](../doc/weishaupt-writes.md) for the explicit
`write_type` option, units, readback and known limitations.
