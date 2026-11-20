// What the connection of the reference model takes and gives, member by
// member of the protocol: the samples of the page "Build an adapter step by
// step", the same in both languages. Each was read from a call of the
// reference model of the release v0.2.0 on the two revisions of the quick
// start (release N and the state N+1); `…` stands for what is left out. A
// sample is an illustration and no code to run. No check holds the samples;
// whoever renews the release calls the members again.
const N = 'fa368575a66d97c94e96dffc62b273ec95511b12';
const N1 = '887b7181d22550eda2fb52fa1a6bd77376d4eb2e';
const FIRST = 'b795d8ac10208df75fbe2f8fb494895e8c4f4402';
const SECOND = '936e50dee4f7a01bdd60ff9105b5e3f3c1ef0d0f';
const GIT = 'git:https://github.com/Degelmann-Solutions/delib-history@';
const VERSION = 'modelx 0.33.0 export, pandas 3.0.6, numpy 2.5.3, Python 3.14.9';

/** A release identity of the reference model, as lines. */
const identity = (label: string, state: string, input: string, indent = ''): string[] =>
  [
    '{',
    `  "label": "${label}",`,
    '  "references": [',
    `    {"kind": "code_state", "value": "${GIT}${state}"},`,
    `    {"kind": "parameter_set", "value": "${GIT}${state}"},`,
    `    {"kind": "input_data", "value": "${GIT}${input}"},`,
    `    {"kind": "engine_version", "value": "${VERSION}"}`,
    '  ]',
    '}',
  ].map((line) => indent + line);

export const samples: Record<string, readonly string[]> = {
  constructor: ['ReferenceModel()', 'ReferenceModel(4)', 'ReferenceModel(1)'],
  stages: [
    'stages = {',
    '    "liability_cashflow": StageDeclaration(',
    '        DomainReference("liability_cashflow", "3"),',
    '        ("Anzahl Verträge", "Bruttobeitrag", "Zahlbeitrag", "Beitragsverrechnung",',
    '         "garantierte Todesfallleistung", "garantierter Rückkaufswert",',
    '         "garantierte Erlebensfallleistung", "kalkulatorische Kosten",',
    '         "Kosten 2. Ordnung ohne Provisionen", "Provisionen", "Netto-Cashflow"),',
    '    ),',
    '}',
  ],
  realisations: ['realisations = frozenset({"text_patch", "revision"})'],
  determines: ['determines = frozenset({"code_state", "parameter_set", "input_data"})'],
  holdable: ['holdable = {"input_data": frozenset({"data"})}'],
  describe: [
    `describe("liability_cashflow", "N", "${N}", {}, repositories)`,
    '',
    ...identity('N', N, N),
  ],
  'describe-input': [
    `describe("liability_cashflow", "N+1", "${N1}", {}, repositories,`,
    `         input_revision="${N}")`,
    '',
    ...identity('N+1', N1, N),
  ],
  resolve: ['resolve("liability_cashflow", release, repositories)', '', 'None'],
  input_revision: ['input_revision(release)', '', `"${N}"`],
  open: [
    'enabled = [',
    '  {',
    `    "id": "${FIRST}",`,
    '    "class": [],',
    '    "description": "Tell release N apart from the present state in the provenance tests…",',
    '    "prerequisites": [],',
    '    "conflicts": [],',
    `    "realisation": {"type": "revision", "source": "git", "revision": "${FIRST}"}`,
    '  }',
    ']',
    'hold = frozenset({"input_data"})',
  ],
  history: [
    'History(',
    '    source="git",',
    `    older="${N}",`,
    `    newer="${N1}",`,
    '    revisions=(',
    `        Revision(id="${FIRST}",`,
    '                 message="Tell release N apart from the present state in the provenance tests\\n\\n…",',
    '                 classes=frozenset()),',
    `        Revision(id="${SECOND}",`,
    '                 message="Lower the lapse rate of policy year 1 from 0.06 to 0.05\\n\\n…",',
    '                 classes=frozenset({"parameter"})),',
    '        …',
    '    ),',
    ')',
  ],
  state_release: [
    `state_release(base, "${FIRST}", frozenset({"input_data"}), repositories)`,
    '',
    ...identity('N', FIRST, N),
  ],
  time_basis: ['time_basis = "policy_month"'],
  quantities: [
    'quantities = [',
    '    ("Anzahl Verträge", "policies"),',
    '    ("Bruttobeitrag", "EUR"),',
    '    ("Zahlbeitrag", "EUR"),',
    '    …',
    '    ("Netto-Cashflow", "EUR"),',
    ']',
  ],
  model_point_ids: ['model_point_ids()', '', '["RLV-000001", "RLV-000002", "RLV-000003", …]'],
  project: [
    'project("RLV-000001")',
    '',
    '[',
    '    (0, [1.0, 1275.411881840093, 733.0114030306528, 542.4004788094402, 15.274524675665258,',
    '         0.0, 0.0, 188.92994976481063, 637.7059409200465, -108.8990123298696]),',
    '    (1, [0.9948047673482483, 0.0, 0.0, 0.0, 15.195169966330255,',
    '         0.0, 0.0, 7.474090024842386, 0.0, -22.66925999117264]),',
    '    …',
    ']',
  ],
  parameters: [
    'parameters()',
    '',
    '[',
    '    {"name": "benefit_schedule", "type": "keyed_table",',
    '     "key_columns": ["schedule_id", "policy_year"], "value_columns": ["benefit_factor"],',
    '     "rows": [{"key": ["konstant", 1], "values": [1.0]}, {"key": ["konstant", 2], "values": [1.0]}, …]},',
    '    {"name": "benefit_schedule_file", "type": "scalar", "value": "benefit_schedule.csv"},',
    '    {"name": "beta_tariff", "type": "scalar", "value": 0.05},',
    '    …',
    ']',
  ],
  project_many: [
    'project_many(["RLV-000001", "RLV-000002"])',
    '',
    '[',
    '    [(0, [1.0, 1275.411881840093, …]), (1, [0.9948047673482483, 0.0, …]), …],',
    '    [(0, [1.0, …]), …],',
    ']',
  ],
  project_target: [
    'project_target(["RLV-000001", "RLV-000002"], ["Bruttobeitrag"], (0, 1))',
    '',
    '[',
    '    [(0, [1275.411881840093]), (1, [0.0])],',
    '    [(0, [1275.411881840093]), (1, [0.0])],',
    ']',
  ],
};
