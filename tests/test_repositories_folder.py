"""Where the commands read the clone: ``--repositories DIR``, else the folder the environment
variable ``DELTARECON_REPOSITORIES`` names, else the nearest folder ``repositories/`` that holds the
clone folder ``delib-history``, in the working directory or one of its parents, else ``repositories/``
in the working directory.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.run import CLONE_NAME, REPOSITORIES_VARIABLE, repositories_folder

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


def holder(folder: Path) -> None:
    """``folder/repositories`` with an (empty) clone folder in it."""
    (folder / "repositories" / CLONE_NAME).mkdir(parents=True)


@pytest.fixture
def tree(monkeypatch, tmp_path):
    """``tmp_path/a/b/c`` as the working directory, without the variable."""
    monkeypatch.delenv(REPOSITORIES_VARIABLE, raising=False)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    return tmp_path


def test_the_option_wins_over_a_folder_found_upward(tree):
    holder(tree)
    assert repositories_folder("given") == Path("given")


@pytest.mark.parametrize("named, expected", [("/elsewhere/named", Path("/elsewhere/named")),
                                             ("relative", Path("relative"))])
def test_the_variable_wins_over_a_folder_found_upward(tree, monkeypatch, named, expected):
    holder(tree)
    monkeypatch.setenv(REPOSITORIES_VARIABLE, named)
    assert repositories_folder(None) == expected


def test_the_folder_in_the_working_directory_is_found(tree):
    holder(tree / "a" / "b" / "c")
    holder(tree)
    assert repositories_folder(None) == tree / "a" / "b" / "c" / "repositories"


def test_the_folder_in_a_parent_is_found(tree):
    holder(tree / "a")
    assert repositories_folder(None) == tree / "a" / "repositories"


def test_the_nearer_of_two_folders_is_found(tree):
    holder(tree)
    holder(tree / "a" / "b")
    assert repositories_folder(None) == tree / "a" / "b" / "repositories"


def test_a_file_named_repositories_is_not_a_folder(tree):
    (tree / "a" / "b" / "repositories").write_text("")
    holder(tree)
    assert repositories_folder(None) == tree / "repositories"


def test_without_a_folder_upward_the_working_directory_is_named(tree):
    assert repositories_folder(None) == tree / "a" / "b" / "c" / "repositories"


def test_a_nearer_folder_without_the_clone_is_passed_over(tree):
    (tree / "a" / "b" / "repositories").mkdir()
    (tree / "a" / "b" / "repositories" / "other").mkdir()
    holder(tree)
    assert repositories_folder(None) == tree / "repositories"


def test_folders_without_the_clone_give_the_working_directory(tree):
    (tree / "a" / "b" / "c" / "repositories").mkdir()
    (tree / "repositories").mkdir()
    (tree / "repositories" / CLONE_NAME).write_text("")  # a file, not a clone folder
    assert repositories_folder(None) == tree / "a" / "b" / "c" / "repositories"


def test_an_empty_variable_searches_upward(tree, monkeypatch):
    holder(tree)
    monkeypatch.setenv(REPOSITORIES_VARIABLE, "")
    assert repositories_folder(None) == tree / "repositories"


def test_a_request_in_a_subfolder_of_the_checkout_finds_the_clone(monkeypatch, tmp_path):
    """A command started below the folder that holds ``repositories/`` reads the clone there."""
    monkeypatch.delenv(REPOSITORIES_VARIABLE, raising=False)
    root = tmp_path / "checkout"
    (root / "runs" / "demo").mkdir(parents=True)
    (root / "repositories").symlink_to(REPOSITORIES, target_is_directory=True)
    monkeypatch.chdir(root / "runs" / "demo")
    assert main(["request", "--revision", START, "--label", "N", "--run-id", "x", "--output", "request.json"]) == 0


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
