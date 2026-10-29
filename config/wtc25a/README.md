# Weishaupt WTC 25-A – eBUS commands (read and write)

Reference for the controller of heating circuit 1 (eBUS address **35**, proprietary B509 read/write), written for the adapter's JSON command format.

## How the command files are organised

The commands are split into three files in `config/wtc25a/`. Only the first one is meant to be loaded into the adapter as-is; the other two are archives kept so nothing has to be rediscovered.

| File | Contents | Load it? |
|---|---|---|
| `wtc25a.json` | **Active set (19 commands, 9 with write).** User-level values worth exposing: setpoints, holiday dates, DHW setpoints, burner/boiler broadcast, bus time. | Yes |
| `wtc25a-installer.json` | **Installer settings (13 commands, 6 with write).** Parameters from the installer menu (`WTC/Installer/*`). Verified on the bus, but intentionally not exposed: changing them can damage the heating installation or its efficiency. | Only on purpose |
| `wtc25a-unused.json` | **Unused values (16 commands, 2 with write).** Either not available on this installation (mixer circuit and floor drying: frozen values; missing sensors) or simply not useful (outside temperature, gradient, ...). | No |

All three files use the same format and can be merged or loaded separately. Total capacity of the adapter is **96 commands, of which at most 16 may have `write_cmd`**, and one HTTP request is limited to **8192 bytes**, so large sets must be uploaded in several parts. The string pool (2048 bytes) also limits the total length of keys and names.

Keys come from one common numbering, so they are unique across the three files: loading several of them never collides, but together they must still fit the capacity limits above.

## Legend

- **Level**: *user* = setting of the user menu; *installer* = installer setting, do not change lightly.
- ⚠ = inconsistency reported in the original source (read and write IDs differ): do not write before checking.
- Unavailable sensors answer `0x8000` (32768, shown as −3276.8 for `/10` values).

## Write status

Verified on a real WTC 25-A: `NormalSetTemp`, `ReducedSetTemp`, `StartOfHoliday.Day`, `StartOfHoliday.Month`, `EndOfHoliday.Day`, `EndOfHoliday.Month`. All other writes are taken from the source documentation and untested. Written values may appear on the entity only after the next read (the read interval, e.g. 300 s).

## Process values – heating circuit

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| HeatDemand |  | Heat demand | `35090203020002` | — | INT16 /10 | °C | measurement |
| SupplyTemperatureWTC |  | Boiler flow temperature seen by the controller | `350902030D0002` | — | INT16 /10 | °C | measurement |
| SupplySetValueHC |  | Heating circuit flow setpoint | `35090203040002` | — | INT16 /10 | °C | measurement |
| SupplyTemperatureHC |  | Heating circuit flow temperature (sensor missing on some installations: −3276.8) | `350902030F0002` | — | INT16 /10 | °C | measurement |
| RoomSetValue |  | Active room setpoint | `35090203120002` | — | INT16 /10 | °C | measurement |
| RoomTemperature |  | Room temperature of the controller | `35090203110002` | — | INT16 /10 | °C | measurement |
| MixedExternalTemperature |  | Smoothed outside temperature | `350902031A0A02` | — | INT16 /10 | °C | measurement |
| ExternalTemperature |  | Outside temperature | `350902030C0002` | — | INT16 /10 | °C | measurement |
| ProgramChooseSwitch |  | Program selector position (no write defined) | `35090203120102` | — | UINT16 | 1 Standby · 3 Normal · 4 Reduced · 5 Summer · 11/12/13 Program 1/2/3 | measurement |

## Process values – domestic hot water

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| DHWSetValue |  | Calculated DHW setpoint | `35090203030002` | — | INT16 /10 | °C | measurement |
| DHWTemperature |  | DHW temperature (−100 when the sensor is on the boiler, not on the controller) | `350902030E0002` | — | INT16 /10 | °C | measurement |

