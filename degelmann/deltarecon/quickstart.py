"""The guided quick start: ``deltarecon quickstart``.

The demo runs the steps of the README quick start without ``replay`` into the new folder
``runs/quickstart-<UTC timestamp>/`` below the working directory: ``request`` silently, then
``run``, ``regression``, ``derive`` and ``search`` as four explained steps. Before each of the four
it explains the step, shows it as a single command and waits for Enter (not with ``--no-pause``);
after it, it summarises the outcome from the files the step wrote. Each step runs in this process
through ``__main__.main`` with its output captured, so it makes every check of the single command.

The texts are in English and German. Without ``--lang`` the first non-empty one of ``LC_ALL``,
``LC_MESSAGES`` and ``LANG`` decides, else ``locale.getlocale()``: a value that starts with ``de``
or ``German`` gives German, anything else English.

The tolerance profile of the search is read from the copy a wheel carries as
``degelmann/deltarecon/profiles`` beside this module, else from ``profiles/`` at the root of a checkout.

Exit status: 0 when every step had its expected status, 1 when one had another (its captured output
is printed and no later step runs), 2 when the folder exists already, 130 when the demo is
interrupted.
"""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import locale
import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Callable

OLDER = "fa368575a66d97c94e96dffc62b273ec95511b12"  # release N on the fixed model
NEWER = "887b7181d22550eda2fb52fa1a6bd77376d4eb2e"  # the state N+1, 32 revisions later
LABEL = "N"
RUN_ID = "run-n-full"
QUANTITY = "Bruttobeitrag"
PERIODS = "0-59"
PROFILE_NAME = "tolerance-bruttobeitrag.json"
RUNS = Path("runs")
PACKAGED_PROFILES = Path(__file__).resolve().parent / "profiles"
PROFILES = PACKAGED_PROFILES if PACKAGED_PROFILES.is_dir() else Path(__file__).resolve().parents[2] / "profiles"
LANGUAGE_VARIABLES = ("LC_ALL", "LC_MESSAGES", "LANG")
# The expected exit status of each step: the regression shows the deviation between N and N+1.
EXPECT = {"request": 0, "run": 0, "regression": 1, "derive": 0, "search": 0}

