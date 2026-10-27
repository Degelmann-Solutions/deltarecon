"""The deviation signature table of ``contracts/v3/compare.md``.

The table condenses one compare result with the outcome ``compared`` and its deviation
file: one row per stage and quantity that deviates. It is a function of that result and the
rows of that file alone and holds no timestamp, so the same comparison gives the same bytes.
This module knows no engine and reads no file: the caller reads the deviation file.
"""
from __future__ import annotations

from .documents import CONTRACT_VERSION
from .export import format_number


def _extreme(deviation: dict, absolute: float) -> dict:
    scale = max(abs(deviation["left"]), abs(deviation["right"]))
    return {"model_point_id": deviation["model_point_id"], "period": deviation["period"],
            "absolute": absolute, "relative": absolute / scale}


def signature_table(result: dict, deviations: list[dict]) -> dict:
    """The signature table of a compare result with the outcome ``compared``.

    ``deviations`` are the rows of the deviation file the result references, as read.
    """
    if result.get("document") != "compare_result" or result.get("outcome") != "compared":
        raise ValueError("a signature table is built from a compare result with the outcome compared only")
    stage = result["stage"]
    by_quantity: dict[str, list[dict]] = {}
    for deviation in deviations:
        by_quantity.setdefault(deviation["quantity"], []).append(deviation)
    rows = []
    for quantity in (entry["name"] for entry in result["quantities"]):
        deviations = by_quantity.get(quantity)
        if not deviations:
            continue
        # The difference of the exported values, before any rounding. Rounding keeps the
        # order of two values, so the sign is that of the difference the rule judged.
        differences = [deviation["right"] - deviation["left"] for deviation in deviations]
        above = [index for index, difference in enumerate(differences) if difference > 0]
        below = [index for index, difference in enumerate(differences) if difference < 0]
        periods = [deviation["period"] for deviation in deviations]
        row = {
            "stage": stage, "quantity": quantity,
            "deviating_model_points": len({deviation["model_point_id"] for deviation in deviations}),
            "deviating_coordinates": len(deviations),
            "right_above_left": len(above), "right_below_left": len(below),
            "first_period": min(periods), "last_period": max(periods),
        }
        # Of equal differences the lowest model point id, then the lowest period: the
        # choice does not depend on the order in which the result stores its deviations.
        def place(i: int) -> tuple[str, int]:
            return deviations[i]["model_point_id"], deviations[i]["period"]

        if above:
            index = min(above, key=lambda i: (-differences[i], place(i)))
            row["largest_increase"] = _extreme(deviations[index], differences[index])
        if below:
            index = min(below, key=lambda i: (differences[i], place(i)))
            row["largest_decrease"] = _extreme(deviations[index], differences[index])
        rows.append(row)
    return {"document": "signature_table", "contract_version": CONTRACT_VERSION, "stage": stage,
            "compare_id": result["compare_id"], "left": result["left"], "right": result["right"],
            "rows": rows}


# --- text for the command line ------------------------------------------------------


def _rounded(value: float) -> str:
    """``value`` at four significant digits. The text is for a reader; the table holds the exact value."""
    return format_number(float(f"{value:.4g}"))


def _extreme_text(label: str, extreme: dict | None) -> str:
    if extreme is None:
        return f"    {label}: none"
    return (f"    {label}: {_rounded(extreme['absolute'])} ({_rounded(100 * extreme['relative'])} %) "
            f"at model point {extreme['model_point_id']}, period {extreme['period']}")


def render_table(table: dict) -> list[str]:
    """The signature table as text lines."""
    if not table["rows"]:
        return ["signature table: no rows"]
    lines = ["signature table:"]
    for row in table["rows"]:
        lines.append(f"  {row['stage']} / {row['quantity']}: {row['deviating_model_points']} model points, "
                     f"{row['deviating_coordinates']} coordinates, periods {row['first_period']} to "
                     f"{row['last_period']}, {row['right_above_left']} above, {row['right_below_left']} below")
        lines.append(_extreme_text("largest increase", row.get("largest_increase")))
        lines.append(_extreme_text("largest decrease", row.get("largest_decrease")))
    return lines


def render_model_points(result: dict, deviations: list[dict]) -> list[str]:
    """One stage-labelled line per deviating model point of a compare result and its deviations."""
    counts: dict[str, list[int]] = {}
    for deviation in deviations:
        entry = counts.setdefault(deviation["model_point_id"], [0, deviation["period"], deviation["period"]])
        entry[0] += 1
        entry[1], entry[2] = min(entry[1], deviation["period"]), max(entry[2], deviation["period"])
    return [f"deviation: {result['stage']} / model point {model_point_id}: {counts[model_point_id][0]} "
            f"coordinates, periods {counts[model_point_id][1]} to {counts[model_point_id][2]}"
            for model_point_id in result["deviating_model_points"]]


def render_coverage(result: dict) -> list[str]:
    """One line per added and removed period range of a compare result."""
    return [f"{label}: {result['stage']} / model point {entry['model_point_id']}, periods "
            f"{entry['first_period']} to {entry['last_period']}"
            for label in ("added", "removed") for entry in result[label]]
