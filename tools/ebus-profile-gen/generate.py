#!/usr/bin/env python3
"""Generate ebus profile/command JSON from a TypeSpec (.tsp) file."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, List

# ensure local imports work when run directly
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import resolver
import tsp_parser
import mapper
import emitter
import validate
from convlog import ConversionLog


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
    p.add_argument(
        "--log",
        help="path for the structured conversion log (default: <out-generated>/<tsp_stem>.conversion.jsonl)",
    )
    p.add_argument("--no-log", dest="log", action="store_const", const="")
    p.add_argument(
        "--log-level",
        choices=["debug", "info", "warn", "error"],
        default="info",
        help="minimum severity written to the conversion log (default: info)",
    )
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

    # Derive output filenames from tsp basename (e.g. 08.ehp.tsp -> 08.ehp.json)
    tsp_stem = os.path.splitext(os.path.basename(args.tsp_file))[0]

    # Determine output paths
    gen_dir = args.out_generated or os.path.join(
        repo_root, "tools", "ebus-profile-gen", "generated"
    )
    profiles_path = args.out_profiles or os.path.join(gen_dir, f"{tsp_stem}.profiles.json")
    commands_path = args.out_commands or os.path.join(gen_dir, f"{tsp_stem}.json")

    # Structured conversion log
    log_path = args.log
    if log_path is None:
        log_path = os.path.join(gen_dir, f"{tsp_stem}.conversion.jsonl")
    log = ConversionLog(path=log_path, level=args.log_level)

    res = resolver.IncludeResolver(ebusd_root)
    try:
        files = res.resolve(tsp_rel)
    except FileNotFoundError as e:
        print(f"error: tsp file not found: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: resolving tsp includes failed: {e}", file=sys.stderr)
        return 2

    parser = tsp_parser.TspParser(files, log=log)
    raw = parser.parse()

    fam = mapper.build_profiles_and_commands(raw, log=log)

    # Derive key prefix: strip leading "NN." from the tsp stem (e.g.
    # 08.ehp → ehp_, 05.vd6 → vd6_, 06.pms → pms_), then add underscore.
    name = re.sub(r"^\d+\.?", "", tsp_stem)
    default_prefix = f"{name.lower()}_" if name else ""
    key_prefix = args.key_prefix if args.key_prefix is not None else default_prefix

    # Convert to flat entries
    profiles_entries = mapper.profiles_to_flat_entries(fam, log=log)
    commands_entries = mapper.commands_to_flat_entries(
        fam, key_prefix=key_prefix, aliases=raw.get("aliases", {}), log=log
    )

    # Emit raw generated output (gitignored)
    em = emitter.Emitter(profiles_path, commands_path)
    em.emit_profiles(profiles_entries)
    em.emit_commands(commands_entries)

    log.info("emit", "profiles written", path=profiles_path, count=len(profiles_entries))
    log.info("emit", "commands written", path=commands_path, count=len(commands_entries))

    # Write the conversion log and print a summary.
    log.write()
    _print_summary(log, log_path)

    if args.validate:
        issues: List[str] = []
        for entry in profiles_entries:
            issues.extend(validate.check_no_trailing_underscores(entry))
        issues.extend(validate.check_no_trailing_underscores(commands_entries))
        issues.extend(
            validate.validate_log(log.records, profiles_entries, commands_entries)
        )
        if issues:
            for i in issues:
                print(f"validation: {i}", file=sys.stderr)
            return 1

    print(f"wrote {len(profiles_entries)} profiles to {profiles_path}")
    print(f"wrote {len(commands_entries)} commands to {commands_path}")
    return 0


def _print_summary(log: ConversionLog, log_path: str) -> None:
    summary = log.summary()
    by_sev = summary["by_severity"]
    by_class = summary["by_classification"]
    print(
        "conversion log: "
        f"{summary['total']} records "
        f"(info={by_sev['info']} warn={by_sev['warn']} error={by_sev['error']}) "
        f"-> {log_path}",
        file=sys.stderr,
    )
    if by_class:
        print(
            "classifications: "
            + ", ".join(f"{k}={v}" for k, v in sorted(by_class.items())),
            file=sys.stderr,
        )
    for severity in ("error", "warn"):
        records = [r for r in log.records if r.get("severity") == severity]
        if not records:
            continue
        print(f"{severity} ({len(records)}):", file=sys.stderr)
        for rec in records[:10]:
            target = (
                rec.get("input_type")
                or rec.get("name")
                or rec.get("scalar")
                or rec.get("model")
                or ""
            )
            print(f"  [{rec.get('stage')}] {rec.get('reason')} — {target}", file=sys.stderr)
        if len(records) > 10:
            print(f"  ... and {len(records) - 10} more (see {log_path})", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