TEXTS = {
    "en": {
        "opening": (
            "DeltaRecon guided quick start. The demo compares two states of the reference model delib-history, "
            "a term life insurance with 350 model points: release N and the state N+1, 32 revisions later. "
            "In four steps it shows how DeltaRecon finds a deviation between two releases and traces it back "
            "to the changes that cause it. Every file goes into {folder}."),
        "prompt": "Press Enter to continue ...",
        "before_run": (
            "Step 1 of 4: compute release N. DeltaRecon runs the model at release N (revision {short}) for all "
            "350 model points and records the result together with its full origin: code, parameters and "
            "portfolio data. This result is the reference that every later step checks against."),
        "after_run": (
            "Release N is computed: {points} model points, {rows} result rows. Files in {folder}: results.csv "
            "(the results), response.json and run-record.json (the record of what was computed with what)."),
        "before_regression": (
            "Step 2 of 4: regression against N+1. DeltaRecon runs the newer state N+1 (revision {short}) on the "
            "same portfolio data as release N and compares the two results value by value. This shows whether "
            "and where the results of the two releases differ. A deviation is expected here; the command "
            "reports it with exit status 1."),
        "after_regression": (
            "The regression shows a deviation: {coordinates} values in {points} model points differ. "
            "Per quantity:"),
        "regression_row": "  {quantity}: {points} model points, {coordinates} values, periods {first} to {last}",
        "after_regression_end": (
            "The deviation is the expected outcome; the demo goes on. Files in {folder}: compare.result.json, "
            "compare.deviations.csv (every differing value), signature-table.json (the table above)."),
        "before_derive": (
            "Step 3 of 4: the changes between N and N+1. DeltaRecon reads the revision history between the two "
            "states and lists every change on its own, in the order in which it was made. Each change is one "
            "revision and is classified: data (the portfolio), parameter (tables such as lapse or cost rates), "
            "code (the calculation rules), or none of these (for example documentation only)."),
        "after_derive": "{count} changes: {data} data, {parameter} parameter, {code} code, {none} without a class.",
        "derive_row": "  {short} [{classes}] {description}",
        "classes": {"data": "data", "parameter": "parameter", "code": "code"},
        "no_class": "no class",
        "after_derive_end": "File: {path} (the change manifest).",
        "before_search": (
            "Step 4 of 4: find the cause in the Bruttobeitrag. Which of the {count} changes cause the deviation "
            "in the Bruttobeitrag, the gross premium, in the first five projection years (periods 0 to 59, one "
            "period per month)? DeltaRecon does not compute every intermediate state; it halves the history "
            "until each deviation belongs to a single change. A deviation is a change of the Bruttobeitrag by "
            "more than one cent per model point and month (the tolerance profile). The portfolio data stay at "
            "release N."),
        "after_search": (
            "Found with {run} of {walk} intermediate states computed ({saved} saved). These changes cause the "
            "deviation in the Bruttobeitrag:"),
        "search_row": "  {short} {description}: sum of the deviation {sum}",
        "not_resolved": (
            "Not resolved: the changes {shorts} exceed the tolerance only together; each one alone stays below "
            "it. DeltaRecon therefore attributes this part of the deviation to none of them."),
        "not_shown": (
            "Not shown: the effect of {count} change(s) of the portfolio data, since the portfolio data stay at "
            "release N."),
        "after_search_end": "Result: {path}.",
        "closing": (
            "Done. Every file is in {folder}. Each step also runs on its own as the command shown before it."),
        "stopped": "stopped",
    },
    "de": {
        "opening": (
            "DeltaRecon – geführter Quick Start. Die Vorführung vergleicht zwei Stände des Referenzmodells "
            "delib-history, einer Risikolebensversicherung mit 350 Modellpunkten: Release N und den Stand N+1, "
            "32 Revisionen später. In vier Schritten zeigt sie, wie DeltaRecon eine Abweichung zwischen zwei "
            "Releases findet und auf die Änderungen zurückführt, die sie verursachen. Alle Dateien landen in "
            "{folder}."),
        "prompt": "Weiter mit der Eingabetaste ...",
        "before_run": (
            "Schritt 1 von 4: Release N rechnen. DeltaRecon rechnet das Modell im Stand von Release N (Revision "
            "{short}) für alle 350 Modellpunkte und hält das Ergebnis mit seiner vollständigen Herkunft fest: "
            "Code, Parameter und Bestandsdaten. Dieses Ergebnis ist die Referenz, gegen die jeder weitere Schritt "
            "prüft."),
        "after_run": (
            "Release N ist gerechnet: {points} Modellpunkte, {rows} Ergebniszeilen. Dateien in {folder}: "
            "results.csv (die Ergebnisse), response.json und run-record.json (der Nachweis, womit was gerechnet "
            "wurde)."),
        "before_regression": (
            "Schritt 2 von 4: Regression gegen N+1. DeltaRecon rechnet den neueren Stand N+1 (Revision {short}) "
            "auf denselben Bestandsdaten wie Release N und vergleicht beide Ergebnisse Wert für Wert. So zeigt "
            "sich, ob und wo sich die Ergebnisse der beiden Releases unterscheiden. Eine Abweichung ist hier "
            "erwartet; der Befehl meldet sie mit dem Exit-Status 1."),
        "after_regression": (
            "Die Regression zeigt eine Abweichung: {coordinates} Werte in {points} Modellpunkten weichen ab. "
            "Je Größe:"),
        "regression_row": "  {quantity}: {points} Modellpunkte, {coordinates} Werte, Perioden {first} bis {last}",
        "after_regression_end": (
            "Die Abweichung ist das erwartete Ergebnis; die Vorführung geht weiter. Dateien in {folder}: "
            "compare.result.json, compare.deviations.csv (jeder abweichende Wert), signature-table.json (die "
            "Tabelle oben)."),
        "before_derive": (
            "Schritt 3 von 4: die Änderungen zwischen N und N+1. DeltaRecon liest die Versionsgeschichte zwischen "
            "den beiden Ständen und listet jede Änderung einzeln auf, in der Reihenfolge, in der sie gemacht "
            "wurde. Jede Änderung ist eine Revision und wird eingeordnet: Daten (der Bestand), Parameter "
            "(Tabellen wie Storno- oder Kostensätze), Code (die Rechenvorschriften) oder nichts davon (zum "
            "Beispiel nur Dokumentation)."),
        "after_derive": (
            "{count} Änderungen: {data} Daten, {parameter} Parameter, {code} Code, {none} ohne Einordnung."),
        "derive_row": "  {short} [{classes}] {description}",
        "classes": {"data": "Daten", "parameter": "Parameter", "code": "Code"},
        "no_class": "ohne Einordnung",
        "after_derive_end": "Datei: {path} (das Änderungsverzeichnis).",
        "before_search": (
            "Schritt 4 von 4: die Ursache im Bruttobeitrag suchen. Welche der {count} Änderungen verursachen die "
            "Abweichung im Bruttobeitrag in den ersten fünf Projektionsjahren (Perioden 0 bis 59, eine Periode je "
            "Monat)? DeltaRecon rechnet nicht jeden Zwischenstand, sondern halbiert die Versionsgeschichte, bis "
            "jede Abweichung einer einzelnen Änderung zugeordnet ist. Als Abweichung zählt eine Änderung des "
            "Bruttobeitrags um mehr als einen Cent je Modellpunkt und Monat (das Toleranzprofil). Die "
            "Bestandsdaten bleiben auf dem Stand von Release N."),
        "after_search": (
            "Gefunden mit {run} von {walk} Zwischenständen ({saved} gespart). Diese Änderungen verursachen die "
            "Abweichung im Bruttobeitrag:"),
        "search_row": "  {short} {description}: Summe der Abweichung {sum}",
        "not_resolved": (
            "Nicht aufgelöst: Die Änderungen {shorts} überschreiten die Toleranz nur zusammen; jede einzelne "
            "bleibt darunter. DeltaRecon ordnet diesen Teil der Abweichung daher keiner von ihnen zu."),
        "not_shown": (
            "Nicht gezeigt: die Wirkung von {count} Änderung(en) der Bestandsdaten, da die Bestandsdaten auf dem "
            "Stand von Release N bleiben."),
        "after_search_end": "Ergebnis: {path}.",
        "closing": (
            "Fertig. Alle Dateien liegen in {folder}. Jeder Schritt läuft auch einzeln, als der Befehl, der vor "
            "ihm gezeigt wurde."),
        "stopped": "abgebrochen",
    },
}


