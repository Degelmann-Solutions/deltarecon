"""The guided quick start: ``deltarecon quickstart``.

The demo runs the steps of the README quick start without ``replay`` in the new folder
``runs/quickstart-<UTC timestamp>/`` below the working directory. It changes into that folder
before the first step and back to the former working directory when it ends, however it ends.
Inside it, ``release-n/`` holds the run of release N, ``regression/`` the regression against N+1
(the run of N+1 in ``regression/run/``), ``changes.json`` the change manifest and ``search/`` the
search. Step 1 is ``request`` and ``run``; steps 2 to 4 are ``regression``, ``derive`` and
``search``. Before each step the demo explains it, shows its commands and waits for Enter (not with
``--no-pause``); after it, it summarises the outcome from the files the step wrote. Each command
runs in this process through ``__main__.main`` with its output captured, so it makes every check of
the single command; the argv run is the argv shown, with every path relative to the demo folder, so
each shown command runs on its own from there.

A command gets ``--repositories``, with the clone folder relative to the demo folder, only when the
demo is given ``--repositories`` or ``DELTARECON_REPOSITORIES`` names a relative folder. Otherwise no
command gets it: from the demo folder a command finds ``repositories/`` of a checkout in a parent
folder, and in a package the launcher's absolute variable applies. The search gets ``--tolerance`` with the profile relative to the demo folder, or
absolute when no relative path exists (another drive on Windows).

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

from .run import REPOSITORIES_VARIABLE

OLDER = "fa368575a66d97c94e96dffc62b273ec95511b12"  # release N on the fixed model
NEWER = "887b7181d22550eda2fb52fa1a6bd77376d4eb2e"  # the state N+1, 32 revisions later
LABEL = "N"
RUN_ID = "run-n-full"
QUANTITY = "Bruttobeitrag"
PERIODS = "0-59"
PROFILE_NAME = "tolerance-bruttobeitrag.json"
RUNS = Path("runs")
# The folders and files inside the demo folder.
RELEASE = Path("release-n")
REGRESSION = Path("regression")
CHANGES = Path("changes.json")
SEARCH = Path("search")
PACKAGED_PROFILES = Path(__file__).resolve().parent / "profiles"
PROFILES = PACKAGED_PROFILES if PACKAGED_PROFILES.is_dir() else Path(__file__).resolve().parents[2] / "profiles"
LANGUAGE_VARIABLES = ("LC_ALL", "LC_MESSAGES", "LANG")
# The expected exit status of each command: the regression shows the deviation between N and N+1.
EXPECT = {"request": 0, "run": 0, "regression": 1, "derive": 0, "search": 0}
# The commands of each of the four steps.
STEP_COMMANDS = {"run": ("request", "run"), "regression": ("regression",), "derive": ("derive",),
                 "search": ("search",)}
CONTINUATION = " " * 6

TEXTS = {
    "en": {
        "opening_heading": "DeltaRecon guided quick start",
        "opening": (
            "The demo compares two states of the reference model delib-history, a term life insurance with 350 "
            "model points: release N and the state N+1, 32 revisions later. In four steps it shows how DeltaRecon "
            "finds a deviation between two releases and traces it back to the changes that cause it. The demo "
            "puts its files into a folder of its own, and every command runs there:"),
        "prompt": "Press Enter to continue ...",
        "command": "Command:",
        "commands": "Commands:",
        "heading_run": "Step 1 of 4: compute release N",
        "before_run": (
            "First, request writes a run request to --output. It records which state is computed (--revision, the "
            "revision {short}), which name this state carries (--label N) and under which identifier the request "
            "runs (--run-id run-n-full). Name and identifier are chosen freely and reappear in the later "
            "comparisons. Without --subset the request covers every model point of the portfolio, with --subset "
            "only the ones named. Then run computes this request and records the result together with its full "
            "origin: code, parameters and portfolio data. This result is the reference that every later step "
            "checks against."),
        "after_run": (
            "Release N is computed: {points} model points, {rows} result rows. Files in release-n: results.csv "
            "(the results), response.json and run-record.json (the record of what was computed with what)."),
        "heading_regression": "Step 2 of 4: regression against N+1",
        "before_regression": (
            "regression takes the record of the run of release N from step 1 (release-n/run-record.json) and, "
            "with --revision, computes the newer state N+1, the revision {short}. It computes on the same "
            "portfolio data and for the same model points as release N and compares the two results value by "
            "value. Without --tolerance it compares exactly: every deviation counts. It writes the run of N+1 "
            "and the comparison into the folder --output, the run into its subfolder run. This shows whether and "
            "where the results of the two releases differ. A deviation is expected here; the command reports it "
            "with exit status 1."),
        "after_regression": (
            "The regression shows a deviation: {coordinates} values in {points} model points differ. "
            "Per quantity:"),
        "regression_row": "  {quantity}: {points} model points, {coordinates} values, periods {first} to {last}",
        "after_regression_end": (
            "The deviation is the expected outcome; the demo goes on. Files in regression: compare.result.json, "
            "compare.deviations.csv (every differing value), signature-table.json (the table above); the run of "
            "N+1 in regression/run."),
        "heading_derive": "Step 3 of 4: the changes between N and N+1",
        "before_derive": (
            "derive takes the record of release N from step 1 (release-n/run-record.json) and the record of N+1 "
            "from step 2 (regression/run/run-record.json) and reads from them which two revisions were computed. "
            "Then it reads the revision history between these two states, lists every change on its own, in the "
            "order in which it was made, and writes this change manifest to --output. Each change is one revision "
            "and is classified: data (the portfolio), parameter (tables such as lapse or cost rates), code (the "
            "calculation rules), or none of these (for example documentation only)."),
        "after_derive": "{count} changes: {data} data, {parameter} parameter, {code} code, {none} without a class.",
        "derive_row": "  {short} [{classes}] {description}",
        "classes": {"data": "data", "parameter": "parameter", "code": "code"},
        "no_class": "no class",
        "after_derive_end": "File: changes.json (the change manifest).",
        "heading_search": "Step 4 of 4: find the cause in the Bruttobeitrag",
        "before_search": (
            "Which of the {count} changes cause the deviation in the Bruttobeitrag, the gross premium (--quantity "
            "Bruttobeitrag), in the first five projection years (--periods 0-59, one period per month)? search "
            "takes the same two records as step 3: release-n/run-record.json and regression/run/run-record.json. "
            "It does not compute every intermediate state; it halves the history until each deviation belongs to "
            "a single change. A deviation is a change of the Bruttobeitrag by more than one cent per model point "
            "and month; the tolerance profile sets this (--tolerance). With --target-only it computes the "
            "intermediate states only for the Bruttobeitrag in these periods and without the model checks; it "
            "computes the two end states in full. It writes the result into the folder --output. The portfolio "
            "data stay at release N."),
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
        "after_search_end": "Result: search/search.result.json.",
        "closing": (
            "Done. Every file is in {folder}. Each step also runs on its own as the command shown before it."),
        "stopped": "stopped",
    },
    "de": {
        "opening_heading": "DeltaRecon – geführter Quick Start",
        "opening": (
            "Die Vorführung vergleicht zwei Stände des Referenzmodells delib-history, einer "
            "Risikolebensversicherung mit 350 Modellpunkten: Release N und den Stand N+1, 32 Revisionen später. "
            "In vier Schritten zeigt sie, wie DeltaRecon eine Abweichung zwischen zwei Releases findet und auf die "
            "Änderungen zurückführt, die sie verursachen. Die Vorführung legt ihre Dateien in einem eigenen Ordner "
            "an, und alle Befehle laufen dort:"),
        "prompt": "Weiter mit der Eingabetaste ...",
        "command": "Befehl:",
        "commands": "Befehle:",
        "heading_run": "Schritt 1 von 4: Release N rechnen",
        "before_run": (
            "Zuerst schreibt request einen Rechenauftrag nach --output. Er hält fest, welcher Stand gerechnet wird "
            "(--revision, die Revision {short}), welchen Namen dieser Stand trägt (--label N) und unter welcher "
            "Kennung der Auftrag läuft (--run-id run-n-full). Name und Kennung sind frei gewählt und erscheinen in "
            "den späteren Vergleichen wieder. Ohne --subset gilt der Auftrag für alle Modellpunkte des Bestands, "
            "mit --subset nur für die genannten. Dann rechnet run diesen Auftrag und hält das Ergebnis mit seiner "
            "vollständigen Herkunft fest: Code, Parameter und Bestandsdaten. Dieses Ergebnis ist die Referenz, "
            "gegen die jeder weitere Schritt prüft."),
        "after_run": (
            "Release N ist gerechnet: {points} Modellpunkte, {rows} Ergebniszeilen. Dateien in release-n: "
            "results.csv (die Ergebnisse), response.json und run-record.json (der Nachweis, womit was gerechnet "
            "wurde)."),
        "heading_regression": "Schritt 2 von 4: Regression gegen N+1",
        "before_regression": (
            "regression nimmt den Nachweis des Laufs von Release N aus Schritt 1 (release-n/run-record.json) und "
            "rechnet mit --revision den neueren Stand N+1, die Revision {short}. Er rechnet auf denselben "
            "Bestandsdaten und für dieselben Modellpunkte wie Release N und vergleicht beide Ergebnisse Wert für "
            "Wert. Ohne --tolerance vergleicht er exakt: Jede Abweichung zählt. Den Lauf von N+1 und den Vergleich "
            "schreibt er in den Ordner --output, den Lauf in dessen Unterordner run. So zeigt sich, ob und wo sich "
            "die Ergebnisse der beiden Releases unterscheiden. Eine Abweichung ist hier erwartet; der Befehl "
            "meldet sie mit dem Exit-Status 1."),
        "after_regression": (
            "Die Regression zeigt eine Abweichung: {coordinates} Werte in {points} Modellpunkten weichen ab. "
            "Je Größe:"),
        "regression_row": "  {quantity}: {points} Modellpunkte, {coordinates} Werte, Perioden {first} bis {last}",
        "after_regression_end": (
            "Die Abweichung ist das erwartete Ergebnis; die Vorführung geht weiter. Dateien in regression: "
            "compare.result.json, compare.deviations.csv (jeder abweichende Wert), signature-table.json (die "
            "Tabelle oben); der Lauf von N+1 in regression/run."),
        "heading_derive": "Schritt 3 von 4: die Änderungen zwischen N und N+1",
        "before_derive": (
            "derive nimmt den Nachweis von Release N aus Schritt 1 (release-n/run-record.json) und den Nachweis "
            "von N+1 aus Schritt 2 (regression/run/run-record.json) und liest daraus, welche zwei Revisionen "
            "gerechnet wurden. Dann liest es die Versionsgeschichte zwischen diesen beiden Ständen, listet jede "
            "Änderung einzeln auf, in der Reihenfolge, in der sie gemacht wurde, und schreibt dieses "
            "Änderungsverzeichnis nach --output. Jede Änderung ist eine Revision und wird eingeordnet: Daten (der "
            "Bestand), Parameter (Tabellen wie Storno- oder Kostensätze), Code (die Rechenvorschriften) oder "
            "nichts davon (zum Beispiel nur Dokumentation)."),
        "after_derive": (
            "{count} Änderungen: {data} Daten, {parameter} Parameter, {code} Code, {none} ohne Einordnung."),
        "derive_row": "  {short} [{classes}] {description}",
        "classes": {"data": "Daten", "parameter": "Parameter", "code": "Code"},
        "no_class": "ohne Einordnung",
        "after_derive_end": "Datei: changes.json (das Änderungsverzeichnis).",
        "heading_search": "Schritt 4 von 4: die Ursache im Bruttobeitrag suchen",
        "before_search": (
            "Welche der {count} Änderungen verursachen die Abweichung im Bruttobeitrag (--quantity Bruttobeitrag) "
            "in den ersten fünf Projektionsjahren (--periods 0-59, eine Periode je Monat)? search nimmt dieselben "
            "beiden Nachweise wie Schritt 3: release-n/run-record.json und regression/run/run-record.json. Es "
            "rechnet nicht jeden Zwischenstand, sondern halbiert die Versionsgeschichte, bis jede Abweichung einer "
            "einzelnen Änderung zugeordnet ist. Als Abweichung zählt eine Änderung des Bruttobeitrags um mehr als "
            "einen Cent je Modellpunkt und Monat; das legt das Toleranzprofil fest (--tolerance). Mit "
            "--target-only rechnet es die Zwischenstände nur für den Bruttobeitrag in diesen Perioden und ohne die "
            "Modellprüfungen; die beiden Endstände rechnet es vollständig. Das Ergebnis schreibt es in den Ordner "
            "--output. Die Bestandsdaten bleiben auf dem Stand von Release N."),
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
        "after_search_end": "Ergebnis: search/search.result.json.",
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


def relative_to(path: Path | str, start: Path | str) -> str:
    """``path`` relative to the folder ``start``, both taken from the working directory; absolute when no
    relative path exists (another drive on Windows)."""
    try:
        return os.path.relpath(Path(path).absolute(), Path(start).absolute())
    except ValueError:
        return str(Path(path).absolute())


def clone_option(folder: Path, repositories: str | None, env=None) -> str | None:
    """The ``--repositories`` value of every command, relative to the demo folder ``folder``: from
    ``repositories`` when given, else from ``DELTARECON_REPOSITORIES`` when it names a relative folder;
    otherwise ``None``, and each command finds the clone itself (upward from the demo folder, or the
    absolute folder the variable names)."""
    env = os.environ if env is None else env
    if repositories is None:
        named = env.get(REPOSITORIES_VARIABLE)
        if not named or Path(named).is_absolute():
            return None
        repositories = named
    return relative_to(repositories, folder)


def quoted(argument: str) -> str:
    return f'"{argument}"' if " " in argument or not argument else argument


def command_lines(argv: list[str], width: int) -> list[str]:
    """``deltarecon <argv>`` indented by two spaces, wrapped between arguments to ``width``; continuation
    lines are indented by six spaces. An option stays on the line of its value."""
    words, index = ["deltarecon"], 0
    while index < len(argv):
        word = quoted(argv[index])
        if word.startswith("--") and index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            word += " " + quoted(argv[index + 1])
            index += 1
        words.append(word)
        index += 1
    lines = ["  " + words[0]]
    for word in words[1:]:
        if len(lines[-1]) + 1 + len(word) > width and lines[-1].strip():
            lines.append(CONTINUATION + word)
        else:
            lines[-1] += " " + word
    return lines


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


def steps(profile: str, clone: str | None = None) -> dict[str, list[str]]:
    """The argv of each command, run from the demo folder: every path relative to it."""
    record = str(RELEASE / "run-record.json")
    newer = str(REGRESSION / "run" / "run-record.json")
    argvs = {
        "request": ["request", "--revision", OLDER, "--label", LABEL, "--run-id", RUN_ID,
                    "--output", str(RELEASE / "request.json")],
        "run": ["run", str(RELEASE / "request.json")],
        "regression": ["regression", record, "--revision", NEWER, "--output", str(REGRESSION)],
        "derive": ["derive", record, newer, "--output", str(CHANGES)],
        "search": ["search", record, newer, "--quantity", QUANTITY, "--periods", PERIODS, "--tolerance", profile,
                   "--target-only", "--output", str(SEARCH)],
    }
    if clone is not None:
        for argv in argvs.values():
            argv += ["--repositories", clone]
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
    argvs = steps(relative_to(profile_path(), folder), clone_option(folder, repositories))
    former = Path.cwd()

    def execute(name: str) -> bool:
        status, output = step(argvs[name])
        if status != EXPECT[name]:
            for line in output.splitlines():
                say(line)
            return False
        return True

    def explain(name: str, **values) -> bool:
        """The heading, the explanation, the commands and the prompt of a step; then run its commands."""
        commands = STEP_COMMANDS[name]
        say()
        say(texts[f"heading_{name}"])
        say()
        paragraph(f"before_{name}", **values)
        say()
        say(texts["commands" if len(commands) > 1 else "command"])
        for command in commands:
            for line in command_lines(argvs[command], width):
                say(line)
        if pause:
            try:
                ask(texts["prompt"] + " ")
            except EOFError:  # no more input counts as Enter
                say()
        return all(execute(command) for command in commands)

    try:
        say(texts["opening_heading"])
        say()
        paragraph("opening")
        say(f"  cd {folder}")
        os.chdir(folder)

        if not explain("run", short=short(OLDER)):
            return 1
        response = read(RELEASE / "response.json")
        say()
        paragraph("after_run", points=integer(len(response["model_points"]), lang),
                  rows=integer(response["export"]["data_rows"], lang))

        if not explain("regression", short=short(NEWER)):
            return 1
        compared = read(REGRESSION / "compare.result.json")
        rows = read(REGRESSION / "signature-table.json")["rows"]
        say()
        paragraph("after_regression", coordinates=integer(sum(r["deviating_coordinates"] for r in rows), lang),
                  points=integer(len(compared["deviating_model_points"]), lang))
        for row in rows:
            say(texts["regression_row"].format(
                quantity=row["quantity"], points=integer(row["deviating_model_points"], lang),
                coordinates=integer(row["deviating_coordinates"], lang), first=row["first_period"],
                last=row["last_period"]))
        paragraph("after_regression_end")

        if not explain("derive"):
            return 1
        changes = read(CHANGES)["changes"]
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
        paragraph("after_derive_end")

        if not explain("search", count=integer(len(changes), lang)):
            return 1
        result = read(SEARCH / "search.result.json")
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
        paragraph("after_search_end")

        say()
        paragraph("closing", folder=folder)
        return 0
    except KeyboardInterrupt:
        say()
        say(texts["stopped"])
        return 130
    finally:
        os.chdir(former)
