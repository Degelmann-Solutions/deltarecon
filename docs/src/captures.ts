// The program output the documentation shows. It is read from the capture
// files under captures/v<release>/, one per platform and language: the
// standard output of `quickstart --lang <language> --no-pause` of the
// released package. No page types output; a component asks this module for
// the part it shows. The build fails, with the file and the missing part,
// when a file or a part is not there.
//
// The parts follow the layout of the demo (a heading per step, the
// explanation, the commands, then what the step wrote):
//   - `session`: the opening and the first step up to its commands, which is
//     what the reader sees before the demo first waits for Enter;
//   - `afterLines`: the paragraph the demo prints after each of its four
//     steps;
//   - `caption`: the paragraph above the table of the search, step 4;
//   - `searchTable`: the head and the rows of that table;
//   - `notResolved`: the "Not resolved" messages below it;
//   - `regressionTable` and `changeTable`: the two four-column tables of the
//     demo, after steps 2 and 3, each with the sentence above it (example.ts);
//   - `unresolved`: the changes each "Not resolved" message names, with
//     their numbers in the table of the changes;
//   - `searchCounts`: how many states there are and how many the search
//     computed, from the sentence above the table of the search;
//   - `example`: the facts of the example a page of prose shows (example.ts):
//     the number of revisions, the number of each revision of the search
//     table in the table of the changes, the revisions of the two states,
//     the number of model points.
// `changeOf`, `quantityOf` and `searchRowOf` give one row of a table by its
// revision or its quantity, for a page that writes about that row.
// Only `session` differs by platform (path separators, the time stamp of the
// demo folder). The other parts are read from the Windows capture and must
// equal the Linux one.
import {
  changeTable as readChangeTable,
  exampleFacts,
  regressionTable as readRegressionTable,
  unresolvedInterval,
  type ChangeRow,
  type ChangeTable,
  type DeviatingRevision,
  type ExampleFacts,
  type RegressionRow,
  type RegressionTable,
} from './example';
import { platforms, tag, type Platform } from './release';
import type { Lang } from './site';

