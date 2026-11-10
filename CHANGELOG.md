# Changelog

Every published release of DeltaRecon has an entry here, newest first: its tag and commit, the commit of `delib-history` its packages hold, the SHA-256 of each archive that was uploaded to the GitHub release, and the date it was published. A release page may be deleted later; its entry here and its tag remain, so the record of what was published, and when, stays in the repository.

The SHA-256 values are those of `SHA256SUMS` in the release folder `dist/release-v<version>/` that the release was uploaded from; after each upload the archives were downloaded again and matched those values. The commit of `delib-history` is read from the clone inside both archives.

## 0.2.0 — published 2026-11-10

- Tag `v0.2.0`, commit `cafb5a702752e926d4cf2bcca25789fe6e40ce4b`
- `delib-history` in the packages: `6a3ca53281ac353963412214cd2b54187facb728`
- `deltarecon-0.2.0-x86_64-pc-windows-msvc.zip` SHA-256 `c44f65968205506fa44af7639b399cd97b96a2fe175ff4ad6cbb2fdd5be4bc4d`
- `deltarecon-0.2.0-x86_64-unknown-linux-gnu.tar.gz` SHA-256 `67d083492770c63db4e264464b73528c51883a7c8b1885ac09f8777b70f1501f`
- Release page: published.
- Changes: an engine other than the reference model connects through the protocol module `degelmann/deltarecon/protocol.py` alone and is selected with `--engine <module>:<class>` and `--engine-path <folder>` (or `DELTARECON_ENGINE` and `DELTARECON_ENGINE_PATH`), without a rebuild of the package; engine options are given as `--engine-option key=value`, which replaces `--path` of the reference model. The tool writes contract version 3.3: an engine declares its stages, their quantities and its domain reference (3.2), and names the history source of its revisions (3.3). The toy engine in `examples/toy_engine/`, with two stages and a revision history that is not a Git repository, shows the protocol, and the package check runs it from both unpacked packages. The oracle is renewed under contract 3.3, the 3.1 oracle archived unchanged in `oracle/archive/2026-10-28/`.

## 0.1.4 — published 2026-11-04

- Tag `v0.1.4`, commit `887584dbf90c2220e108b8fb4e911f7903def02c`
- `delib-history` in the packages: `6a3ca53281ac353963412214cd2b54187facb728`
- `deltarecon-0.1.4-x86_64-pc-windows-msvc.zip` SHA-256 `54c1d32bc50f5f2e148b66ef5550a0808d20abd00ac67f34e6d69aef31a43b72`
- `deltarecon-0.1.4-x86_64-unknown-linux-gnu.tar.gz` SHA-256 `1f9345dd7e40321e19b7efee236db67a861718865ac5c295ed73cb5387b8a74a`
- Release page: published.
- Changes: the worker processes compute with single-threaded BLAS (`OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` are `1` while a pool runs), so one worker per processor no longer exhausts the memory a small Windows machine can commit; the number of workers is unchanged.

## 0.1.3 — published 2026-11-02

- Tag `v0.1.3`, commit `ffc37ff3c3b30a9c417e77335f19859c1bd83085`
- `delib-history` in the packages: `6a3ca53281ac353963412214cd2b54187facb728`
- `deltarecon-0.1.3-x86_64-pc-windows-msvc.zip` SHA-256 `2ced94dff134ec6b8bd3e43fb5c15360b265b65941371ef34af63ccbd4d06621`
- `deltarecon-0.1.3-x86_64-unknown-linux-gnu.tar.gz` SHA-256 `1ae77db92948ae22e740f67b9cc8132cd90b8ac55f878c6fe417be3419f7e7c2`
- Release page: published.
- Changes: the packages carry no trace of the build machine (no reflog in the packaged `delib-history`, its remote the public repository, no install path in the wheel metadata), start Python isolated from the current folder and the user's site-packages, and both hold one clone of `delib-history`; the guided demo reports a missing clone where it can be created and answers a folder it cannot create with a message instead of a traceback, and a clone that cannot be read is reported as such, not as missing.

## 0.1.2 — published 2026-11-02

- Tag `v0.1.2`, commit `9b205ae87d40b63553751347146bfcc402c88546`
- `delib-history` in the packages: `6a3ca53281ac353963412214cd2b54187facb728`
- `deltarecon-0.1.2-x86_64-pc-windows-msvc.zip` SHA-256 `9a936ac884f31f4af3f842a8940f1d3fc3c5b6ee63d9effbb916c0589263a422`
- `deltarecon-0.1.2-x86_64-unknown-linux-gnu.tar.gz` SHA-256 `b585b69adeacfdc95e900f064c190f87c04b86298110f06d3fa8527be929aac8`
- Release page: deleted 2026-11-02; tag kept.
- Changes: the copyright line of `LICENSE` names Degelmann GmbH; the packages hold `delib-history` brought up to date, whose own files name Degelmann GmbH as well.

## 0.1.1 — published 2026-11-01

- Tag `v0.1.1`, commit `20638768c655193bb637ed1461556734585827f1`
- `delib-history` in the packages: `ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33`
- `deltarecon-0.1.1-x86_64-pc-windows-msvc.zip` SHA-256 `ca98174f07d48239b350c3fe631c93002788a476dcd18892aaf3255e1d130134`
- `deltarecon-0.1.1-x86_64-unknown-linux-gnu.tar.gz` SHA-256 `f0c3dede22bfe4b2be3606d2d0f1a885168323ef96c155760a39fb7c17790fc5`
- Release page: deleted 2026-11-02; tag kept.
- Changes: the guided demo `deltarecon quickstart`, started by `quickstart.cmd` or `./quickstart`, and a guide in German and English in each package.

## 0.1.0 — published 2026-10-29

- Tag `v0.1.0`, commit `8416c3021ff97e909f272863e449ad52e4be2e06`
- `delib-history` in the packages: `d24778f298dd2547455ada346529704bb1f03071`
- `deltarecon-0.1.0-x86_64-pc-windows-msvc.zip` SHA-256 `607133cc76cc46a13013b2120b9418af611e345a3ca7a44251ad012529e4952a`
- `deltarecon-0.1.0-x86_64-unknown-linux-gnu.tar.gz` SHA-256 `9726e286ed6f7655712fc08e9044a6f8fbd0750928e4504ffd873f37d30cc7e2`
- Release page: deleted 2026-11-02; tag kept.
- Changes: the first release: a package for Windows and one for Linux, each with a Python 3.14.9, the locked libraries, the contract pack and `delib-history`, built to run the quick start without Python, uv or Git on the machine.
