# ebus-profile-gen

Dev-only generator that reads ebusd-configuration TypeSpec (.tsp) files (including includes/templates) and emits raw JSON output into `tools/ebus-profile-gen/generated/` (gitignored). The user then saves/curates profiles and commands where they want via `--out-profiles` and `--out-commands`.

## Purpose

Read ebusd-configuration `.tsp` files for a device, parse registers/fields, group into canonical profiles (to deduplicate), and emit JSON shaped to our firmware constraints.

## Constraints

- **No trailing underscores** in any emitted JSON field names
- **Heap-free shape**: values must fit FixedString/StaticVector assumptions (ProfileFS<24> etc.). Avoid emitting runtime strings we don't need
- **write id semantics**: commands that are writable must have `wid` per our decision (derive from tsp write semantics); NN is derived at runtime
- **Deterministic**: sort keys, stable formatting to keep diffs readable
- **Dev-only**: never linked into PlatformIO build, no runtime dependency in firmware

## Layout

```
tools/ebus-profile-gen/
├── README.md                    # this file
├── __init__.py
├── generate.py                  # generator entry point
├── resolver.py                  # include/template resolution
├── tsp_parser.py                # minimal TypeSpec subset parser
├── model.py                     # internal IR (FieldIR/ProfileIR/CommandIR/FamilyIR)
├── mapper.py                    # tsp → our schema + profile grouping
├── emitter.py                   # write raw generated JSON
├── validate.py                  # enforce constraints
├── requirements.txt             # dev deps (stdlib by default)
├── ebusd-configuration/         # ebusd-configuration repo (checkout or symlink — gitignored)
├── ebus-typespec/               # ebus-typespec library (checkout or symlink — gitignored)
    └── generated/                   # raw generator output (gitignored)
        ├── <tsp_stem>.profiles.json # flat data profile entries (data_profiles.json schema)
        └── <tsp_stem>.json          # command entries (config/simulation.json schema)
```

### Input Repositories

#### ebusd-configuration (input)

This directory holds the ebusd-configuration repository (TypeSpec `.tsp` files). It is **gitignored** — you check it out or link it yourself:

```bash
# Option 1: check out directly
git clone https://github.com/john30/ebusd-configuration.git tools/ebus-profile-gen/ebusd-configuration

# Option 2: link to an existing checkout
ln -s /path/to/ebusd-configuration tools/ebus-profile-gen/ebusd-configuration
```

The CLI reads `.tsp` files from here via `--ebusd-root` (defaults to `tools/ebus-profile-gen/ebusd-configuration`).

#### ebus-typespec (input)

This directory holds the ebus-typespec TypeSpec library that provides the type definitions, decorators, and templates used by ebusd-configuration. It is **gitignored** — you check it out or link it yourself:

```bash
# Option 1: check out directly
git clone https://github.com/john30/ebus-typespec tools/ebus-profile-gen/ebus-typespec

# Option 2: link to an existing checkout
ln -s /path/to/ebus-typespec tools/ebus-profile-gen/ebus-typespec
```

The parser uses type definitions from this library (e.g., `Ebus.Num.UCH`, `Ebus.Num.D2C`, `Ebus.Str.IGN`, etc.) to properly resolve field types in the `.tsp` files.

### Output: `generated/` (raw, gitignored)

By default the CLI writes raw generated output to `tools/ebus-profile-gen/generated/`, using the tsp basename (e.g. `08.ehp.tsp` → `08.ehp.profiles.json` / `08.ehp.json`):

- `<tsp_stem>.profiles.json` — flat entries `{name, datatype, unit, divider, digits, min, max}` matching the `profiles/data_profiles.json` schema. These can be copied to `profiles/data_profiles_user.json` (the overlay) at compile time.
- `<tsp_stem>.json` — command entries matching `config/simulation.json` schema:
  `{key, name, zz, id, [nn], wid, interval, master, fields: [{name, profile, position, ha_profile}]}`.
  `wid` is omitted for read-only commands, `interval` defaults to 0 (passive only), `master` defaults to false, `ha_profile` is empty — fill these in by hand.
  `zz` is the destination byte; `id` is the read id `PB SB Dx...` (2-6 bytes) and the read NN is derived as `len(id)-2` unless an explicit `nn` override is given; `wid` is the write id with the same layout (the runtime NN also counts the appended value bytes).
  `key` is prefixed (default: derived from tsp filename, e.g. `08.ehp.tsp` → `ehp_8d`).
  Use `--key-prefix` to override the default prefix.

This directory is **gitignored** — raw output never gets committed by accident.

### Saving profiles and commands (manual, on purpose)

Profiles are **not** auto-merged into `profiles/`. You add them on purpose by hand:

```bash
# Generate raw output to generated/
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp

# Output: generated/08.ehp.profiles.json and generated/08.ehp.json

# Then copy profiles you want to keep into the overlay (manual step)
cp tools/ebus-profile-gen/generated/08.ehp.profiles.json profiles/data_profiles_user.json

# Commands: save wherever you want, upload to adapter later
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --out-commands config/private/vaillant-08-ehp-commands.json

# Custom key prefix
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --key-prefix vaillant_ \
  --out-commands config/private/vaillant-08-ehp-commands.json
```