const files = import.meta.glob<string>('./captures/*/*.txt', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** What the lines of a part begin with, per language. They are found, not shown. */
const markers: Record<
  Lang,
  { step: RegExp; notResolved: string; result: string; computed: RegExp }
> = {
  en: {
    step: /^Step (\d) of 4: /,
    notResolved: 'Not resolved:',
    result: 'Result:',
    computed: /(\d+) of (\d+) were computed/,
  },
  de: {
    step: /^Schritt (\d) von 4: /,
    notResolved: 'Nicht aufgelöst:',
    result: 'Ergebnis:',
    computed: /Gerechnet wurden (\d+) von (\d+)/,
  },
};
const STEPS = 4;

export interface SessionLine {
  text: string;
  /** A heading of the demo: the first line and the heading of a step. */
  heading: boolean;
}

export interface SearchRow {
  revision: string;
  description: string;
  /** The sum as the demo prints it in the language, with its sign. */
  sum: string;
  /** The same sum as a number. */
  value: number;
}

export interface SearchTable {
  head: [string, string, string];
  rows: SearchRow[];
}

export interface SearchCounts {
  /** How many states the search computed. */
  computed: number;
  /** How many states there are: release N and one after each change. */
  states: number;
}

interface Parts {
  session: SessionLine[];
  afterLines: string[];
  searchTable: SearchTable;
  notResolved: string[];
  example: ExampleFacts;
  regressionTable: RegressionTable;
  changeTable: ChangeTable;
  unresolved: DeviatingRevision[][];
  searchCounts: SearchCounts;
}

function fileOf(platform: Platform, lang: Lang): string {
  return `captures/${tag}/${platform}-${lang}.txt`;
}

/** A sum of the demo as a number: `+24,110.00` (en), `+24.110,00` (de). */
function numberOf(sum: string, lang: Lang, file: string): number {
  const plain =
    lang === 'en' ? sum.replaceAll(',', '') : sum.replaceAll('.', '').replace(',', '.');
  if (!/^[+-]\d+\.\d{2}$/.test(plain)) {
    throw new Error(`src/${file}: "${sum}" is not a sum with a sign and two decimals.`);
  }
  return Number(plain);
}

function read(platform: Platform, lang: Lang): Parts {
  const file = fileOf(platform, lang);
  const source = files[`./${file}`];
  if (source === undefined) {
    throw new Error(`src/${file}: the capture file is missing.`);
  }
  const missing = (part: string): Error => new Error(`src/${file}: ${part} is missing.`);
  const lines = source.split('\n');
  const marker = markers[lang];

  // The line each step begins at; the end of the last step is the end of the file.
  const starts: number[] = [];
  lines.forEach((line, index) => {
    const step = marker.step.exec(line);
    if (step && Number(step[1]) === starts.length + 1) starts.push(index);
  });
  if (starts.length !== STEPS) throw missing(`the heading of step ${starts.length + 1}`);

  /** The paragraphs of a step: runs of lines between blank lines. */
  const paragraphsOf = (step: number): { first: number; lines: string[] }[] => {
    const paragraphs: { first: number; lines: string[] }[] = [];
    for (let index = starts[step - 1]; index < (starts[step] ?? lines.length); index += 1) {
      if (lines[index].trim() === '') continue;
      const last = paragraphs.at(-1);
      if (last && last.first + last.lines.length === index) last.lines.push(lines[index]);
      else paragraphs.push({ first: index, lines: [lines[index]] });
    }
    return paragraphs;
  };
  /** Where the paragraph of the commands of a step stands among its paragraphs. */
  const commandsOf = (step: number, paragraphs: { lines: string[] }[]): number => {
    const at = paragraphs.findIndex((paragraph) => paragraph.lines[1]?.startsWith('  deltarecon '));
    if (at === -1) throw missing(`the commands of step ${step}`);
    return at;
  };

  // The session: everything up to the end of the commands of step 1.
  const first = paragraphsOf(1);
  const commands = first[commandsOf(1, first)];
  const session = lines
    .slice(0, commands.first + commands.lines.length)
    .map((text, index) => ({ text, heading: index === 0 || index === starts[0] }));
  if (session[0].text.trim() === '') throw missing('the heading of the opening');

  // What the demo prints after each step: the paragraph after the commands.
  const afterLines: string[] = [];
  let table: { first: number; lines: string[] } | undefined;
  for (let step = 1; step <= STEPS; step += 1) {
    const paragraphs = paragraphsOf(step);
    const at = commandsOf(step, paragraphs);
    const after = paragraphs[at + 1];
    if (!after) throw missing(`the line after step ${step}`);
    afterLines.push(after.lines.map((line) => line.trim()).join(' '));
    if (step === STEPS) table = paragraphs[at + 2];
  }

  // The table of the search: a head row, then one row per revision.
  if (!table || table.lines.length < 2) throw missing('the table of the search');
  const head = table.lines[0].trim().split(/\s{2,}/);
  if (head.length !== 3) throw missing('the head row of the table of the search, three columns,');
  const rows = table.lines.slice(1).map((line, index) => {
    const cells = /^\s*(\S+)\s+(.*\S)\s{2,}(\S+)$/.exec(line);
    if (!cells) throw missing(`row ${index + 1} of the table of the search (line ${table.first + index + 2})`);
    const [, revision, description, sum] = cells;
    return { revision, description, sum, value: numberOf(sum, lang, file) };
  });

  // The "Not resolved" messages: each from its first line to the next blank
  // line or the line that names the result file.
  const notResolved: string[] = [];
  for (let index = starts[STEPS - 1]; index < lines.length; index += 1) {
    if (!lines[index].startsWith(marker.notResolved)) continue;
    const message: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() !== '' &&
      !lines[index].startsWith(marker.result)
    ) {
      message.push(lines[index].trim());
      index += 1;
    }
    notResolved.push(message.join(' '));
  }
  if (notResolved.length === 0) throw missing(`the message "${marker.notResolved}"`);

  // The facts of the example, with the number of each revision of the table.
  const example = exampleFacts(
    source,
    lang,
    rows.map((row) => row.revision),
    file,
  );

  // The two four-column tables. Each stands in its step, under the sentence
  // the demo prints after the commands of that step.
  const regression = readRegressionTable(source, file);
  if (regression.caption !== afterLines[1]) throw missing('the table of the regression in step 2');
  const changes = readChangeTable(source, file);
  if (changes.caption !== afterLines[2]) throw missing('the table of the changes in step 3');

  // The changes each "Not resolved" message names.
  const unresolved = notResolved.map((message) => unresolvedInterval(message, changes.rows, file));

  // How many states the search computed, and of how many: one state more
  // than there are changes.
  const counted = marker.computed.exec(afterLines[STEPS - 1]);
  if (!counted) throw missing('the number of states the search computed');
  const searchCounts = { computed: Number(counted[1]), states: Number(counted[2]) };
  if (searchCounts.states !== example.revisions + 1) {
    throw missing(`one state more than the ${example.revisions} changes (the search names ${searchCounts.states})`);
  }

  return {
    session,
    afterLines,
    searchTable: { head: head as [string, string, string], rows },
    notResolved,
    example,
    regressionTable: regression,
    changeTable: changes,
    unresolved,
    searchCounts,
  };
}

