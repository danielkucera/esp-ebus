# Weishaupt WTC-60 — three heating circuits

These files extend the command export from 2026-10-31 14:03:55. They use the
same JSON array and compact, one-command-per-line layout as `../wtc25a/wtc25a.json`.
Together they contain 93 commands, including 12 writable commands. Load the
boiler file and whichever heating circuits are present:

| File | Contents | Commands | Writable |
|---|---|---|---|
| [`wtc60-boiler.json`](wtc60-boiler.json) | Shared boiler, outside and hot-water measurements | 15 | 0 |
| [`wtc60-hc2.json`](wtc60-hc2.json) | Circuit 2 | 32 | 4 |
| [`wtc60-hc3.json`](wtc60-hc3.json) | Circuit 3 | 34 | 4 |
| [`wtc60-hc4.json`](wtc60-hc4.json) | Circuit 4 | 12 | 4 |

Each file is independently uploadable. Keys are unique across the four files;
the adapter merges them into one command set. There is no combined JSON file
to maintain alongside these definitions. Splitting the files does not reduce
runtime memory when all circuits are loaded.

| Circuit | WCM-FS read slave | WCM-FS write master | Mixer |
|---|---|---|---|---|
| 2 | `75` | `70` | `51` |
| 3 | `f5` | `f0` | `52` |
| 4 | `1c` | `17` | `53` |

Addresses and circuit numbers are installation-specific. This is a WTC-60 with
WCM-FS controllers, WCM-EM mixers and an official app connected through WCM-COM
Home. Do not substitute the WTC25-A's `35 0902` / `35 0903` commands: this set
reads controller parameters with `5022` and writes them with `5023`.

## Keys and parameter numbers

The WTC25-A README describes its numeric keys as a common numbering across its
three command files. They are local command identifiers, not the parameter
numbers listed in its documentation: for example, key `36` means normal setpoint,
whose parameter ID is `0x0005` and whose documented menu number is 171.

This set keeps the exported descriptive keys so HTTP/MQTT clients continue to
work. A key must also distinguish circuits: parameter `0x0005` alone cannot
identify all three normal setpoints. The protocol parameter IDs below provide
the useful correspondence between the two installations; they are not claimed
to be industry-wide identifiers.

## Reuse from WTC25-A

The comparison covers all three WTC25-A JSON files. The reusable pieces are
field decoding, built-in profiles and parameter meanings, rather than complete
controller commands:

| WTC25-A definition | WTC-60 equivalent | Reusable part / difference |
|---|---|---|
| Key `36`, normal setpoint | `hcN_normal` | Parameter `0x0005`, INT16 /10, 5–30 °C, `number_temperature` |
| Key `41`, reduced setpoint | `hcN_reduced` | Parameter `0x0008`, INT16 /10, 5–30 °C, `number_temperature` |
| Key `38`, program switch | `hcN_operating_mode` | Parameter `0x0112`, UINT16 and the seven mode codes; WTC25-A defines only a read, WTC-60 also has a captured circuit 2 write |
| Key `45`, active room setpoint | `hcN_room_set` | Parameter `0x0012`, INT16 /10, `sensor_temperature` |
| Key `46`, room temperature | `hcN_room` | Parameter `0x0011` for the circuit 4 read; circuits 2/3 use passive `5014` instead |
| Key `52`, target flow temperature | `hcN_flow_set` | Parameter `0x0004` for the circuit 4 read; circuits 2/3 use passive `5014` instead |
| Unused-file key `51`, measured circuit flow | `hcN_flow` | Parameter `0x000f`, INT16 /10 for the circuit 4 mixer read; circuits 2/3 use passive `5014` instead |
| Key `58`, field `dhw` | `wtc_dhw` | Identical passive `fe500a0d`, master payload position 8, `data1c_celsius` |
| Key `58`, field `outside` | `wtc_outside` | Identical passive `fe500a0d`, master payload position 10, `int8_celsius` |

The WTC-60 temperature definitions already reuse the shared built-in data and HA
profiles. No copied profile overlays are needed. The WTC25-A program-mode HA
overlay only lists five modes; reusing it would omit program 1 and program 3.

