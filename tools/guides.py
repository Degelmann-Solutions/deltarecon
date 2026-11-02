"""The guides of a package folder: ``LIESMICH.txt`` (German) and ``README.txt`` (English), UTF-8
without BOM, LF on Linux and CRLF on Windows. Each names the version and platform, how to start
the guided demo, the six commands of the README quick start (``STEPS`` of
``tools/quick_start_steps.py``; on Windows a cmd and a PowerShell block), and the README at the tag
``v<version>``.
"""
from __future__ import annotations

from pathlib import Path

from tools.common import REPOSITORY_URL
from tools.quick_start_steps import STEPS
from tools.targets import LAUNCHER, TARGETS, WINDOWS_LAUNCHER, WINDOWS_TARGET

# The guides in the package folder: German and English.
GUIDES = {"de": "LIESMICH.txt", "en": "README.txt"}


def guide_commands(target_name: str, prefix: str) -> list[str]:
    """The six commands of the README quick start (``STEPS`` of ``tools/quick_start_steps.py``), with
    ``uv run deltarecon`` replaced by ``prefix`` and, for Windows, every ``/`` by ``\\``."""
    lines = []
    for step in STEPS.values():
        assert step["argv"][:3] == ["uv", "run", "deltarecon"], step["argv"]
        arguments = step["argv"][3:]
        if target_name == WINDOWS_TARGET:
            arguments = [argument.replace("/", "\\") for argument in arguments]
        lines.append(" ".join([prefix, *arguments]))
    return lines


def _block(lines: list[str]) -> str:
    return "".join(f"    {line}\n" for line in lines)


def guide_text(lang: str, target_name: str, version: str) -> str:
    """The guide of the package folder, German (``de``) or English (``en``), for the target: the guided
    demo first, then the six commands of the README, then where to read on. LF on Linux, CRLF on Windows."""
    windows = target_name == WINDOWS_TARGET
    platform = TARGETS[target_name]["platform"]
    readme = f"{REPOSITORY_URL}/blob/v{version}/README.md"
    stamp = "<UTC-Zeit>" if lang == "de" else "<UTC time>"
    demo_folder = f"runs\\quickstart-{stamp}\\" if windows else f"runs/quickstart-{stamp}/"
    runs = "runs\\" if windows else "runs/"
    if windows:
        cmd = _block(guide_commands(target_name, WINDOWS_LAUNCHER))
        powershell = _block(guide_commands(target_name, ".\\" + WINDOWS_LAUNCHER))
    else:
        sh = _block(guide_commands(target_name, "./" + LAUNCHER))
    if lang == "de":
        title = f"DeltaRecon {version} für {platform}"
        intro = ("Dieser Ordner ist das DeltaRecon-Paket. Es braucht kein Python, kein uv und kein Git.\n")
        if windows:
            intro += ("Das Paket ist nicht signiert; SmartScreen kann deshalb beim Start warnen.\n")
            start = ("Starten Sie die Demo mit einem Doppelklick auf quickstart.cmd. Oder öffnen Sie\n"
                     "cmd in diesem Ordner und geben Sie ein:\n\n"
                     "    quickstart.cmd\n\n"
                     "Oder öffnen Sie PowerShell in diesem Ordner und geben Sie ein:\n\n"
                     "    .\\quickstart.cmd\n\n")
            end = "Am Ende bleibt das Fenster offen, bis Sie eine Taste drücken.\n"
            example = ".\\quickstart.cmd --lang en --no-pause"
            single = ("In cmd:\n\n" + cmd + "\nIn PowerShell:\n\n" + powershell)
        else:
            start = ("Starten Sie die Demo im Terminal in diesem Ordner:\n\n"
                     "    ./quickstart\n\n")
            end = "Am Ende wartet sie im Terminal auf Enter, bevor sie sich beendet.\n"
            example = "./quickstart --lang en --no-pause"
            single = sh
        body = f"""{title}

{intro}
1. Die geführte Demo

{start}Die Demo erklärt vier Schritte und wartet vor jedem auf Enter. Sie spricht
die Sprache des Systems; --lang de oder --lang en wählt Deutsch oder Englisch,
--no-pause lässt sie ohne Warten durchlaufen, zum Beispiel:

    {example}

Sie schreibt ihre Dateien in den neuen Ordner {demo_folder} in diesem
Ordner und nennt ihn am Anfang und am Ende.
{end}
2. Die einzelnen Befehle

Die Demo führt die Befehle des Schnellstarts für Sie aus, ohne replay. Einzeln
starten Sie sie aus diesem Ordner. Sie schreiben nach {runs} in diesem Ordner.

{single}
Der Befehl regression endet absichtlich mit dem Status 1: Er meldet die
Abweichung zwischen den beiden Revisionen. Die folgenden Befehle laufen
trotzdem.

3. Weiterlesen

Jeder Befehl ist in der README.md des Projekts auf GitHub beschrieben, im Stand dieser Version:
{readme}
LICENSE in diesem Ordner ist die Lizenz von DeltaRecon.
"""
    elif lang == "en":
        title = f"DeltaRecon {version} for {platform}"
        intro = "This folder is the DeltaRecon package. It needs no Python, no uv and no Git.\n"
        if windows:
            intro += "The package is not signed, so SmartScreen may warn when you start it.\n"
            start = ("Start the demo with a double click on quickstart.cmd. Or open cmd in this\n"
                     "folder and type:\n\n"
                     "    quickstart.cmd\n\n"
                     "Or open PowerShell in this folder and type:\n\n"
                     "    .\\quickstart.cmd\n\n")
            end = "At the end the window stays open until you press a key.\n"
            example = ".\\quickstart.cmd --lang de --no-pause"
            single = ("In cmd:\n\n" + cmd + "\nIn PowerShell:\n\n" + powershell)
        else:
            start = ("Start the demo in a terminal in this folder:\n\n"
                     "    ./quickstart\n\n")
            end = "At the end it waits in the terminal for Enter before it closes.\n"
            example = "./quickstart --lang de --no-pause"
            single = sh
        body = f"""{title}

{intro}
1. The guided demo

{start}The demo explains four steps and waits for Enter before each. It speaks the
language of the system; --lang de or --lang en chooses German or English,
--no-pause runs it through without waiting, for example:

    {example}

It writes its files to the new folder {demo_folder} in this folder
and names it at the start and at the end.
{end}
2. The single commands

The demo runs the commands of the quick start for you, apart from replay. To run
them one by one, start them from this folder. They write to {runs} in this folder.

{single}
The regression exits with status 1 by design: it reports the deviation between
the two revisions. The next commands run all the same.

3. Read on

Every command is described in the project's README.md on GitHub, as of this version:
{readme}
LICENSE in this folder is the licence of DeltaRecon.
"""
    else:
        raise ValueError(f"no guide in the language {lang!r}")
    return body.replace("\n", "\r\n") if windows else body


def write_guides(folder: Path, target_name: str, version: str) -> list[Path]:
    """Both guides of the target in ``folder``, UTF-8 without BOM."""
    paths = []
    for lang, name in GUIDES.items():
        path = folder / name
        path.write_bytes(guide_text(lang, target_name, version).encode("utf-8"))
        paths.append(path)
    return paths
