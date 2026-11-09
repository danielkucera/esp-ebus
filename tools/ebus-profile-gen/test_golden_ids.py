#!/usr/bin/env python3
"""Golden id/wid/position assertions for the ebus-profile generator.

Verifies resolved read/write addressing of representative commands against
the archived ebusd CSV ground truth (concatenation model: template PBSB +
base D bytes + member ext), BI byte-grouping (consecutive BI0..BI7 runs
collapse to one UINT8 field carrying a `bits` name->bit map), write-only
commands with an empty id, 1-based byte positions of fields, and composite
expansion field shapes (plain models → positioned leaves). Run from the
repo root:

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
    """Assert read/write addressing for a command against ground truth.

    Entries carry the split schema (pbsb/dx, wpbsb/wdx); assertions still
    speak in concatenated id/wid hex so the archived-CSV constants stay
    byte-identical to the pre-split golden file.
    """
    global _checks
    _checks += 1
    entries = by_name.get(name)

    def _read_id(e: Dict[str, Any]) -> str:
        return (e.get("pbsb") or "") + (e.get("dx") or "")

    def _write_id(e: Dict[str, Any]) -> str:
        return (e.get("wpbsb") or "") + (e.get("wdx") or "")

    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        if wid_hex is None:
            assert all(
                _read_id(e) == id_hex and not _write_id(e) for e in entries
            ), f"{name}: expected id={id_hex!r} read-only, got " + str(
                [(_read_id(e), _write_id(e)) for e in entries]
            )
        else:
            assert all(
                _read_id(e) == id_hex and _write_id(e) == wid_hex
                for e in entries
            ), f"{name}: expected id={id_hex!r} wid={wid_hex!r}, got " + str(
                [(_read_id(e), _write_id(e)) for e in entries]
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
            f"got {[(e.get('pbsb'), e.get('dx')) for e in by_name[name]]}"
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


def expect_positions(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, positions: List[int]
) -> None:
    """Assert 1-based byte positions of a command's fields.

    Positions are data-part byte offsets (firmware: field_pos = position-1),
    so successors of a multi-byte field shift accordingly.
    """
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        for e in entries:
            got = [f["position"] for f in e["fields"]]
            assert got == positions, (
                f"{name}: expected positions={positions}, got {got}"
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_fields(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, field_names: List[str]
) -> None:
    """Assert the exact field-name list of a command (expansion shape)."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        for e in entries:
            got = [f["name"] for f in e["fields"]]
            assert got == field_names, (
                f"{name}: expected fields={field_names}, got {got}"
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_bits(
    by_name: Dict[str, List[Dict[str, Any]]],
    name: str,
    field_name: str,
    bits: Dict[str, int],
) -> None:
    """Assert the `bits` map of a byte-grouped (BI0..BI7) field."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        for e in entries:
            got = {
                f["name"]: f.get("bits")
                for f in e["fields"]
                if "bits" in f
            }
            assert got.get(field_name) == bits, (
                f"{name}: expected bits[{field_name!r}]={bits}, "
                f"got {got.get(field_name)}"
            )
            bits_field = next(
                (f for f in e["fields"] if f["name"] == field_name), None
            )
            assert bits_field is not None and (
                bits_field.get("ha_profile") == "binary_sensor"
            ), (
                f"{name}: bits field {field_name!r} must carry "
                f"ha_profile=binary_sensor, got "
                f"{bits_field.get('ha_profile') if bits_field else None!r}"
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
    expect(hcmode, "set_mode", "b51000", "b51000")
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
    expect(vd4, "switch_relays", "b5090d2700", "b5090e2700")
    expect(vd4, "actual_digital_inputs", "b5090d3a00", "b5090e3a00")

    # 08.ehp: concat ids, imported models, phase NOT gated.
    ehp = entries_for("src/vaillant/08.ehp.tsp")
    expect(ehp, "comp_starts_hwc", "b5090da800")
    expect(ehp, "phase_status", "b5090d8800")
    expect(ehp, "date_time", "b50400")
    expect(ehp, "iotest", "", "b50602")
    expect(ehp, "clearerrorhistory", "", "b5030201")
    expect(ehp, "set_mode", "b51000", "b51000")

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

    # Byte positions: 1-based data-part offsets, not field ordinals —
    # successors of multi-byte fields shift (char3@2 → char4@5 → d2b@9).
    expect_positions(hcmode, "date_time", [1, 2, 5, 9])
    expect_positions(broadcast, "vdatetime", [1, 4])
    expect_positions(e7c, "monday_heating_temp", [1, 3, 5, 7, 9, 11, 13])

    # Composite expansion: plain models become positioned leaf sub-fields
    # (full field path joined with '_'); consecutive BI0..BI7 runs collapse
    # into one UINT8 field carrying the `bits` name->bit map.
    expect_fields(
        errors, "currenterror",
        ["value_error", "value_error_1", "value_error_2",
         "value_error_3", "value_error_4"],
    )
    expect_positions(errors, "currenterror", [1, 3, 5, 7, 9])
    expect_fields(
        errors, "errorhistory",
        ["index", "errorhistory_status", "errorhistory_time",
         "errorhistory_date", "errorhistory_error"],
    )
    expect_positions(errors, "errorhistory", [1, 2, 3, 5, 8])
    expect_fields(
        t392, "cc_timer__monday",
        ["value_slot1_slot_from", "value_slot1_slot_to",
         "value_slot1_slot_1_from", "value_slot1_slot_1_to",
         "value_slot1_slot_2_from", "value_slot1_slot_2_to",
         "value_daysel"],
    )
    expect_positions(t392, "cc_timer__monday", [1, 2, 3, 4, 5, 6, 7])
    expect_fields(ehp, "phase_status", ["value_phase"])
    expect_bits(
        ehp, "phase_status", "value_phase",
        {"value_phase": 0, "value_phase_1": 1, "value_phase_2": 2},
    )
    expect_fields(
        hcmode, "set_mode",
        ["hcmode", "flowtempdesired", "hwctempdesired", "hwcflowtempdesired",
         "ign", "disablehc", "ign_1", "remoteControlHcPump"],
    )
    expect_positions(hcmode, "set_mode", [1, 2, 3, 4, 5, 6, 7, 8])
    expect_bits(
        hcmode, "set_mode", "disablehc",
        {"disablehc": 0, "disablehwctapping": 1, "disablehwcload": 2},
    )
    expect_bits(
        hcmode, "set_mode", "remoteControlHcPump",
        {"remoteControlHcPump": 0, "releaseBackup": 1, "releaseCooling": 2},
    )
    expect_fields(
        ehp, "set_mode",
        ["hcmode", "flowtempdesired", "hwctempdesired", "hwcflowtempdesired",
         "ign", "disablehc", "ign_1", "remoteControlHcPump"],
    )
    expect_fields(vd4, "switch_relays", ["bi"])
    expect_positions(vd4, "switch_relays", [1])
    expect_bits(vd4, "switch_relays", "bi", {"bi": 0, "bi_1": 1})
    expect_fields(vd4, "actual_digital_inputs", ["bi"])
    expect_positions(vd4, "actual_digital_inputs", [1])
    expect_bits(vd4, "actual_digital_inputs", "bi", {"bi": 0, "bi_1": 1})

    if _failures:
        print(f"FAIL: {_failures.__len__()}/{_checks} checks failed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {_checks} golden id checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