## User parameters – heating

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| NormalSetTemp | 171 | Normal temperature setpoint | `35090203050002` | `350903040500` | INT16 /10 | °C | user |
| ReducedSetTemp | 172 | Reduced temperature setpoint | `35090203080002` | `350903040800` | INT16 /10 | °C | user |
| FrostProtection | 173 | Room frost protection | `35090203140A02` | `35090304140A` | INT16 /10 | °C | user |
| SummerWinterChangeOverTemperature | 174 | Summer / winter changeover temperature | `35090203160102` | `350903041601` | INT16 /10 | °C | user |
| Gradient | 175 | Heating curve slope | `350902030E0102` | `350903040E01` | INT16 /10 |  | user |

## User parameters – holiday

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| StartOfHoliday | 181 | Holiday start (day + month, read only) | `350902031B0104` | — | UINT16 ×2 |  | user |
| StartOfHoliday.Day | 181 | Holiday start – day | `350902031B0102` | `350903041B01` | UINT16 | 0 = off · 1…31 | user |
| StartOfHoliday.Month | 181 | Holiday start – month (the source listed an inconsistent write ID `3509031C0102`; `350903041C01` was verified) | `350902031C0102` | `350903041C01` | UINT16 | 0 = off · 1…12 | user |
| EndOfHoliday | 182 | Holiday end (day + month, read only) | `350902031E0104` | — | UINT16 ×2 |  | user |
| EndOfHoliday.Day | 182 | Holiday end – day | `350902031E0102` | `350903041E01` | UINT16 | 0 = off · 1…31 | user |
| EndOfHoliday.Month | 182 | Holiday end – month | `350902031F0102` | `350903041F01` | UINT16 | 0 = off · 1…12 | user |
| HolidayTemp | 183 | Temperature during holidays (⚠ inconsistent write ID: `3509032D0102`) | `350902032D0102` | ⚠ to be checked | UINT16 | 0 frost protection · 1 reduced | user |

## User parameters – domestic hot water

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| DHWSetpoint | 176 | DHW setpoint | `35090203130002` | `350903041300` | INT16 /10 | °C | user |
| DHWMin | 177 | Minimum DHW temperature | `35090203330102` | `350903043301` | INT16 /10 | °C | user |

## Installer parameters – heating (34x–35x)

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| RoomInfluence | 341 | Influence of the room temperature | `350902030F0102` | `350903040F01` | UINT16 | 0…20 · 0xFFFF = off | installer |
| RoomSensorCorrection | 342 | Room sensor correction | `35090203090102` | `350903040901` | INT16 /10 | °C | installer |
| Adaption | 343 | Heating curve adaption | `35090203150102` | `350903041501` | UINT16 | 0 off · 1 on | installer |
| RoomThermostat | 344 | Room thermostat | `350902031C0A02` | `350903041C0A` | INT16 | °C | installer |
| Reduces | 350 | Reduced mode: frost protection or reduced temperature | `35090203320102` | `350903043201` | UINT16 | 0 frost protection · 1 reduced | installer |
| MinSupplyTemperature | 351 | Minimum flow temperature | `350902032B0102` | `350903042B01` | INT16 /10 | °C | installer |
| MaxSupplyTemperature | 352 | Maximum flow temperature | `35090203280002` | `350903042800` | INT16 /10 | °C | installer |
| SwitchOnSetting | 353 | Switch-on delay | `35090203100102` | `350903041001` | UINT16 | min | installer |
| SwitchOffSetting | 354 | Switch-off delay | `350902032E0102` | `350903042E01` | UINT16 | min | installer |

## Installer parameters – domestic hot water (36x–37x)

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| DHWMode | 361 | DHW mode | `35090203350102` | `350903043501` | UINT16 | 0 DHW program · 1 24 h · 2 DHW before heating | installer |
| MaxDHWTemp | 362 | Maximum DHW temperature | `35090203340102` | `350903043401` | INT16 /10 | °C | installer |
| LegionnairesFunction | 363 | Legionella protection (address to be checked in the source) | `35090203010102` | `350903040101` | UINT16 | 0 off · other = weekday (undocumented) | installer |
| TypeOfConstruction | 371 | Building type | `35090203280102` | `350903042801` | UINT16 | 0 heavy · 1 light | installer |

