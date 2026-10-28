"""The compare contract as implemented by ``degelmann.deltarecon``: compare result, signature table, record.

The runs come from the stub engine of ``conftest.py``, so the tests need no
calculation engine. The expected deviation list is computed in ``conftest.py``, from the
two exports, with ``rounded`` and ``deviates`` there: an oracle that
shares no code with ``degelmann/deltarecon/compare.py``. Its rule is built like that of the core,
so it finds faults of wiring and not a shared misreading of the contract. Against that
stand the cases with an answer worked out by hand, and an oracle of another construction
that rounds with fractions.
"""
from __future__ import annotations

import json
import random
import shutil
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.compare import (COMPARE_SCHEMA, CheckedRun, compare, compare_runs, exceeds, no_deviation,
                                parameter_diff, read_tolerance, round_half_away)
from degelmann.deltarecon.export import read_deviations
from degelmann.deltarecon.documents import RECORD_SCHEMA, Rejection, document_bytes, schema_errors, sha256_file
from degelmann.deltarecon.run import UsageError
from degelmann.deltarecon.signature import render_table, signature_table

from conftest import (EXACT, EXAMPLES, POINTS, RECORD_ID, StubEngine, StubSession, compare_request, deviates,
                      deviation_rows, expected_deviations, folder_hashes, projection_periods, rehash, roles,
                      rounded, run_side, stored, without_volatile, written_under)

COUNT, CASH = "Anzahl Verträge", "Netto-Cashflow"
OUTPUTS = ["compare.deviations.csv", "compare.result.json", "compare.run-record.json", "signature-table.json"]
HEADER_ONLY = "model_point_id,period,quantity,left,right\n"


def entry(upper=(0, 0), lower=(0, 0), decimals=None) -> dict:
    result = {"upper": {"abs_tol": upper[0], "rel_tol": upper[1]},
              "lower": {"abs_tol": lower[0], "rel_tol": lower[1]}}
    if decimals is not None:
        result["decimals"] = decimals
    if decimals is not None or any(upper) or any(lower):
        result["derivation"] = "Synthetic test profile."
    return result


def written(world: Path) -> list[str]:
    return sorted(p.name for p in world.iterdir() if p.is_file() and p.name != "compare.request.json")


def assert_record(world: Path, outcome: str, table: bool) -> dict:
    """The run record of the comparison lists its documents with their hashes."""
    record = stored(world / "compare.run-record.json")
    assert not schema_errors(record, RECORD_SCHEMA)
    assert record["procedure"] == {"type": "compare"} and record["outcome"] == outcome
    assert RECORD_ID.fullmatch(record["record_id"]) and record["parameters"] == []
    assert roles(record["inputs"]) == {"request": "compare.request.json"}
    expected = {"result": "compare.result.json"}
    if table:
        expected["deviations"] = "compare.deviations.csv"
        expected["signature_table"] = "signature-table.json"
    assert roles(record["outputs"]) == expected
    for item in record["inputs"] + record["outputs"]:
        assert sha256_file(world / item["artifact"]["path"]) == item["artifact"]["sha256"]
    return record


# --- compare, deviations and none ---------------------------------------------------

# The right release moves four model points by different amounts.
POINTS_MOVED = ("id,first,last,base\nMP-B,0,2,2.004\nMP-A,12,13,1.75\nMP-C,0,0,1.5e-05\nMP-D,3,4,1e16\n"
                "MP-F,0,3,0.5\n")
POINTS_LEFT = POINTS + "MP-F,0,3,0.6\n"

PROFILES = {
    "exact": {},
    "explicit-zero": {COUNT: entry(), CASH: entry()},
    "absolute": {CASH: entry(upper=(0.25, 0), lower=(0.25, 0))},
    "relative": {COUNT: entry(upper=(0, 0.01), lower=(0, 0.2)), CASH: entry(upper=(0, 0.15))},
    "decimals": {COUNT: entry(decimals=2), CASH: entry(decimals=1)},
    "asymmetric": {COUNT: entry(upper=(1, 0)), CASH: entry(lower=(1, 0))},
    "wide": {COUNT: entry(upper=(1, 0), lower=(1, 0)), CASH: entry(upper=(10, 0), lower=(10, 0))},
}


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_compare_lists_every_deviating_coordinate_and_no_other(world, capsys, profile):
    per_quantity = PROFILES[profile]
    left, right = run_side(world, "left", POINTS_LEFT), run_side(world, "right", POINTS_MOVED)
    expected = expected_deviations(left.export_path, right.export_path, per_quantity)
    assert (profile == "wide") == (expected == [])
    before = folder_hashes(world)

    status = main(["compare", str(compare_request(world, per_quantity))])
    output = capsys.readouterr().out
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA)
    assert result["outcome"] == "compared" and result["compare_id"] == "compare-stub"
    assert result["deviations"] == {"path": "compare.deviations.csv",
                                    "sha256": sha256_file(world / "compare.deviations.csv")}
    assert deviation_rows(world / "compare.result.json") == expected
    assert result["deviating_model_points"] == sorted({d["model_point_id"] for d in expected})
    assert result["compared_coordinates"] == 24 and result["added"] == result["removed"] == []
    assert result["tolerance"] == {"per_quantity": per_quantity}
    assert result["left"] == {"run_id": "run-left", "release_label": "rel-left"}
    assert result["right"] == {"run_id": "run-right", "release_label": "rel-right"}
    assert result["time_basis"] == {"id": "policy_month"}
    assert [q["name"] for q in result["quantities"]] == [COUNT, CASH]

    # Exit status 0 only for "no deviation"; the table is written for every compared result.
    assert status == (1 if expected else 0)
    assert ("compare: no deviation above tolerance" in output) == (not expected)
    assert written(world) == OUTPUTS
    table = stored(world / "signature-table.json")
    assert not schema_errors(table, COMPARE_SCHEMA) and table["document"] == "signature_table"
    assert bool(table["rows"]) == bool(expected)
    record = assert_record(world, "compared", table=True)
    assert [r["label"] for r in record["releases"]] == ["rel-left", "rel-right"]
    for model_point_id in result["deviating_model_points"]:
        assert f"liability_cashflow / model point {model_point_id}:" in output
    # The runs are read, never written.
    assert {name: digest for name, digest in folder_hashes(world).items()
            if "/" in name} == {name: digest for name, digest in before.items() if "/" in name}


def test_the_same_values_show_no_deviation_and_an_empty_table(world, capsys):
    run_side(world, "left"), run_side(world, "right")
    assert main(["compare", str(compare_request(world))]) == 0
    assert "compare: no deviation above tolerance" in capsys.readouterr().out
    result = stored(world / "compare.result.json")
    assert result["outcome"] == "compared" and result["compared_coordinates"] == 16
    assert deviation_rows(world / "compare.result.json") == []
    assert (world / "compare.deviations.csv").read_text("utf-8") == HEADER_ONLY
    assert result["deviating_model_points"] == result["added"] == result["removed"] == []
    assert result["parameter_diff"] == []
    assert stored(world / "signature-table.json")["rows"] == []
    assert_record(world, "compared", table=True)


# --- boundary and rounding ----------------------------------------------------------


def one_point(base: str) -> str:
    return f"id,first,last,base\nMP-A,0,0,{base}\n"


def deviating_quantities(world: Path, left: str, right: str, per_quantity: dict) -> list[str]:
    """Compare two runs of one model point and one period whose two quantities hold ``left`` and ``right``."""
    for name in ("left", "right", "rel-left", "rel-right"):
        shutil.rmtree(world / name, ignore_errors=True)
    for name in OUTPUTS:
        (world / name).unlink(missing_ok=True)
    run_side(world, "left", one_point(left)), run_side(world, "right", one_point(right))
    compared = compare(compare_request(world, per_quantity))
    result = compared.result
    assert result["outcome"] == "compared" and result["compared_coordinates"] == 2
    listed = deviation_rows(compared.result_path)
    assert listed == compared.deviations
    return [deviation["quantity"] for deviation in listed]


def test_a_difference_equal_to_its_bound_is_no_deviation_and_the_bounds_are_not_symmetric(world):
    profile = {COUNT: entry(upper=(0.25, 0)), CASH: entry(lower=(0.25, 0))}
    # Right lies 0.25 above left: exactly on the upper bound of the count, beyond the zero one of the cash flow.
    assert deviating_quantities(world, "100", "100.25", profile) == [CASH]
    # The same two values, exchanged: the roles of upper and lower are exchanged with them.
    assert deviating_quantities(world, "100.25", "100", profile) == [COUNT]
    # Just beyond the bound.
    assert deviating_quantities(world, "100", "100.25000000000001", profile) == [COUNT, CASH]
    # A relative bound: 0.001 * 1201 = 1.201 covers a difference of 1, and 0.0005 * 1201 does not.
    relative = {COUNT: entry(upper=(0, 0.001), lower=(0, 0.001)), CASH: entry(upper=(0, 0.0005))}
    assert deviating_quantities(world, "1200", "1201", relative) == [CASH]
    # Exactly on a relative bound: 0.5 * max(1, 2) = 1.
    assert deviating_quantities(world, "1", "2", {COUNT: entry(upper=(0, 0.5)), CASH: entry(upper=(0, 0.25))}) \
        == [CASH]
    # The larger of the absolute and the relative part applies.
    assert deviating_quantities(world, "1", "2", {COUNT: entry(upper=(1, 0.1)), CASH: entry(upper=(0.1, 0.5))}) \
        == []
    # With all parts at zero every difference deviates.
    assert deviating_quantities(world, "1", "1.0000000000000002", {}) == [COUNT, CASH]


