<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# API Contract

Normative reference for the runtime interfaces of the INTERNAL firmware:
HTTP values API, MQTT topics and payloads, cron writes, and Home
Assistant discovery behavior. Curl recipes are in
[`doc/commands.md`](commands.md); the command JSON schema in
[`doc/command-schema.md`](command-schema.md). Wiki pages are narrative
guides and may lag — this file and the code it documents ship together.

## Channel rule

- **Machine data → MQTT push** (values, errors, discovery).
- **Human/debug → HTTP pull** (health, metrics, logs, values, views).
- Exceptions: the web UI composes views from HTTP; liveness
  (online/offline) is announced on both channels.

## Write contract (all transports)

Every write — HTTP, MQTT `request`, MQTT `set/#`, cron — routes through
the same encoder. The adapter is **one-shot stateless**: a write payload
carries the complete field set, and the adapter never accumulates
partial field state across requests (no read-modify-write of guessed
values).

A write payload's `value` is either:

| Form | Applies to | Encoded as |
|---|---|---|
| Scalar (`55`, `"A"`) | single-field commands only | that field's bytes |
| Object (`{"field1":v1,…}`) | any writable command | every field's bytes, concatenated in ascending `position` order |

Rules, enforced **before anything reaches the bus** (a violation returns
an error / drops the message; the telegram is never partially sent):

- **All non-filler fields are required.** Missing keys reject — there is
  no partial update and no defaulting to the previous on-bus value.
- **Unknown keys reject** (typos never silently pad).
- **Duplicate keys reject.**
- **Scalar on a multi-field command rejects** — it would encode only the
  first field and truncate the wire payload.
- **`ign` / `ign_*` filler fields are never client input**: omitted keys
  with those names are auto-padded with `0x00` of the profile datatype's
  width. Explicit values for them are accepted and used as-is.
- **Ranges**: the encoded number must fall inside the field's
  `min`/`max` (profile defaults, per-field overrides in the command).
  A `max` of `0` means *no upper bound* (profiles whose TypeSpec
  metadata was not popped by the generator carry `max = 0`).
- **Field positions must be strictly increasing** across a command's
  fields (write encoding order = position order).

The total telegram data portion (wid tail + value) is capped at 16
bytes; a value that overflows it fails as "Invalid write command
format".

## HTTP

Base: `<device-ip>`. All bodies are JSON; success and error responses
share one envelope:

```json
{ "id": "write", "status": "successful" }
{ "id": "write", "status": "failed", "error": "Invalid value for key '42'" }
```

On 200 the `status` is a success word (`"successful"`, or a more
specific one such as `"requested"`); on 4xx it is `"failed"` with a
human-readable `error`.

### `GET /api/v1/app/values`

Array of value rows, sorted by key. Single-field commands (no `bits`)
emit one row; multi-field commands and `bits` fields emit **one row per
field** (per bit for `bits`) so renderers never see nested objects:

```json
{ "key": "01", "name": "Outside_Temperature", "value": 21.5,
  "unit": "°C", "age": 12, "write": false, "active": true }
{ "key": "42", "name": "Set_Timer/value", "field": "value",
  "value": 55, "unit": "", "age": 3, "write": true, "active": false }
```

- `value` — scalar for single-field rows, number/string/`null` otherwise
  (sentinels decode to `null` unless the field is `raw`).
- `text` — present only when the HA profile maps the value to a label
  (key/value pairs); omitted otherwise.
- `age` — seconds since the last evaluation; `write` — command is
  writable; `active` — `interval > 0`.

### `POST /api/v1/app/values/read`

Body: `{"key":"01"}`. Resets the command's timer so the value is
physically re-polled before the next publish — never served from cache
alone. Errors: `400` malformed body, `404` unknown key.

### `POST /api/v1/app/values/write`

Body: `{"key":"42","value":…}` with `value` per the write contract.

```bash
# single-field
curl -X POST -H "Content-Type: application/json" \
  -d '{"key":"01","value":21.5}' \
  http://<device-ip>/api/v1/app/values/write

# multi-field (object form; ign fillers auto-pad)
curl -X POST -H "Content-Type: application/json" \
  -d '{"key":"42","value":{"value":55}}' \
  http://<device-ip>/api/v1/app/values/write
```

