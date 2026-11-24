// The facts of the example the documentation shows, read from a capture of
// the guided demo (captures.ts): how many revisions lie between release N
// and the state N+1, which number each revision of the search table carries
// in the table of the changes, the revisions of the two states, and the
// number of model points. A page shows these and types none of them.
//
// It also reads the two four-column tables of the demo, each with the
// sentence the demo prints above it: the table of the regression (step 2)
// and the table of the changes (step 3); and the changes a "Not resolved"
// message names, with their numbers.
//
// Every reader takes the text of one capture and throws, with the file and
// the missing part, when a part is not there; the build then fails.
//
// Like site.ts, this file imports nothing but a type, so that the check
// scripts can load it (see scripts/harness.mjs).
import type { Lang } from './site';

export interface DeviatingRevision {
  /** The number of the revision in the table of the changes, from 1. */
  number: number;
  /** Its short hash, as the program prints it. */
  revision: string;
}

export interface ExampleFacts {
  /** How many revisions the table of the changes lists: from release N to the state N+1. */
  revisions: number;
  /** The revisions of the search table, in its order, each with its number. */
  deviating: DeviatingRevision[];
  /** The revision of release N, as a short hash. */
  releaseN: string;
  /** The revision of the state N+1, as a short hash. */
  stateN1: string;
  /** The number of model points of the portfolio, as the program prints it. */
  modelPoints: string;
}

/** A row of the table of the regression, as the program prints it. */
export interface RegressionRow {
  /** The name of the quantity, German in both languages. */
  quantity: string;
  /** In how many model points the quantity differs. */
  modelPoints: string;
  /** How many of its values differ. */
  values: string;
  /** The first and the last period that differs: "0 to 479". */
  periods: string;
}

export interface RegressionTable {
  /** The sentence the demo prints above the table. */
  caption: string;
  head: [string, string, string, string];
  rows: RegressionRow[];
}

/** A row of the table of the changes, as the program prints it. */
export interface ChangeRow {
  /** The number of the change, from 1. */
  number: number;
  /** Its short hash. */
  revision: string;
  /** Its class or classes, in the words of the language. */
  classes: string;
  /** Its description, English in both languages. */
  description: string;
}

export interface ChangeTable {
  /** The sentence the demo prints above the table. */
  caption: string;
  head: [string, string, string, string];
  rows: ChangeRow[];
}

/** A row of the table of the changes: its number, the short hash, the rest. */
const changeRow = /^\s*(\d+)\s+([0-9a-f]{7})\s{2,}\S/;
/**
 * A row of the table of the regression: a name, two whole numbers and the
 * first and last period ("0 to 479", "0 bis 479"), two spaces or more apart.
 */
const regressionRow = /^\s{2}(\S.*?)\s{2,}(\d[\d.,]*)\s{2,}(\d[\d.,]*)\s{2,}(\d+ \S+ \d+)$/;
/** A short hash as a word of a message. */
const shortHash = /(?<![0-9a-z])[0-9a-f]{7}(?![0-9a-z])/g;
/** The revision a command computes, as a full hash. */
const computed = /--revision\s+([0-9a-f]{40})\b/g;
/**
 * The number before the words for "model points" in the opening sentence,
 * per language. The sentence may wrap between the number and the words.
 */
const modelPoints: Record<Lang, RegExp> = {
  en: /(\d[\d,]*)\s+model\s+points/,
  de: /(\d[\d.]*)\s+Modellpunkte/,
};

/**
 * What stands above the first row of a table at line `first`: its head row
 * of four columns and, a blank line above, the sentence of the demo.
 */
function aboveRows(
  lines: readonly string[],
  first: number,
  table: string,
  missing: (part: string) => Error,
): { caption: string; head: [string, string, string, string] } {
  const head = (lines[first - 1] ?? '').trim().split(/\s{2,}/);
  if (head.length !== 4 || head[0] === '') {
    throw missing(`the head row of ${table}, four columns,`);
  }
  let end = first - 2;
  while (end >= 0 && lines[end].trim() === '') end -= 1;
  let start = end;
  while (start > 0 && lines[start - 1].trim() !== '') start -= 1;
  const above = lines.slice(Math.max(start, 0), end + 1);
  const caption = above.map((line) => line.trim()).join(' ');
  // A sentence of the demo is not indented; a command or a table is.
  if (caption === '' || above.some((line) => /^\s/.test(line))) {
    throw missing(`the sentence above ${table}`);
  }
  return { caption, head: head as [string, string, string, string] };
}

/**
 * The table of the regression of one capture: the sentence above it, its
 * head row and one row per quantity that deviates.
 */
export function regressionTable(source: string, file: string): RegressionTable {
  const missing = (part: string): Error => new Error(`src/${file}: ${part} is missing.`);
  const lines = source.split('\n');
  const first = lines.findIndex((line) => regressionRow.test(line));
  if (first === -1) throw missing('the table of the regression');
  const rows: RegressionRow[] = [];
  for (let index = first; index < lines.length; index += 1) {
    const row = regressionRow.exec(lines[index]);
    if (!row) break;
    rows.push({ quantity: row[1], modelPoints: row[2], values: row[3], periods: row[4] });
  }
  return { ...aboveRows(lines, first, 'the table of the regression', missing), rows };
}