def test_the_rule_on_values_with_a_sign_a_zero_or_a_large_magnitude(world):
    """Cases with an expected answer worked out by hand, where a misreading of the rule would show."""
    # The larger of the two parts, not their sum: 1.5 lies above max(1, 0.01 * 101.5) and below 1 + 1.015.
    assert deviating_quantities(world, "100", "101.5", {COUNT: entry(upper=(1, 0.01)), CASH: entry(upper=(2, 0))}) \
        == [COUNT]
    # A relative bound is taken on the magnitude: -101 lies 1 below -100, and 0.02 * 101 covers that,
    # 0.005 * 101 does not.
    assert deviating_quantities(world, "-100", "-101", {COUNT: entry(lower=(0, 0.02)),
                                                        CASH: entry(lower=(0, 0.005))}) == [CASH]
    # Zero on one side: exactly on an absolute bound of 5, and beyond a relative bound of 0.5 * 5.
    assert deviating_quantities(world, "0", "5", {COUNT: entry(upper=(5, 0)), CASH: entry(upper=(0, 0.5))}) == [CASH]
    assert deviating_quantities(world, "5", "0", {}) == [COUNT, CASH]
    listed = deviation_rows(world / "compare.result.json")[0]
    assert (listed["left"], listed["right"]) == (5.0, 0.0)
    # Large values that differ in the last place deviate exactly, and not within a relative bound.
    assert deviating_quantities(world, "1e16", "1.0000000000000002e16", {}) == [COUNT, CASH]
    assert deviating_quantities(world, "1e16", "1.0000000000000002e16",
                                {COUNT: entry(upper=(0, 1e-15)), CASH: entry(upper=(0, 1e-17))}) == [CASH]
    # Rounding comes first, and the relative bound is taken on the rounded values: 0.4 and 1.4 round
    # to 0 and 1, so the bound is 0.8 * 1 and not 0.8 * 1.4.
    assert deviating_quantities(world, "0.4", "1.4", {COUNT: entry(upper=(0, 0.8), decimals=0),
                                                      CASH: entry(upper=(0, 1), decimals=0)}) == [COUNT]


@pytest.mark.parametrize("left, right, decimals, deviation", [
    ("0.6972", "0.6974", 2, False),  # both round to 0.7
    ("0.6949", "0.6951", 2, True),   # 0.69 and 0.7: the values round apart
    ("0.125", "0.13", 2, False),     # commercial: half away from zero
    ("0.125", "0.12", 2, True),
    ("2.675", "2.68", 2, False),     # the written decimal is rounded, not its binary expansion
    ("2.675", "2.67", 2, True),
    ("1234.5", "1235", 0, False),
    ("1234.4999", "1235", 0, True),
    ("0.1", "0.1000000000000004", 15, False),
])
def test_values_are_rounded_commercially_before_the_rule(world, left, right, decimals, deviation):
    profile = {COUNT: entry(decimals=decimals), CASH: entry(decimals=decimals)}
    assert deviating_quantities(world, left, right, profile) == ([COUNT, CASH] if deviation else [])
    # The deviation holds the exported values, before any rounding.
    if deviation:
        listed = deviation_rows(world / "compare.result.json")[0]
        assert (listed["left"], listed["right"]) == (float(left), float(right))


def test_a_whole_number_of_decimals_written_as_a_float_is_that_integer(world):
    """JSON Schema counts ``2.0`` as an integer, and the parser returns a float."""
    profile = {COUNT: entry(decimals=2.0), CASH: entry(decimals=2.0)}
    assert b'"decimals": 2.0' in document_bytes(profile)
    assert deviating_quantities(world, "0.6972", "0.6974", profile) == []
    assert deviating_quantities(world, "0.6949", "0.6951", profile) == [COUNT, CASH]
    assert round_half_away(2.675, 2.0) == round_half_away(2.675, 2) == 2.68


def test_a_period_written_as_a_float_is_compared_as_the_integer(world, capsys):
    """A response of another writer may state ``first_period`` as ``12.0``."""
    left, right = run_side(world, "left", POINTS_LEFT), run_side(world, "right", POINTS_MOVED)
    expected = expected_deviations(left.export_path, right.export_path, {})
    written_response = right.response_path.read_bytes()
    assert written_response.count(b'"first_period": 12,') == 1
    right.response_path.write_bytes(written_response.replace(b'"first_period": 12,', b'"first_period": 12.0,'))
    rehash(world / "right")
    assert b'"first_period": 12.0,' in right.response_path.read_bytes()
    assert main(["compare", str(compare_request(world))]) == 1
    result = stored(world / "compare.result.json")
    assert result["outcome"] == "compared" and deviation_rows(world / "compare.result.json") == expected
    assert expected
    assert result["compared_coordinates"] == 24 and result["added"] == result["removed"] == []


# --- alignment on projection periods ----------------------------------------------


def by_projection_period(self, model_point_id):
    """The stub values counted from the first period of the model point: equal per projection period."""
    _, first, last, base = next(p for p in self.points if p[0] == model_point_id)
    return [(period, [float(base), float(base) * (period - int(first) + 1)])
            for period in range(int(first), int(last) + 1)]


def test_a_first_period_that_moves_is_compared_on_projection_periods(world, capsys):
    """On policy_month each run counts a model point from its own first exported period."""
    engine = engine_with(project=by_projection_period)
    run_side(world, "left", "id,first,last,base\nMP-P,144,299,2\n", engine=engine)
    run_side(world, "right", "id,first,last,base\nMP-P,156,299,2\n", engine=engine)
    assert main(["compare", str(compare_request(world))]) == 1
    result = stored(world / "compare.result.json")
    assert result["outcome"] == "compared" and deviation_rows(world / "compare.result.json") == []
    # Projection periods 0 to 143 are common; the left run has 156 periods, the right one 144.
    assert result["compared_coordinates"] == 144 * 2 and result["added"] == []
    assert result["removed"] == [{"model_point_id": "MP-P", "first_period": 144, "last_period": 155}]
    assert "removed: liability_cashflow / model point MP-P, periods 144 to 155" in capsys.readouterr().out


def test_a_deviation_of_an_in_force_point_is_written_in_projection_periods(world):
    run_side(world, "left", "id,first,last,base\nMP-P,144,160,2\n")
    right = run_side(world, "right", "id,first,last,base\nMP-P,144,160,2\n")
    export = right.export_path.read_text("utf-8")
    assert "MP-P,150,2,302\n" in export
    right.export_path.write_text(export.replace("MP-P,150,2,302\n", "MP-P,150,2,303\n"), "utf-8")
    rehash(world / "right")
    assert main(["compare", str(compare_request(world))]) == 1
    assert deviation_rows(world / "compare.result.json") == [
        {"model_point_id": "MP-P", "period": 6, "quantity": CASH, "left": 302.0, "right": 303.0}]
    (row,) = stored(world / "signature-table.json")["rows"]
    assert (row["first_period"], row["last_period"], row["largest_increase"]["period"]) == (6, 6, 6)


def test_on_valuation_year_periods_are_compared_and_written_as_they_are(world):
    engine = engine_with(time_basis="valuation_year")
    run_side(world, "left", "id,first,last,base\nMP-P,1,5,2\n", engine=engine)
    right = run_side(world, "right", "id,first,last,base\nMP-P,2,5,2\n", engine=engine)
    export = right.export_path.read_text("utf-8")
    right.export_path.write_text(export.replace("MP-P,4,2,10\n", "MP-P,4,2,11\n"), "utf-8")
    rehash(world / "right")
    assert main(["compare", str(compare_request(world))]) == 1
    result = stored(world / "compare.result.json")
    assert result["removed"] == [{"model_point_id": "MP-P", "first_period": 1, "last_period": 1}]
    assert result["added"] == [] and result["compared_coordinates"] == 4 * 2
    assert deviation_rows(world / "compare.result.json") == [
        {"model_point_id": "MP-P", "period": 4, "quantity": CASH, "left": 10.0, "right": 11.0}]


def test_a_point_of_one_run_only_is_added_on_its_own_projection_periods(world):
    run_side(world, "left", "id,first,last,base\nMP-A,0,2,1\n")
    run_side(world, "right", "id,first,last,base\nMP-A,0,2,1\nMP-N,60,62,1\n")
    assert main(["compare", str(compare_request(world))]) == 1
    result = stored(world / "compare.result.json")
    assert result["added"] == [{"model_point_id": "MP-N", "first_period": 0, "last_period": 2}]
    assert result["removed"] == [] and deviation_rows(world / "compare.result.json") == []


def test_alignment_is_built_once_and_never_applied_twice():
    from degelmann.deltarecon.compare import align
    response = {"quantities": [{"name": COUNT, "unit": "policies"}], "time_basis": {"id": "policy_month"}}
    run = CheckedRun(response, {("P", 144): [1.0], ("P", 145): [2.0]})
    aligned = align(run)
    assert aligned.values == {("P", 0): [1.0], ("P", 1): [2.0]} and aligned.aligned
    assert align(run) is aligned and align(aligned) is aligned
    other = CheckedRun({**response, "time_basis": {"id": "valuation_year"}}, {("P", 3): [1.0]})
    assert align(other) is other
    unknown = CheckedRun({**response, "time_basis": {"id": "calendar_quarter"}}, {("P", 3): [1.0]})
    assert align(unknown) is unknown


