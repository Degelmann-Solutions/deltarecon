// The glossary register of the documentation: every entry with its anchor
// and, per language, its term, the word forms the check looks for, and its
// explanation. The Glossary page, the glossary link (components/Term.astro)
// and the check (scripts/check-glossary.mjs) read it; a term stands here and
// in no other file.
//
// Like site.ts, this file imports nothing but a type, so that the check
// scripts can load it (see scripts/harness.mjs).
import type { Lang } from './site';

export interface EntryText {
  /** The term as the Glossary shows it and as a glossary link prints it. */
  term: string;
  /**
   * The other forms of the term that count as an occurrence: plurals, German
   * cases. A match is a whole word. English matches without regard to case;
   * German matches the case as written.
   */
  forms: readonly string[];
  /**
   * The explanation in plain words. It is trusted markup: it may hold inline
   * code and a word marked with its language.
   */
  explanation: string;
}

export interface Entry {
  /** Anchor of the entry on the Glossary, the same in both languages. */
  anchor: string;
  en: EntryText;
  de: EntryText;
  /**
   * Set where the term is a word of one language in both languages, as the
   * quantity name Bruttobeitrag: the term then carries that language on a
   * page of the other one.
   */
  termLang?: Lang;
}

export const entries: readonly Entry[] = [
  {
    anchor: 'bruttobeitrag',
    termLang: 'de',
    en: {
      term: 'Bruttobeitrag',
      forms: [],
      explanation:
        'The gross premium. A quantity of the reference model; the program prints its German name in both languages.',
    },
    de: {
      term: 'Bruttobeitrag',
      forms: ['Bruttobeitrags', 'Bruttobeitrages', 'Bruttobeiträge', 'Bruttobeiträgen'],
      explanation:
        'Eine Größe des Referenzmodells, englisch „<span lang="en">gross premium</span>“. Das Programm gibt ihren deutschen Namen in beiden Sprachen aus.',
    },
  },
  {
    anchor: 'change-manifest',
    en: {
      term: 'Change manifest',
      forms: ['change manifests'],
      explanation:
        'The list of every change between two states, each on its own, in the order in which it was made.',
    },
    de: {
      term: 'Änderungsverzeichnis',
      forms: ['Änderungsverzeichnisses', 'Änderungsverzeichnisse', 'Änderungsverzeichnissen'],
      explanation:
        'Die Liste aller Änderungen zwischen zwei Ständen, jede einzeln, in der Reihenfolge, in der sie gemacht wurde.',
    },
  },
  {
    anchor: 'class',
    en: {
      term: 'Class',
      forms: ['classes'],
      explanation:
        'What a change touches: data (the portfolio), parameter (tables such as lapse or cost rates), code (the calculation rules), or none of these, for example documentation only. A change can have several classes.',
    },
    de: {
      term: 'Einordnung',
      forms: ['Einordnungen'],
      explanation:
        'Was eine Änderung betrifft: Daten (der Bestand), Parameter (Tabellen wie Storno- oder Kostensätze), Code (die Rechenvorschriften) oder nichts davon, zum Beispiel nur Dokumentation. Eine Änderung kann mehrere Einordnungen haben.',
    },
  },
  {
    anchor: 'deviation',
    en: {
      term: 'Deviation',
      forms: ['deviations'],
      explanation:
        'A difference between the results of two releases. In the search of the quick start, a change of the <span lang="de">Bruttobeitrag</span> by more than one cent per model point and month counts as a deviation.',
    },
    de: {
      term: 'Abweichung',
      forms: ['Abweichungen'],
      explanation:
        'Ein Unterschied zwischen den Ergebnissen zweier Releases. In der Suche des Quick Starts zählt eine Änderung des Bruttobeitrags um mehr als einen Cent je Modellpunkt und Monat als Abweichung.',
    },
  },
  {
    anchor: 'exit-status',
    en: {
      term: 'Exit status',
      forms: ['exit statuses'],
      explanation:
        'The number with which a command reports how it ended. The regression reports 1 when the two results differ; in the quick start this is the expected outcome.',
    },
    de: {
      term: 'Exit-Status',
      forms: [],
      explanation:
        'Die Zahl, mit der ein Befehl meldet, wie er geendet hat. Die Regression meldet 1, wenn sich die beiden Ergebnisse unterscheiden; im Quick Start ist das das erwartete Ergebnis.',
    },
  },
  {
    anchor: 'not-resolved',
    en: {
      term: 'Not resolved',
      forms: [],
      explanation:
        'Several changes exceed the tolerance only together; each one alone stays below it. DeltaRecon therefore attributes this part of the deviation to none of them.',
    },
    de: {
      term: 'Nicht aufgelöst',
      forms: [
        'Nicht aufgelöste',
        'Nicht aufgelösten',
        'Nicht aufgelöster',
        'Nicht aufgelöstes',
        'Nicht aufgelöstem',
        'nicht aufgelöst',
        'nicht aufgelöste',
        'nicht aufgelösten',
        'nicht aufgelöster',
        'nicht aufgelöstes',
        'nicht aufgelöstem',
      ],
      explanation:
        'Mehrere Änderungen überschreiten die Toleranz nur zusammen; jede einzelne bleibt darunter. DeltaRecon ordnet diesen Teil der Abweichung daher keiner von ihnen zu.',
    },
  },
  {
    anchor: 'record',
    en: {
      term: 'Record',
      forms: ['records'],
      explanation:
        'What a run leaves behind besides its results: the record of what was computed with what, code, parameters and portfolio data.',
    },
    de: {
      term: 'Nachweis',
      forms: ['Nachweises', 'Nachweise', 'Nachweisen'],
      explanation:
        'Was ein Lauf neben seinen Ergebnissen hinterlässt: der Nachweis, womit was gerechnet wurde, also Code, Parameter und Bestandsdaten.',
    },
  },
  {
    anchor: 'reference-model',
    en: {
      term: 'Reference model',
      forms: ['reference models'],
      explanation:
        'The model <code translate="no">delib-history</code> that ships in the package: a term life insurance with 350 model points.',
    },
    de: {
      term: 'Referenzmodell',
      forms: ['Referenzmodells', 'Referenzmodelle', 'Referenzmodellen'],
      explanation:
        'Das Modell <code translate="no">delib-history</code>, das im Paket enthalten ist: eine Risikolebensversicherung mit 350 Modellpunkten.',
    },
  },
  {
    anchor: 'regression',
    en: {
      term: 'Regression',
      forms: ['regressions'],
      explanation:
        'Computes a newer state on the same portfolio data and for the same model points as an older release, and compares the two results value by value.',
    },
    de: {
      term: 'Regression',
      forms: ['Regressionen'],
      explanation:
        'Rechnet einen neueren Stand auf denselben Bestandsdaten und für dieselben Modellpunkte wie ein älteres Release und vergleicht beide Ergebnisse Wert für Wert.',
    },
  },
  {
    anchor: 'revision',
    en: {
      term: 'Revision',
      forms: ['revisions'],
      explanation:
        'One change in the history of the model. Each change is one revision; release N+1 of the quick start lies 32 revisions after release N.',
    },
    de: {
      term: 'Revision',
      forms: ['Revisionen'],
      explanation:
        'Eine Änderung in der Historie des Modells. Jede Änderung ist eine Revision; der Stand N+1 des Quick Starts liegt 32 Revisionen nach Release N.',
    },
  },
  {
    anchor: 'tolerance-profile',
    en: {
      term: 'Tolerance profile',
      forms: ['tolerance profiles'],
      explanation:
        'Sets for each quantity how far a value may lie above and below the value it is compared with before the difference counts as a deviation. Each of the two bounds has an absolute and a relative part, and the profile states where they come from. A quantity without an entry is compared exactly; without a tolerance profile that holds for every quantity.',
    },
    de: {
      term: 'Toleranzprofil',
      forms: ['Toleranzprofils', 'Toleranzprofile', 'Toleranzprofilen'],
      explanation:
        'Legt je Größe fest, wie weit ein Wert über und unter dem Vergleichswert liegen darf, bevor die Differenz als Abweichung zählt. Jede der beiden Schranken hat einen absoluten und einen relativen Anteil, und das Profil nennt ihre Herleitung. Eine Größe ohne Eintrag wird exakt verglichen; ohne Toleranzprofil gilt das für jede Größe.',
    },
  },
  {
    anchor: 'value',
    en: {
      term: 'Value',
      forms: ['values'],
      explanation: 'One quantity of one model point in one period.',
    },
    de: {
      term: 'Wert',
      forms: ['Werte', 'Werten', 'Wertes', 'Werts'],
      explanation: 'Eine Größe eines Modellpunkts in einer Periode.',
    },
  },
];

