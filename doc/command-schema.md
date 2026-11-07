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
| `id` | hex string | one of `id`/`read_cmd` | Read message id, 2..6 bytes `PB SB DD…`. |
| `read_cmd` | hex string | one of `id`/`read_cmd` | Legacy wire form (see below); migrated to `id` on save. |
| `wid` | hex string | no | Write message id, 2..6 bytes. Presence = command is writable. Empty/absent = read-only. |
| `write_cmd` | hex string | no | Legacy wire form of `wid`; the NN byte is discarded on parse. |
| `zz` | hex string | yes with `id`/`wid` | Target address, 1 byte. |
| `nn` | hex string | no | Explicit read-NN override, 1 byte (quirks only — see Frame construction). |
| `write_type` | string | no | `"simple"` (default) or `"weishaupt"` ([`doc/weishaupt-writes.md`](weishaupt-writes.md)). |
| `interval` | number | no | Seconds. `0` = passive (evaluate when seen on the bus); `> 0` = actively poll every N seconds. |
| `master` | bool | no | Value lives in the master part (`true`) or the slave answer (`false`). |
| `fields` | array | yes | Decoders for the data bytes (see below), 1..13 entries. |

`COMMAND_CAPACITY` is 96 commands (`platformio.ini`).

## Input forms: compact vs legacy

Two input forms are accepted; stored files use the compact form.

- **Compact** — `zz` + `id` (+ optional `nn`) (+ optional `wid`):
  ebusd-style decomposition, NN never appears for writes.
- **Legacy** — `read_cmd` / `write_cmd` as full wire hex
  `ZZ PB SB NN D…`. Accepted on input and migrated to compact on save:

  - `read_cmd`: if `NN == len(id) - 2` the NN is derivable and dropped;
    otherwise it is kept as an explicit `nn` override (master-message
    quirks, e.g. `feb5160301`).
  - `write_cmd`: the NN byte is discarded unconditionally — it encodes
    `value_len`, which is unknowable from the hex (no validation, no
    override).

`id`/`wid` decompose as `PB SB` + up to 4 tail bytes. The register tail
of `wid` equals `id`'s in all observed data; they are stored separately
because some vendors change PB (Wolf `5022`→`5023`) or D1
(`0d`→`0e`). An empty `id` with a `wid` is a write-only command.
`id`/`wid` are opaque — no byte-role assumptions are made (a corpus
survey found D1 carrying four different roles across vendors, even
within one vendor).

## Frame construction (runtime)

Read telegram built from `zz` + `id`:

```
ZZ id[0] id[1] NN id[2..]
NN = len(id) - 2          (or the explicit `nn` override)
```

Write telegram built from `zz` + `wid` + encoded value:

```
ZZ wid[0] wid[1] NN wid[2..] <value bytes>
NN = len(wid) - 2 + value_len     (always derived from the bytes
                                   actually appended — never stored)
```

The NN byte of a legacy `write_cmd` is discarded at parse; write NN is
never taken from JSON. Passive matching compares the full telegram
including the derived NN (collision-safe).

Example: `zz=10`, `id=b5090d01` reads as `10 b5 09 02 0d 01`. With
`wid=b5090e01`, a 2-byte value writes as `10 b5 09 04 0d 01 vv vv`.

The total data portion (wid tail + value) is capped at **16 bytes**.
Frames whose id/wid would exceed 6 bytes are rejected at parse
(`logged` and ignored on legacy input, `400` on upload).

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
| Data bytes per telegram (wid tail + value) | 16 |
| `id` / `wid` | 2..6 bytes |
| `zz` / `nn` | 1 byte |
| Legacy `read_cmd` / `write_cmd` | 4..8 wire bytes |
| Strings (key, name, field names, …) | shared pool: 255 strings, 2 KB total, ≤255 chars each |

Past the string pool, names silently stop resolving — keep names short.

## Examples

Single-field read + write:

```json
{
  "key": "01",
  "name": "Outside_Temperature",
  "zz": "fe",
  "id": "070009",
  "wid": "",
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
  "id": "b5090d01",
  "wid": "b5090e01",
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
`10 b5 09 04 0d 01 00 37`. `ign`/`ign_*` fields are never client input;
see [`doc/api.md`](api.md) for the write payload contract.