def test_a_target_only_run_is_aligned_from_its_first_target_period():
    """A window of the target 12-14 starts 12 periods after the valuation date: 156 is projection period 12."""
    from degelmann.deltarecon.compare import align
    response = {"quantities": [{"name": COUNT, "unit": "policies"}], "time_basis": {"id": "policy_month"},
                "target": {"quantities": [COUNT], "periods": {"first": 12, "last": 14}}}
    run = CheckedRun(response, {("P", 156): [1.0], ("P", 157): [2.0], ("P", 158): [3.0], ("Q", 12): [4.0]})
    assert align(run).values == {("P", 12): [1.0], ("P", 13): [2.0], ("P", 14): [3.0], ("Q", 12): [4.0]}
    whole = CheckedRun({**response, "target": {"quantities": [COUNT]}}, {("P", 144): [1.0], ("P", 145): [2.0]})
    assert align(whole).values == {("P", 0): [1.0], ("P", 1): [2.0]}


def test_the_target_window_counts_from_the_period_origin_of_the_time_basis():
    from degelmann.deltarecon.compare import period_origin, target_window
    assert period_origin("policy_month", 144) == 144 and period_origin("calendar_month", 144) == 0
    assert target_window("policy_month", 144, 300, None) == (144, 300)
    assert target_window("policy_month", 144, 300, (12, 14)) == (156, 158)
    assert target_window("policy_month", 144, 150, (0, 59)) == (144, 150)  # clipped at the last period
    first, last = target_window("policy_month", 144, 150, (12, 14))
    assert first > last  # the window is empty
    assert target_window("calendar_month", 144, 300, (100, 200)) == (144, 200)  # clipped at the first period


def test_two_target_only_runs_are_compared_on_projection_periods(world):
    """MP-A starts at month 12 in the left run and at 24 in the right one; the target 1-1 pairs months 13 and 25."""
    target = {"quantities": [COUNT], "periods": {"first": 1, "last": 1}}
    run_side(world, "left", target=target)
    right = run_side(world, "right", POINTS.replace("MP-A,12,13,1.5", "MP-A,24,25,1.5"), target=target)
    assert {p["model_point_id"]: p["first_period"] for p in right.response["model_points"]}["MP-A"] == 25
    assert main(["compare", str(compare_request(world))]) == 0
    result = stored(world / "compare.result.json")
    assert result["outcome"] == "compared" and result["added"] == result["removed"] == []
    assert result["quantities"] == [{"name": COUNT, "unit": "policies"}] and result["compared_coordinates"] == 3


VALUES = [0.0, 1.0, -1.0, 0.125, -0.125, 2.675, 0.6949, 0.6951, 0.6972, 0.6974, 1234.5, 1e-5, 1e16,
          0.1 + 0.2, 0.3, 100.0, 100.25, -38.5, -32.5, 5e-324, 123456.789]
ENTRIES = [None, entry(), entry(upper=(0.25, 0)), entry(lower=(0.25, 0)), entry(upper=(0, 0.01), lower=(0, 0.2)),
           entry(decimals=2), entry(decimals=0), entry(decimals=15), entry(upper=(0.01, 0.001), decimals=1)]


def test_the_rule_of_the_core_agrees_with_the_oracle_on_a_grid():
    exact = {"upper": EXACT, "lower": EXACT}

    def in_reach(value: float, tolerance: dict | None) -> bool:
        # The oracle rounds with 28 significant digits; 1e16 at 15 places is beyond them.
        return abs(value) < 1e12 or (tolerance or {}).get("decimals", 0) < 10

    for decimals in (0, 1, 2, 5, 15):
        for value in VALUES:
            if in_reach(value, {"decimals": decimals}):
                assert round_half_away(value, decimals) == rounded(value, decimals), (value, decimals)
    checked = 0
    for tolerance in ENTRIES:
        for left in VALUES:
            for right in VALUES:
                if in_reach(left, tolerance) and in_reach(right, tolerance):
                    checked += 1
                    assert exceeds(left, right, tolerance) == deviates(left, right, tolerance or exact), \
                        (left, right, tolerance)
    assert checked > 3900


def test_rounding_holds_for_the_largest_values():
    assert round_half_away(1.7976931348623157e308, 15) == 1.7976931348623157e308
    assert round_half_away(-1e300, 2) == -1e300 and round_half_away(-0.004, 2) == 0


# --- coverage -----------------------------------------------------------------------


def test_coverage_differences_are_ranges_and_never_deviations(world, capsys):
    """Another selection, a model point on one side only, and other period ranges.

    On ``policy_month`` the ranges are projection periods: each model point counts from its first
    exported period in each run, so a range that ends earlier or later shows at its end only."""
    left_points = "id,first,last,base\nMP-A,12,13,1.5\nMP-B,0,2,2\nMP-C,0,0,1e-05\nMP-G,5,9,3\nMP-L,0,1,4\n"
    right_points = ("id,first,last,base\nMP-A,12,15,1.5\nMP-B,0,5,2\nMP-C,0,0,1e-05\nMP-G,5,6,3\nMP-R,2,3,4\n"
                    "MP-D,3,4,1e16\n")
    run_side(world, "left", left_points)
    run_side(world, "right", right_points,
             selection={"mode": "subset", "model_point_ids": ["MP-A", "MP-B", "MP-C", "MP-G", "MP-R"]})
    assert main(["compare", str(compare_request(world))]) == 1
    output = capsys.readouterr().out
    assert "no deviation" not in output
    assert "added: liability_cashflow / model point MP-B, periods 3 to 5" in output
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA) and result["outcome"] == "compared"
    # The longest contiguous ranges, by model point id and first period.
    assert result["added"] == [
        {"model_point_id": "MP-A", "first_period": 2, "last_period": 3},
        {"model_point_id": "MP-B", "first_period": 3, "last_period": 5},
        {"model_point_id": "MP-R", "first_period": 0, "last_period": 1}]
    assert result["removed"] == [
        {"model_point_id": "MP-G", "first_period": 2, "last_period": 4},
        {"model_point_id": "MP-L", "first_period": 0, "last_period": 1}]
    # Never a deviation and never filled with zero: only common coordinates are compared.
    assert deviation_rows(world / "compare.result.json") == [] and result["deviating_model_points"] == []
    assert result["compared_coordinates"] == 2 * (2 + 3 + 1 + 2)
    assert stored(world / "signature-table.json")["rows"] == []
    assert_record(world, "compared", table=True)


def test_coverage_on_one_side_only_and_ranges_of_neighbouring_model_points(world, capsys):
    """Only added, then only removed; the ranges of two model points never join. On ``valuation_year``
    periods are compared and written as they are."""
    engine = engine_with(time_basis="valuation_year")
    run_side(world, "left", "id,first,last,base\nMP-A,0,0,1\n", engine=engine)
    # MP-X ends at period 2 and MP-Y starts at period 3.
    run_side(world, "right", "id,first,last,base\nMP-A,0,0,1\nMP-X,0,2,1\nMP-Y,3,4,1\n", engine=engine)
    ranges = [{"model_point_id": "MP-X", "first_period": 0, "last_period": 2},
              {"model_point_id": "MP-Y", "first_period": 3, "last_period": 4}]
    assert main(["compare", str(compare_request(world))]) == 1
    assert "no deviation" not in capsys.readouterr().out
    result = stored(world / "compare.result.json")
    assert (result["added"], result["removed"], deviation_rows(world / "compare.result.json")) == (ranges, [], [])

    # The same two runs with the sides exchanged: only removed.
    for name in OUTPUTS:
        (world / name).unlink()
    assert main(["compare", str(compare_request(world, left="right", right="left"))]) == 1
    assert "no deviation" not in capsys.readouterr().out
    result = stored(world / "compare.result.json")
    assert (result["added"], result["removed"], deviation_rows(world / "compare.result.json")) == ([], ranges, [])


def test_alignment_is_by_the_exact_id_and_does_not_depend_on_the_row_order(world):
    """Ids that differ by case or length are different model points; export rows may come in any order."""
    run_side(world, "left", "id,first,last,base\nMP-a,0,0,9\nMP-A,0,0,1\nMP-AA,0,0,2\nMP-AAA,0,0,4\nMP-B,0,0,5\n")
    run_side(world, "right", "id,first,last,base\nMP-A,0,0,1.5\nMP-AA,0,0,3\nMP-b,0,0,9\n")

    def check() -> None:
        compared = compare(compare_request(world))
        result = compared.result
        assert result["outcome"] == "compared", result
        # Ordered by Unicode code point: upper case before lower case, a prefix before its extension.
        assert [(d["model_point_id"], d["quantity"], d["left"], d["right"])
                for d in deviation_rows(compared.result_path)] == [
            ("MP-A", COUNT, 1.0, 1.5), ("MP-A", CASH, 1.0, 1.5), ("MP-AA", COUNT, 2.0, 3.0), ("MP-AA", CASH, 2.0, 3.0)]
        assert result["deviating_model_points"] == ["MP-A", "MP-AA"] and result["compared_coordinates"] == 4
        assert [r["model_point_id"] for r in result["removed"]] == ["MP-AAA", "MP-B", "MP-a"]
        assert [r["model_point_id"] for r in result["added"]] == ["MP-b"]

    check()
    # The same export with its data rows in the opposite order gives the same result.
    for name in OUTPUTS:
        (world / name).unlink()
    for side in ("left", "right"):
        path = world / side / "results.csv"
        header, *rows = path.read_text("utf-8").splitlines()
        path.write_text("\n".join([header] + rows[::-1]) + "\n", "utf-8")
        rehash(world / side)
    check()


# --- incompatible -------------------------------------------------------------------


def engine_with(**attributes) -> StubEngine:
    """A stub engine whose sessions declare another time basis or other quantities."""
    session = type("OtherSession", (StubSession,), attributes)

    class OtherEngine(StubEngine):
        @contextmanager
        def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
            with super().open(release, enabled, manifest_dir, repositories, hold) as opened:
                opened.__class__ = session
                yield opened

    return OtherEngine()


