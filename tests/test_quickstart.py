"""The guided quick start ``deltarecon quickstart`` with a fake step and a fake prompt.

The fake step writes small result files in the shapes the real steps write, relative to the working
directory it is called in, and returns given statuses, so these tests run no model. The run of the
real demo against the pin of the quick-start search is in ``tests/test_quick_start.py`` and runs on
request.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from degelmann.deltarecon import quickstart as demo
from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.run import REPOSITORIES_VARIABLE

from conftest import ROOT, load_measure_tool

NOW = datetime.datetime(2026, 10, 29, 12, 0, 0, tzinfo=datetime.timezone.utc)
FOLDER = Path("runs") / "quickstart-20261029T120000Z"
REVISIONS = ["a" * 40, "b" * 40, "c" * 40, "d" * 40]
NAMES = ["request", "run", "regression", "derive", "search"]
WIDTH = 99  # COLUMNS=100 below


def write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), "utf-8")


def fake_files(name: str) -> None:
    """The files the command ``name`` writes, reduced to what the demo reads, below the working directory."""
    if name == "run":
        write(Path("release-n") / "response.json", {"model_points": [{}] * 350, "export": {"data_rows": 80580}})
    elif name == "regression":
        write(Path("regression") / "compare.result.json", {"outcome": "compared", "deviating_model_points": ["1", "2", "3"]})
        write(Path("regression") / "signature-table.json", {"rows": [
            {"quantity": "Bruttobeitrag", "deviating_model_points": 3, "deviating_coordinates": 1200,
             "first_period": 0, "last_period": 479},
            {"quantity": "Provisionen", "deviating_model_points": 2, "deviating_coordinates": 34,
             "first_period": 1, "last_period": 12}]})
    elif name == "derive":
        write(Path("changes.json"), {"changes": [
            {"id": REVISIONS[0], "class": ["data"], "description": "Change the portfolio\n\nbody"},
            {"id": REVISIONS[1], "class": ["parameter", "code"], "description": "Lower the lapse rate"},
            {"id": REVISIONS[2], "class": [], "description": "Say more in the README"},
            {"id": REVISIONS[3], "class": ["code"], "description": "Raise the charge"}]})
    elif name == "search":
        write(Path("search") / "search.result.json", {
            "runs": {"search": 3, "walk": 5, "saved": 2},
            "contributions": [
                {"revisions": [REVISIONS[1]], "contributions": [
                    {"quantity": "Bruttobeitrag", "contributes": True, "sum": 24109.994, "absolute_sum": 1.0}]},
                {"revisions": [REVISIONS[3]], "contributions": [
                    {"quantity": "Bruttobeitrag", "contributes": True, "sum": -4429.49, "absolute_sum": 1.0}]},
                {"revisions": [REVISIONS[0]], "contributions": [
                    {"quantity": "Bruttobeitrag", "contributes": False}]}],
            "findings": [{"code": "interval_not_resolved", "message": "m", "revisions": REVISIONS[2:]}],
            "held": [{"kind": "input_data", "not_shown": [REVISIONS[0]]}]})


class Steps:
    """A fake ``step``: records each argv and the working directory, writes the files, returns the status."""

    def __init__(self, statuses: dict[str, int] | None = None):
        self.statuses = {**demo.EXPECT, **(statuses or {})}
        self.argvs: list[list[str]] = []
        self.cwds: list[Path] = []

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        name = argv[0]
        self.argvs.append(argv)
        self.cwds.append(Path.cwd())
        fake_files(name)
        return self.statuses[name], f"output of {name}\n"


class Prompt:
    def __init__(self, raises: type[BaseException] | None = None):
        self.raises = raises
        self.prompts: list[str] = []

    def __call__(self, text: str) -> str:
        self.prompts.append(text)
        if self.raises:
            raise self.raises
        return ""


@pytest.fixture
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "100")
    monkeypatch.delenv(REPOSITORIES_VARIABLE, raising=False)
    return tmp_path


def flat(text: str) -> str:
    """``text`` with every run of whitespace as one space, so wrapped paragraphs compare."""
    return re.sub(r"\s+", " ", text)


def run_demo(lang="en", pause=False, statuses=None, ask=None, repositories=None, step=None):
    steps = step or Steps(statuses)
    ask = ask or Prompt()
    status = demo.quickstart(lang, pause, repositories, step=steps, ask=ask, now=NOW)
    return status, steps, ask


def shown_commands(out: str) -> list[list[str]]:
    """The commands below each label line, joined from their wrapped lines and split into words."""
    lines, commands, index = out.splitlines(), [], 0
    while index < len(lines):
        if lines[index] in ("Command:", "Commands:", "Befehl:", "Befehle:"):
            index += 1
            while index < len(lines) and lines[index].startswith("  deltarecon "):
                words = lines[index].split()
                index += 1
                while index < len(lines) and re.match(r" {6}\S", lines[index]):
                    words += lines[index].split()
                    index += 1
                commands.append(words)
        else:
            index += 1
    return commands


def checkout_argvs(tmp_path: Path) -> dict[str, list[str]]:
    """The argvs of a demo started in ``tmp_path`` without the variable and without ``--repositories``."""
    folder = tmp_path / FOLDER
    return demo.steps(os.path.relpath(demo.profile_path(), folder))


def test_the_steps_equal_the_readme_quick_start_without_replay():
    """The tool's steps without ``replay``, with the README's folders mapped to those of the demo folder."""
    tool = load_measure_tool()
    readme_profile = "profiles/tolerance-bruttobeitrag.json"
    folders = {"runs/n-full/request.json": str(Path("release-n") / "request.json"),
               "runs/n-full/run-record.json": str(Path("release-n") / "run-record.json"),
               "runs/regression-n": "regression",
               "runs/regression-n/run/run-record.json": str(Path("regression") / "run" / "run-record.json"),
               "runs/changes.json": "changes.json",
               "runs/search": "search",
               readme_profile: "PROFILE"}
    ours = demo.steps("PROFILE")
    assert list(ours) == [name for name in tool.STEPS if name != "replay"]
    for name, argv in ours.items():
        readme = tool.STEPS[name]["argv"]
        assert readme[:3] == ["uv", "run", "deltarecon"]
        assert all(not a.startswith("runs/") or a in folders for a in readme[3:]), name
        assert argv == [folders.get(a, a) for a in readme[3:]], name
        assert demo.EXPECT[name] == tool.STEPS[name]["expect"], name
    assert demo.steps("P", "../../x")["run"][-2:] == ["--repositories", "../../x"]


def test_the_happy_path_runs_in_the_demo_folder_and_summarises_the_files(cwd, capsys):
    status, steps, ask = run_demo("en")
    assert status == 0
    assert Path.cwd() == cwd  # back in the former working directory
    assert [argv[0] for argv in steps.argvs] == NAMES
    assert steps.cwds == [cwd / FOLDER] * 5
    assert steps.argvs == list(checkout_argvs(cwd).values())
    assert not any("--repositories" in argv for argv in steps.argvs)
    assert (cwd / FOLDER / "release-n" / "response.json").is_file()
    assert ask.prompts == []
    out = capsys.readouterr().out
    text = flat(out)
    assert "output of" not in out  # the commands' own output is captured, not printed
    assert "--repositories" not in out
    assert out.startswith("DeltaRecon guided quick start\n\nThe demo compares two states")
    assert f"\n  cd {FOLDER}\n" in out
    assert "(--revision, the revision fa36857)" in text and "the revision 887b718." in text
    assert "Release N is computed: 350 model points, 80,580 result rows. Files in release-n:" in text
    assert "1,234 values in 3 model points differ" in text
    assert "A value is one quantity of one model point in one period." in text
    assert ("one period.\n\n"
            "  Quantity       Model points  Values   Periods\n"
            "  Bruttobeitrag             3   1,200  0 to 479\n"
            "  Provisionen               2      34   1 to 12\n"
            "\nThe deviation is the expected outcome") in out
    assert "Total" not in out
    assert "the run of N+1 in regression/run." in text
    assert "4 changes: 1 data, 1 parameter, 2 code, 1 without a class (a change can have several classes)." in text
    assert ("without a class (a change can have several classes).\n\n"
            "  No.  Revision  Class            Description\n"
            "    1  aaaaaaa   data             Change the portfolio\n"
            "    2  bbbbbbb   parameter, code  Lower the lapse rate\n"
            "    3  ccccccc   no class         Say more in the README\n"
            "    4  ddddddd   code             Raise the charge\n"
            "\nFile: changes.json") in out
    assert "File: changes.json (the change manifest)." in text
    assert "Which of the 4 changes cause" in text
    assert ("\n2 revisions deviate in the Bruttobeitrag. 3 of 5 were computed (2 computations saved).\n\n"
            "  Revision  Description           Sum of the deviation\n"
            "  bbbbbbb   Lower the lapse rate            +24,109.99\n"
            "  ddddddd   Raise the charge                 -4,429.49\n"
            "\nNot resolved:") in out
    assert "aaaaaaa   Change" not in out  # a change that does not contribute has no row
    assert "Not resolved: the changes ccccccc, ddddddd exceed the tolerance only together;" in text
    assert "Not shown" not in out
    assert "Result: search/search.result.json." in text
    assert text.rstrip().endswith(f"Done. Every file is in {FOLDER}.")
    assert "`" not in out


def test_the_layout_of_a_step(cwd, capsys):
    """Heading on its own line, a blank line, the wrapped explanation, a blank line, the label, the
    indented commands wrapped between arguments, continuation lines indented by six spaces."""
    _, steps, _ = run_demo("en")
    out = capsys.readouterr().out
    lines = out.splitlines()
    for heading, label in (("Step 1 of 4: compute release N", "Commands:"),
                           ("Step 2 of 4: regression against N+1", "Command:"),
                           ("Step 3 of 4: the changes between N and N+1", "Command:"),
                           ("Step 4 of 4: find the cause in the Bruttobeitrag", "Command:")):
        at = lines.index(heading)
        assert lines[at - 1] == "" and lines[at + 1] == ""
        end = lines.index("", at + 2)
        assert lines[at + 2].strip() and all(len(line) <= WIDTH for line in lines[at + 2:end])
        assert lines[end + 1] == label
        assert lines[end + 2].startswith("  deltarecon ")
    for line in lines:
        if line.startswith("  deltarecon ") or re.match(r" {6}\S", line):
            assert len(line) <= WIDTH or " " not in line.strip(), line
    assert [w[1:] for w in shown_commands(out)] == steps.argvs  # the argv shown is the argv run
    assert any(line.startswith(demo.CONTINUATION + "--") for line in lines)  # the search wraps at 99


def test_an_option_stays_with_its_value_when_a_command_wraps():
    lines = demo.command_lines(["search", "a" * 30, "b" * 30, "--quantity", "Bruttobeitrag", "--target-only"], 61)
    assert lines == ["  deltarecon search " + "a" * 30, "      " + "b" * 30 + " --quantity Bruttobeitrag",
                     "      --target-only"]
    assert demo.command_lines(["x", "with space"], 80) == ['  deltarecon x "with space"']


def test_the_table_aligns_to_the_widest_entry_or_header():
    rows = [("Kosten 2. Ordnung ohne Provisionen", "350", "80,580", "0 to 479"), ("Anzahl", "1", "5", "1 to 2")]
    assert demo.table(("Quantity", "Model points", "Values", "Periods"), rows) == [
        "  Quantity                            Model points  Values   Periods",
        "  Kosten 2. Ordnung ohne Provisionen           350  80,580  0 to 479",
        "  Anzahl                                         1       5    1 to 2"]
    assert demo.table(("No.", "Revision"), [("1", "abc"), ("10", "abcdefghij")], right={0}) == [
        "  No.  Revision", "    1  abc", "   10  abcdefghij"]


def test_the_german_texts_and_numbers(cwd, capsys):
    assert run_demo("de")[0] == 0
    out = capsys.readouterr().out
    text = flat(out)
    assert out.startswith("DeltaRecon – geführter Quick Start\n\nDie Vorführung vergleicht")
    assert "\nSchritt 1 von 4: Release N rechnen\n\nZuerst schreibt request einen Rechenauftrag nach --output." in out
    assert "\nBefehle:\n  deltarecon request " in out and "\nBefehl:\n  deltarecon regression " in out
    assert "Release N ist gerechnet: 350 Modellpunkte, 80.580 Ergebniszeilen." in text
    assert "Die Regression zeigt eine Abweichung: 1.234 Werte in 3 Modellpunkten weichen ab." in text
    assert "Ein Wert ist eine Größe eines Modellpunkts in einer Periode." in text
    assert ("Periode.\n\n"
            "  Größe          Modellpunkte  Werte   Perioden\n"
            "  Bruttobeitrag             3  1.200  0 bis 479\n"
            "  Provisionen               2     34   1 bis 12\n"
            "\nDie Abweichung ist das erwartete Ergebnis") in out
    assert "4 Änderungen: 1 Daten, 1 Parameter, 2 Code, 1 ohne Einordnung (eine Änderung kann mehrere Einordnungen haben)." in text
    assert ("Einordnungen haben).\n\n"
            "  Nr.  Revision  Einordnung       Beschreibung\n"
            "    1  aaaaaaa   Daten            Change the portfolio\n"
            "    2  bbbbbbb   Parameter, Code  Lower the lapse rate\n"
            "    3  ccccccc   ohne Einordnung  Say more in the README\n"
            "    4  ddddddd   Code             Raise the charge\n"
            "\nDatei: changes.json") in out
    assert ("\n2 Revisionen weichen im Bruttobeitrag ab. Gerechnet wurden 3 von 5 (2 Berechnungen gespart).\n\n"
            "  Revision  Beschreibung          Summe der Abweichung\n"
            "  bbbbbbb   Lower the lapse rate            +24.109,99\n"
            "  ddddddd   Raise the charge                 -4.429,49\n"
            "\nNicht aufgelöst:") in out
    assert "Nicht aufgelöst: Die Änderungen ccccccc, ddddddd" in text
    assert "Nicht gezeigt" not in out
    assert "Ergebnis: search/search.result.json." in text
    assert text.rstrip().endswith(f"Fertig. Alle Dateien liegen in {FOLDER}.")


def test_both_languages_have_the_same_texts():
    assert set(demo.TEXTS["en"]) == set(demo.TEXTS["de"])
    for key, value in demo.TEXTS["en"].items():
        if isinstance(value, str):
            assert re.findall(r"\{(\w+)\}", value) == re.findall(r"\{(\w+)\}", demo.TEXTS["de"][key]), key


def search_result_step(**changes):
    """A fake step whose search result has the members ``changes`` replaced."""
    steps = Steps()

    def step(argv):
        status, output = steps(argv)
        if argv[0] == "search":
            path = Path("search") / "search.result.json"
            write(path, {**json.loads(path.read_text("utf-8")), **changes})
        return status, output

    return step


@pytest.mark.parametrize("held", [[], [{"kind": "input_data", "not_shown": []}],
                                  [{"kind": "input_data", "not_shown": REVISIONS[:2]}]])
def test_no_held_entry_prints_anything(cwd, capsys, held):
    def summary(changes: dict) -> str:
        assert run_demo("en", step=search_result_step(**changes))[0] == 0
        out = capsys.readouterr().out
        shutil.rmtree(cwd / FOLDER)
        return out.split("Step 4 of 4")[1]

    assert summary({"held": held}) == summary({"held": []})


@pytest.mark.parametrize("lang, sentence", [
    ("en", "1 revision deviates in the Bruttobeitrag. 3 of 5 were computed (2 computations saved)."),
    ("de", "1 Revision weicht im Bruttobeitrag ab. Gerechnet wurden 3 von 5 (2 Berechnungen gespart).")])
def test_one_deviating_revision_takes_the_singular(cwd, capsys, lang, sentence):
    one = [{"revisions": [REVISIONS[1]], "contributions": [
        {"quantity": "Bruttobeitrag", "contributes": True, "sum": 1.0, "absolute_sum": 1.0}]}]
    assert run_demo(lang, step=search_result_step(contributions=one))[0] == 0
    out = capsys.readouterr().out
    assert "\n" + sentence + "\n\n" in out


@pytest.mark.parametrize("value, lang, expected", [
    (24109.994, "en", "+24,109.99"), (24109.994, "de", "+24.109,99"), (-4429.49, "en", "-4,429.49"),
    (-4429.49, "de", "-4.429,49"), (0.004, "de", "+0,00"), (None, "en", "-")])
def test_sums_have_a_sign_two_decimals_and_the_separators_of_the_language(value, lang, expected):
    assert demo.signed(value, lang) == expected


@pytest.mark.parametrize("value, lang, expected", [
    (80580, "en", "80,580"), (80580, "de", "80.580"), (1234567, "de", "1.234.567"), (17, "de", "17")])
def test_whole_numbers_have_the_thousands_separator_of_the_language(value, lang, expected):
    assert demo.integer(value, lang) == expected


def test_the_demo_waits_before_each_of_the_four_steps(cwd, capsys):
    status, _, ask = run_demo("de", pause=True)
    assert status == 0
    assert ask.prompts == ["Weiter mit der Eingabetaste ... "] * 4


def test_end_of_input_counts_as_enter(cwd, capsys):
    status, steps, ask = run_demo("en", pause=True, ask=Prompt(EOFError))
    assert status == 0
    assert len(ask.prompts) == 4 and len(steps.argvs) == 5


@pytest.mark.parametrize("lang, line", [("en", "stopped"), ("de", "abgebrochen")])
def test_an_interrupt_at_a_prompt_stops_with_130(cwd, capsys, lang, line):
    status, steps, _ = run_demo(lang, pause=True, ask=Prompt(KeyboardInterrupt))
    assert status == 130
    assert steps.argvs == []  # step 1 shows request and run under its one prompt
    assert capsys.readouterr().out.splitlines()[-1] == line
    assert Path.cwd() == cwd


@pytest.mark.parametrize("failing", NAMES)
def test_a_step_with_another_status_prints_its_output_and_stops(cwd, capsys, failing):
    other = 1 - demo.EXPECT[failing]
    status, steps, _ = run_demo("en", statuses={failing: other})
    assert status == 1
    assert Path.cwd() == cwd
    assert [argv[0] for argv in steps.argvs] == NAMES[:NAMES.index(failing) + 1]
    out = capsys.readouterr().out
    assert out.rstrip().endswith(f"output of {failing}")
    assert "Done." not in out


@pytest.mark.parametrize("compare_result", [None, {"outcome": "incompatible", "diagnostics": []}, "not json"])
def test_a_regression_that_compares_nothing_prints_its_output_and_stops(cwd, capsys, compare_result):
    """Status 1 of a rejected regression or of a failed run of N+1 is not the expected deviation."""
    steps = Steps()

    def step(argv):
        if argv[0] != "regression":
            return steps(argv)
        steps.argvs.append(argv)
        if compare_result is not None:
            path = Path("regression") / "compare.result.json"
            path.parent.mkdir(parents=True)
            path.write_text(compare_result if isinstance(compare_result, str) else json.dumps(compare_result))
        return 1, "regression: rejected\n"

    status, _, _ = run_demo("en", step=step)
    assert status == 1
    assert Path.cwd() == cwd
    assert [argv[0] for argv in steps.argvs] == ["request", "run", "regression"]
    out = capsys.readouterr().out
    assert out.rstrip().endswith("regression: rejected")
    assert "The regression shows a deviation" not in out


def test_an_existing_folder_exits_with_2(cwd, capsys):
    (cwd / FOLDER).mkdir(parents=True)
    status, steps, _ = run_demo("en")
    assert status == 2
    assert steps.argvs == []
    assert Path.cwd() == cwd
    assert capsys.readouterr().err == f"error: {FOLDER} exists already\n"


@pytest.mark.parametrize("variable, option, expected", [
    (None, None, None),
    ("", None, None),
    ("clones", None, os.path.join("..", "..", "clones")),
    ("ABSOLUTE", None, None),
    ("ABSOLUTE", "mine", os.path.join("..", "..", "mine")),
    (None, "ABSOLUTE", "ABSOLUTE-RELATIVE"),
])
def test_the_clone_folder_of_the_commands(cwd, capsys, monkeypatch, variable, option, expected):
    """``--repositories`` relative to the demo folder only when the demo is given it or the variable names a
    relative folder; otherwise each command finds the clone itself."""
    absolute = str(cwd.parent / "elsewhere")
    if variable is not None:
        monkeypatch.setenv(REPOSITORIES_VARIABLE, absolute if variable == "ABSOLUTE" else variable)
    if option == "ABSOLUTE":
        option, expected = absolute, os.path.relpath(absolute, cwd / FOLDER)
    status, steps, _ = run_demo("en", repositories=option)
    assert status == 0
    for argv in steps.argvs:
        if expected is None:
            assert "--repositories" not in argv
        else:
            assert argv[-2:] == ["--repositories", expected]
    assert [w[1:] for w in shown_commands(capsys.readouterr().out)] == steps.argvs


def test_the_profile_of_the_search_is_relative_to_the_demo_folder(cwd):
    _, steps, _ = run_demo("en")
    search = steps.argvs[-1]
    profile = search[search.index("--tolerance") + 1]
    assert not Path(profile).is_absolute()
    assert (cwd / FOLDER / profile).resolve() == demo.profile_path().resolve()


def test_a_path_without_a_relative_form_stays_absolute(monkeypatch):
    def refuse(path, start):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(demo.os.path, "relpath", refuse)
    assert demo.relative_to("/x/profiles/p.json", "runs/q") == str(Path("/x/profiles/p.json").absolute())


@pytest.mark.parametrize("env, system, expected", [
    ({"LANG": "de_DE.UTF-8"}, None, "de"),
    ({"LANG": "C.UTF-8"}, "de_DE", "en"),
    ({}, "German_Germany", "de"),
    ({}, "de_DE", "de"),
    ({}, "English_United States", "en"),
    ({}, None, "en"),
    ({"LC_ALL": "", "LC_MESSAGES": "de_AT.UTF-8", "LANG": "en_US.UTF-8"}, None, "de"),
    ({"LC_ALL": "en_GB.UTF-8", "LANG": "de_DE.UTF-8"}, None, "en"),
    ({"LANG": "GERMAN"}, None, "de"),
])
def test_the_language_of_the_system(env, system, expected):
    assert demo.system_language(env, lambda: (system, None)) == expected


def test_the_profile_of_a_checkout_is_the_tracked_one(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert demo.profile_path() == ROOT / "profiles" / "tolerance-bruttobeitrag.json"


def profile_in(folder: Path) -> Path:
    path = folder / "profiles" / demo.PROFILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    return path


@pytest.fixture
def deep(tmp_path, monkeypatch):
    """``tmp_path/a/b`` as the working directory."""
    folder = tmp_path / "a" / "b"
    folder.mkdir(parents=True)
    monkeypatch.chdir(folder)
    return folder


def test_the_profile_in_the_working_directory_is_taken(deep):
    profile_in(deep.parent)
    nearest = profile_in(deep)
    assert demo.profile_path() == nearest


def test_the_profile_in_a_parent_is_taken(deep):
    found = profile_in(deep.parent.parent)
    assert demo.profile_path() == found


def test_a_folder_named_like_the_profile_is_passed_over(deep):
    (deep / "profiles" / demo.PROFILE_NAME).mkdir(parents=True)
    found = profile_in(deep.parent)
    assert demo.profile_path() == found


@pytest.mark.parametrize("packaged", [True, False])
def test_without_a_profile_upward_the_wheel_copy_else_the_checkout_is_taken(deep, monkeypatch, tmp_path, packaged):
    wheel = tmp_path / "site-packages" / "degelmann" / "deltarecon" / "profiles"
    checkout = tmp_path / "checkout" / "profiles"
    if packaged:
        wheel.mkdir(parents=True)
    # As the module sets it: the wheel's copy when it is present, else the checkout's.
    monkeypatch.setattr(demo, "PACKAGED_PROFILES", wheel)
    monkeypatch.setattr(demo, "PROFILES", wheel if packaged else checkout)
    assert demo.profile_path() == (wheel if packaged else checkout) / demo.PROFILE_NAME


def test_the_happy_path_shows_the_profile_of_the_working_directory(cwd, capsys):
    profile_in(cwd)
    _, steps, _ = run_demo("en")
    search = steps.argvs[-1]
    expected = os.path.join("..", "..", "profiles", demo.PROFILE_NAME)
    assert search[search.index("--tolerance") + 1] == expected
    assert f"--tolerance {expected}" in capsys.readouterr().out


def test_the_command_line_passes_its_options(monkeypatch):
    seen = {}
    monkeypatch.setattr(demo, "quickstart", lambda lang, pause, repositories: seen.update(
        lang=lang, pause=pause, repositories=repositories) or 0)
    monkeypatch.setattr(demo, "system_language", lambda: "de")
    assert main(["quickstart", "--no-pause", "--lang", "en", "--repositories", "x"]) == 0
    assert seen == {"lang": "en", "pause": False, "repositories": "x"}
    assert main(["quickstart"]) == 0
    assert seen == {"lang": "de", "pause": True, "repositories": None}