def system_language(env=None, getlocale: Callable = locale.getlocale) -> str:
    """``de`` or ``en`` from the first non-empty one of ``LC_ALL``, ``LC_MESSAGES`` and ``LANG``,
    else from ``getlocale()``."""
    env = os.environ if env is None else env
    value = next((env[name] for name in LANGUAGE_VARIABLES if env.get(name)), None)
    if value is None:
        try:
            value = getlocale()[0]
        except (ValueError, TypeError):
            value = None
    return "de" if (value or "").lower().startswith(("de", "german")) else "en"


def profile_path() -> Path:
    """The tolerance profile of the search: the wheel's copy beside this module, else the checkout's."""
    return PROFILES / PROFILE_NAME


def integer(value: int, lang: str) -> str:
    """A whole number with the thousands separator of the language: ``80,580`` or ``80.580``."""
    text = f"{value:,}"
    return text.replace(",", ".") if lang == "de" else text


def signed(value: float | None, lang: str) -> str:
    """A sum with sign and two decimals: ``+24,110.00`` or ``+24.110,00``."""
    if value is None:
        return "-"
    text = f"{value:+,.2f}"
    return text.translate(str.maketrans(",.", ".,")) if lang == "de" else text


def short(revision: str) -> str:
    return revision[:7]


def shown(path: Path | str) -> str:
    """``path`` relative to the working directory when it lies below it, else absolute."""
    path = Path(path)
    try:
        relative = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        return str(path)
    return str(path) if relative.startswith("..") else relative


def command_line(argv: list[str]) -> str:
    return " ".join(["deltarecon", *(f'"{a}"' if " " in a or not a else a for a in argv)])


def main_step(argv: list[str]) -> tuple[int, str]:
    """Run one command through ``__main__.main`` in this process: its exit status and its output."""
    from .__main__ import main

    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            status = main(argv)
        except SystemExit as exit_:  # a usage error of argparse
            status = exit_.code if isinstance(exit_.code, int) else 2
    return status, output.getvalue()


def steps(folder: Path, profile: str, repositories: str | None = None) -> dict[str, list[str]]:
    """The argv of each step, ``folder`` in place of ``runs/``."""
    record = str(folder / "n-full" / "run-record.json")
    newer = str(folder / "regression-n" / "run" / "run-record.json")
    argvs = {
        "request": ["request", "--revision", OLDER, "--label", LABEL, "--run-id", RUN_ID,
                    "--output", str(folder / "n-full" / "request.json")],
        "run": ["run", str(folder / "n-full" / "request.json")],
        "regression": ["regression", record, "--revision", NEWER, "--output", str(folder / "regression-n")],
        "derive": ["derive", record, newer, "--output", str(folder / "changes.json")],
        "search": ["search", record, newer, "--quantity", QUANTITY, "--periods", PERIODS, "--tolerance", profile,
                   "--target-only", "--output", str(folder / "search")],
    }
    if repositories is not None:
        for argv in argvs.values():
            argv += ["--repositories", repositories]
    return argvs


