// What the page "Write a tolerance profile" shows in both languages: the
// tolerance profile of the package, the example profile the reader writes,
// and the command that uses it.
//
// `packaged` is the file `profiles/tolerance-bruttobeitrag.json` of the
// released package, line for line; scripts/check-release.mjs holds it
// against that file.
export const packaged: readonly string[] = [
  '{',
  '  "per_quantity": {',
  '    "Bruttobeitrag": {',
  '      "upper": { "abs_tol": 0.01, "rel_tol": 0 },',
  '      "lower": { "abs_tol": 0.01, "rel_tol": 0 },',
  '      "derivation": "A premium is settled in whole cents, so a change of the gross premium of a model point and policy month below one cent is not a change a person would act on. The bound is absolute and symmetric, without rounding, so that a change of about 0.006 per coordinate stays below it while two such changes in a row exceed it."',
  '    }',
  '  }',
  '}',
];

/** The place of the derivation in the example, which the reader fills in. */
export const DERIVATION = { en: '<derivation>', de: '<Herleitung>' } as const;

/**
 * The example profile: the commissions are rounded to two decimal places
 * and then compared exactly. The released `deltarecon` accepted it, with a
 * sentence in the place of the derivation, in a search on the reference
 * model.
 */
export function example(lang: 'en' | 'de'): string[] {
  return [
    '{',
    '  "per_quantity": {',
    '    "Provisionen": {',
    '      "upper": { "abs_tol": 0, "rel_tol": 0 },',
    '      "lower": { "abs_tol": 0, "rel_tol": 0 },',
    '      "decimals": 2,',
    `      "derivation": "${DERIVATION[lang]}"`,
    '    }',
    '  }',
    '}',
  ];
}

/** The search of "Your own calculations" for the commissions, with the example profile. */
export const search = {
  windows: [
    String.raw`.\deltarecon.cmd search $Q\release-n\run-record.json $Q\regression\run\run-record.json --quantity Provisionen --periods 0-59 --tolerance profiles\mein-profil.json --target-only --output $Q\search-provisionen-profil`,
  ],
  linux: [
    './deltarecon search $Q/release-n/run-record.json $Q/regression/run/run-record.json --quantity Provisionen --periods 0-59 --tolerance profiles/mein-profil.json --target-only --output $Q/search-provisionen-profil',
  ],
};

/** The quantities of the reference model, by the names its results give them. */
export const quantities: readonly string[] = [
  'Anzahl Verträge',
  'Bruttobeitrag',
  'Zahlbeitrag',
  'Beitragsverrechnung',
  'garantierte Todesfallleistung',
  'garantierter Rückkaufswert',
  'garantierte Erlebensfallleistung',
  'Kosten 2. Ordnung ohne Provisionen',
  'Provisionen',
  'Netto-Cashflow',
];