Neither complete boiler command is identical: WTC25-A groups four temperatures
under key `58`, while this installation already exposes separate `wtc_*` keys
and actively polls boiler flow/flue temperatures using `5003`. Replacing those
with key `58` would change client keys, field names and update behavior. Keep
the matching DHW/outside field definitions, but do not load both versions just
to obtain the same two measurements.

No shared JSON include is introduced: the upload format accepts command arrays,
without an include/template mechanism. Extracting the two broadcast fields into
a cross-model file would require changing the WTC25-A command layout or adding
a generation step. Keeping the small upload files self-contained preserves both
installations' interfaces. WTC25-A burner/time fields and installer/holiday writes
have not been validated on this installation and are not added by this split.

## Circuit commands

Replace `N` with 2, 3 or 4 in the keys below. All temperature values are degrees
Celsius; clients must not multiply them by ten themselves.

| Key | Value | Access | Source / parameter | Interval |
|---|---|---|---|---|
| `hcN_normal` | Stored normal room setpoint | Read/write, 5–30 °C | `0x0005`, INT16 /10 | 60 s |
| `hcN_reduced` | Stored reduced room setpoint | Read/write, 5–30 °C | `0x0008`, INT16 /10 | 60 s |
| `hcN_operating_mode` | Selected operating mode | Read/write, discrete values below | `0x0112`, UINT16 | 30 s |
| `hcN_presence_override` | Temporary presence override | Read/write, 0 or 1 | `0x006d`, UINT16 | 30 s |
| `hcN_room_set` | Currently active room setpoint | Read only | `0x0012`, INT16 /10 | 60 s |
| `hcN_room` | Measured room temperature | Read only | Circuits 2/3: `5014` master, position 4, DATA2B; circuit 4: controller `0x0011`, INT16 /10 | Passive / 60 s |
| `hcN_flow_set` | Target flow temperature | Read only | Circuits 2/3: `5014` master, position 2, DATA2B; circuit 4: controller `0x0004`, INT16 /10 | Passive / 60 s |
| `hcN_flow` | Measured flow temperature | Read only | Circuits 2/3: `5014` response, position 3, DATA2B; circuit 4: mixer `53`, `0x000f`, INT16 /10 | Passive / 30 s |
| `hcN_operating_level` | Current operating level | Read only, circuits **2 and 3 only** | `5014` master, position 1, UINT8 | Passive |

The HC3 export also includes `hc3_flow_poll`, a 30-second active read of mixer
parameter `0x000f` (INT16 /10), matching the existing HC4 mixer-flow read.
It exposes the separately polled value without replacing the passive `hc3_flow`
field or creating a duplicate Home Assistant sensor.

The HC3 file now polls the observed minimum and maximum supply-temperature
registers (`0x012b` and `0x0028`) as `hc3_supply_min` and `hc3_supply_max`.
The log shows writes of 8.0 °C and 65.0 °C, respectively.

Passive fields use the firmware's one-based payload positions. No circuit 4
`5014` status telegram was identified, so no `hc4_operating_level` command is
invented. Use its selected mode and active room setpoint to inspect its settings;
a selected time program alone does not tell you which operating level is active.

The boiler commands decode the passive `500a` broadcast into status, operating
phase, flags, temperatures, outside temperature and trend. The controller's
`0507` telegrams decode demand, requested temperature, pressure, output degree
and hot-water setpoint. `wtc_device_identification` exposes the fixed ASCII
manufacturer marker and remaining identifier bytes from `f6 07 04 00`.
`wtc_flow` and `wtc_flue` actively read boiler temperatures every 10 seconds;
`wtc_dhw` and `wtc_outside` remain available as before.

The 2026-11-01 log also contains `fe 07 04` broadcast identification frames and
one `fe 07 00 09` bus-time frame. These are exposed as raw hex because the
broadcast identification is not tied to a known device address, and the bus
time payload's field offsets have not been verified for this frame. The
payload-free `fe 07 ff 00` broadcast is decoded by `wtc_sign_of_life` as the
standard eBUS sign-of-life message. It is a bus-wide definition, not specific
to circuit 2; the source address (observed here as `0x70`) remains in the raw
telegram.