const cache = new Map<string, Parts>();
function parts(platform: Platform, lang: Lang): Parts {
  const key = `${platform}-${lang}`;
  let found = cache.get(key);
  if (!found) {
    found = read(platform, lang);
    cache.set(key, found);
  }
  return found;
}

/** The parts that do not differ by platform; the build fails where they do. */
function shared(lang: Lang): Parts {
  const [first, ...others] = platforms.map((platform) => ({ platform, parts: parts(platform, lang) }));
  for (const other of others) {
    for (const part of [
      'afterLines',
      'searchTable',
      'notResolved',
      'example',
      'regressionTable',
      'changeTable',
      'unresolved',
      'searchCounts',
    ] as const) {
      if (JSON.stringify(first.parts[part]) !== JSON.stringify(other.parts[part])) {
        throw new Error(
          `src/${fileOf(first.platform, lang)} and src/${fileOf(other.platform, lang)} differ in "${part}"; only paths and the time stamp of the demo folder may differ.`,
        );
      }
    }
  }
  return first.parts;
}

/** The opening of the demo up to the commands of its first step. */
export function session(platform: Platform, lang: Lang): SessionLine[] {
  return parts(platform, lang).session;
}

/** The paragraph the demo prints after each of its four steps. */
export function afterLines(lang: Lang): string[] {
  return shared(lang).afterLines;
}

/** The paragraph above the table of the search: how many revisions deviate. */
export function caption(lang: Lang): string {
  return shared(lang).afterLines[STEPS - 1];
}

/** The table of the search: its head and one row per revision. */
export function searchTable(lang: Lang): SearchTable {
  return shared(lang).searchTable;
}

/** The "Not resolved" messages of the search. */
export function notResolved(lang: Lang): string[] {
  return shared(lang).notResolved;
}

/**
 * The facts of the example: how many revisions lie between the two states,
 * the number of each revision of the search table, the revisions of the two
 * states, the number of model points.
 */
export function example(lang: Lang): ExampleFacts {
  return shared(lang).example;
}

/** The table of the regression, step 2: the sentence above it, head and rows. */
export function regressionTable(lang: Lang): RegressionTable {
  return shared(lang).regressionTable;
}

/** The table of the changes, step 3: the sentence above it, head and rows. */
export function changeTable(lang: Lang): ChangeTable {
  return shared(lang).changeTable;
}

/** The changes each "Not resolved" message names, with their numbers. */
export function unresolved(lang: Lang): DeviatingRevision[][] {
  return shared(lang).unresolved;
}

/** How many states there are and how many the search computed. */
export function searchCounts(lang: Lang): SearchCounts {
  return shared(lang).searchCounts;
}

/** The row of a table a page writes about; the build fails where it is not there. */
function rowOf<Row>(rows: readonly Row[], found: (row: Row) => boolean, part: string, lang: Lang): Row {
  const row = rows.find(found);
  if (!row) throw new Error(`src/${fileOf(platforms[0], lang)}: ${part} is missing.`);
  return row;
}

/** The row of a revision in the table of the changes. */
export function changeOf(lang: Lang, revision: string): ChangeRow {
  return rowOf(
    changeTable(lang).rows,
    (row) => row.revision === revision,
    `the revision ${revision} in the table of the changes`,
    lang,
  );
}

/** The row of a quantity in the table of the regression. */
export function quantityOf(lang: Lang, quantity: string): RegressionRow {
  return rowOf(
    regressionTable(lang).rows,
    (row) => row.quantity === quantity,
    `the quantity "${quantity}" in the table of the regression`,
    lang,
  );
}

/** The row of a revision in the table of the search. */
export function searchRowOf(lang: Lang, revision: string): SearchRow {
  return rowOf(
    searchTable(lang).rows,
    (row) => row.revision === revision,
    `the revision ${revision} in the table of the search`,
    lang,
  );
}

/** The first sentence of a paragraph of the demo. A number holds no ". ". */
export function firstSentence(paragraph: string): string {
  const end = paragraph.indexOf('. ');
  return end === -1 ? paragraph : paragraph.slice(0, end + 1);
}
