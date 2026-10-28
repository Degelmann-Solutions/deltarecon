"""Where the commands read the clone: ``--repositories DIR``, else the folder the environment
variable ``DELTARECON_REPOSITORIES`` names, else ``repositories/`` in the working directory.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.run import REPOSITORIES_VARIABLE, repositories_folder

from conftest import REPOSITORIES, START

# Every command that reads the clone of the reference model repository.
READERS = ("request", "run", "replay", "regression", "derive", "walk", "search")


def test_the_option_ranks_before_the_variable_before_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(REPOSITORIES_VARIABLE, "/elsewhere/named")
    assert repositories_folder("/given") == Path("/given")
    assert repositories_folder(None) == Path("/elsewhere/named")
    monkeypatch.setenv(REPOSITORIES_VARIABLE, "relative")
    assert repositories_folder(None).resolve() == tmp_path / "relative"
    monkeypatch.setenv(REPOSITORIES_VARIABLE, "")
    assert repositories_folder(None) == tmp_path / "repositories"
    monkeypatch.delenv(REPOSITORIES_VARIABLE)
    assert repositories_folder(None) == tmp_path / "repositories"


@pytest.mark.parametrize("command", READERS)
def test_the_help_of_every_command_that_reads_the_clone_names_the_variable(command, capsys):
    with pytest.raises(SystemExit) as stopped:
        main([command, "--help"])
    assert stopped.value.code == 0
    assert REPOSITORIES_VARIABLE in capsys.readouterr().out


def request(monkeypatch, folder: Path, *options: str) -> tuple[int, bytes | None]:
    """The exit status of ``request`` for the start commit, started in the new ``folder``, and the
    request it wrote there."""
    folder.mkdir()
    monkeypatch.chdir(folder)
    status = main(["request", "--revision", START, "--label", "N", "--run-id", "x",
                   "--output", "request.json", *options])
    written = folder / "request.json"
    return status, written.read_bytes() if written.exists() else None


def test_a_request_reads_the_clone_the_variable_names_unless_the_option_names_another(monkeypatch, tmp_path, capsys):
    status, expected = request(monkeypatch, tmp_path / "option", "--repositories", str(REPOSITORIES))
    assert status == 0 and expected is not None

    monkeypatch.setenv(REPOSITORIES_VARIABLE, str(REPOSITORIES))
    assert request(monkeypatch, tmp_path / "variable") == (0, expected)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv(REPOSITORIES_VARIABLE, str(empty))
    assert request(monkeypatch, tmp_path / "option-wins", "--repositories", str(REPOSITORIES)) == (0, expected)
    assert request(monkeypatch, tmp_path / "variable-wins") == (1, None)
    capsys.readouterr()
