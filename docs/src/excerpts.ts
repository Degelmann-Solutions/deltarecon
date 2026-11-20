// The code a page shows of the repository, as it stands at the tag of the
// release the documentation applies to (release.json): the excerpts, each
// with its file and its lines, and the number of lines of the files a page
// states the size of. Nothing here is read from Git at build time, so the
// build needs no clone; scripts/check-excerpts.mjs holds every excerpt and
// every number of the built pages against `git show v<release>:<file>`.
//
// An excerpt is copied, never typed:
//   git show v<release>:<file> | sed -n '<first>,<last>p'
// A backtick in the copied lines is then written ${'`'}, since the code
// stands in a template.
import type { Lang } from './site';

export interface Excerpt {
  /** The file, by its path in the repository. */
  file: string;
  /** The first and the last line shown, counted from 1. */
  first: number;
  last: number;
  /** The lines as they stand in the file, character for character. */
  code: string;
}

/**
 * The code between the first and the last line break of a template. A backtick
 * of the code, which would end the template, is written `${'`'}`.
 */
const lines = (text: TemplateStringsArray, ...ticks: string[]): string =>
  String.raw(text, ...ticks).replace(/^\n/, '').replace(/\n$/, '');

export const excerpts: Record<string, Excerpt> = {
  // How the session of the reference model answers the first two questions.
  'session-questions': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 871,
    last: 876,
    code: lines`
    def model_point_ids(self) -> list[str]:
        with _readable_formula_errors():
            return [str(value) for value in self._points()[MODEL_POINT_ID_COLUMN]]

    def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
        return self._project_index(self._index(model_point_id))
`,
  },
  // The class of the reference model and its four statements about itself.
  'class-statements': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 997,
    last: 1005,
    code: lines`
class ReferenceModel:
    """The engine of the stage ${'`'}${'`'}liability_cashflow${'`'}${'`'}: modelx with the model ${'`'}${'`'}RLV_DE_S${'`'}${'`'},
    computed through its export or through modelx, as the engine version names."""

    # The stage of the domain reference of the pack, under the pair the pack reserves for it.
    stages = {STAGE: StageDeclaration(LIABILITY_CASHFLOW, tuple(STAGE_QUANTITIES[STAGE]))}
    realisations = frozenset({changes_contract.TEXT_PATCH, changes_contract.REVISION})
    determines = DETERMINED_KINDS
    holdable = {"input_data": frozenset({"data"})}  # the model point table, the class ${'`'}${'`'}data${'`'}${'`'}
`,
  },
  // How the reference model finds the folder of its histories.
  'repositories-folder': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 411,
    last: 420,
    code: lines`
    if repositories is not None:
        return Path(repositories)
    named = os.environ.get(REPOSITORIES_VARIABLE)
    if named:
        return Path(named)
    here = Path.cwd()
    for folder in (here, *here.parents):
        if (folder / REPOSITORIES_FOLDER / CLONE_NAME).is_dir():
            return folder / REPOSITORIES_FOLDER
    return here / REPOSITORIES_FOLDER
`,
  },
  // The check of a release: the clone and the files of its state.
  'locate-release': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1050,
    last: 1058,
    code: lines`
    def _locate(self, release: dict, repositories: Path) -> tuple[Path, dict[str, str]]:
        """The clone and the files of the release state: path and blob id.

        The files are those of the state commit, with the model point table of the
        input-data commit in place of its own.
        """
        revision, input_revision = parse_identity(release)
        clone = find_clone(repositories)
        return clone, self._files(clone, revision, input_revision)
`,
  },
  // The body of `describe`: options, the commit of the revision, the references.
  'describe-release': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1095,
    last: 1097,
    code: lines`
        path = path_option(options)
        commit = resolve_revision(revision, repositories)
        return {"label": label, "references": release_references(commit, input_revision, path)}
`,
  },
  // The part of `open` that restores the state into a scratch folder.
  'open-scratch': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1148,
    last: 1158,
    code: lines`
        with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as scratch:
            state = Path(scratch) / CLONE_NAME
            state.mkdir()
            # The model point table of the input-data commit lies over the restored tree.
            export_tree(clone, files, state)
            if patches:
                changes_contract.apply_changes(state, patches, manifest_dir)
            model = _read_model(state / PRODUCT_FOLDER)
            try:
                if path == "modelx":
                    yield ReferenceModelSession(model, workers=self.workers, state=state)
`,
  },
  // The quantities of the reference model, in domain order.
  'quantities': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 210,
    last: 221,
    code: lines`
QUANTITIES = (
    ("Anzahl Verträge", "policies", "pols_if", ("pols_if",)),
    ("Bruttobeitrag", "EUR", "prem_gross", ("prem_gross",)),
    ("Zahlbeitrag", "EUR", "premiums", ("premiums",)),
    ("Beitragsverrechnung", "EUR", "prem_rebate", ("prem_rebate",)),
    ("garantierte Todesfallleistung", "EUR", "claims_death", ("claims", "DEATH")),
    ("garantierter Rückkaufswert", "EUR", "claims_lapse", ("claims", "LAPSE")),
    ("garantierte Erlebensfallleistung", "EUR", "claims_maturity", ("claims", "MATURITY")),
    ("Kosten 2. Ordnung ohne Provisionen", "EUR", "expenses", ("expenses",)),
    ("Provisionen", "EUR", "commissions", ("commissions",)),
    ("Netto-Cashflow", "EUR", "net_cf", ("net_cf",)),
)
`,
  },
  // The end of `history`: each revision with its message and its classes.
  'history-revisions': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1119,
    last: 1125,
    code: lines`
        between = line[:line.index(old)][::-1]  # after the older commit, oldest first
        messages = log_messages(clone, between)
        revisions = []
        for parent, revision, message in zip([old] + between, between, messages):
            classes = {path_class(path) for path in touched_paths(clone, parent, revision)} - {None}
            revisions.append(Revision(revision, message, frozenset(classes)))
        return History(SOURCE, old, new, tuple(revisions))
`,
  },
  // `path_class`: the class of a path of the repository.
  'path-class': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 528,
    last: 537,
    code: lines`
def path_class(path: str) -> str | None:
    """The class of a path of the repository: ${'`'}${'`'}data${'`'}${'`'}, ${'`'}${'`'}parameter${'`'}${'`'}, ${'`'}${'`'}code${'`'}${'`'}, or none."""
    if path == MODEL_POINT_PATH:
        return "data"
    if path.startswith(f"{PRODUCT_FOLDER}/{MODEL_NAME}/"):
        return "code"
    folder, _, name = path.rpartition("/")
    if folder == PRODUCT_FOLDER and name.endswith(".csv"):
        return "parameter"
    return None
`,
  },
  // The body of `state_release`: the state after a revision.
  'state-release': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1082,
    last: 1086,
    code: lines`
        state, input_revision = recorded_identity(base)
        if revision is not None:
            state, input_revision = revision, (input_revision if "input_data" in hold else revision)
        return {"label": base["label"],
                "references": release_references(state, input_revision, release_path(base))}
`,
  },
  // The class is called with the worker count.
  'constructor': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1007,
    last: 1009,
    code: lines`
    def __init__(self, workers: int | None = None):
        """${'`'}${'`'}workers${'`'}${'`'} is the number of worker processes of a session, see :func:${'`'}worker_count${'`'}."""
        self.workers = worker_count(workers)
`,
  },
  // `input_revision` of the reference model.
  'input-revision': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1099,
    last: 1101,
    code: lines`
    def input_revision(self, release: dict) -> str:
        """The input-data revision of a recorded identity of any engine version, see :func:${'`'}recorded_identity${'`'}."""
        return recorded_identity(release)[1]
`,
  },
  // `resolve` of the reference model.
  'resolve-release': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1103,
    last: 1105,
    code: lines`
    def resolve(self, stage: str, release: dict, repositories: Path) -> None:
        # One stage: the run admits only a stage of ${'`'}${'`'}stages${'`'}${'`'}, so ${'`'}${'`'}stage${'`'}${'`'} selects nothing here.
        self._locate(release, repositories)
`,
  },
  // The two attributes of the session of the reference model.
  'session-attributes': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 812,
    last: 814,
    code: lines`
class ReferenceModelSession:
    time_basis = TIME_BASIS
    quantities = [(name, unit) for name, unit, _, _ in QUANTITIES]
`,
  },
  // `project_many` of the reference model.
  'project-many': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 878,
    last: 884,
    code: lines`
    def project_many(self, model_point_ids: list[str]) -> list:
        """The outcome of each id in the given order: its periods or its :class:${'`'}ModelPointFailure${'`'}.

        The parent maps each id to its row; the workers project by row and return the periods
        or the message of a failure, so a message is the same on every worker count.
        """
        return self._project_rows(model_point_ids, "_project_index")
`,
  },
  // `project_target` of the reference model.
  'project-target': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 886,
    last: 891,
    code: lines`
    def project_target(self, model_point_ids: list[str], quantities: list[str],
                       periods: tuple[int, int] | None) -> list:
        """The outcome of each id in the given order: the periods of its target window, with one value
        per name of ${'`'}${'`'}quantities${'`'}${'`'}, or its :class:${'`'}ModelPointFailure${'`'}; see "Target-only runs"."""
        return self._project_rows(model_point_ids, "_project_target_index", tuple(quantities),
                                  None if periods is None else tuple(periods))
`,
  },
  // The projection of one model point: results, checks, values per period.
  'project-index': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 945,
    last: 966,
    code: lines`
    def _project_index(self, index: int) -> list[tuple[int, list[float]]]:
        """The periods of the point of row ${'`'}${'`'}index${'`'}${'`'}. Raises :class:${'`'}ModelPointFailure${'`'}."""
        with self._projection(index, "result_cf") as projection:
            try:
                frame = projection.result_cf()
            except Exception as exc:  # a modelx FormulaError wraps the cause
                raise ModelPointFailure(self._failure("result_cf", exc, projection, index)) from None
            problems = []
            for check in CHECKS:
                try:
                    if not bool(getattr(projection, check)()):
                        problems.append(f"{check} is false")
                except Exception as exc:
                    problems.append(self._failure(check, exc, projection, index))
            if problems:
                raise ModelPointFailure("; ".join(problems))
            try:
                columns = [[float(value) for value in frame[column]] for _, _, column, _ in QUANTITIES]
                periods = [int(period) for period in frame.index]
            except Exception as exc:
                raise _form_failure("result_cf", exc) from None
            return [(period, [column[row] for column in columns]) for row, period in enumerate(periods)]
`,
  },
  // The parameter inventory of the reference model.
  'parameters': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 972,
    last: 994,
    code: lines`
    def _parameters(self) -> list[dict]:
        inventory: dict[str, dict] = {}

        def add(parameter: dict) -> None:
            if parameter["name"] in inventory:
                raise RuntimeError(f"two parameters of the model have the name {parameter['name']}")
            inventory[parameter["name"]] = parameter

        for space in (self._model.Projection, self._model.Data):
            for name, value in space.refs.items():
                if not name.startswith("_") and name not in NOT_A_PARAMETER and _is_scalar(value):
                    add({"name": name, "type": "scalar", "value": _plain(value)})
        for name in PARAMETER_TABLES:
            frame = getattr(self._model.Data, name)()
            value_columns = [str(c) for c in frame.columns if c not in NOT_A_VALUE_COLUMN]
            rows = []
            for key, values in zip(frame.index, frame[value_columns].itertuples(index=False, name=None)):
                key = list(key) if isinstance(key, tuple) else [key]
                rows.append({"key": [_plain(k) for k in key], "values": [_plain(v) for v in values]})
            add({"name": name, "type": "keyed_table",
                 "key_columns": [str(c) for c in frame.index.names],
                 "value_columns": value_columns, "rows": rows})
        return [inventory[name] for name in sorted(inventory)]
`,
  },
  // `open` refuses a revision of another history source first.
  'open-foreign': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1131,
    last: 1135,
    code: lines`
        foreign = [c["id"] for c in enabled
                   if c["realisation"]["type"] == changes_contract.REVISION and c["realisation"]["source"] != SOURCE]
        if foreign:
            raise Rejection("unsupported_realisation", f"The change {foreign[0]} is a revision of another history "
                            f"source than {SOURCE}, which the reference model cannot realise.", change_ids=foreign)
`,
  },
  // `open`: the files of the state, after the last enabled revision.
  'open-revisions': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1136,
    last: 1147,
    code: lines`
        clone, files = self._locate(release, repositories)
        path = release_path(release)
        revisions = [c["realisation"]["revision"] for c in enabled
                     if c["realisation"]["type"] == changes_contract.REVISION]
        patches = [c for c in enabled if c["realisation"]["type"] != changes_contract.REVISION]
        if revisions:  # the state after the last enabled revision; the request's state is the base
            _, input_revision = parse_identity(release)
            last = revisions[-1]
            try:
                files = self._files(clone, last, input_revision if "input_data" in hold else last)
            except Rejection as rejection:  # the request is accepted; the state cannot be restored
                raise RuntimeError(rejection.message) from None
`,
  },
};

