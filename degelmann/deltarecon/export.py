"""The per-model-point export and the deviation file: CSV profile, number format, and rules.

The writer writes the writer form in deterministic order. The reader accepts the reader
grammar of ``contracts/v3/README.md``. ``check_export`` applies rules 9 to 13 of
``contracts/v3/run.md`` to a succeeded response and its export; ``read_deviations``
applies rules 9 to 13 of ``contracts/v3/compare.md`` to a deviation file.
"""
from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path

from .documents import Rejection, validator, write_new

NUMBER = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?(e-?[1-9][0-9]*)?")
INTEGER = re.compile(r"0|-?[1-9][0-9]*")
READER_NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
READER_INTEGER = re.compile(r"-?[0-9]+")
NON_FINITE = re.compile(r"[+-]?(nan|inf|infinity)", re.IGNORECASE)
KEY_COLUMNS = ["model_point_id", "period"]
DEVIATION_COLUMNS = ["model_point_id", "period", "quantity", "left", "right"]


# --- number format ------------------------------------------------------------------


def is_readable_number(text: str) -> bool:
    """The reader grammar of the number format: a finite decimal number with a point."""
    return bool(READER_NUMBER.fullmatch(text)) and abs(float(text)) != float("inf")


def is_profile_number(text: str) -> bool:
    """The writer grammar of the number format: grammar, finite, shortest round-trip digits."""
    if not NUMBER.fullmatch(text):
        return False
    value = float(text)
    if value == 0:
        return text == "0"
    if value in (float("inf"), float("-inf")) or value != value:
        return False

    def digits(literal: str) -> str:
        mantissa = literal.lower().lstrip("-").split("e")[0].replace(".", "")
        return mantissa.strip("0")

    return digits(text) == digits(repr(value))