## Installer parameters – mixer / floor circuit (355–383)

Not part of the source's device file. These values were frozen on the reference installation (no mixer circuit), see `wtc25a-unused.json`.

| Name | Rep. | Description | Read | Write | Type | Unit / values | Level |
|---|---|---|---|---|---|---|---|
| BoilerMKIncrease | 355 | Boiler / mixer circuit increase | `35090203110102` | `350903041101` | INT16 /10 | °C | installer |
| MaxMixerRuntime | 356 | Maximum mixer valve runtime | `350902032B0002` | `350903042B00` | UINT16 | s | installer |
| SpeedVariation | 357 | Pump speed variation mode | `35090203310102` | `350903043101` | UINT16 | 0 operating level · 1 curve | installer |
| MaxPumpSpeed | 358 | Maximum pump speed | `350902032F0102` | `350903042F01` | UINT16 | % | installer |
| MinPumpSpeed | 359 | Minimum pump speed | `35090203300102` | `350903043001` | UINT16 | % | installer |
| DHWOperation | 360 | DHW operation | `35090203370102` | `350903043701` | UINT16 | 0 priority · 1 sliding · 2 parallel | installer |
| FloorDryingFunction | 381 | Screed drying (read only) | `350902031A0102` | — | UINT16 | 0 off · 1 functional · 2 before laying · 3 both | installer |
| FloorDryingDay | 382 | Screed drying day (read only) | `35090203120A02` | — | UINT16 |  | installer |
| FloorDryingTemperature | 383 | Screed drying temperature (read only) | `35090203130A02` | — | INT16 | °C | installer |

## Time programs (address 35, read and write) – 105 values

5 programs × 7 days × 3 slots. **Read**: `35090203` + `DS` + `PP` + `02`. **Write**: `35090304` + `DS` + `PP` + start + end. Not included in the command files.

| Program | PP | Weishaupt parameters |
|---|---|---|
| Heating 1 (`HP1`) | `14` | 121–127 |
| Heating 2 (`HP2`) | `15` | 131–137 |
| Heating 3 (`HP3`) | `16` | 141–147 |
| Domestic hot water (`WP`) | `17` | 151–157 |
| Circulation pump (`ZP`) | `1A` | 161–167 |

`DS` = day (tens) + slot (units: 1 → `0`, 2 → `1`, 3 → `2`): Monday `10 11 12`, Tuesday `20 21 22`, Wednesday `30 31 32`, Thursday `40 41 42`, Friday `50 51 52`, Saturday `60 61 62`, Sunday `70 71 72`.
Value: 2 bytes, start then end, in quarter hours since midnight (`18` = 06:00, `58` = 22:00, `60` = 24:00).
Example, HP3, Wednesday, slot 2: read `35090203311602`.

## Addresses 08 (combustion controller) and f6 – read only

No write definition in the source. Read: `ZZ PBSB NN ID`.

| Data | Raw command | Note |
|---|---|---|
| Statistic1: burner hours since service + SCOT errors | `08500067B2A3` | read once per hour |
| Statistic2: signal, supply, CRC and stopped-fan errors | `0850006BB2AF` | |
| Statistic3: fan, PWM pump, gas valves, gas pressure, DHW turbine | `0850007FB2BB` | |
| Statistic4: outside / DHW / flue gas / boiler sensors, H2 shutdown, flame simulation | `08500003B2C7` | |
| Statistic5: flame loss, no flame formation | `08500017B2D3` | |
| Statistic6: STW, operating hours of the day, number of power-ups | `0850001BB2DF` | |
| Fan speed (setpoint / measured) | `085000BC1162016511700174` | multiply by 60 |
| User setpoints of the controller | `085000C1623D` | |
| Heat demand circuit 1 | `f650005F03BB` | |
| System setpoint / system DHW setpoint | `f650002703C3` · `f6500033016F` | |
| **State broadcast** (phase, flags, load, flow, flue gas, DHW, outside, setpoint) | `fe500a0d` | 13 bytes, passive; positions 2 to 13 |
