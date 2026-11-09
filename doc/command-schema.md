<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Command Schema

Normative reference for the command JSON accepted by HTTP/MQTT command
upload and the on-disk store. Upload recipes are in
[`doc/commands.md`](commands.md); profile and datatype tables in
[`doc/datatype_mapping.md`](datatype_mapping.md); runtime write payloads
in [`doc/api.md`](api.md).

Commands persist in LittleFS and load at restart. Uploads are validated
before install (`POST /api/v1/app/commands/evaluate`); a command with an
error is rejected as a whole, never installed truncated.

## Top-level keys

| Key | Type | Required | Meaning |
|---|---|---|---|
| `key` | string | yes | Unique id, e.g. `"01"`. Referenced by writes, cron rules, HA entity ids. |
| `name` | string | yes | Display name and MQTT topic base, e.g. `"Outside_Temperature"`. |
| `pbsb` | hex string | one of `pbsb`/`read_cmd` | Read message `PB SB` (2 bytes) — first half of the read id. `""` = write-only command. |
| `dx` | hex string | no | Read message tail `DD…` (0..4 bytes). Read id = `pbsb` + `dx`; requires a non-empty `pbsb`. |
| `read_cmd` | hex string | one of `pbsb`/`read_cmd` | Legacy wire form (see below); migrated to `pbsb`/`dx` on save. |
| `wpbsb` | hex string | no | Write message `PB SB` (2 bytes) — first half of the write id. Presence of `wpbsb`/`wdx` = command is writable; absent = read-only. |
| `wdx` | hex string | no | Write message tail (0..4 bytes). Write id = `wpbsb` + `wdx`; requires a non-empty `wpbsb`. |
| `write_cmd` | hex string | no | Legacy wire form of the write id; the NN byte is discarded on parse. |
| `zz` | hex string | yes with `pbsb`/`wpbsb` | Target address, 1 byte. Not required for pure `read_cmd` input (the wire hex carries ZZ). |
| `nn` | hex string | no | Explicit read-NN override, 1 byte (quirks only — see Frame construction). |
| `write_type` | string | no | `"simple"` (default) or `"weishaupt"` ([`doc/weishaupt-writes.md`](weishaupt-writes.md)). |
| `interval` | number | no | Seconds. `0` = passive (evaluate when seen on the bus); `> 0` = actively poll every N seconds. |
| `master` | bool | no | Value lives in the master part (`true`) or the slave answer (`false`). |
| `fields` | array | yes | Decoders for the data bytes (see below), 1..13 entries. |

`COMMAND_CAPACITY` is 96 commands (`platformio.ini`).

## Input forms: split vs legacy

Three input forms are accepted; stored files use the split form.

- **Split** (stored form) — `pbsb` + `dx` (+ optional `nn`) for the
  read side, `wpbsb` + `wdx` for the write side: the wire `PB SB`
  prefix is explicit per direction, the register tail stays an opaque
  byte run. NN never appears for writes.
- **Compact** (retired) — `zz` + `id` (+ optional `nn`) (+ optional
  `wid`): accepted only from stored files for migration (below);
  `/evaluate` and `/insert` reject it (`400 Unsupported key 'id'`,
  also for a tabular `id` header column).
- **Legacy wire** — `read_cmd` / `write_cmd` as full wire hex
  `ZZ PB SB NN D…`. Accepted on input and migrated to split on save:

  - `read_cmd`: if `NN` equals the length of the data tail `D…` the NN
    is derivable and dropped; otherwise it is kept as an explicit `nn`
    override (master-message quirks, e.g. `feb5160301`).
  - `write_cmd`: the NN byte is discarded unconditionally — it encodes
    `value_len`, which is unknowable from the hex (no validation, no
    override).

`pbsb`/`wpbsb` are exactly the wire `PB SB` bytes (2 bytes; `""` when
that side is absent); `dx`/`wdx` carry the register tail (0..4 bytes).
The register tail of `wdx` equals `dx`'s in all observed data; the
halves are stored separately because some vendors change PB (Wolf
`5022`→`5023`) or D1 (`0d`→`0e`). A command with only `wpbsb`/`wdx`
(`pbsb` empty) is write-only; a command without `wpbsb`/`wdx` is
read-only. `dx`/`wdx` are opaque — no byte-role assumptions are made
(a corpus survey found D1 carrying four different roles across vendors,
even within one vendor).