def read(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def quickstart(lang: str, pause: bool = True, repositories: str | None = None,
               step: Callable[[list[str]], tuple[int, str]] | None = None, ask: Callable = input,
               now: datetime.datetime | None = None) -> int:
    """Run the guided quick start; the exit status."""
    step = step or main_step
    texts = TEXTS[lang]
    now = now or datetime.datetime.now(datetime.timezone.utc)
    folder = RUNS / f"quickstart-{now:%Y%m%dT%H%M%SZ}"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    width = max(40, min(shutil.get_terminal_size((100, 24)).columns, 100) - 1)

    def say(line: str = "") -> None:  # a character the console cannot encode must not end the demo
        print(line.encode(encoding, "replace").decode(encoding, "replace"), flush=True)

    def paragraph(key: str, **values) -> None:
        say(textwrap.fill(texts[key].format(**values), width, break_long_words=False, break_on_hyphens=False))

    try:
        folder.mkdir(parents=True)
    except FileExistsError:
        print(f"error: {folder} exists already", file=sys.stderr)
        return 2
    argvs = steps(folder, shown(profile_path()), repositories)

    def execute(name: str) -> bool:
        status, output = step(argvs[name])
        if status != EXPECT[name]:
            for line in output.splitlines():
                say(line)
            return False
        return True

    def explain(key: str, name: str, **values) -> None:
        say()
        paragraph(key, **values)
        say()
        say(command_line(argvs[name]))
        if pause:
            try:
                ask(texts["prompt"] + " ")
            except EOFError:  # no more input counts as Enter
                say()

    try:
        paragraph("opening", folder=shown(folder))
        if not execute("request"):
            return 1

        explain("before_run", "run", short=short(OLDER))
        if not execute("run"):
            return 1
        response = read(folder / "n-full" / "response.json")
        say()
        paragraph("after_run", points=integer(len(response["model_points"]), lang),
                  rows=integer(response["export"]["data_rows"], lang), folder=shown(folder / "n-full"))

        explain("before_regression", "regression", short=short(NEWER))
        if not execute("regression"):
            return 1
        regression = folder / "regression-n"
        compared = read(regression / "compare.result.json")
        rows = read(regression / "signature-table.json")["rows"]
        say()
        paragraph("after_regression", coordinates=integer(sum(r["deviating_coordinates"] for r in rows), lang),
                  points=integer(len(compared["deviating_model_points"]), lang))
        for row in rows:
            say(texts["regression_row"].format(
                quantity=row["quantity"], points=integer(row["deviating_model_points"], lang),
                coordinates=integer(row["deviating_coordinates"], lang), first=row["first_period"],
                last=row["last_period"]))
        paragraph("after_regression_end", folder=shown(regression))

        explain("before_derive", "derive")
        if not execute("derive"):
            return 1
        changes = read(folder / "changes.json")["changes"]
        descriptions = {change["id"]: change["description"].splitlines()[0] if change["description"] else ""
                        for change in changes}
        counts = {kind: integer(sum(kind in change["class"] for change in changes), lang)
                  for kind in ("data", "parameter", "code")}
        say()
        paragraph("after_derive", count=integer(len(changes), lang),
                  none=integer(sum(not change["class"] for change in changes), lang), **counts)
        for change in changes:
            classes = ", ".join(texts["classes"][kind] for kind in change["class"]) or texts["no_class"]
            say(texts["derive_row"].format(short=short(change["id"]), classes=classes,
                                           description=descriptions[change["id"]]))
        paragraph("after_derive_end", path=shown(folder / "changes.json"))

        explain("before_search", "search", count=integer(len(changes), lang))
        if not execute("search"):
            return 1
        result = read(folder / "search" / "search.result.json")
        runs = result["runs"]
        say()
        paragraph("after_search", run=integer(runs["search"], lang), walk=integer(runs["walk"], lang),
                  saved=integer(runs["saved"], lang))
        for entry in result["contributions"]:
            for contribution in entry["contributions"]:
                if contribution["contributes"]:
                    revisions = entry["revisions"]
                    description = descriptions.get(revisions[0], "") if len(revisions) == 1 else ""
                    say(texts["search_row"].format(short=", ".join(short(r) for r in revisions),
                                                   description=description,
                                                   sum=signed(contribution.get("sum"), lang)))
        for finding in result["findings"]:
            if finding["code"] == "interval_not_resolved":
                paragraph("not_resolved", shorts=", ".join(short(r) for r in finding.get("revisions", [])))
            else:  # a finding the texts do not name is shown as the search prints it
                say(f"finding: {finding['code']}: {finding['message']}")
        for held in result["held"]:
            if held["kind"] == "input_data" and held["not_shown"]:
                paragraph("not_shown", count=integer(len(held["not_shown"]), lang))
        paragraph("after_search_end", path=shown(folder / "search" / "search.result.json"))

        say()
        paragraph("closing", folder=shown(folder))
        return 0
    except KeyboardInterrupt:
        say()
        say(texts["stopped"])
        return 130
