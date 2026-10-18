#!/usr/bin/env python3
"""Generate ebus profile/command JSON from a TypeSpec (.tsp) file."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

# ensure local imports work when run directly
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import resolver
import tsp_parser
import mapper
import emitter
import validate


def main() -> int:
    p = argparse.ArgumentParser(description="ebus-profile-configuration TSP → data profiles generator")
    p.add_argument("--ebusd-root", default="tools/ebus-profile-gen/ebusd-configuration")
    p.add_argument("--ebus-typespec-root", default="tools/ebus-profile-gen/ebus-typespec")
    p.add_argument("tsp_file", help="tsp path relative to ebusd-root or absolute")
    p.add_argument(
        "--key-prefix",
        help="key prefix for command keys (default: derived from tsp filename, e.g. 08.ehp.tsp → ehp_)",
    )
    p.add_argument(
        "--out-generated",
        help="output dir for both raw generated files (default: tools/ebus-profile-gen/generated/)",
    )
    p.add_argument("--out-profiles", help="explicit path for generated profiles JSON")
    p.add_argument("--out-commands", help="explicit path for generated commands JSON")
    p.add_argument("--validate", action="store_true", default=True)
    p.add_argument("--no-validate", dest="validate", action="store_false")
    args = p.parse_args()

    repo_root = os.getcwd()
    ebusd_root = args.ebusd_root
    if not os.path.isabs(ebusd_root):
        ebusd_root = os.path.abspath(os.path.join(repo_root, ebusd_root))
    ebus_typespec_root = args.ebus_typespec_root
    if not os.path.isabs(ebus_typespec_root):
        ebus_typespec_root = os.path.abspath(os.path.join(repo_root, ebus_typespec_root))

    tsp_rel = args.tsp_file
    if not tsp_rel:
        print("error: need tsp file", file=sys.stderr)
        return 2

    # validate tsp exists
    tsp_abs_check = tsp_rel
    if not os.path.isabs(tsp_abs_check):
        cand1 = os.path.abspath(os.path.join(ebusd_root, tsp_rel))
        cand2 = os.path.abspath(os.path.join(repo_root, tsp_rel))
        if os.path.exists(cand1):
            tsp_abs_check = cand1
        elif os.path.exists(cand2):
            tsp_abs_check = cand2
        else:
            tsp_abs_check = cand1
    if not os.path.exists(tsp_abs_check):
        print(f"error: tsp file not found: {tsp_rel}", file=sys.stderr)
        return 2

    res = resolver.IncludeResolver(ebusd_root)
    try:
        files = res.resolve(tsp_rel)
    except FileNotFoundError as e:
        print(f"error: tsp file not found: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: resolving tsp includes failed: {e}", file=sys.stderr)
        return 2

    parser = tsp_parser.TspParser(files)
    raw = parser.parse()

    fam = mapper.build_profiles_and_commands(raw)

    # Derive output filenames from tsp basename (e.g. 08.ehp.tsp -> 08.ehp.json)
    tsp_stem = os.path.splitext(os.path.basename(args.tsp_file))[0]

    # Derive key prefix: strip leading digits/dots from stem, add underscore
    # e.g. 08.ehp → ehp_, 08.bai → bai_
    import re

    stem_match = re.search(r"([a-zA-Z]+)$", tsp_stem)
    default_prefix = f"{stem_match.group(1).lower()}_" if stem_match else ""
    key_prefix = args.key_prefix if args.key_prefix is not None else default_prefix

    # Determine output paths
    gen_dir = args.out_generated or os.path.join(
        repo_root, "tools", "ebus-profile-gen", "generated"
    )
    profiles_path = args.out_profiles or os.path.join(gen_dir, f"{tsp_stem}.profiles.json")
    commands_path = args.out_commands or os.path.join(gen_dir, f"{tsp_stem}.json")

    # Convert to flat entries
    profiles_entries = mapper.profiles_to_flat_entries(fam)
    commands_entries = mapper.commands_to_flat_entries(fam, key_prefix=key_prefix, aliases=raw.get("aliases", {}))

    # Emit raw generated output (gitignored)
    em = emitter.Emitter(profiles_path, commands_path)
    em.emit_profiles(profiles_entries)
    em.emit_commands(commands_entries)

    if args.validate:
        issues: List[str] = []
        for entry in profiles_entries:
            issues.extend(validate.check_no_trailing_underscores(entry))
        try:
            with open(commands_path) as f:
                cobj = json.load(f)
            issues.extend(validate.check_no_trailing_underscores(cobj))
        except Exception as e:
            issues.append(f"failed to validate commands: {e}")
        if issues:
            for i in issues:
                print(f"validation: {i}", file=sys.stderr)
            return 1

    print(f"wrote {len(profiles_entries)} profiles to {profiles_path}")
    print(f"wrote {len(commands_entries)} commands to {commands_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
