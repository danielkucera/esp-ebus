# Optional Weishaupt 5023 writes

INTERNAL firmware supports the captured WCM-FS parameter-write format when a
command explicitly sets `"weishaupt_write": true`. Omit this property, or set
it to false, to preserve the existing write behavior: append the encoded value
to `write_cmd` without modifying either byte sequence.

## Command definition

```json
{
  "key": "hk2_normal",
  "name": "Weishaupt/Downstairs/Normal_room_setpoint",
  "read_cmd": "75502203700500",
  "write_cmd": "70502309000500",
  "weishaupt_write": true,
  "interval": 60,
  "master": false,
  "fields": [
    {"name": "value", "profile": "int16_celsius_div10", "position": 1,
     "min": 5, "max": 30}
  ]
}
```

The seven-byte prefix is `destination 50 23 09 crc_placeholder parameter_lo
parameter_hi`. The encoded value must contain exactly two bytes. The builder
appends the value and `5d010000`, then replaces `crc_placeholder` with the inner
checksum over parameter ID, value and suffix. This checksum uses polynomial
0x5c, zero initialization and incoming bits shifted into the low bit.
The ordinary eBUS frame checksum remains the library's responsibility.

Malformed opted-in prefixes or values are rejected before sending. Existing
commands, including 5023 commands without the opt-in, keep their original bytes.
The option survives JSON export and saving/reloading the command set. In the
compact storage format it is an optional eighth column, after `fields`; older
seven-column records default to false. New configurations using this option
require firmware that supports it.

HTTP, MQTT and cron use the same write builder. For HTTP:

```sh
curl -f -X POST -H 'Content-Type: application/json' \
  --data '{"key":"hk2_normal","value":21}' \
  http://ADAPTER-IP/api/v1/app/values/write
```

Values are degrees Celsius; the profile handles multiplication by ten. Normal
and reduced are stored room-temperature settings. Changing one does not switch
the operating mode or time program, and is not equivalent to forcing an active
room setpoint or a flow-temperature target. Verify acceptance through the
regular readback and the WCM-FS display; an API success only confirms queuing.

## Profiles and example

Two profiles are appended to the registry without changing existing indices:

- `int16_celsius_div10`: signed 16-bit little-endian, divisor 10, one decimal.
- `uint16_celsius`: unsigned 16-bit little-endian, divisor 1, no decimals.

`config/weishaupt-wtc.json` is an optional example for one observed WTC-60
installation with three WCM-EM 2.1 circuits and two WCM-FS 2.0 controllers.
It is not installed automatically. Adapt the addresses to your installation.
The six normal/reduced writes and their readbacks were captured at addresses
70/75, f0/f5 and 17/1c. The six complete write telegrams are regression fixtures.
Flow and room measurements use observed 5014 exchanges; the fourth circuit's
flow-temperature association was checked against the user's display. Its
requested flow temperature and the active room setpoints are not identified
and are not included. No measured room temperature is provided for the fourth
circuit, which has no room sensor. The outside and hot-water values come from
500A broadcasts and were checked against the installation displays.

The checksum was also checked against 16 captured writes. These checks confirm
the encoding of those messages, not every parameter or WCM model, and do not
replace checking writes on the physical installation.
