# Reproductions of the oracle

The first row is the run that computed the published hashes under contract version 3.0. Every later row is one run of the README section "Reproduce the reference attribution" from fresh clones, checked with `sha256sum -c` against `SHA256SUMS` in this folder. The published hashes are never changed to match a run; a run that differs is recorded here with the differing files and the cause.

| Date | Operating system | CPU | Python | Engine version | deltarecon | delib-history | Result |
|---|---|---|---|---|---|---|---|
| 2026-10-24 | Linux 6.6.87.2 under WSL2 | Intel Core i7-12800HX, x86-64 | 3.14.9, uv-managed, installed by `uv sync` (uv 0.13.5) | `modelx 0.33.0, pandas 3.0.6, numpy 2.5.3, Python 3.14.9` | the commit that pins Python 3.14.9 | `ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33` | the run that computed the published hashes; 24 of 24 signature tables equal the archived ones apart from `contract_version` |

The run used fresh clones of deltarecon and `delib-history`. The deltarecon clone held the code of the commit that pins Python 3.14.9; that commit adds only the hash of `walk.result.json`, the text of this file, the README text on the computation and its durations, and the docstring of `tests/test_oracle.py`, none of which the run reads. Its requests are the bytes `deltarecon request` writes for the two revisions, and equal the archived requests apart from `contract_version` and the engine version. Each of its 24 signature tables, with `contract_version` set back to `2.0`, hashes to the digest the archived `SHA256SUMS` lists. In the same clone `uv run pytest -q` passed before the runs. Durations: the two runs about 90 s each, the walk of 36 states about 77 minutes.

An earlier computation under Python 3.12.13, with deltarecon at commit `426d1b6a197c2da426c048678a1a21794a4b6b23` and the engine version `modelx 0.33.0, pandas 3.0.6, numpy 2.5.3, Python 3.12.13`, gave the same 24 signature tables and the `walk.result.json` hash `867081d325a053653f15e3bfa8e0cc9cfa06931fecd72594ca8b4143e9b2e0cc`. That hash was replaced when the interpreter moved to Python 3.14.9, because the walk result holds the hashes of the run responses and each response names the engine version.

## Archive

The oracle published on 2026-10-22 under contract version 2.0 is kept unchanged in [`archive/2026-10-22/`](archive/2026-10-22/): its two requests, its `SHA256SUMS`, and its `REPRODUCTIONS.md` with the computation under Linux and the reproduction under Windows. It is reproduced with deltarecon at commit `a53516d`.
