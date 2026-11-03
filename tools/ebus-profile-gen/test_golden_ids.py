#!/usr/bin/env python3
"""Golden id/wid assertions for the ebus-profile generator.

Verifies resolved read/write addressing of representative commands against
the archived ebusd CSV ground truth (concatenation model: template PBSB +
base D bytes + member ext), the BI bitfield gate, and write-only commands
with an empty id. Run from the repo root:

    python3 tools/ebus-profile-gen/test_golden_ids.py
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mapper  # noqa: E402
import resolver  # noqa: E402
import tsp_parser  # noqa: E402
from convlog import NULL_LOG  # noqa: E402

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_EBUSD_ROOT = os.path.join(_REPO_ROOT, "tools", "ebus-profile-gen", "ebusd-configuration")
_TYPESPEC_ROOT = os.path.join(_REPO_ROOT, "tools", "ebus-profile-gen", "ebus-typespec")

_failures: List[str] = []
_checks = 0


def entries_for(tsp_rel: str) -> Dict[str, List[Dict[str, Any]]]:
    """Run the generate.py pipeline in-process and index entries by name."""
    res = resolver.IncludeResolver(_EBUSD_ROOT, _TYPESPEC_ROOT)
    files = res.resolve(tsp_rel)
    raw = tsp_parser.TspParser(files).parse()
    fam = mapper.build_profiles_and_commands(raw, log=NULL_LOG)
    stem = os.path.splitext(os.path.basename(tsp_rel))[0]
    name = re.sub(r"^\d+\.?", "", stem)
    prefix = f"{name.lower()}_" if name else ""
    entries = mapper.commands_to_flat_entries(
        fam, key_prefix=prefix, aliases=raw.get("aliases", {}), log=NULL_LOG
    )
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        by_name.setdefault(e["name"], []).append(e)
    return by_name


def expect(
    by_name: Dict[str, List[Dict[str, Any]]],
    name: str,
    id_hex: Optional[str],
    wid_hex: Optional[str] = None,
) -> None:
    """Assert id/wid for a command (wid_hex=None asserts read-only)."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        if wid_hex is None:
            assert all(
                e.get("id") == id_hex and not e.get("wid") for e in entries
            ), f"{name}: expected id={id_hex!r} read-only, got " + str(
                [(e.get("id"), e.get("wid")) for e in entries]
            )
        else:
            assert all(
                e.get("id") == id_hex and e.get("wid") == wid_hex
                for e in entries
            ), f"{name}: expected id={id_hex!r} wid={wid_hex!r}, got " + str(
                [(e.get("id"), e.get("wid")) for e in entries]
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_absent(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, why: str = ""
) -> None:
    global _checks
    _checks += 1
    try:
        assert not by_name.get(name), (
            f"{name}: expected absent{(' (' + why + ')') if why else ''}, "
            f"got {[(e.get('id'), e.get('wid')) for e in by_name[name]]}"
        )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_zz(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, zz_hex: str
) -> None:
    """Assert the destination byte for a command (archived ZZ column)."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        assert all(e.get("zz") == zz_hex for e in entries), (
            f"{name}: expected zz={zz_hex!r}, got "
            + str([e.get("zz") for e in entries])
        )
    except AssertionError as exc:
        _failures.append(str(exc))


def main() -> int:
    # hcmode_inc: @inherit chains, BI gate, no fabricated 0x0d.
    hcmode = entries_for("src/vaillant/hcmode_inc.tsp")
    expect(hcmode, "date_time", "b50400")
    expect(hcmode, "status16", "b50416")
    expect(hcmode, "status01", "b51101")
    expect(hcmode, "status02", "b51102")
    expect(hcmode, "status", "b51103")
    expect(hcmode, "status_cir_pump", "b51200", "b51200")
    expect(hcmode, "wm", "", "b505")
    expect_absent(hcmode, "set_mode", "BI bitfield gate")
    expect_absent(hcmode, "rm", "inherited via date_time")

    # iotesthp_inc: write-only commands carry wid only.
    iotesthp = entries_for("src/vaillant/iotesthp_inc.tsp")
    expect(iotesthp, "iotest", "", "b50602")
    expect(iotesthp, "ioteststop", "", "b50601")
    expect(iotesthp, "rm", "b504")
    expect(iotesthp, "wm", "", "b505")

    # errors_inc: @base D-byte tails, write-only clear.
    errors = entries_for("src/vaillant/errors_inc.tsp")
    expect(errors, "currenterror", "b5030001")
    expect(errors, "errorhistory", "b5030101")
    expect(errors, "clearerrorhistory", "", "b5030201")

    # 05.vd4: wid inheritance through is-template flatten, BI gate.
    vd4 = entries_for("src/vaillant/05.vd4.tsp")
    expect(vd4, "enable_monitoring", "b5090d0100", "b5090e0100")
    expect_absent(vd4, "switch_relays", "BI bitfield gate")
    expect_absent(vd4, "actual_digital_inputs", "BI bitfield gate")

    # 08.ehp: concat ids, imported models, phase NOT gated.
    ehp = entries_for("src/vaillant/08.ehp.tsp")
    expect(ehp, "comp_starts_hwc", "b5090da800")
    expect(ehp, "phase_status", "b5090d8800")
    expect(ehp, "date_time", "b50400")
    expect(ehp, "iotest", "", "b50602")
    expect(ehp, "clearerrorhistory", "", "b5030201")
    expect_absent(ehp, "set_mode", "BI bitfield gate (imported)")

    # broadcast: b/wi write side shares the base tail; archived ZZ is FE
    # (alias BROADCAST = Targets.broadcast resolves via union constants).
    broadcast = entries_for("src/vaillant/broadcast.tsp")
    expect(broadcast, "vdatetime", "b51600", "b51600")
    expect(broadcast, "outsidetemp", "b51601")
    expect(broadcast, "hwc_status", "b50527")
    expect(broadcast, "load", "b50506")
    expect_zz(broadcast, "vdatetime", "fe")
    expect_zz(broadcast, "outsidetemp", "fe")
    expect_zz(hcmode, "date_time", "08")

    # 15.e7c: is-template + @ext variadic ids/wids.
    e7c = entries_for("src/vaillant/15.e7c.tsp")
    expect(e7c, "heating_schedule_enable", "b5090d0200", "b5090e0200")
    expect(e7c, "monday_heating_time", "b5090d0500", "b5090e0500")

    # 15.392: timer PBSB (B515) and per-direction PBSB (r B504 / w B505).
    t392 = entries_for("src/vaillant/15.392.tsp")
    expect(t392, "cc_timer__monday", "b5150002", "b5150002")
    expect(t392, "setpoints__monday", "b5041901", "b5052e01")

    if _failures:
        print(f"FAIL: {_failures.__len__()}/{_checks} checks failed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {_checks} golden id checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