/**
 * The table of the changes of one capture: the sentence above it, its head
 * row and one row per change. The columns of a row are cut where the head
 * row begins them, since a class may hold a space. `exampleFacts` asserts
 * that the rows are numbered from 1 without a gap.
 */
export function changeTable(source: string, file: string): ChangeTable {
  const missing = (part: string): Error => new Error(`src/${file}: ${part} is missing.`);
  const lines = source.split('\n');
  const first = lines.findIndex((line) => changeRow.test(line));
  if (first === -1) throw missing('the table of the changes');
  const above = aboveRows(lines, first, 'the table of the changes', missing);
  // Where the last two columns begin in the head row, and so in every row.
  const headLine = lines[first - 1];
  const classAt = headLine.indexOf(above.head[2], headLine.indexOf(above.head[1]) + above.head[1].length);
  const descriptionAt = headLine.indexOf(above.head[3], classAt + above.head[2].length);
  const rows: ChangeRow[] = [];
  for (let index = first; index < lines.length; index += 1) {
    const line = lines[index];
    const row = changeRow.exec(line);
    if (!row) break;
    const classes = line.slice(classAt, descriptionAt).trim();
    const description = line.slice(descriptionAt).trim();
    if (
      classes === '' ||
      description === '' ||
      line[classAt - 1] !== ' ' ||
      line[descriptionAt - 1] !== ' '
    ) {
      throw missing(`row ${rows.length + 1} of the table of the changes (line ${index + 1}), in the columns of its head row,`);
    }
    rows.push({ number: Number(row[1]), revision: row[2], classes, description });
  }
  return { ...above, rows };
}

/**
 * The changes a "Not resolved" message names, in its order, each with its
 * number in the table of the changes. They must follow one another there:
 * the message names one interval of the history.
 */
export function unresolvedInterval(
  message: string,
  changes: readonly ChangeRow[],
  file: string,
): DeviatingRevision[] {
  const missing = (part: string): Error => new Error(`src/${file}: ${part} is missing.`);
  const named = (message.match(shortHash) ?? []).map((revision) => {
    const row = changes.find((change) => change.revision === revision);
    if (!row) {
      throw missing(`the revision ${revision} of a "Not resolved" message in the table of the changes`);
    }
    return { number: row.number, revision };
  });
  if (named.length === 0) throw missing('a revision in a "Not resolved" message');
  named.forEach((entry, index) => {
    if (entry.number !== named[0].number + index) {
      throw missing(`an interval of changes that follow one another in a "Not resolved" message (${entry.revision})`);
    }
  });
  return named;
}

/**
 * The facts of the example in one capture. `deviating` names the revisions
 * of its search table, in the order of the table.
 */
export function exampleFacts(
  source: string,
  lang: Lang,
  deviating: readonly string[],
  file: string,
): ExampleFacts {
  const missing = (part: string): Error => new Error(`src/${file}: ${part} is missing.`);

  // The table of the changes: one row per revision, with its number.
  const { rows } = changeTable(source, file);
  const changes = rows.map((row) => row.revision);

  // Every revision of the search table stands in it.
  if (deviating.length === 0) throw missing('a revision of the search table');
  for (const revision of deviating) {
    if (!changes.includes(revision)) {
      throw missing(`the revision ${revision} of the search table in the table of the changes`);
    }
  }
  // Its rows are numbered from 1 without a gap, so their count is the number
  // of revisions and a number is a place on the trace.
  rows.forEach((row, index) => {
    if (row.number !== index + 1) throw missing(`row ${index + 1} of the table of the changes`);
  });

  // The two states: the first two revisions a command computes.
  const [first, second] = [...new Set([...source.matchAll(computed)].map((match) => match[1]))];
  if (!first) throw missing('the revision of release N (--revision in step 1)');
  if (!second) throw missing('the revision of the state N+1 (--revision in step 2)');
  const short = changes[0].length;
  const releaseN = first.slice(0, short);
  const stateN1 = second.slice(0, short);
  for (const [name, hash] of [
    ['release N', releaseN],
    ['the state N+1', stateN1],
  ]) {
    if (!new RegExp(`(?<![0-9a-f])${hash}(?![0-9a-f])`).test(source)) {
      throw missing(`the short hash ${hash} of ${name}`);
    }
  }
  if (changes.at(-1) !== stateN1) {
    throw missing(`the state N+1 (${stateN1}) as the last row of the table of the changes`);
  }

  const numbered = deviating.map((revision) => ({ number: changes.indexOf(revision) + 1, revision }));

  const points = modelPoints[lang].exec(source);
  if (!points) throw missing('the number of model points');

  return {
    revisions: changes.length,
    deviating: numbered,
    releaseN,
    stateN1,
    modelPoints: points[1],
  };
}
