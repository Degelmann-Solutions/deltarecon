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