/** The id of the page register (site.ts) under which the Glossary stands. */
export const glossaryPage = 'glossary';

export function findEntry(anchor: string): Entry | undefined {
  return entries.find((entry) => entry.anchor === anchor);
}

/** A term without its marks and in small letters: Ä sorts under A. */
function sortKey(term: string): string {
  return term.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

/** The letter an entry stands under in a language. */
export function letterOf(entry: Entry, lang: Lang): string {
  return sortKey(entry[lang].term).charAt(0).toUpperCase();
}

/** The entries in the alphabetical order of a language. */
export function entriesOf(lang: Lang): Entry[] {
  return [...entries].sort((a, b) => {
    const [first, second] = [sortKey(a[lang].term), sortKey(b[lang].term)];
    return first < second ? -1 : first > second ? 1 : 0;
  });
}

/** The letters that have entries in a language, each with its entries. */
export function lettersOf(lang: Lang): { letter: string; entries: Entry[] }[] {
  const letters: { letter: string; entries: Entry[] }[] = [];
  for (const entry of entriesOf(lang)) {
    const letter = letterOf(entry, lang);
    const last = letters.at(-1);
    if (last?.letter === letter) last.entries.push(entry);
    else letters.push({ letter, entries: [entry] });
  }
  return letters;
}

/** Anchor of a letter label. It differs by language, as the letters do. */
export function letterAnchor(letter: string): string {
  return `letter-${letter.toLowerCase()}`;
}

/** The language a term is written in on a page of `lang`. */
export function termLanguage(entry: Entry, lang: Lang): Lang {
  return entry.termLang ?? lang;
}

/** Address of an entry, given the address of the Glossary of a language. */
export function entryAddress(glossaryAddress: string, entry: Entry): string {
  return `${glossaryAddress}#${entry.anchor}`;
}

/**
 * The entries a page source links with the glossary link, `<Term id="…">`.
 * "Appears in" on the Glossary is derived from it.
 */
export function termsUsed(source: string): string[] {
  const anchors = [...source.matchAll(/<Term\s[^>]*?\bid=(["'])(.*?)\1/g)].map((match) => match[2]);
  return [...new Set(anchors)];
}
