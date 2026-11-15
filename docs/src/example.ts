// The facts of the example the documentation shows, read from a capture of
// the guided demo (captures.ts): how many revisions lie between release N
// and the state N+1, which number each revision of the search table carries
// in the table of the changes, the revisions of the two states, and the
// number of model points. A page shows these and types none of them.
//
// `exampleFacts` takes the text of one capture and throws, with the file and
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

/** A row of the table of the changes: its number, the short hash, the rest. */
const changeRow = /^\s*(\d+)\s+([0-9a-f]{7})\s{2,}\S/;
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
  const rows: { number: number; revision: string }[] = [];
  for (const line of source.split('\n')) {
    const row = changeRow.exec(line);
    if (row) rows.push({ number: Number(row[1]), revision: row[2] });
  }
  if (rows.length === 0) throw missing('the table of the changes');
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