Errors: `400` invalid value / read-only command / malformed body;
`404` unknown key. Success means *enqueued on the bus*, not *acknowledged
by the slave*.

## MQTT

Root topic: `ebus/<unique-id>/` by default (unique id from the device
MAC), configurable (`rootTopic`); a custom root gets a trailing `/`.

### Published topics

| Topic | Payload | Retained |
|---|---|---|
| `<root>values/…` | decoded values (see modes below) | no |
| `<root>response` | `{"id":…,"status":…,"bytes":…}` for `request` commands | no |
| `<root>errors` | evaluated bus errors | no |
| `<root>state` | slim telemetry every 10 s (uptime, version, heap, bus health) | no |
| `<root>available` | `{"value":"online"}` on connect; broker last-will `{"value":"offline"}` | yes |

### Subscribed topics

| Topic | Payload |
|---|---|
| `<root>request` | `{"id":"read","key":…}` / `{"id":"write","key":…,"value":…}` / `{"id":"restart"}` |
| `<root>set/#` | suffix after `set/` is the command key; payload is the value |

- `read` resets the command timer (force re-poll, like HTTP read) and
  re-publishes the value; unknown key answers on `response`.
- `write` accepts `value` in **either write-contract form** (scalar or
  object) and answers on `response` — JSON objects are accepted here
  regardless of the configured payload mode.
- `set/<key>` is the direct-write form (also what Home Assistant uses):
  payload is a scalar for single-field commands or a JSON object for
  multi-field ones. Failures are logged, not answered (no correlation id
  on this path).
- `request`/`set` answers and values are only queued while connected;
  they refresh on the next poll cycle, keeping `publish_failed` clean
  across reconnects.

### Value payload modes (`mqttPayload`)

Config key `mqttPayload`, one of `json_multi` (default), `json_single`,
`plain`. Topic names are lowercased.

| Mode | single-field | multi-field | field carrying `bits` |
|---|---|---|---|
| `json_multi` | `values/<cmd>` → `{"value":v}` | `values/<cmd>` → `{"f1":v1,…}` | bit names as keys inside the command's object |
| `json_single` | `values/<cmd>` → `{"value":v}` | `values/<field>` → `{"value":v}` | `values/<bit>` → `{"value":0\|1}` |
| `plain` | `values/<cmd>` → `v` | `values/<field>` → `v` | `values/<bit>` → `0\|1` |

## Cron

Rules fire **writes** on wall-clock schedules (complement to interval
polling, which only reads).

- Storage/limit: max 32 rules, persisted in LittleFS; HTTP
  `GET/POST /api/v1/app/cron`, `POST /api/v1/app/cron/load`,
  `POST /api/v1/app/cron/evaluate`.
- Rule: `{"id","schedule","command_key","value","enabled"}` —
  `schedule` is a standard 5-field cron expression evaluated in
  **local time** (SNTP + timezone must be correct).
- `value` is stored as raw JSON and may be **scalar or object** — the
  same write contract applies.
- Validated at save (unknown command, read-only command, bad value →
  rejected) and again at fire time (rule skipped with a warning if the
  command disappeared or the value went out of range).
- At most one fire per minute per rule.

## Home Assistant discovery

Requires MQTT. On (re)connect the adapter publishes retained configs to:

```
homeassistant/<component>/<device-id>/<object_id>/config
```

- `<device-id>` = `ebus<unique-id>` (groups all entities into one HA
  device); `<object_id>` = `key_name_field`, sanitized.
- Only fields with an `ha_profile` get entities; states flow through the
  regular `<root>values/…` topics (modes above), availability through
  `<root>available`.
- **Writable entities** (`number`/`switch`/`select`) get
  `command_topic = <root>set/<key>` with `command_template = {{value}}`
  — HA publishes the scalar straight to the direct-write topic.
- **Multi-field commands never get writable entities**: a scalar HA
  command can never carry the full object payload, so those components
  are converted to read-only `sensor`s, and the retained discovery
  config of the writable component they replace is cleared alongside.
- **`number` min/max are omitted when the field's `max` is `0`** (no
  upper bound — see write contract) so HA applies its own defaults
  instead of clamping the slider to a zero-width range.
- A `bits` field publishes one `binary_sensor` per bit.
- Discovery re-publishes on every (re)connect; disabling HA clears the
  retained configs.