def other_stage(world: Path, monkeypatch) -> None:
    from degelmann.deltarecon import run as run_module
    monkeypatch.setitem(run_module.STAGE_QUANTITIES, "other_stage",
                        run_module.STAGE_QUANTITIES["liability_cashflow"])
    run_side(world, "right")
    response = stored(world / "right" / "response.json")
    response["stage"] = "other_stage"
    (world / "right" / "response.json").write_bytes(document_bytes(response))


INCOMPATIBLE = {
    "stage_mismatch": other_stage,
    "time_basis_mismatch": lambda world, _: run_side(world, "right", engine=engine_with(time_basis="valuation_year")),
    "quantity_mismatch": lambda world, _: run_side(world, "right", engine=engine_with(
        quantities=[("Anzahl Verträge", "policies"), ("Provisionen", "EUR")])),
    "unit_mismatch": lambda world, _: run_side(world, "right", engine=engine_with(
        quantities=[("Anzahl Verträge", "policies"), ("Netto-Cashflow", "kEUR")])),
}


@pytest.mark.parametrize("code", sorted(INCOMPATIBLE))
def test_runs_that_cannot_be_compared_are_incompatible(world, monkeypatch, capsys, code):
    run_side(world, "left")
    INCOMPATIBLE[code](world, monkeypatch)
    assert main(["compare", str(compare_request(world))]) == 1
    output = capsys.readouterr().out
    assert "compare: incompatible" in output and f"diagnostic: {code}:" in output
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA)
    # No result lists: no deviation list, no coverage lists, and no parameter diff.
    assert sorted(result) == ["compare_id", "contract_version", "diagnostics", "document", "outcome", "stage"]
    assert result["outcome"] == "incompatible" and [d["code"] for d in result["diagnostics"]] == [code]
    # Both identities can be read, so the record is written; a table is not.
    assert written(world) == ["compare.result.json", "compare.run-record.json"]
    assert_record(world, "incompatible", table=False)


def test_the_rules_are_applied_in_their_numbered_order(world):
    """Stage before time basis before quantity names before units before the tolerance names."""
    run_side(world, "left")
    run_side(world, "right", engine=engine_with(
        time_basis="valuation_year", quantities=[("Anzahl Verträge", "pieces"), ("Provisionen", "EUR")]))
    result = compare(compare_request(world, {"Zahlbeitrag": entry()})).result
    assert result["diagnostics"][0]["code"] == "time_basis_mismatch"
    for name in OUTPUTS:
        (world / name).unlink(missing_ok=True)
    shutil.rmtree(world / "right")
    run_side(world, "right", engine=engine_with(quantities=[("Anzahl Verträge", "pieces"), ("Provisionen", "EUR")]))
    assert compare(compare_request(world, {"Zahlbeitrag": entry()})).result["diagnostics"][0]["code"] == \
        "quantity_mismatch"


# --- rejected -----------------------------------------------------------------------


def edit_export(folder: Path, old: str, new: str, rehash: bool = True) -> None:
    path = folder / "results.csv"
    text = path.read_text("utf-8")
    assert old in text
    path.write_text(text.replace(old, new), "utf-8")
    if rehash:
        response = stored(folder / "response.json")
        response["export"]["artifact"]["sha256"] = sha256_file(path)
        (folder / "response.json").write_bytes(document_bytes(response))


def edit_document(path: Path, edit) -> None:
    document = stored(path)
    edit(document)
    path.write_bytes(document_bytes(document))


def failed_run(world: Path) -> None:
    shutil.rmtree(world / "right")
    run_side(world, "right", POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise"))


def error_run(world: Path) -> None:
    shutil.rmtree(world / "right")
    run_side(world, "right", "id,first,last,base\n")


def rejected_run(world: Path) -> None:
    shutil.rmtree(world / "right")
    run_side(world, "right", selection={"mode": "subset", "model_point_ids": ["MP-9999"]})


def duplicate_parameter(record: dict) -> None:
    record["parameters"].append(dict(record["parameters"][0]))


def duplicate_key(record: dict) -> None:
    record["parameters"].append({"name": "table", "type": "keyed_table", "key_columns": ["year"],
                                 "value_columns": ["rate"], "rows": [{"key": [1], "values": [0.1]},
                                                                     {"key": [1.0], "values": [0.2]}]})


def row_off_its_columns(record: dict) -> None:
    record["parameters"].append({"name": "table", "type": "keyed_table", "key_columns": ["year"],
                                 "value_columns": ["rate"], "rows": [{"key": [1, 2], "values": [0.1]}]})


# Name -> (what is altered before the request is stored, per_quantity, code, the record is written).
REJECTED = {
    "failed-response": (failed_run, {}, "model_point_failed", True),
    "error-response": (error_run, {}, "no_model_point", True),
    "rejected-response": (rejected_run, {}, "unknown_model_point", False),
    "rule-7-quantity-order": (lambda w: edit_document(w / "right" / "response.json",
                                                      lambda r: r["quantities"].reverse()), {},
                              "quantity_mismatch", True),
    "rule-8-export-missing": (lambda w: (w / "right" / "results.csv").unlink(), {}, "artifact_missing", True),
    "rule-8-export-other-hash": (lambda w: edit_export(w / "right", "MP-B,1,2,4\n", "MP-B,1,2,5\n", rehash=False),
                                 {}, "artifact_hash_mismatch", True),
    "rule-9-number-format": (lambda w: edit_export(w / "right", "MP-B,1,2,4\n", "MP-B,1,2,NaN\n"), {},
                             "non_finite_value", True),
    "rule-10-selection": (lambda w: edit_document(w / "left" / "response.json", lambda r: r.update(
        selection={"mode": "subset", "model_point_ids": ["MP-A", "MP-B", "MP-C"]})), {},
        "unrequested_coordinate", True),
    "rule-11-reversed-range": (lambda w: edit_document(w / "right" / "response.json",
                                                       lambda r: r["model_points"][0].update(first_period=14)),
                               {}, "inconsistent_response", True),
    "rule-12-duplicate-row": (lambda w: edit_export(w / "right", "MP-B,1,2,4\n", "MP-B,1,2,4\nMP-B,1,2,4\n"), {},
                              "duplicate_coordinate", True),
    "rule-12-missing-row": (lambda w: edit_export(w / "left", "MP-B,1,2,4\n", ""), {}, "missing_coordinate", True),
    "rule-13-row-count": (lambda w: edit_document(w / "right" / "response.json",
                                                  lambda r: r["export"].update(data_rows=7)), {},
                          "inconsistent_response", True),
    "tolerance-for-an-undeclared-quantity": (lambda w: None, {"Provisionen": entry()}, "unknown_quantity", True),
    "inventory-duplicate-name": (lambda w: edit_document(w / "right" / "run-record.json", duplicate_parameter), {},
                                 "invalid_inventory", True),
    "inventory-duplicate-key": (lambda w: edit_document(w / "left" / "run-record.json", duplicate_key), {},
                                "invalid_inventory", True),
    "inventory-row-off-its-columns": (lambda w: edit_document(w / "left" / "run-record.json", row_off_its_columns),
                                      {}, "invalid_inventory", True),
    "response-not-a-response": (lambda w: shutil.copyfile(w / "right" / "request.json",
                                                          w / "right" / "response.json"), {},
                                "schema_violation", False),
    "unsupported-stage": (lambda w: None, {}, "unsupported_stage", True),
}


@pytest.mark.parametrize("case", sorted(REJECTED))
def test_a_broken_rule_rejects_the_comparison_with_its_diagnostic(world, capsys, case):
    alter, per_quantity, code, with_record = REJECTED[case]
    run_side(world, "left"), run_side(world, "right")
    alter(world)
    members = {"stage": "asset_cashflow"} if case == "unsupported-stage" else {}
    assert main(["compare", str(compare_request(world, per_quantity, **members))]) == 1
    output = capsys.readouterr().out
    assert "compare: rejected" in output and f"diagnostic: {code}:" in output
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA)
    assert result["outcome"] == "rejected" and [d["code"] for d in result["diagnostics"]] == [code]
    assert "deviations" not in result and "parameter_diff" not in result
    if case == "error-response":
        assert "The right run has ended with an error" in result["diagnostics"][0]["message"]
    # The result is written alone unless the release identities of both sides can be read.
    assert written(world) == ["compare.result.json"] + (["compare.run-record.json"] if with_record else [])
    if with_record:
        record = stored(world / "compare.run-record.json")
        assert not schema_errors(record, RECORD_SCHEMA)
        assert record["outcome"] == "rejected" and len(record["releases"]) == 2
        assert roles(record["outputs"]) == {"result": "compare.result.json"}


@pytest.mark.parametrize("alter, code", [
    (lambda w: (w / "right" / "response.json").unlink(), "artifact_missing"),
    (lambda w: edit_document(w / "left" / "response.json", lambda r: r.update(run_id="other")),
     "artifact_hash_mismatch"),
    (lambda w: (w / "left" / "run-record.json").unlink(), "artifact_missing"),
    (lambda w: edit_document(w / "right" / "run-record.json",
                             lambda r: r.update(record_id="record-00000000-0000-4000-8000-000000000000")),
     "artifact_hash_mismatch"),
])
def test_a_missing_or_altered_artifact_of_the_request_rejects_the_comparison(world, alter, code):
    run_side(world, "left"), run_side(world, "right")
    path = compare_request(world)
    alter(world)  # after the request has stored the hashes
    assert main(["compare", str(path)]) == 1
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA)
    assert result["outcome"] == "rejected" and result["diagnostics"][0]["code"] == code
    # A response that is missing or altered gives no identity; a record that is does.
    with_record = "run-record" in result["diagnostics"][0]["message"]
    assert written(world) == ["compare.result.json"] + (["compare.run-record.json"] if with_record else [])