At compile time, `scripts/generate_data_profiles.py` merges `profiles/data_profiles.json` + `profiles/data_profiles_user.json` into `include/app/data_profile_gen.hpp`.

## Usage

```bash
# From explicit tsp path (relative to ebusd-root)
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp

# Save outputs to custom locations
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --out-profiles my-profiles.json \
  --out-commands my-commands.json

# Custom key prefix
python3 tools/ebus-profile-gen/generate.py \
  src/vaillant/08.ehp.tsp \
  --key-prefix vaillant_ \
  --out-commands my-commands.json
```

## Current Status and Known Issues

**Status: Parser and command format fixed, profile mapping needs refinement**

### Working
- TypeSpec file parsing (including models with explicit fields)
- Template model detection (ReadonlyRegister, ServiceUpdateRegister, etc.)
- Type mapping from TypeSpec types to project datatypes (partial)
- JSON output generation
- Decorator capture for all models (including those with bodies)
- Command format generation (ZZ PB SB NN Dx) with correct MF from aliases

### Known Issues

1. **Command key generation**
   - Currently: `ehp_001`, `ehp_002`, ... (sequential with prefix)
   - Expected: Simple hex or decimal strings like `"09"`, `"32"`, `"a8"`
   - Fix needed: Use `ext_pb` from decorator as the key, formatted as hex

2. **Profile name mapping**
   - Currently: Using basic type names like `"uint32"`, `"int16"`
   - Expected: Using existing profile names from `profiles/data_profiles.json` like `"data2c_celsius"`, `"uint32_hour"`
   - Fix needed: Map TypeSpec scalar types (cntstarts, tempsensor, presssensor, etc.) to appropriate profile names

3. **Command name formatting**
   - Currently: snake_case like `"comp_starts_hwc"`
   - Expected: Hierarchical format like `"Compressor/Starts_HWC"` or `"Buffer/Middle_Temperature"`
   - Fix needed: Convert names to use slash/underscore hierarchy

4. **Data profile fields**
   - Currently: Basic fields with no min/max values
   - Expected: Populate divider, digits, min, max from scalar definitions and @step decorators
   - Fix needed: Extract and apply metadata from TypeSpec scalars and decorators

### Next Steps

The critical parser bug (double increment in `_parse_model_inline`) has been fixed. All models, including those with explicit field bodies, now have their decorators properly captured.

Remaining work focuses on the mapper to improve output quality:
1. Fix command key generation to use `ext_pb` from decorators
2. Correct the `read_cmd` format to include proper MF, PB, SB values
3. Improve profile name mapping to use existing profile names
4. Enhance command name formatting to match the hierarchical convention
5. Populate data profile metadata (divider, digits, min, max) from TypeSpec definitions

Defaults:
- `--ebusd-root`: `tools/ebus-profile-gen/ebusd-configuration`
- `--ebus-typespec-root`: `tools/ebus-profile-gen/ebus-typespec`
- `--key-prefix`: derived from tsp filename (e.g. `08.ehp.tsp` → `ehp_`)
- `--out-generated`: `tools/ebus-profile-gen/generated/`
- `--validate`: true (fail on constraint violations)
- `--log`: `<out-generated>/<tsp_stem>.conversion.jsonl` (write; gitignored)
- `--log-level`: `info` (min severity written; `debug|info|warn|error`)
- `--no-log`: disable conversion log writing

## Conversion log (`generated/<tsp_stem>.conversion.jsonl`)

The generator emits a structured JSONL conversion log alongside the two output
files. One record per decision (parse/resolve/template/profile/command/emit),
so you can debug *what* was converted and *why* something was skipped or
defaulted:

```
{"stage":"parse","severity":"warn","reason":"scalar redefined ...","scalar":"cntstarts","line":8,...}
{"stage":"resolve","severity":"warn","reason":"type has no ebusd→library mapping ...","input_type":"phaseok","datatype":"phaseok",...}
{"stage":"command","severity":"warn","reason":"zz+id collides ...","zz":"08","id":"b5090d0800","name":"source","duplicate":...}
```

Each record carries `stage`, `severity`, `reason`, `classification` (`native` /
`profile` / `unsupported` / `defaulted`), `action`, plus context
(`model`, `field`, `scalar`, `key`, `name`, `zz`, `id`, `profile`,
`line`, `namespace`, `source`). The CLI prints a severity summary plus the
top warnings to stderr, with the full detail in the JSONL file.

Use `--log-level warn` to suppress debug noise, `--no-log` to skip writing the
file, or `--log <path>` to override the location. Validation (`--validate`)
fails on defaulted/unsupported type mappings, emitted template definitions,
zz+id collisions, writable commands without a `wid`, referenced
profiles that do not exist, and trailing underscores — treating the generator
output as ready to use only when none of those are present.

