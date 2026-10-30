"""The guided quick start ``deltarecon quickstart`` with a fake step and a fake prompt.

The fake step writes small result files in the shapes the real steps write and returns given
statuses, so these tests run no model. The run of the real demo against the pin of the quick-start
search is in ``tests/test_quick_start.py`` and runs on request.
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest

from degelmann.deltarecon import quickstart as demo
from degelmann.deltarecon.__main__ import main

from conftest import ROOT, load_measure_tool

NOW = datetime.datetime(2026, 10, 29, 12, 0, 0, tzinfo=datetime.timezone.utc)
FOLDER = Path("runs") / "quickstart-20261029T120000Z"
REVISIONS = ["a" * 40, "b" * 40, "c" * 40, "d" * 40]
NAMES = ["request", "run", "regression", "derive", "search"]


def write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), "utf-8")


def fake_files(name: str, folder: Path) -> None:
    """The files the step ``name`` writes, reduced to what the demo reads."""
    if name == "run":
        write(folder / "n-full" / "response.json",
              {"model_points": [{}] * 350, "export": {"data_rows": 80580}})
    elif name == "regression":
        write(folder / "regression-n" / "compare.result.json", {"deviating_model_points": ["1", "2", "3"]})
        write(folder / "regression-n" / "signature-table.json", {"rows": [
            {"quantity": "Bruttobeitrag", "deviating_model_points": 3, "deviating_coordinates": 1200,
             "first_period": 0, "last_period": 479},
            {"quantity": "Provisionen", "deviating_model_points": 2, "deviating_coordinates": 34,
             "first_period": 1, "last_period": 12}]})
    elif name == "derive":
        write(folder / "changes.json", {"changes": [
            {"id": REVISIONS[0], "class": ["data"], "description": "Change the portfolio\n\nbody"},
            {"id": REVISIONS[1], "class": ["parameter", "code"], "description": "Lower the lapse rate"},
            {"id": REVISIONS[2], "class": [], "description": "Say more in the README"},
            {"id": REVISIONS[3], "class": ["code"], "description": "Raise the charge"}]})
    elif name == "search":
        write(folder / "search" / "search.result.json", {
            "runs": {"search": 3, "walk": 5, "saved": 2},
            "contributions": [{"revisions": [REVISIONS[1]], "contributions": [
                {"quantity": "Bruttobeitrag", "contributes": True, "sum": 24109.994, "absolute_sum": 1.0}]}],
            "findings": [{"code": "interval_not_resolved", "message": "m", "revisions": REVISIONS[2:]}],
            "held": [{"kind": "input_data", "not_shown": [REVISIONS[0]]}]})


class Steps:
    """A fake ``step``: records each argv, writes the files of the step, returns its status."""

    def __init__(self, folder: Path, statuses: dict[str, int] | None = None):
        self.folder = folder
        self.statuses = {**demo.EXPECT, **(statuses or {})}
        self.argvs: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        name = argv[0]
        self.argvs.append(argv)
        fake_files(name, self.folder)
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
    return tmp_path


def flat(text: str) -> str:
    """``text`` with every run of whitespace as one space, so wrapped paragraphs compare."""
    return re.sub(r"\s+", " ", text)


def run_demo(lang="en", pause=False, statuses=None, ask=None, repositories=None):
    steps = Steps(FOLDER, statuses)
    ask = ask or Prompt()
    status = demo.quickstart(lang, pause, repositories, step=steps, ask=ask, now=NOW)
    return status, steps, ask


def test_the_steps_equal_the_readme_quick_start_without_replay():
    tool = load_measure_tool()
    work = Path("runs") / "quickstart-x"
    profile = "profiles/tolerance-bruttobeitrag.json"
    ours = demo.steps(work, "PROFILE")
    assert list(ours) == [name for name in tool.STEPS if name != "replay"]
    for name, argv in ours.items():
        expected = tool.rewrite(tool.STEPS[name]["argv"], work)
        assert expected[:3] == ["uv", "run", "deltarecon"]
        assert [profile if a == "PROFILE" else a for a in argv] == expected[3:], name
        assert demo.EXPECT[name] == tool.STEPS[name]["expect"], name
    assert demo.steps(work, "P", "/clone")["run"][-2:] == ["--repositories", "/clone"]


def test_the_happy_path_runs_the_steps_in_order_and_summarises_the_files(cwd, capsys):
    status, steps, ask = run_demo("en")
    assert status == 0
    assert [argv[0] for argv in steps.argvs] == NAMES
    assert steps.argvs == list(demo.steps(FOLDER, demo.shown(demo.profile_path())).values())
    assert ask.prompts == []
    out = capsys.readouterr().out
    text = flat(out)
    assert "output of" not in out  # the steps' own output is captured, not printed
    assert text.startswith("DeltaRecon guided quick start.")
    assert f"Every file goes into {FOLDER}." in text
    assert "(revision fa36857)" in text and "(revision 887b718)" in text
    assert "Release N is computed: 350 model points, 80,580 result rows." in text
    assert "1,234 values in 3 model points differ" in text
    assert "  Bruttobeitrag: 3 model points, 1,200 values, periods 0 to 479\n" in out
    assert "  Provisionen: 2 model points, 34 values, periods 1 to 12\n" in out
    assert "4 changes: 1 data, 1 parameter, 2 code, 1 without a class." in text
    assert "  aaaaaaa [data] Change the portfolio\n" in out
    assert "  bbbbbbb [parameter, code] Lower the lapse rate\n" in out
    assert "  ccccccc [no class] Say more in the README\n" in out
    assert "Which of the 4 changes cause" in text
    assert "Found with 3 of 5 intermediate states computed (2 saved)." in text
    assert "  bbbbbbb Lower the lapse rate: sum of the deviation +24,109.99\n" in out
    assert "Not resolved: the changes ccccccc, ddddddd exceed the tolerance only together;" in text
    assert "Not shown: the effect of 1 change(s) of the portfolio data" in text
    assert f"Result: {FOLDER / 'search' / 'search.result.json'}." in text
    assert text.rstrip().endswith(f"Done. Every file is in {FOLDER}. Each step also runs on its own as the "
                                  "command shown before it.")
    for argv in steps.argvs[1:]:  # each of the four steps is shown as a single command
        assert "deltarecon " + " ".join(argv) + "\n" in out


def test_the_german_texts_and_numbers(cwd, capsys):
    assert run_demo("de")[0] == 0
    out = capsys.readouterr().out
    text = flat(out)
    assert text.startswith("DeltaRecon – geführter Quick Start.")
    assert "Release N ist gerechnet: 350 Modellpunkte, 80.580 Ergebniszeilen." in text
    assert "Die Regression zeigt eine Abweichung: 1.234 Werte in 3 Modellpunkten weichen ab." in text
    assert "  Bruttobeitrag: 3 Modellpunkte, 1.200 Werte, Perioden 0 bis 479\n" in out
    assert "4 Änderungen: 1 Daten, 1 Parameter, 2 Code, 1 ohne Einordnung." in text
    assert "  bbbbbbb [Parameter, Code] Lower the lapse rate\n" in out
    assert "Gefunden mit 3 von 5 Zwischenständen (2 gespart)." in text
    assert "  bbbbbbb Lower the lapse rate: Summe der Abweichung +24.109,99\n" in out
    assert "Nicht aufgelöst: Die Änderungen ccccccc, ddddddd" in text
    assert "Nicht gezeigt: die Wirkung von 1 Änderung(en) der Bestandsdaten" in text
    assert text.rstrip().endswith("als der Befehl, der vor ihm gezeigt wurde.")


def test_both_languages_have_the_same_texts():
    assert set(demo.TEXTS["en"]) == set(demo.TEXTS["de"])
    for key, value in demo.TEXTS["en"].items():
        if isinstance(value, str):
            assert re.findall(r"\{(\w+)\}", value) == re.findall(r"\{(\w+)\}", demo.TEXTS["de"][key]), key


def test_held_input_data_with_no_change_not_shown_prints_no_line(cwd, capsys):
    steps = Steps(FOLDER)

    def step(argv):
        status, output = steps(argv)
        if argv[0] == "search":
            path = FOLDER / "search" / "search.result.json"
            write(path, {**json.loads(path.read_text("utf-8")), "held": [{"kind": "input_data", "not_shown": []}]})
        return status, output

    assert demo.quickstart("en", False, None, step=step, ask=Prompt(), now=NOW) == 0
    assert "Not shown" not in capsys.readouterr().out


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
    assert [argv[0] for argv in steps.argvs] == ["request"]
    assert capsys.readouterr().out.splitlines()[-1] == line


@pytest.mark.parametrize("failing", NAMES)
def test_a_step_with_another_status_prints_its_output_and_stops(cwd, capsys, failing):
    other = 1 - demo.EXPECT[failing]
    status, steps, _ = run_demo("en", statuses={failing: other})
    assert status == 1
    assert [argv[0] for argv in steps.argvs] == NAMES[:NAMES.index(failing) + 1]
    out = capsys.readouterr().out
    assert out.rstrip().endswith(f"output of {failing}")
    assert "Done." not in out


def test_an_existing_folder_exits_with_2(cwd, capsys):
    (cwd / FOLDER).mkdir(parents=True)
    status, steps, _ = run_demo("en")
    assert status == 2
    assert steps.argvs == []
    assert capsys.readouterr().err == f"error: {FOLDER} exists already\n"


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


def test_the_profile_of_a_checkout_is_the_tracked_one():
    assert demo.profile_path() == ROOT / "profiles" / "tolerance-bruttobeitrag.json"


def test_the_command_line_passes_its_options(monkeypatch):
    seen = {}
    monkeypatch.setattr(demo, "quickstart", lambda lang, pause, repositories: seen.update(
        lang=lang, pause=pause, repositories=repositories) or 0)
    monkeypatch.setattr(demo, "system_language", lambda: "de")
    assert main(["quickstart", "--no-pause", "--lang", "en", "--repositories", "x"]) == 0
    assert seen == {"lang": "en", "pause": False, "repositories": "x"}
    assert main(["quickstart"]) == 0
    assert seen == {"lang": "de", "pause": True, "repositories": None}