@pytest.mark.parametrize("case, code", [
    ("not-json", "invalid_json"), ("duplicate-member", "duplicate_member"),
    ("wrong-version", "unsupported_version"), ("no-tolerance", "schema_violation"),
    ("general-tolerance", "schema_violation"), ("bound-without-derivation", "schema_violation"),
    ("a-result", "schema_violation")])
def test_a_request_that_is_not_a_compare_request_writes_nothing(world, capsys, case, code):
    run_side(world, "left"), run_side(world, "right")
    path = compare_request(world)
    request, text = stored(path), path.read_text("utf-8")
    data = {
        "not-json": b"{ this is not JSON",
        "duplicate-member": text.replace('"compare_id"', '"compare_id": "x",\n  "compare_id"', 1).encode("utf-8"),
        "wrong-version": document_bytes({**request, "contract_version": "4.0", "tolerance": {}}),
        "no-tolerance": document_bytes({k: v for k, v in request.items() if k != "tolerance"}),
        "general-tolerance": document_bytes({**request, "tolerance": {"abs_tol": 0.5, "rel_tol": 0}}),
        "bound-without-derivation": document_bytes({**request, "tolerance": {"per_quantity": {
            CASH: {"upper": {"abs_tol": 0.5, "rel_tol": 0}, "lower": EXACT}}}}),
        "a-result": document_bytes({"document": "compare_result", "contract_version": "3.0",
                                    "stage": "liability_cashflow", "compare_id": "x", "outcome": "rejected",
                                    "diagnostics": [{"code": "invalid_json", "message": "x"}]}),
    }[case]
    path.write_bytes(data)
    assert main(["compare", str(path)]) == 1
    output = capsys.readouterr().out
    assert "compare: rejected" in output and f"diagnostic: {code}:" in output
    assert written(world) == []


# --- parameter diff -----------------------------------------------------------------

TABLE = {"name": "table", "type": "keyed_table", "key_columns": ["year", "kind"], "value_columns": ["rate"],
         "rows": [{"key": [1, "a"], "values": [0.1]}, {"key": [2, "a"], "values": [0.2]},
                  {"key": [2, "b"], "values": [0.3]}, {"key": [10, "a"], "values": [0.4]}]}


def scalar(name: str, value) -> dict:
    return {"name": name, "type": "scalar", "value": value}


def test_parameter_diff_has_one_typed_entry_per_parameter_that_differs():
    left = [scalar("equal", 0.01), scalar("flag", True), scalar("gone", 0), scalar("one", 1), scalar("rate", 0.01),
            scalar("text", "1"), TABLE, {**TABLE, "name": "table_columns"}, {**TABLE, "name": "table_equal"},
            scalar("to_table", 5)]
    right = [scalar("equal", 0.01), scalar("flag", 1), scalar("new", "x"), scalar("one", 1.0), scalar("rate", 0.0125),
             scalar("text", 1),
             {**TABLE, "rows": [{"key": [1, "a"], "values": [0.1]}, {"key": [2, "a"], "values": [0.25]},
                                {"key": [3, "a"], "values": [0.5]}, {"key": [10, "a"], "values": [0.4]}]},
             {**TABLE, "name": "table_columns", "value_columns": ["other"]},
             {**TABLE, "name": "table_equal", "rows": list(reversed(TABLE["rows"]))},
             {**TABLE, "name": "to_table"}]
    diff = parameter_diff(left, right)
    for item in diff:
        assert not schema_errors(item, "compare.schema.json#/$defs/parameter_change"), item["name"]
    assert [(e["name"], e["change"]) for e in diff] == [
        ("flag", "changed"), ("gone", "removed"), ("new", "added"), ("rate", "changed"), ("table", "changed"),
        ("table_columns", "replaced"), ("text", "changed"), ("to_table", "replaced")]
    by_name = {e["name"]: e for e in diff}
    # A boolean and a number, and a number and a string, are never equal; 1 and 1.0 are one value.
    assert by_name["flag"] == {"name": "flag", "change": "changed", "type": "scalar", "old": True, "new": 1}
    assert by_name["text"] == {"name": "text", "change": "changed", "type": "scalar", "old": "1", "new": 1}
    assert by_name["rate"] == {"name": "rate", "change": "changed", "type": "scalar", "old": 0.01, "new": 0.0125}
    assert by_name["gone"] == {"name": "gone", "change": "removed", "old": scalar("gone", 0)}
    assert by_name["new"] == {"name": "new", "change": "added", "new": scalar("new", "x")}
    # Row entries by key, and none for a row that is equal.
    assert by_name["table"] == {"name": "table", "change": "changed", "type": "keyed_table", "rows": [
        {"key": [2, "a"], "change": "changed", "old": [0.2], "new": [0.25]},
        {"key": [2, "b"], "change": "removed", "old": [0.3]},
        {"key": [3, "a"], "change": "added", "new": [0.5]}]}
    assert by_name["table_columns"]["old"]["value_columns"] == ["rate"]
    assert by_name["table_columns"]["new"]["value_columns"] == ["other"]
    assert by_name["to_table"]["old"] == scalar("to_table", 5) and by_name["to_table"]["new"]["type"] == "keyed_table"


def test_parameter_diff_is_made_also_without_deviations_and_only_with_both_records(world, capsys):
    run_side(world, "left")
    run_side(world, "right", params="name,value\nrate,0.02\nextra,7\n")
    edit_document(world / "right" / "run-record.json", lambda record: record["parameters"].append(TABLE))
    assert main(["compare", str(compare_request(world))]) == 0  # the diff does not change the outcome
    assert "no deviation above tolerance" in capsys.readouterr().out
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA) and deviation_rows(world / "compare.result.json") == []
    assert result["parameter_diff"] == [
        {"name": "extra", "change": "added", "new": scalar("extra", 7.0)},
        {"name": "label", "change": "removed", "old": scalar("label", "base")},
        {"name": "rate", "change": "changed", "type": "scalar", "old": 0.01, "new": 0.02},
        {"name": "table", "change": "added", "new": TABLE}]
    for name in OUTPUTS:
        (world / name).unlink()
    for records in ({"left": True, "right": False}, {"left": False, "right": False}):
        path = compare_request(world)
        request = stored(path)
        for side, keep in records.items():
            if not keep:
                del request[side]["run_record"]
        path.write_bytes(document_bytes(request))
        result = compare(path).result
        assert result["outcome"] == "compared" and "parameter_diff" not in result
        for name in OUTPUTS:
            (world / name).unlink()


# --- signature table ----------------------------------------------------------------


def recount(result: dict, deviations: list[dict]) -> list[dict]:
    """The rows of the signature table, counted over the deviation file without the core."""
    rows = []
    for quantity in [q["name"] for q in result["quantities"]]:
        listed = [d for d in deviations if d["quantity"] == quantity]
        if not listed:
            continue
        up = [d for d in listed if d["right"] > d["left"]]
        down = [d for d in listed if d["right"] < d["left"]]
        row = {"stage": result["stage"], "quantity": quantity,
               "deviating_model_points": len({d["model_point_id"] for d in listed}),
               "deviating_coordinates": len(listed), "right_above_left": len(up), "right_below_left": len(down),
               "first_period": min(d["period"] for d in listed), "last_period": max(d["period"] for d in listed)}
        for member, group, pick in (("largest_increase", up, max), ("largest_decrease", down, min)):
            if group:
                best = pick(d["right"] - d["left"] for d in group)
                first = next(d for d in group if d["right"] - d["left"] == best)
                row[member] = {"model_point_id": first["model_point_id"], "period": first["period"],
                               "absolute": best, "relative": best / max(abs(first["left"]), abs(first["right"]))}
        rows.append(row)
    return rows


@pytest.mark.parametrize("profile", ["exact", "decimals", "asymmetric", "relative"])
def test_signature_table_counts_the_deviation_list_and_has_reproducible_bytes(world, tmp_path, profile):
    run_side(world, "left", POINTS_LEFT), run_side(world, "right", POINTS_MOVED)
    compare_request(world, PROFILES[profile])
    other = tmp_path / "elsewhere" / "deep"
    shutil.copytree(world, other)  # the same comparison in another folder

    first = compare(world / "compare.request.json")
    second = compare(other / "compare.request.json")
    table = stored(world / "signature-table.json")
    assert (world / "signature-table.json").read_bytes() == (other / "signature-table.json").read_bytes()
    listed = deviation_rows(world / "compare.result.json")
    assert (world / "signature-table.json").read_bytes() == document_bytes(signature_table(first.result, listed))
    assert first.table == second.table == table and first.deviations == listed
    assert "recorded_at" not in table and not schema_errors(table, COMPARE_SCHEMA)

    result = stored(world / "compare.result.json")
    assert {m: table[m] for m in ("stage", "compare_id", "left", "right")} == {
        m: result[m] for m in ("stage", "compare_id", "left", "right")}
    # One row per stage and quantity that deviates, in quantity order, every row with the stage.
    assert table["rows"] == recount(result, listed) and table["rows"]
    quantities = [row["quantity"] for row in table["rows"]]
    assert quantities == [q["name"] for q in result["quantities"] if q["name"] in quantities]
    assert all(row["stage"] == "liability_cashflow" for row in table["rows"])
    for row in table["rows"]:
        assert row["right_above_left"] + row["right_below_left"] == row["deviating_coordinates"]
        assert ("largest_increase" in row) == (row["right_above_left"] > 0)
        assert ("largest_decrease" in row) == (row["right_below_left"] > 0)
    assert sum(row["deviating_coordinates"] for row in table["rows"]) == len(listed)


