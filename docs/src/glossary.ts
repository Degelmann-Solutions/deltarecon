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
  /** The id of the page of the register that says more about the term; the entry links to it. */
  more?: string;
}

export const entries: readonly Entry[] = [
  {
    anchor: 'adapter',
    en: {
      term: 'Adapter',
      forms: ['adapters'],
      explanation:
        'The piece that connects a calculation engine to DeltaRecon. Through it DeltaRecon has the engine compute a state of the model, reads the history of the changes, and learns which files are data, parameters and code.',
    },
    de: {
      term: 'Adapter',
      forms: ['Adapters', 'Adaptern'],
      explanation:
        'Das Verbindungsstück zwischen einer Rechen-Engine und DeltaRecon. Über ihn lässt DeltaRecon die Engine einen Stand des Modells rechnen, liest die Historie der Änderungen und erfährt, welche Dateien Daten, Parameter und Code sind.',
    },
  },
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
    anchor: 'compare-request',
    en: {
      term: 'Compare request',
      forms: ['compare requests'],
      explanation:
        'The file that says what a comparison compares: it names the two runs and holds the tolerance profile. The commands <code translate="no">replay</code>, <code translate="no">regression</code>, <code translate="no">walk</code> and <code translate="no">search</code> write theirs themselves; you write one by hand only for the command <code translate="no">compare</code>.',
    },
    de: {
      term: 'Vergleichsanfrage',
      forms: ['Vergleichsanfragen'],
      explanation:
        'Die Datei, die sagt, was ein Vergleich vergleicht: Sie nennt die beiden Läufe und enthält das Toleranzprofil. Die Befehle <code translate="no">replay</code>, <code translate="no">regression</code>, <code translate="no">walk</code> und <code translate="no">search</code> schreiben ihre selbst; von Hand schreiben Sie eine nur für den Befehl <code translate="no">compare</code>.',
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
    anchor: 'signature-table',
    en: {
      term: 'Signature table',
      forms: ['signature tables'],
      explanation:
        'The summary of a comparison, one row per quantity that deviates: in how many model points and values it deviates, in which periods, and the largest increase and the largest decrease. The first table of the quick start shows a part of it.',
    },
    de: {
      term: 'Signaturtabelle',
      forms: ['Signaturtabellen'],
      explanation:
        'Die Zusammenfassung eines Vergleichs, eine Zeile je Größe, die abweicht: in wie vielen Modellpunkten und Werten sie abweicht, in welchen Perioden, dazu der größte Anstieg und der größte Rückgang. Die erste Tabelle des Quick Starts zeigt einen Teil davon.',
    },
  },
  {
    anchor: 'tolerance-profile',
    more: 'tolerance-profile',
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
  {
    anchor: 'release',
    en: {
      term: 'Release',
      forms: ['releases'],
      explanation:
        'A state of the model that is named completely: code, parameters and input data, each by its revision. For the reference model a release is one revision of the history.',
    },
    de: {
      term: 'Release',
      forms: ['Releases'],
      explanation:
        'Ein Stand des Modells, der vollständig benannt ist: Code, Parameter und Bestandsdaten, jeweils mit ihrer Revision. Beim Referenzmodell ist ein Release eine Revision der Versionsgeschichte.',
    },
  },
  {
    anchor: 'state',
    en: {
      term: 'State',
      forms: ['states'],
      explanation:
        'The model after a certain number of changes. State 0 is the older of the two revisions; after each change follows a further state.',
    },
    de: {
      term: 'Stand',
      forms: ['Stands', 'Standes', 'Stände', 'Ständen'],
      explanation:
        'Das Modell nach einer bestimmten Zahl von Änderungen. Stand 0 ist die ältere der beiden Revisionen; nach jeder Änderung folgt ein weiterer Stand.',
    },
  },
  {
    anchor: 'run',
    en: {
      term: 'Run',
      forms: ['runs'],
      explanation:
        'One calculation: a release is projected for the selected model points. A run ends with an outcome, for example <code translate="no">succeeded</code>, and leaves its record behind.',
    },
    de: {
      term: 'Lauf',
      forms: ['Laufs', 'Laufes', 'Läufe', 'Läufen'],
      explanation:
        'Eine Rechnung: Ein Release wird für die gewählten Modellpunkte projiziert. Ein Lauf endet mit einem Ausgang, zum Beispiel <code translate="no">succeeded</code>, und hinterlässt seinen Nachweis.',
    },
  },
  {
    anchor: 'run-request',
    en: {
      term: 'Run request',
      forms: ['run requests'],
      explanation:
        'The file that says what a run is to compute: the release and the model points. The command <code translate="no">request</code> writes it, the command <code translate="no">run</code> computes it.',
    },
    de: {
      term: 'Anfrage',
      forms: ['Anfragen'],
      explanation:
        'Die Datei, die sagt, was ein Lauf rechnen soll: das Release und die Modellpunkte. Der Befehl <code translate="no">request</code> schreibt sie, der Befehl <code translate="no">run</code> rechnet sie.',
    },
  },
  {
    anchor: 'model-point',
    en: {
      term: 'Model point',
      forms: ['model points'],
      explanation:
        'The smallest unit for which an engine gives results: a single contract, an aggregated contract record, or an output group. The reference model has 350 model points.',
    },
    de: {
      term: 'Modellpunkt',
      forms: ['Modellpunkts', 'Modellpunktes', 'Modellpunkte', 'Modellpunkten'],
      explanation:
        'Die kleinste Einheit, für die eine Engine Ergebnisse ausgibt: ein einzelner Vertrag, ein verdichteter Vertragsdatensatz oder eine Ausgabegruppe. Das Referenzmodell hat 350 Modellpunkte.',
    },
  },
  {
    anchor: 'quantity',
    en: {
      term: 'Quantity',
      forms: ['quantities'],
      explanation:
        'What the model gives per model point and period under one name, for example the <span lang="de">Bruttobeitrag</span> or the commissions, <span lang="de">Provisionen</span>.',
    },
    de: {
      term: 'Größe',
      forms: ['Größen'],
      explanation:
        'Was das Modell je Modellpunkt und Periode unter einem Namen ausgibt, zum Beispiel der Bruttobeitrag oder die Provisionen.',
    },
  },
  {
    anchor: 'period',
    en: {
      term: 'Period',
      forms: ['periods'],
      explanation:
        'One projection month, counted from 0 at the valuation date.',
    },
    de: {
      term: 'Periode',
      forms: ['Perioden'],
      explanation:
        'Ein Projektionsmonat, gezählt ab 0 am Bewertungsstichtag.',
    },
  },
  {
    anchor: 'input-data',
    en: {
      term: 'Input data',
      forms: ['portfolio data'],
      explanation:
        'The portfolio that is computed; for the reference model the table of the model points.',
    },
    de: {
      term: 'Bestandsdaten',
      forms: [],
      explanation:
        'Der Bestand, für den gerechnet wird; beim Referenzmodell die Tabelle der Modellpunkte.',
    },
  },
  {
    anchor: 'target',
    en: {
      term: 'Target',
      forms: ['targets'],
      explanation:
        'The part of the results that a search is limited to: one or several quantities and a range of periods. The search then judges and sums only the values of the target.',
    },
    de: {
      term: 'Ziel',
      forms: ['Ziels', 'Zieles', 'Ziele', 'Zielen'],
      explanation:
        'Der Teil der Ergebnisse, auf den eine Suche eingegrenzt ist: eine oder mehrere Größen und ein Bereich von Perioden. Die Suche beurteilt und summiert dann nur die Werte des Ziels.',
    },
  },
  {
    anchor: 'interval',
    en: {
      term: 'Interval',
      forms: ['intervals', 'stretch', 'stretches'],
      explanation:
        'A connected piece of the history between two states. The search judges an interval by comparing the states at its two ends.',
    },
    de: {
      term: 'Abschnitt',
      forms: ['Abschnitts', 'Abschnittes', 'Abschnitte', 'Abschnitten'],
      explanation:
        'Ein zusammenhängendes Stück der Versionsgeschichte zwischen zwei Ständen. Die Suche beurteilt einen Abschnitt, indem sie die Stände an seinen beiden Enden vergleicht.',
    },
  },
  {
    anchor: 'remainder',
    en: {
      term: 'Remainder',
      forms: ['remainders'],
      explanation:
        'What differs between two records and belongs to no revision, for example another version of the core of the engine. The remainder belongs to no change.',
    },
    de: {
      term: 'Rest',
      forms: ['Rests', 'Restes'],
      explanation:
        'Was sich zwischen zwei Nachweisen unterscheidet und zu keiner Revision gehört, zum Beispiel eine andere Version des Kerns der Engine. Der Rest gehört zu keiner Änderung.',
    },
  },
  {
    anchor: 'history',
    en: {
      term: 'History',
      forms: ['histories'],
      explanation:
        'The sequence of the revisions of a model, in the order in which they were made. The package holds that of the reference model in the folder <code translate="no">delib-history</code>.',
    },
    de: {
      term: 'Versionsgeschichte',
      forms: ['Versionsgeschichten', 'Historie'],
      explanation:
        'Die Folge der Revisionen eines Modells, in der Reihenfolge, in der sie gemacht wurden. Das Paket enthält die des Referenzmodells im Ordner <code translate="no">delib-history</code>.',
    },
  },
  {
    anchor: 'main-line',
    en: {
      term: 'Main line',
      forms: ['main lines'],
      explanation:
        'The revisions of the history that lead from the older revision to the newer one. A branch that was merged counts on it as one change.',
    },
    de: {
      term: 'Hauptlinie',
      forms: ['Hauptlinien'],
      explanation:
        'Die Revisionen der Versionsgeschichte, die von der älteren zur neueren Revision führen. Ein Seitenzweig, der zusammengeführt wurde (Merge), zählt auf ihr als eine Änderung.',
    },
  },
  {
    anchor: 'engine',
    en: {
      term: 'Engine',
      forms: ['engines'],
      explanation:
        'The program that computes the model. DeltaRecon computes nothing itself: it has the engine compute through its adapter. Without an engine of your own, DeltaRecon computes with the reference model.',
    },
    de: {
      term: 'Engine',
      forms: ['Engines'],
      explanation:
        'Das Programm, das das Modell rechnet. DeltaRecon rechnet nicht selbst: Es lässt die Engine über ihren Adapter rechnen. Ohne eigene Engine rechnet DeltaRecon mit dem Referenzmodell.',
    },
  },
  {
    anchor: 'protocol',
    en: {
      term: 'Protocol',
      forms: ['protocols'],
      explanation:
        'The fixed set of questions that DeltaRecon asks an engine. An adapter answers them; the file <code translate="no">degelmann/deltarecon/protocol.py</code> describes them.',
    },
    de: {
      term: 'Protokoll',
      forms: ['Protokolls', 'Protokolle'],
      explanation:
        'Der feste Satz von Fragen, die DeltaRecon einer Engine stellt. Ein Adapter beantwortet sie; die Datei <code translate="no">degelmann/deltarecon/protocol.py</code> beschreibt sie.',
    },
  },
  {
    anchor: 'computation-path',
    en: {
      term: 'Computation path',
      forms: ['computation paths'],
      explanation:
        'The way the reference model computes: through the export of the model that modelx writes, which is the default, or through modelx itself.',
    },
    de: {
      term: 'Rechenweg',
      forms: ['Rechenwegs', 'Rechenweges', 'Rechenwege', 'Rechenwegen'],
      explanation:
        'Der Weg, auf dem das Referenzmodell rechnet: über den Export des Modells, den modelx schreibt (die Voreinstellung), oder über modelx selbst.',
    },
  },
  {
    anchor: 'package-folder',
    en: {
      term: 'Package folder',
      forms: ['package folders'],
      explanation:
        'The folder that unpacking the archive creates. You start the quick start and the single commands in it.',
    },
    de: {
      term: 'Paketordner',
      forms: ['Paketordners'],
      explanation:
        'Der Ordner, der beim Entpacken des Archivs entsteht. In ihm starten Sie den Quick Start und die einzelnen Befehle.',
    },
  },
  {
    anchor: 'starter',
    en: {
      term: 'Starter',
      forms: ['starters'],
      explanation:
        'The file in the package folder with which you start the quick start: <code translate="no">quickstart.cmd</code> on Windows, <code translate="no">quickstart</code> on Linux.',
    },
    de: {
      term: 'Startdatei',
      forms: ['Startdateien'],
      explanation:
        'Die Datei im Paketordner, mit der Sie den Quick Start starten: <code translate="no">quickstart.cmd</code> unter Windows, <code translate="no">quickstart</code> unter Linux.',
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
