# Reproductions of the oracle

The first row is the run that computed the published hashes, from fresh clones of both public repositories. Every later row is one run of the README section "Reproduce the reference attribution" from fresh clones, checked with `sha256sum -c` against `SHA256SUMS` in this folder. The published hashes are never changed to match a run; a run that differs is recorded here with the differing files and the cause.

| Date | Operating system | CPU | Python | Engine version | deltarecon | delib-history | Result |
|---|---|---|---|---|---|---|---|
| 2026-10-22 | Linux 6.6.87.2 under WSL2 | Intel Core i7-12800HX, x86-64 | 3.12.13, installed by `uv sync` | `modelx 0.33.0, pandas 3.0.6, numpy 2.5.3, Python 3.12.13` | `45f7f064e878d600e3b736e2a74643485746605a` | `ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33` | 25 of 25 OK; the run that computed the published hashes |
| 2026-10-23 | Windows NT 10.0 build 26300, Git Bash | Intel Core i7-12800HX, x86-64 (reported as Intel64 Family 6 Model 151 Stepping 2; same host as row 1) | 3.12.13, the build `uv` downloads (`cpython-3.12.13-windows-x86_64-none`), on `PATH` with `UV_NO_MANAGED_PYTHON=1` | `modelx 0.33.0, pandas 3.0.6, numpy 2.5.3, Python 3.12.13` | `a53516dd14532eff56a812811f194d63dcf53170` | `ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33` | 25 of 25 OK |

Both rows ran on the same hardware. The second differs in operating system, in the Python build (python-build-standalone for Windows against the Linux build compiled with Clang) and in the numpy wheel (built with MSVC against GCC; both bundle OpenBLAS 0.3.34.106.0). Whether other hardware, another CPU vendor or another architecture such as ARM64, gives the same bytes is not checked yet.

Between the two deltarecon commits no file under `degelmann/` or `contracts/` and not `uv.lock` changes: `a53516d` adds to `45f7f06` the oracle files, `tests/test_oracle.py` and README changes. The two requests it adds are the bytes the first run wrote, so both rows run the same input.

## Notes on the Windows run

- `uv 0.9.15` knows no Python 3.12.13, so `uv sync --python 3.12.13` failed; `uv self update` to 0.13.5 fixed it.
- `uv 0.13.5` downloaded the interpreter but failed with Windows os error 448 ("untrusted mount point") while creating the junction of its minor version link, also with a fresh `UV_PYTHON_INSTALL_DIR`. The run used the downloaded interpreter folder, copied to `C:\py31213`, first on `PATH` and with `UV_NO_MANAGED_PYTHON=1`; every README command then ran unchanged.
- Durations: the two runs 176 s and 143 s, the walk of 36 states 4446 s.