/**
 * The signature of each member of the protocol, as it stands at the tag: the
 * lines of the file, without the indentation they share. The member card
 * (components/Member.astro) shows it; scripts/check-excerpts.mjs holds it
 * against the tag like an excerpt. The two optional operations of a session
 * have no line of their own in the protocol, which describes them in a
 * comment: their signature is that of the reference model.
 */
export const signatures: Record<string, Excerpt> = {
  'Engine.stages': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 167,
    last: 167,
    code: lines`
stages: Mapping[str, StageDeclaration]
`,
  },
  'Engine.realisations': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 168,
    last: 168,
    code: lines`
realisations: frozenset[str]  # the realisation types of a change the engine can apply
`,
  },
  'Engine.determines': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 169,
    last: 169,
    code: lines`
determines: frozenset[str]    # the kinds of release reference one revision fixes
`,
  },
  'Engine.holdable': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 172,
    last: 172,
    code: lines`
holdable: Mapping[str, frozenset[str]]
`,
  },
  'Engine.repositories_folder': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 174,
    last: 174,
    code: lines`
def repositories_folder(self, given: Path | str | None) -> Path:
`,
  },
  'Engine.resolve': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 182,
    last: 182,
    code: lines`
def resolve(self, stage: str, release: dict, repositories: Path) -> None:
`,
  },
  'Engine.describe': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 194,
    last: 195,
    code: lines`
def describe(self, stage: str, label: str, revision: str, options: Mapping[str, str], repositories: Path,
             input_revision: str | None = None) -> dict:
`,
  },
  'Engine.input_revision': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 211,
    last: 211,
    code: lines`
def input_revision(self, release: dict) -> str:
`,
  },
  'Engine.open': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 220,
    last: 221,
    code: lines`
def open(self, stage: str, release: dict, enabled: list[dict], manifest_dir: Path | None,
         repositories: Path, hold: frozenset[str] = frozenset()) -> ContextManager[Session]:
`,
  },
  'Engine.history': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 247,
    last: 247,
    code: lines`
def history(self, older: dict, newer: dict, repositories: Path) -> History:
`,
  },
  'Engine.state_release': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 269,
    last: 270,
    code: lines`
def state_release(self, base: dict, revision: str | None, hold: frozenset[str],
                  repositories: Path) -> dict:
`,
  },
  'Session.time_basis': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 59,
    last: 59,
    code: lines`
time_basis: str
`,
  },
  'Session.quantities': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 60,
    last: 60,
    code: lines`
quantities: list[tuple[str, str]]  # name and unit, in export column order
`,
  },
  'Session.model_point_ids': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 62,
    last: 62,
    code: lines`
def model_point_ids(self) -> list[str]:
`,
  },
  'Session.project': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 65,
    last: 65,
    code: lines`
def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
`,
  },
  'Session.parameters': {
    file: 'degelmann/deltarecon/protocol.py',
    first: 85,
    last: 85,
    code: lines`
def parameters(self) -> list[dict]:
`,
  },
  'Session.project_many': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 878,
    last: 878,
    code: lines`
def project_many(self, model_point_ids: list[str]) -> list:
`,
  },
  'Session.project_target': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 886,
    last: 887,
    code: lines`
def project_target(self, model_point_ids: list[str], quantities: list[str],
                   periods: tuple[int, int] | None) -> list:
`,
  },
  'constructor': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 1007,
    last: 1007,
    code: lines`
def __init__(self, workers: int | None = None):
`,
  },
};