The `500a` flag bytes are retained as hex: byte 3 bit 3 is flame, bits 4/5 are
gas valves, bit 6 is pump and bit 7 is error; byte 4 bit 1 is summer/winter and
bit 7 is heating/DHW selection. The upstream definitions identify the remaining
bits as unknown. Meanings and units for `0902`/`0903` parameter IDs are not
assigned without a matching definition; observed raw values are retained below.

The larger 2026-11-01 log also contains unlabelled `0902` reads and `0704`
identification replies. The observed `0902` reads are exposed as raw UINT16
values under `*_mixer_parameter_*_raw` and `*_controller_parameter_*_raw`
keys; their meanings and units are not known. Device identification replies are
split into raw 8-byte and 2-byte hex fields. The boiler's `085003018b` response
is exposed as a raw 5-byte hex field. These entries preserve the observed data
without presenting an unsupported semantic interpretation.

The same log captures seven `0903` writes each on circuits 2 and 3. Registers
`0x0a20`, `0x0285`, `0x0973`, `0x0141` and `0x09b1` have observed values `0`,
`0`, `2`, `2` and `180`; passive capture commands expose these as raw UINT16
without transmitting writes. Supply-temperature writes to `0x0028` and `0x012b`
are decoded as INT16 /10: 65.0 °C maximum and 8.0 °C minimum. Meanings for the
other parameter IDs remain unconfirmed; the captures are not writable commands.