Stored files written before the split (`id`/`wid` keys, or tabular
rows under an `id` header) are accepted by the persistence loader and
the file-oriented `POST /api/v1/app/commands/upload` endpoint (both
parse with the retired keys allowed): the file is installed and
immediately rewritten in the split schema (one-shot, logged as
`rewrote legacy commands file in split schema`). The JSON-row endpoints
`/evaluate` and `/insert` reject `id`/`wid` as unknown keys/columns.

## Frame construction (runtime)

Read telegram built from `zz` + `pbsb` + `dx`:

```
ZZ pbsb[0] pbsb[1] NN dx…
NN = len(dx)                 (or the explicit `nn` override)
```

Write telegram built from `zz` + `wpbsb` + `wdx` + encoded value:

```
ZZ wpbsb[0] wpbsb[1] NN wdx… <value bytes>
NN = len(wdx) + value_len    (always derived from the bytes
                              actually appended — never stored)
```

The NN byte of a legacy `write_cmd` is discarded at parse; write NN is
never taken from JSON. Passive matching compares the full telegram
including the derived NN (collision-safe).

Example: `zz=10`, `pbsb=b509`, `dx=0d01` reads as `10 b5 09 02 0d 01`.
With `wpbsb=b509`, `wdx=0d01`, a 2-byte value writes as
`10 b5 09 04 0d 01 vv vv`.

The total data portion (wdx tail + value) is capped at **16 bytes**.
Frames whose concatenated read/write id would exceed 6 bytes are
rejected at parse (`logged` and ignored on legacy input, `400` on
upload).

## `fields[]` entries

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | Value name within the command (and MQTT payload key / HA entity suffix). |
| `profile` | string | yes | Data profile reference (datatype + divider + digits + unit) — see [`doc/datatype_mapping.md`](datatype_mapping.md). Unknown profile rejects the command. |
| `position` | number | yes | 1-based byte offset into the data bytes (after NN). `0`/absent defaults to 1. |
| `ha_profile` | string | no | Home Assistant profile reference; `""`/absent = MQTT-only (no HA entity). See `profiles/ha_profiles.json`. |
| `bits` | object | no | Bit-name map: `{ "enable": 0, "fault": 1, … }` — names → bit indices, dense from 0, at most 8. The field's byte expands into one value/topic/HA binary sensor per bit. |
| `raw` | bool | no | Skip sentinel-to-null mapping and always render the raw number — see [`doc/datatype_mapping.md`](datatype_mapping.md). |
| `min` / `max` | number | no | Per-field plausibility/writing range overrides, stored per command key — see [`doc/datatype_mapping.md`](datatype_mapping.md). |

Field order in JSON does not matter at write time: multi-field write
payloads are encoded in ascending `position` order, and positions must
be strictly increasing across a command's fields (all generated
command sets satisfy this).

## Limits

| Limit | Value |
|---|---|
| Fields per command | 13 (`COMMAND_MAX_FIELDS`) |
| Commands | 96 (`COMMAND_CAPACITY`) |
| Data bytes per telegram (wdx tail + value) | 16 |
| `pbsb` / `wpbsb` | 2 bytes (or empty) |
| `dx` / `wdx` | 0..4 bytes |
| Concatenated read/write id | 2..6 bytes |
| `zz` / `nn` | 1 byte |
| Legacy `read_cmd` / `write_cmd` | 4..8 wire bytes |
| Strings (key, name, field names, …) | shared pool: 255 strings, 2 KB total, ≤255 chars each |

Past the string pool, names silently stop resolving — keep names short.

## Examples

Single-field read:

```json
{
  "key": "01",
  "name": "Outside_Temperature",
  "zz": "fe",
  "pbsb": "0700",
  "dx": "09",
  "interval": 0,
  "master": true,
  "fields": [
    {
      "name": "value",
      "profile": "data2b_celsius",
      "position": 1,
      "ha_profile": "sensor_temperature"
    }
  ]
}
```

Multi-field with an `ign` filler (schematic):

```json
{
  "key": "42",
  "name": "Set_Timer",
  "zz": "10",
  "pbsb": "b509",
  "dx": "0d01",
  "wpbsb": "b509",
  "wdx": "0e01",
  "interval": 0,
  "master": true,
  "fields": [
    { "name": "ign",   "profile": "uint8", "position": 1 },
    { "name": "value", "profile": "uint8", "position": 2 }
  ]
}
```

A write of `{"key":"42","value":{"value":55}}` encodes `ign` as `00`
(auto-pad) and `value` as `37`, giving wire
`10 b5 09 04 0e 01 00 37`. `ign`/`ign_*` fields are never client input;
see [`doc/api.md`](api.md) for the write payload contract.