/** The files a page states the size of. */
export const files = {
  /** The connection of the reference model. */
  connection: 'degelmann/deltarecon/engines/reference_model.py',
  /** The protocol between DeltaRecon and an engine. */
  protocol: 'degelmann/deltarecon/protocol.py',
} as const;

/** The number of lines of each such file at the tag. */
const lineCounts: Record<string, number> = {
  [files.connection]: 1170,
  [files.protocol]: 281,
};

/** What is wrong with an excerpt of the register, one sentence per fault. */
export function excerptFaults(excerpt: Excerpt): string[] {
  const faults: string[] = [];
  if (!Number.isInteger(excerpt.first) || !Number.isInteger(excerpt.last) || excerpt.first < 1 || excerpt.last < excerpt.first) {
    faults.push(`its lines ${excerpt.first} to ${excerpt.last} are no range`);
    return faults;
  }
  const held = excerpt.code.split('\n').length;
  const named = excerpt.last - excerpt.first + 1;
  if (held !== named) faults.push(`it holds ${held} lines and names ${named} (${excerpt.first} to ${excerpt.last})`);
  return faults;
}

/** The number of lines of a file at the tag; throws for a file without one. */
export function lineCount(file: string): number {
  const count = lineCounts[file];
  if (count === undefined) throw new Error(`no number of lines for "${file}" (src/excerpts.ts)`);
  return count;
}

/** A number as the language writes it: 1,170 in English, 1.170 in German. */
export function inWords(count: number, lang: Lang): string {
  return String(count).replace(/\B(?=(\d{3})+$)/g, lang === 'de' ? '.' : ',');
}