These mappings were cross-checked against the upstream
[`f6..sc.csv`](https://github.com/J0EK3R/ebusd-configuration-weishaupt/blob/master/weishaupt/f6..sc.csv),
[`51..hc2.csv`](https://github.com/J0EK3R/ebusd-configuration-weishaupt/blob/master/weishaupt/51..hc2.csv)
and [`hc.expert.inc`](https://github.com/J0EK3R/ebusd-configuration-weishaupt/blob/master/weishaupt/hc.expert.inc)
definitions, plus the independent
[WTC-OB telegram notes](https://github.com/B-o-r-i-s-M/Weishaupt-WTC-OB-ebusd-Home-Assistant/blob/main/docs/03-protokoll.md).
Those projects cover different installations and models, so only matching
service layouts, parameters and field types are reused here.

## Selected operating mode: valid write values

These values apply to `hc2_operating_mode`, `hc3_operating_mode` and
`hc4_operating_mode`. They are discrete codes, not a continuous range.

| Value | Mode |
|---|---|
| 1 | Standby |
| 3 | Continuous normal |
| 4 | Continuous reduced |
| 5 | Summer |
| 11 | Time program 1 |
| 12 | Time program 2 |
| 13 | Time program 3 |

All seven codes were captured as writes to circuit 2's parameter `0x0112` and
confirmed by subsequent reads in `/tmp/weishaupt-presence.jsonl`, captured on
2026-10-31 between 13:58 and 14:02 CET. The app selected program 1, program 2,
program 3, summer, normal, reduced, standby, then restored program 1, about
30 seconds apart. All nine captured writes, including an initial standby write,
match the firmware's inner-checksum algorithm.

The selectors for circuits 3 and 4 use the same parameter with their respective
controller addresses; their mode writes have **not** been captured independently.
Selecting normal/reduced here changes the selected mode. To resume scheduling,
select program 11, 12 or 13. This is separate from the temporary override below.

The JSON leaves the HA profile unset for mode selectors. The firmware currently
limits HA enum profiles to five entries, so a seven-mode selector cannot be
represented completely by one such profile. No partial enum or misleading
numeric min/max range is supplied. HTTP clients must send only the listed codes;
the generic UINT16 field does not enforce this discrete whitelist.

## Presence override: valid write values

| Value | Meaning supported by the capture |
|---|---|
| 0 | Cancel the temporary override and resume the selected program's behavior |
| 1 | Enable the temporary override; during scheduled normal operation, this produced reduced operation (Away) |

The earlier circuit 2 presence capture showed `0x006d` alternating between 1
and 0, with the active room setpoint changing between 16 °C and 20 °C while
program 1 remained selected. The expected override lifetime is until the next
scheduled change or cancellation; the capture did not span that scheduled expiry.
It also did not establish the behavior of value 1 during scheduled reduced
operation. Do not label this universally as “1 = reduced, 0 = normal.”

Reads of `0x006d` returning zero were captured for all three controllers. The
write behavior was captured on circuit 2; circuits 3/4 use the corresponding
address substitution.

## Current operating level

The passive `hc2_operating_level` and `hc3_operating_level` commands report the
controller-to-mixer status byte, rather than the selected program code:

| Value | Observed meaning |
|---|---|
| 0 | Standby, observed after selecting standby on circuit 2 |
| 1 | Reduced/inactive heating level; also observed with summer selected |
| 3 | Normal heating level |

This byte does not distinguish all seven selected modes. For example, program 1
may currently run at normal or reduced level. Other byte values are undocumented.

## Verification limits

- Existing command keys, temperatures, addresses, intervals and limits are
  preserved. Command names use abstract circuit numbers, not room locations.
- Normal/reduced setpoint writes were captured for all three circuits during the
  earlier investigation. Circuit 2 mode and presence writes were captured through
  the official app; this is protocol evidence, not a test of adapter-issued writes.
- Circuit 2 active room setpoint `0x0012` was captured at 10 °C in standby/summer,
  20 °C in normal, and 16 °C in reduced. Circuit 3/4 active room-setpoint reads
  extend that parameter to their controllers and need physical confirmation.
- Circuit 4 target flow `0x0004` was read successfully at `1c` in the latest
  capture (33.5 °C). Its measured flow is read from mixer `53` separately.
- Circuit 4 room temperature `0x0011` is inferred from the controller parameter
  used successfully on circuit 2. It has not been captured at `1c`; the controller
  may lack a usable room sensor. Confirm the value against the installation before
  using it in automation. A read failure or unavailable sensor must not be treated
  as a valid room temperature.

## Loading and writing

Use firmware with the Weishaupt encoder described in
[`../../doc/weishaupt-writes.md`](../../doc/weishaupt-writes.md). All required data
profiles are built in. Temperature fields use the built-in HA profiles
`sensor_temperature` and `number_temperature`; no profile overlays are required.

Each compact JSON file fits the 8192-byte HTTP body limit. Loading all four uses
93 of the configured 96 command slots, 12 of 16 write slots, and 13 of 16
field-override slots. Its unique keys, names and field names occupy 6355 bytes
in the string pool on a fresh load. The `master` branch currently provides only
2048 bytes, so this command set requires the separate StringPool-capacity
increase to 8192 bytes. This WTC-60 change does not include that increase.
Additional commands and older names retained in the runtime pool also consume
space; reboot after saving a replacement set if needed.

Upload merges commands by key; it does not remove unrelated existing commands.
To load this complete installation, run from the repository root:

```sh
EBUS_URL="http://192.168.10.195"
for file in config/wtc60/wtc60-boiler.json \
            config/wtc60/wtc60-hc2.json \
            config/wtc60/wtc60-hc3.json \
            config/wtc60/wtc60-hc4.json; do
  curl -f -X POST -H 'Content-Type: application/json' \
    --data-binary "@$file" \
    "$EBUS_URL/api/v1/app/commands/upload" || break
done
```

Omit circuit files you do not need. Existing installations using the earlier
combined file can upload these four files without changing client keys. Omitting
a circuit file does not delete commands that were previously loaded for it.

For example, select time program 2 on circuit 3:

```sh
curl -f -X POST -H 'Content-Type: application/json' \
  --data '{"key":"hc3_operating_mode","value":12}' \
  "$EBUS_URL/api/v1/app/values/write"
```

A successful response means the write was queued. Check the asynchronous
readback and the physical controller/app to confirm acceptance.