def test_a_signature_table_that_would_violate_its_schema_writes_no_part_of_the_comparison(world, monkeypatch):
    run_side(world, "left", POINTS_LEFT), run_side(world, "right", POINTS_MOVED)
    request = compare_request(world)
    broken = {"document": "signature_table"}
    assert schema_errors(broken, COMPARE_SCHEMA)
    monkeypatch.setattr("degelmann.deltarecon.compare.signature_table", lambda result, deviations: broken)
    with pytest.raises(AssertionError, match=r"^signature-table\.json would violate compare\.schema\.json: "):
        compare(request)
    # The result and the table are checked before either is written, and the deviation file
    # written before them is removed again: no part of the comparison stays, and no record.
    assert written(world) == []


def test_signature_table_names_the_extremes_with_signed_differences():
    def deviation(model_point_id, period, quantity, left, right):
        return {"model_point_id": model_point_id, "period": period, "quantity": quantity, "left": left,
                "right": right}

    result = {"document": "compare_result", "contract_version": "3.0", "stage": "liability_cashflow",
              "compare_id": "compare-x", "outcome": "compared",
              "left": {"run_id": "a", "release_label": "N"}, "right": {"run_id": "b", "release_label": "M"},
              "quantities": [{"name": COUNT, "unit": "policies"}, {"name": "Zahlbeitrag", "unit": "EUR"},
                             {"name": CASH, "unit": "EUR"}]}
    deviations = [deviation("MP-A", 3, CASH, 100.0, 104.0), deviation("MP-A", 4, CASH, -8.0, -4.0),
                  deviation("MP-A", 5, CASH, 10.0, 2.0), deviation("MP-B", 0, COUNT, 1.0, 0.5),
                  deviation("MP-B", 7, CASH, 0.0, -8.0), deviation("MP-C", 1, CASH, 1.0, 5.0)]
    table = signature_table(result, deviations)
    assert not schema_errors(table, COMPARE_SCHEMA)
    assert table["rows"] == [
        {"stage": "liability_cashflow", "quantity": COUNT, "deviating_model_points": 1,
         "deviating_coordinates": 1, "right_above_left": 0, "right_below_left": 1, "first_period": 0,
         "last_period": 0,
         "largest_decrease": {"model_point_id": "MP-B", "period": 0, "absolute": -0.5, "relative": -0.5}},
        {"stage": "liability_cashflow", "quantity": CASH, "deviating_model_points": 3,
         "deviating_coordinates": 5, "right_above_left": 3, "right_below_left": 2, "first_period": 1,
         "last_period": 7,
         # Of the three increases of 4 the lowest model point id, then the lowest period; of the two
         # decreases of 8 likewise.
         "largest_increase": {"model_point_id": "MP-A", "period": 3, "absolute": 4.0, "relative": 4.0 / 104.0},
         "largest_decrease": {"model_point_id": "MP-A", "period": 5, "absolute": -8.0, "relative": -0.8}}]
    # The text rounds to four significant digits and gives the relative difference in per cent;
    # the table keeps the exact values.
    assert render_table(table) == [
        "signature table:",
        "  liability_cashflow / Anzahl Verträge: 1 model points, 1 coordinates, periods 0 to 0, 0 above, 1 below",
        "    largest increase: none",
        "    largest decrease: -0.5 (-50 %) at model point MP-B, period 0",
        "  liability_cashflow / Netto-Cashflow: 3 model points, 5 coordinates, periods 1 to 7, 3 above, 2 below",
        "    largest increase: 4 (3.846 %) at model point MP-A, period 3",
        "    largest decrease: -8 (-80 %) at model point MP-A, period 5"]
    # The choice among equal differences does not depend on the stored order of the deviations.
    assert signature_table(result, list(reversed(deviations))) == table


@pytest.mark.parametrize("outcome", ["incompatible", "rejected"])
def test_there_is_no_signature_table_for_another_outcome(outcome):
    result = {"document": "compare_result", "contract_version": "3.0", "stage": "liability_cashflow",
              "compare_id": "compare-x", "outcome": outcome,
              "diagnostics": [{"code": "unit_mismatch", "message": "x"}]}
    with pytest.raises(ValueError):
        signature_table(result, [])


@pytest.mark.parametrize("edit, valid", [
    (lambda row: None, True),
    (lambda row: row.pop("stage"), False),
    (lambda row: row.pop("largest_increase"), False),              # the count is above zero
    (lambda row: row.update(right_above_left=0), False),           # the count is zero
    (lambda row: row.update(largest_decrease=dict(row["largest_increase"])), False),
    (lambda row: row["largest_increase"].update(absolute=-1.0), False),
    (lambda row: row["largest_increase"].pop("relative"), False),
    (lambda row: row.update(deviating_coordinates=0), False),
    (lambda row: row.update(sum_of_differences=1.0), False),
])
def test_signature_table_schema(edit, valid):
    table = json.loads((EXAMPLES / "reference" / "compare.signature-table.json").read_text("utf-8"))
    edit(table["rows"][1])
    assert (not schema_errors(table, COMPARE_SCHEMA)) == valid
    assert schema_errors({**table, "recorded_at": "2026-10-03T09:05:00Z"}, COMPARE_SCHEMA)


# --- an oracle of another construction ----------------------------------------------

# ``rounded`` and ``deviates`` of ``conftest.py`` are built like the core: a decimal
# number quantized half up. The oracle below rounds with fractions and no decimal module,
# and builds lists and ranges in its own way, so a shared misreading has to be made twice
# in two different constructions.


def fraction_round(value: float, decimals: int) -> float:
    scaled = Fraction(repr(value)) * 10 ** decimals  # the exact value of the written decimal
    whole = (abs(scaled) + Fraction(1, 2)).__floor__()
    return float(Fraction(whole if scaled >= 0 else -whole, 10 ** decimals))


def fraction_deviates(left: float, right: float, tolerance: dict | None) -> bool:
    if tolerance is None:
        return left != right
    if "decimals" in tolerance:
        left, right = fraction_round(left, tolerance["decimals"]), fraction_round(right, tolerance["decimals"])
    difference, magnitude = right - left, max(abs(left), abs(right))

    def bound(pair: dict) -> float:
        relative = pair["rel_tol"] * magnitude
        return pair["abs_tol"] if pair["abs_tol"] >= relative else relative

    return difference > bound(tolerance["upper"]) or -difference > bound(tolerance["lower"])


def random_value(rnd: random.Random) -> float:
    kind = rnd.random()
    if kind < 0.1:
        return 0.0
    if kind < 0.3:  # decimal ties
        return round(rnd.uniform(-1000, 1000), rnd.randint(0, 4)) + rnd.choice([0, 0.5, 0.05, 0.005, 0.0005])
    if kind < 0.5:
        return rnd.uniform(-1e6, 1e6)
    if kind < 0.6:
        return rnd.choice([-1, 1]) * 10 ** rnd.uniform(-12, 17)
    if kind < 0.7:
        return float(rnd.randint(-10 ** 6, 10 ** 6))
    if kind < 0.8:
        return rnd.choice([-1, 1]) * (rnd.randint(0, 99999) + 0.5) / 10 ** rnd.randint(0, 6)
    return rnd.uniform(-50, 50)


def random_tolerance(rnd: random.Random) -> dict | None:
    if rnd.random() < 0.15:
        return None
    parts = [0, 0, 0.25, 0.01, 1, 1e-9, 0.001, 0.5, 0.1]
    tolerance = {"upper": {"abs_tol": rnd.choice(parts), "rel_tol": rnd.choice(parts)},
                 "lower": {"abs_tol": rnd.choice(parts), "rel_tol": rnd.choice(parts)}}
    if rnd.random() < 0.5:
        tolerance["decimals"] = rnd.choice([0, 1, 2, 3, 5, 9, 15])
    return tolerance


def test_the_rule_of_the_core_agrees_with_an_oracle_of_another_construction():
    rnd = random.Random(20261012)  # a fixed seed: the same cases in every run
    deviating = 0
    for _ in range(20000):
        left = random_value(rnd)
        right = left + rnd.choice([0, 0.25, -0.25, 0.01, -0.01, 1e-9, 1, -1]) if rnd.random() < 0.4 \
            else random_value(rnd)
        if rnd.random() < 0.1:
            right = left * (1 + rnd.choice([0.001, -0.001, 0.01, 0.5, -0.5]))
        tolerance = random_tolerance(rnd)
        expected = fraction_deviates(left, right, tolerance)
        deviating += expected
        assert exceeds(left, right, tolerance) == expected, (left, right, tolerance)
    assert 4000 < deviating < 16000  # both answers occur often


def ranges_of(keys) -> list[dict]:
    result = []
    for model_point_id in sorted({key[0] for key in keys}):
        periods = sorted(period for other, period in keys if other == model_point_id)
        start = previous = periods[0]
        for period in periods[1:] + [None]:
            if period is None or period != previous + 1:
                result.append({"model_point_id": model_point_id, "first_period": start, "last_period": previous})
                start = period
            previous = period
    return result