def format_number(value) -> str:
    """A finite number in writer form: shortest round-trip digits, then normalised."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("a non-finite value has no writer form")
    if value == 0:
        return "0"
    mantissa, _, exponent = repr(value).partition("e")
    if mantissa.endswith(".0"):
        mantissa = mantissa[:-2]
    if not exponent:
        return mantissa
    sign = "-" if exponent.startswith("-") else ""
    return f"{mantissa}e{sign}{exponent.lstrip('+-').lstrip('0')}"


def read_number(text: str, source: str = "export") -> float:
    """A quantity value under the reader grammar."""
    if READER_NUMBER.fullmatch(text):
        value = float(text)
        if math.isfinite(value):
            return value
        raise Rejection("number_format", f"The number {text[:40]!r} is too large for a finite value.")
    if NON_FINITE.fullmatch(text):
        raise Rejection("non_finite_value", f"The {source} holds the non-finite value {text!r}.")
    raise Rejection("number_format", f"The field {text[:40]!r} is not a number of the number format.")


# --- writer -------------------------------------------------------------------------


def _field(text: str) -> str:
    if any(mark in text for mark in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def export_bytes(quantity_names: list[str], rows) -> bytes:
    """The export of ``rows``, each ``(model_point_id, period, values)``, in writer order."""
    lines = [",".join(_field(name) for name in KEY_COLUMNS + list(quantity_names))]
    for model_point_id, period, values in sorted(rows, key=lambda row: (row[0], row[1])):
        if len(values) != len(quantity_names):
            raise ValueError("a row does not hold one value per quantity")
        lines.append(",".join([_field(model_point_id), str(int(period))]
                              + [format_number(value) for value in values]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_export(path: Path, quantity_names: list[str], rows) -> None:
    write_new(path, export_bytes(quantity_names, rows))


def deviation_bytes(deviations: list[dict]) -> bytes:
    """The deviation file of ``deviations``, each a dict with the five columns, in the given order.

    The caller orders the deviations as the README states; the writer keeps that order.
    """
    lines = [",".join(DEVIATION_COLUMNS)]
    for deviation in deviations:
        lines.append(",".join([_field(deviation["model_point_id"]), str(int(deviation["period"])),
                               _field(deviation["quantity"]), format_number(deviation["left"]),
                               format_number(deviation["right"])]))
    return ("\n".join(lines) + "\n").encode("utf-8")


# --- reader -------------------------------------------------------------------------


def export_rows(path: Path) -> list[list[str]]:
    data = path.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n") and not data.startswith(b"\xef\xbb\xbf"), path
    return list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))


def export_errors(path: Path, check=None, integer=INTEGER) -> list[str]:
    """Violations of the writer form, or of another form given by check and integer.

    A file with the header of a deviation file is checked as one: its third column holds
    a quantity name, not a number.
    """
    check = check or is_profile_number
    rows = export_rows(path)
    header, errors = rows[0], []
    names = 3 if header == DEVIATION_COLUMNS else 2  # the columns before the numbers
    if header[:2] != KEY_COLUMNS or len(header) < 3:
        errors.append("header")
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != len(header) or not all(row[:names]):
            errors.append(f"line {number}: fields")
            continue
        if not integer.fullmatch(row[1]):
            errors.append(f"line {number}: period {row[1]!r}")
        errors.extend(f"line {number}: number {text!r}" for text in row[names:]
                      if not check(text))
    return errors


def _csv_rows(path: Path, source: str) -> list[list[str]]:
    """The rows of a file under the CSV profile. ``source`` names the file in a diagnostic."""
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise Rejection("export_format", f"The {source} starts with a byte order mark.")
    if b"\r" in data:
        raise Rejection("export_format", f"The {source} holds a carriage return; the line end is a line feed.")
    if not data.endswith(b"\n"):
        raise Rejection("export_format", f"The {source} does not end with a line feed.")
    try:
        text = data.decode("utf-8")
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise Rejection("export_format", f"The {source} is not CSV under the CSV profile: {exc}.") from None
    if "".join(",".join(_field(field) for field in row) + "\n" for row in rows) != text:
        raise Rejection("export_format", f"A field of the {source} is quoted otherwise than the CSV profile states.")
    return rows


def read_export(path: Path, quantity_names: list[str]) -> list[tuple[str, int, list[float]]]:
    """Read an export under the CSV profile and the reader grammar (run rule 9)."""
    rows = _csv_rows(path, "export")
    if not rows or rows[0] != KEY_COLUMNS + list(quantity_names):
        raise Rejection("export_format", "The header of the export does not match the declared quantities.")
    result = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != len(rows[0]):
            raise Rejection("export_format", f"Line {number} of the export has {len(row)} fields, "
                            f"the header has {len(rows[0])}.")
        if not row[0]:
            raise Rejection("export_format", f"Line {number} of the export has an empty model point id.")
        if not READER_INTEGER.fullmatch(row[1]):
            raise Rejection("number_format", f"Line {number} of the export has the period {row[1][:40]!r}.")
        result.append((row[0], int(row[1]), [read_number(text) for text in row[2:]]))
    return result


def read_deviations(path: Path, quantity_names: list[str], deviates=None) -> list[dict]:
    """Read a deviation file and apply rules 9 to 13 of the compare contract, in their order.

    ``quantity_names`` are the quantities of the compare result, in their order.
    ``deviates`` judges a row by the tolerance rule of the compare result (rule 13); without
    it a row deviates when its two values differ. Return
    one entry per row, with the members of the columns.
    """
    source = "deviation file"
    rows = _csv_rows(path, source)  # rule 9
    if not rows or rows[0] != DEVIATION_COLUMNS:
        raise Rejection("export_format", f"The header of the deviation file is not {','.join(DEVIATION_COLUMNS)}.")
    deviations = []
    id_schema = validator("common.schema.json#/$defs/id")
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != len(DEVIATION_COLUMNS):
            raise Rejection("export_format", f"Line {number} of the deviation file has {len(row)} fields, "
                            f"the header has {len(DEVIATION_COLUMNS)}.")
        if not row[0] or not row[2]:
            raise Rejection("export_format", f"Line {number} of the deviation file has an empty field.")
        if not id_schema.is_valid(row[0]):
            raise Rejection("export_format", f"Line {number} of the deviation file has a model point id that "
                            "the schema of an id forbids: it holds a control character.")
        if not READER_INTEGER.fullmatch(row[1]):
            raise Rejection("number_format", f"Line {number} of the deviation file has the period {row[1][:40]!r}.")
        deviations.append({"model_point_id": row[0], "period": int(row[1]), "quantity": row[2],
                           "left": read_number(row[3], source), "right": read_number(row[4], source)})

    position = {name: index for index, name in enumerate(quantity_names)}
    unknown = [d for d in deviations if d["quantity"] not in position]  # rule 10
    if unknown:
        raise Rejection("unknown_quantity", f"The deviation file names the quantity {unknown[0]['quantity']!r}, "
                        "which the compare result does not declare.",
                        model_point_ids=_ids(d["model_point_id"] for d in unknown))
    keys = [(d["model_point_id"], d["period"], position[d["quantity"]]) for d in deviations]
    seen, repeated = set(), set()
    for key in keys:  # rule 11
        if key in seen:
            repeated.add(key[0])
        seen.add(key)
    if repeated:
        raise Rejection("duplicate_coordinate", "The deviation file repeats a coordinate.",
                        model_point_ids=_ids(repeated))
    if keys != sorted(keys):  # rule 12
        raise Rejection("export_format", "The rows of the deviation file are not ordered by model point id, "
                        "period, and quantity order.")
    deviates = deviates or (lambda d: d["left"] != d["right"])
    within = [d["model_point_id"] for d in deviations if not deviates(d)]  # rule 13
    if within:
        raise Rejection("not_a_deviation", "A row of the deviation file does not deviate by the tolerance "
                        "rule: its values are equal or differ within the tolerance.",
                        model_point_ids=_ids(within))
    return deviations


# --- completeness -------------------------------------------------------------------


def _ids(values) -> list[str]:
    return sorted(set(values))


def check_export(response: dict, path: Path) -> dict[tuple[str, int], list[float]]:
    """Rules 9 to 13 of the run contract. Return the values by model point id and period."""
    rows = read_export(path, [quantity["name"] for quantity in response["quantities"]])  # rule 9
    # A period written as ``12.0`` passes the schema as an integer and is read as one.
    ranges = [{**point, "first_period": int(point["first_period"]), "last_period": int(point["last_period"])}
              for point in response["model_points"]]
    named = [point["model_point_id"] for point in ranges]

    selection = response["selection"]  # rule 10
    if selection["mode"] == "subset":
        missing = set(selection["model_point_ids"]) - set(named)
        if missing:
            raise Rejection("missing_coordinate", "A selected model point is absent from the response.",
                            model_point_ids=_ids(missing))
        surplus = set(named) - set(selection["model_point_ids"])
        if surplus:
            raise Rejection("unrequested_coordinate", "The response names a model point that was not selected.",
                            model_point_ids=_ids(surplus))

    repeated = {name for name in named if named.count(name) > 1}  # rule 11
    if repeated:
        raise Rejection("inconsistent_response", "The response lists a model point twice.",
                        model_point_ids=_ids(repeated))
    reversed_ranges = [p["model_point_id"] for p in ranges if p["first_period"] > p["last_period"]]
    if reversed_ranges:
        raise Rejection("inconsistent_response", "A period range of the response is reversed.",
                        model_point_ids=_ids(reversed_ranges))

    expected = {(p["model_point_id"], period)  # rule 12
                for p in ranges for period in range(p["first_period"], p["last_period"] + 1)}
    values: dict[tuple[str, int], list[float]] = {}
    duplicates = []
    for model_point_id, period, numbers in rows:
        if (model_point_id, period) in values:
            duplicates.append(model_point_id)
        values[(model_point_id, period)] = numbers
    if duplicates:
        raise Rejection("duplicate_coordinate", "The export repeats a model point and period.",
                        model_point_ids=_ids(duplicates))
    absent = expected - set(values)
    if absent:
        raise Rejection("missing_coordinate", "The export lacks a row of a declared period range.",
                        model_point_ids=_ids(key[0] for key in absent))
    further = set(values) - expected
    if further:
        raise Rejection("unrequested_coordinate", "The export holds a row outside the declared period ranges.",
                        model_point_ids=_ids(key[0] for key in further))

    if response["export"]["data_rows"] != len(expected):  # rule 13
        raise Rejection("inconsistent_response",
                        f"The response states {response['export']['data_rows']} rows; "
                        f"its period ranges add up to {len(expected)}.")
    return values
