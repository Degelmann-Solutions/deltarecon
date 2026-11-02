"""The release tools of DeltaRecon.

The command-line modules, each run as ``uv run python tools/<name>.py``:

- ``build_package``: build the Linux or Windows package and check an archive;
- ``release``: build both packages of a release from one clean commit;
- ``measure_quick_start``: measure the README quick start, here or through the Windows package;
- ``windows_host``: run the README quick start natively on the Windows host of a WSL session.

The library modules, which the command-line modules and the tests import and which never import
a command-line module:

- ``common``: the checkout root, the pin of the quick-start search, ``Failed`` and ``Refused``,
  ``git_text``, ``engine_version``, ``sha256_file``, and the names shared with the package;
- ``quick_start_steps``: the quick-start steps of the README and how their folders are rewritten;
- ``host``: running PowerShell scripts on the Windows host and comparing a search with the pin;
- ``targets``: the target platforms, the launcher and starter texts, and the package names;
- ``python_runtime``: the project version, the pinned Python and its download;
- ``assembly``: the build of a package folder and its archive;
- ``guides``: the guides ``LIESMICH.txt`` and ``README.txt`` of a package;
- ``package_check``: the parts the Linux and the Windows check share;
- ``check_linux`` and ``check_windows``: the check of a Linux and of a Windows archive.
"""