def test_whole_comparisons_agree_with_an_oracle_of_another_construction():
    """Eleven quantities in no alphabetical order, values of any sign, odd ids, rows in any order."""
    rnd = random.Random(20261012)
    names = [f"q{i}" for i in (7, 3, 9, 1, 5, 0, 8, 2, 6, 4, 10)]

    def response(run_id: str) -> dict:
        return {"stage": "liability_cashflow", "time_basis": {"id": "policy_month"}, "run_id": run_id,
                "quantities": [{"name": name, "unit": "EUR"} for name in names], "release": {"label": run_id}}

    def shuffled(values: dict) -> dict:
        items = list(values.items())
        rnd.shuffle(items)
        return dict(items)

    deviating = one_sided = 0
    for _ in range(60):
        ids = [f"MP-{i:03d}" for i in range(rnd.randint(1, 12))] + rnd.sample(
            ["mp-001", "MP-001 ", "Mp-1", "10", "9", "Ä", "Z"], 3)
        left, right = {}, {}
        for model_point_id in ids:
            for side in (left, right):
                if rnd.random() < 0.15:  # a model point on one side only
                    continue
                first = rnd.randint(0, 5)
                spans = [(first, first + rnd.randint(0, 6))]
                if rnd.random() < 0.3:  # a gap in the periods
                    spans.append((spans[0][1] + rnd.randint(1, 4), spans[0][1] + rnd.randint(4, 8)))
                for start, end in spans:
                    for period in range(start, end + 1):
                        side[model_point_id, period] = [random_value(rnd) for _ in names]
        for key in set(left) & set(right):
            right[key] = [old if rnd.random() < 0.6 else
                          (new if rnd.random() < 0.5 else old + rnd.choice([0.25, -0.25, 1e-9, -1, 0.004]))
                          for old, new in zip(left[key], right[key])]
        left, right = shuffled(left), shuffled(right)
        profile = {name: tolerance for name in names if (tolerance := random_tolerance(rnd)) is not None}
        request = {"stage": "liability_cashflow", "compare_id": "compare-fuzz", "tolerance": {"per_quantity": profile}}
        result, deviations = compare_runs(request, CheckedRun(response("left"), left),
                                          CheckedRun(response("right"), right))

        # On policy_month both sides are compared on projection periods.
        left, right = projection_periods(left), projection_periods(right)
        common = set(left) & set(right)
        expected = [{"model_point_id": key[0], "period": key[1], "quantity": name,
                     "left": left[key][index], "right": right[key][index]}
                    for key in sorted(common) for index, name in enumerate(names)
                    if fraction_deviates(left[key][index], right[key][index], profile.get(name))]
        assert result["outcome"] == "compared"
        assert deviations == expected
        assert result["deviating_model_points"] == sorted({d["model_point_id"] for d in expected})
        assert result["compared_coordinates"] == len(common) * len(names)
        assert result["added"] == ranges_of(set(right) - set(left))
        assert result["removed"] == ranges_of(set(left) - set(right))
        # The table of the result against a recount that takes the tie-break from the content.
        rows = signature_table({**result, "document": "compare_result"}, deviations)["rows"]
        assert [row["quantity"] for row in rows] == [n for n in names if any(d["quantity"] == n for d in expected)]
        for row in rows:
            listed = [d for d in expected if d["quantity"] == row["quantity"]]
            assert row["deviating_coordinates"] == len(listed)
            assert row["deviating_model_points"] == len({d["model_point_id"] for d in listed})
            for member, sign in (("largest_increase", 1), ("largest_decrease", -1)):
                group = [d for d in listed if sign * (d["right"] - d["left"]) > 0]
                assert (member in row) == bool(group)
                if group:
                    best = sorted(group, key=lambda d: (-sign * (d["right"] - d["left"]), d["model_point_id"],
                                                        d["period"]))[0]
                    assert (row[member]["model_point_id"], row[member]["period"], row[member]["absolute"]) == (
                        best["model_point_id"], best["period"], best["right"] - best["left"])
        deviating += bool(expected)
        one_sided += bool(result["added"] or result["removed"])
    assert deviating > 50 and one_sided > 50


# --- the reference example ----------------------------------------------------------


def test_the_reference_example_is_recomputed_by_the_core(tmp_path):
    folder = tmp_path / "reference"
    shutil.copytree(EXAMPLES / "reference", folder)
    for name in ("compare.result.json", "compare.deviations.csv", "compare.run-record.json",
                 "compare.signature-table.json"):
        (folder / name).unlink()
    with written_under("3.0"):  # the examples are 3.0 documents
        compared = compare(folder / "compare.request.json", signature_name="compare.signature-table.json")
    assert compared.outcome == "compared" and not compared.no_deviation
    for name in ("compare.result.json", "compare.deviations.csv", "compare.signature-table.json"):
        assert (folder / name).read_bytes() == (EXAMPLES / "reference" / name).read_bytes(), name
    # The run record names the execution: only its record id and its time differ.
    record = stored(folder / "compare.run-record.json")
    example = stored(EXAMPLES / "reference" / "compare.run-record.json")
    assert RECORD_ID.fullmatch(record["record_id"]) and record["record_id"] != example["record_id"]
    assert without_volatile(record) == without_volatile(example)


@pytest.mark.parametrize("name", ["signature-table", "signature-empty"])
def test_the_signature_table_examples_are_recomputed_by_the_core(tmp_path, name):
    folder = tmp_path / name
    shutil.copytree(EXAMPLES / name, folder)
    outputs = ("compare.result.json", "compare.deviations.csv", "compare.signature-table.json")
    for output in outputs:
        (folder / output).unlink()
    with written_under("3.0"):  # the examples are 3.0 documents
        compared = compare(folder / "compare.request.json", record_name=None,
                           signature_name="compare.signature-table.json")
    assert compared.outcome == "compared" and compared.no_deviation == (name == "signature-empty")
    for output in outputs:
        assert (folder / output).read_bytes() == (EXAMPLES / name / output).read_bytes(), output


# --- no file is overwritten ---------------------------------------------------------


@pytest.mark.parametrize("name", OUTPUTS)
def test_compare_overwrites_no_file(world, capsys, name):
    run_side(world, "left"), run_side(world, "right")
    path = compare_request(world)
    (world / name).write_bytes(b"kept")
    before = folder_hashes(world)
    assert main(["compare", str(path)]) == 2
    assert "exists already" in capsys.readouterr().err
    assert folder_hashes(world) == before
    assert main(["compare", str(world / "absent.json")]) == 2


# --- tolerance files ----------------------------------------------------------------


def test_a_tolerance_file_is_checked_against_the_schema_and_the_declared_quantities(tmp_path):
    quantities = [{"name": COUNT, "unit": "policies"}, {"name": CASH, "unit": "EUR"}]
    assert read_tolerance(None, quantities) == {"per_quantity": {}}  # there is no default profile
    path = tmp_path / "tolerance.json"
    profile = {"per_quantity": {CASH: entry(decimals=2)}}
    path.write_bytes(document_bytes(profile))
    assert read_tolerance(path, quantities) == profile
    for content in (b"", b'{"per_quantity": {}, "per_quantity": {}}', b'{"abs_tol": 0, "rel_tol": 0}',
                    document_bytes({"per_quantity": {"Provisionen": entry()}})):
        path.write_bytes(content)
        with pytest.raises(UsageError):
            read_tolerance(path, quantities)
    with pytest.raises(UsageError):
        read_tolerance(tmp_path / "absent.json", quantities)
    assert not isinstance(UsageError("x"), Rejection)


# --- a difference that is not finite ------------------------------------------------


def test_a_difference_that_is_not_finite_rejects_the_comparison_and_names_the_model_points(world, capsys):
    left = "id,first,last,base\nMP-A,0,0,-1e308\nMP-B,0,0,1\nMP-C,0,0,1.7976931348623157e308\n"
    right = "id,first,last,base\nMP-A,0,0,1e308\nMP-B,0,0,2\nMP-C,0,0,-1.7976931348623157e308\n"
    run_side(world, "left", left), run_side(world, "right", right)
    assert main(["compare", str(compare_request(world, {COUNT: entry(decimals=2)}))]) == 1
    output = capsys.readouterr().out
    assert "compare: rejected" in output and "diagnostic: non_finite_difference:" in output
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA) and result["outcome"] == "rejected"
    (diagnostic,) = result["diagnostics"]
    assert diagnostic["code"] == "non_finite_difference" and diagnostic["model_point_ids"] == ["MP-A", "MP-C"]
    # The result and its record are written; there is no deviation file and no table.
    assert written(world) == ["compare.result.json", "compare.run-record.json"]
    assert_record(world, "rejected", table=False)
    # Equal values are never subtracted: the same extreme values on both sides compare.
    for name in OUTPUTS:
        (world / name).unlink(missing_ok=True)
    assert main(["compare", str(compare_request(world, left="left", right="left"))]) == 0


# --- the engine versions of the two runs --------------------------------------------


def with_engine_version(world: Path, side: str, version: str | None) -> None:
    def edit(record):
        references = record["releases"][0]["references"]
        references[:] = [r for r in references if r["kind"] != "engine_version"]
        if version is not None:
            references.append({"kind": "engine_version", "value": version})
    edit_document(world / side / "run-record.json", edit)


@pytest.mark.parametrize("left, right, named", [
    ("engine 1", "engine 2", True), ("engine 1", "engine 1", False), ("engine 1", None, False),
    (None, None, False)])
def test_the_result_names_two_engine_versions_that_differ(world, capsys, left, right, named):
    run_side(world, "left"), run_side(world, "right", POINTS_MOVED)
    with_engine_version(world, "left", left), with_engine_version(world, "right", right)
    assert main(["compare", str(compare_request(world))]) == 1
    output = capsys.readouterr().out
    result = stored(world / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA) and result["outcome"] == "compared"
    if named:
        assert result["engine_version"] == {"left": left, "right": right}
        assert list(result)[list(result).index("right") + 1] == "engine_version"
        assert "engine version: left engine 1, right engine 2" in output
    else:
        assert "engine_version" not in result and "engine version" not in output
    # The member does not change the table.
    assert stored(world / "signature-table.json")["rows"]


def test_a_rejected_result_names_the_engine_versions_and_an_incompatible_one_does_not(world):
    run_side(world, "left", "id,first,last,base\nMP-A,0,0,-1e308\n")
    run_side(world, "right", "id,first,last,base\nMP-A,0,0,1e308\n")
    with_engine_version(world, "left", "engine 1"), with_engine_version(world, "right", "engine 2")
    result = compare(compare_request(world)).result
    assert result["outcome"] == "rejected" and result["engine_version"] == {"left": "engine 1", "right": "engine 2"}
    assert not schema_errors(result, COMPARE_SCHEMA)
    assert schema_errors({**result, "outcome": "incompatible"}, COMPARE_SCHEMA)
    assert not schema_errors({k: v for k, v in result.items() if k != "engine_version"} | {"outcome": "incompatible"},
                             COMPARE_SCHEMA)


# --- the deviation file -------------------------------------------------------------

HEADER = "model_point_id,period,quantity,left,right\n"
NAMES = [COUNT, CASH]


@pytest.mark.parametrize("body, code", [
    ("MP-A,0,Anzahl Verträge,1,1\n", "not_a_deviation"),
    ("MP-A,0,Anzahl Verträge,-0,0\n", "not_a_deviation"),
    ("MP-A,0,Provisionen,1,2\n", "unknown_quantity"),
    ("MP-A,0,Anzahl Verträge,1,2\nMP-A,0,Anzahl Verträge,1,2\n", "duplicate_coordinate"),
    ("MP-B,0,Anzahl Verträge,1,2\nMP-A,0,Anzahl Verträge,1,2\n", "export_format"),     # model point order
    ("MP-A,0,Netto-Cashflow,1,2\nMP-A,0,Anzahl Verträge,1,2\n", "export_format"),     # quantity order
    ("MP-A,1,Anzahl Verträge,1,2\nMP-A,0,Anzahl Verträge,1,2\n", "export_format"),    # period order
    ("MP-A,0,Anzahl Verträge,1,NaN\n", "non_finite_value"),
    ("MP-A,0,Anzahl Verträge,1,\"1,5\"\n", "number_format"),
    ("MP-A,0.5,Anzahl Verträge,1,2\n", "number_format"),
    ("MP-A,0,,1,2\n", "export_format"),
    ("MP-\x01,0,Anzahl Verträge,1,2\n", "export_format"),                              # a forbidden id
    ("MP-A,0,Anzahl Verträge,1\n", "export_format"),
])
def test_the_reader_of_the_deviation_file_applies_its_rules(tmp_path, body, code):
    path = tmp_path / "compare.deviations.csv"
    path.write_bytes((HEADER + body).encode("utf-8"))
    with pytest.raises(Rejection) as caught:
        read_deviations(path, NAMES)
    assert caught.value.code == code


def test_rule_13_judges_a_row_by_the_tolerance_of_the_compare_result(tmp_path):
    """A row within the tolerance of the result is no deviation, also when its values differ."""
    folder = tmp_path / "reference"
    shutil.copytree(EXAMPLES / "reference", folder)
    result = stored(folder / "compare.result.json")
    # Kosten 2. Ordnung ohne Provisionen allows 0.25 upwards: 100 against 100.25 lies on the bound.
    cost = "Kosten 2. Ordnung ohne Provisionen"
    for row, code in ((f"MP-0001,0,{cost},100,100.25\n", "not_a_deviation"),
                      (f"MP-0001,0,{cost},100.25,100\n", None)):
        path = folder / "compare.deviations.csv"
        path.write_bytes((HEADER + row).encode("utf-8"))
        result["deviations"] = {"path": path.name, "sha256": sha256_file(path)}
        if code is None:
            assert not no_deviation(result, folder)
        else:
            with pytest.raises(Rejection) as caught:
                no_deviation(result, folder)
            assert caught.value.code == code


def test_the_reader_of_the_deviation_file_takes_the_writer_form_and_the_reader_grammar(tmp_path):
    path = tmp_path / "compare.deviations.csv"
    path.write_bytes((HEADER + "MP-A,0,Anzahl Verträge,1,2\nMP-A,0,Netto-Cashflow,1.50,1E+1\n"
                      '"MP-Z,1",-1,Netto-Cashflow,-0,5e-324\n').encode("utf-8"))
    assert read_deviations(path, NAMES) == [
        {"model_point_id": "MP-A", "period": 0, "quantity": COUNT, "left": 1.0, "right": 2.0},
        {"model_point_id": "MP-A", "period": 0, "quantity": CASH, "left": 1.5, "right": 10.0},
        {"model_point_id": "MP-Z,1", "period": -1, "quantity": CASH, "left": 0.0, "right": 5e-324}]
    path.write_bytes(b"model_point_id,period,quantity,right,left\n")
    with pytest.raises(Rejection) as caught:
        read_deviations(path, NAMES)
    assert caught.value.code == "export_format"
    path.write_bytes(HEADER.encode("utf-8"))
    assert read_deviations(path, NAMES) == []


@pytest.mark.parametrize("case_id, code", [
    ("not-a-deviation", "not_a_deviation"), ("deviation-unknown-quantity", "unknown_quantity"),
    ("deviation-duplicate-coordinate", "duplicate_coordinate"), ("deviation-within-tolerance", "not_a_deviation")])
def test_the_negative_deviation_files_of_the_pack_are_rejected_by_the_core(case_id, code):
    folder = EXAMPLES / "negative" / case_id
    result = stored(folder / "compare.result.json")
    assert not schema_errors(result, COMPARE_SCHEMA)
    with pytest.raises(Rejection) as caught:
        no_deviation(result, folder)
    assert caught.value.code == code


def test_a_deviation_file_with_another_hash_is_rejected(tmp_path):
    folder = tmp_path / "reference"
    shutil.copytree(EXAMPLES / "reference", folder)
    result = stored(folder / "compare.result.json")
    assert not no_deviation(result, folder)
    (folder / "compare.deviations.csv").write_bytes(HEADER.encode("utf-8"))
    with pytest.raises(Rejection) as caught:
        no_deviation(result, folder)
    assert caught.value.code == "artifact_hash_mismatch"
    (folder / "compare.deviations.csv").unlink()
    with pytest.raises(Rejection) as caught:
        no_deviation(result, folder)
    assert caught.value.code == "artifact_missing"


def test_the_other_negative_cases_of_story_9_carry_the_diagnostic_the_core_gives(tmp_path):
    folder = tmp_path / "non-finite-difference"
    shutil.copytree(EXAMPLES / "negative" / "non-finite-difference", folder)
    (folder / "compare.result.json").unlink()
    with written_under("3.0"):  # the examples are 3.0 documents
        result = compare(folder / "compare.request.json", record_name=None).result
    assert (folder / "compare.result.json").read_bytes() == \
        (EXAMPLES / "negative" / "non-finite-difference" / "compare.result.json").read_bytes()
    assert result["diagnostics"][0]["model_point_ids"] == ["MP-0001"]
    assert sorted(p.name for p in folder.iterdir() if p.name.startswith("compare.")) == [
        "compare.request.json", "compare.result.json"]


# --- preloaded runs -------------------------------------------------------------------


def test_preloaded_runs_give_the_same_comparison_without_reading_the_runs_again(world, monkeypatch):
    """``compare(..., runs=...)`` writes the same documents as a comparison that reads both runs,
    and does not check the two runs again."""
    from degelmann.deltarecon import compare as compare_module

    per_quantity = PROFILES["relative"]
    left, right = run_side(world, "left", POINTS_LEFT), run_side(world, "right", POINTS_MOVED)
    compare_request(world, per_quantity)
    folders = {}
    for name in ("read", "preloaded"):
        folders[name] = world / name
        for part in ("left", "right", "compare.request.json"):
            (shutil.copytree if part in ("left", "right") else shutil.copyfile)(world / part, folders[name] / part)
    done = {"read": compare(folders["read"] / "compare.request.json")}
    checked = []
    monkeypatch.setattr(compare_module, "check_run", lambda *arguments: checked.append(arguments))
    runs = (CheckedRun(left.response, left.values), CheckedRun(right.response, right.values))
    done["preloaded"] = compare(folders["preloaded"] / "compare.request.json", runs=runs)
    assert checked == []

    assert done["read"].outcome == done["preloaded"].outcome == "compared"
    assert done["read"].result == done["preloaded"].result and done["read"].deviations == done["preloaded"].deviations
    assert done["read"].deviations and done["read"].table == done["preloaded"].table
    for name in ("compare.result.json", "compare.deviations.csv", "signature-table.json"):
        assert (folders["read"] / name).read_bytes() == (folders["preloaded"] / name).read_bytes(), name
    one, two = (stored(folder / "compare.run-record.json") for folder in folders.values())
    assert {**one, "record_id": None, "recorded_at": None} == {**two, "record_id": None, "recorded_at": None}


def test_preloaded_runs_still_check_the_artifacts_the_request_names(world):
    left, right = run_side(world, "left", POINTS_LEFT), run_side(world, "right", POINTS_MOVED)
    path = compare_request(world)
    response = world / "right" / "response.json"
    response.write_bytes(response.read_bytes() + b" ")
    runs = (CheckedRun(left.response, left.values), CheckedRun(right.response, right.values))
    done = compare(path, runs=runs)
    assert done.outcome == "rejected" and done.result["diagnostics"][0]["code"] == "artifact_hash_mismatch"
