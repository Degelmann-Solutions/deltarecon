// Checks the pages of prose of the built site in Chromium: section headings,
// the wide figure with the idea figure and its bars, the row list, the path
// block. Run after the build: `npm run check`.
//
// A page of prose is a page that holds section headings or lists sections in
// the chapter tree (frontmatter `sections`). What a page must show stands in
// `prosePages` below, so that a changed anchor fails here until both places
// agree. A page of prose without an entry there fails.
//
// First the reader of the facts of the example (src/example.ts), on the
// capture files of the release: it gives the number of revisions, the number
// of each revision of the search table, the revisions of the two states and
// the number of model points; and it throws on a capture text whose table of
// the changes lacks a revision of the search table, lacks its rows, or whose
// commands name no revision. The build shows those facts, so a capture that
// lacks one fails the build. The same file reads the two four-column tables
// of the demo and the interval of a "Not resolved" message: each is held
// against the capture in a second way. The reader of the table of the
// regression must throw on a capture text without the table, without its
// head row and without the sentence above it; the reader of the table of
// the changes on one without the table, without its head row and with a row
// that leaves the columns of its head row; the reader of the interval on a
// message with a revision the table of the changes does not hold, without a
// revision, and with changes that do not follow one another.
//
// Then, for every page of prose of both languages:
//   - every level-2 heading of the content is a section heading with the
//     anchor `prosePages` names, in its order, and is a link to itself; the
//     page holds no "on this page" list: no other link leads to a section,
//     apart from a section `prosePages` names as linked from the content
//     (the options several commands share and the sections of the commands,
//     on "Single commands"), which must then be linked; where `prosePages`
//     says so (`tree`), the chapter tree lists the sections under the page,
//     each as a link to its anchor, in their order, and on no other page of
//     prose does it list any;
//   - where `prosePages` names the commands of a page: every inline code
//     of the content that is the name of a command is a link to the section
//     of that command, apart from the section of the command itself, which
//     holds no link to itself but its heading;
//   - no part of the content names a step that is not there (the mark a
//     step card replaces);
//   - the platform switches of a page of prose, which stand between its
//     blocks: those `prosePages` names, in order, each named by its place
//     ("Command, request, Windows"), and those without a command. Windows on
//     the first visit; a tab list of two buttons, the copy button after it,
//     then the command, a named region that takes focus; a click on "Linux"
//     changes every switch while the used one keeps focus; the copy button
//     copies the command that is shown; a switch without a command holds no
//     code block and no copy button; axe with Linux chosen; at 390 px tabs
//     and copy button are at least 40 px high; with JavaScript off both
//     parts stand one after the other, Windows first, each under its label,
//     without tabs and buttons;
//   - the language switch, at the address of a section, opens the
//     counterpart at the same section;
//   - a wide figure holds its caption, which is text; no text of a figure is
//     below 11 px;
//   - the idea figure: the two boxes name the revisions of the two states
//     as the capture does; one square per revision, 7 px, those of the
//     search table 11 px with their number, hidden from assistive
//     technology; the two lines of text begin with the counts; the caption
//     names the numbers. At 1280 px the boxes stand left and right of the
//     trace; at 390 and 320 px they stack, box, trace, box, and the squares
//     keep their size, stand apart and stay inside the figure;
//   - the bars below it: one per revision of the search table, the label
//     "number · revision", the sum as the capture of the language prints it;
//   - a row list numbers its rows and closes with a hairline; a list
//     without numbers (`plain`) is an unordered list whose rows carry none;
//     a label above a list is a small mono label in capitals and the name
//     of the list; the code name
//     of a row follows its name as inline code that is not translated, in
//     weight 400; the tag of a row is a small mono label in capitals with a
//     hairline border, at 1280 px at the right end of the row and at 390 and
//     320 px below its text; where `prosePages` names the numbers of code
//     names and tags, the page holds as many;
//   - a sub-heading is a level-3 heading of 18 px after a section heading;
//     where `prosePages` names their number, the page holds as many;
//   - the connection figure: one per page, a wide figure and an ordered list
//     of the three boxes `prosePages` names per language, each with its two
//     small lines; only the box `prosePages` names as built is dashed, the
//     others are solid; the first trace carries the one label, in teal-text;
//     the caption is text. At 1280 px the boxes stand side by side with the
//     label between the first two; at 390 and 320 px they are a stack with
//     the label between the first two; nothing is scaled and nothing
//     reaches beyond the figure;
//   - the yardstick box: a block of the page with a navy border, its tag,
//     the line with the number of lines in 22 px, and a text that names a
//     file as inline code;
//   - a code excerpt: a figure with a head row that names its file first, a
//     caption, and the code as a named region, named after its file, that
//     takes focus with the focus ring, is not translated, holds no markup
//     (uncoloured) and scrolls sideways inside its box, at 390 px with the
//     arrow keys; no copy button and nothing to copy;
//   - the two four-column tables of the demo (DemoTable.astro): head row,
//     rows and the sentence above as the capture of the language prints
//     them; the table of the search: revision and sum of each row as the
//     capture prints them, a caption that is not empty. For all three: the
//     roles written out, a header per row. At
//     1280 px a row is one line; at 390 and 320 px every row, the head row
//     included, is a record of two lines with every column name visible,
//     and no cell reaches beyond the window;
//   - the line of the changes: one square per change, 7 px, those of the
//     search table 11 px with their number, a bracket from the first to the
//     last change of the interval that is not resolved, with their numbers;
//     the key names the numbers; at 1280 px the key stands right of the
//     trace, at 390 and 320 px below it, and the squares keep their size;
//     the bars below it as under the idea figure;
//   - the wide flow diagram: a wide figure that is an ordered list of the
//     boxes `prosePages` names, in their order, each numbered, without a
//     mono line; the trace ends in the pad and the words `prosePages` names;
//     the first row list of the page names the same parts in the same order,
//     so that the diagram stands as text beside itself. At 1280 px the boxes
//     stand side by side from left to right with the end right of them; at
//     390 and 320 px they are a stack with the end below; nothing is scaled
//     and every box stays inside the figure;
//   - the path block: the four stages of the register in order, each with
//     its number, its name, one sentence and a link to each of its pages but
//     the page itself, by the name and address of the register;
//   - nothing in the content moves; no sideways scrolling at 1280, 390 and
//     320 px; axe at 1280 and 390 px.
// Exits non-zero and names page and part of every failed expectation.
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import {
  BASE,
  DESKTOP,
  PHONE,
  RING,
  expectations,
  loadExample,
  loadHints,
  loadPages,
  loadRegister,
  loadRelease,
  openPage,
  pageChecks,
  root,
  startPreview,
} from './harness.mjs';

/** What each page of prose must show: the anchors of its sections, in order. */
const prosePages = {
  overview: {
    sections: ['what-it-does', 'what-you-need', 'what-you-get', 'for-you', 'next'],
    // The section the language switch is tried at.
    counterpart: 'what-you-get',
    idea: true,
    rows: 3,
    path: true,
  },
  'understand-the-results': {
    sections: ['regression-table', 'change-table', 'search-result'],
    counterpart: 'change-table',
    rows: 23,
    // The three tables of the demo and the line of the changes.
    tables: true,
    line: true,
  },
  'how-deltarecon-works': {
    sections: ['path', 'search', 'limits'],
    counterpart: 'limits',
    rows: 9,
    // The wide flow diagram: its boxes in order and what its trace ends in.
    flow: {
      en: {
        boxes: ['Two recorded results', 'The changes in order', 'Search by halving', 'Attribution to single changes'],
        end: 'search result',
      },
      de: {
        boxes: ['Zwei Ergebnisse mit Nachweis', 'Die Änderungen der Reihe nach', 'Suche durch Halbieren', 'Zuordnung zu einzelnen Änderungen'],
        end: 'Suchergebnis',
      },
    },
  },
  'tolerance-profile': {
    sections: ['what', 'file', 'rule', 'write', 'faults'],
    counterpart: 'rule',
    rows: 17,
    codes: 7,
    tags: 1,
    switches: { places: ['search'], plain: 0 },
  },
  'single-commands': {
    sections: ['start', 'request', 'run', 'replay', 'compare', 'regression', 'derive', 'walk', 'search', 'quickstart', 'shared-options'],
    counterpart: 'search',
    rows: 91,
    // The sections the content links to: the section the sections of the
    // commands link to, and the section of each command, which the name of
    // the command links to wherever the text names it.
    linked: ['shared-options', 'request', 'run', 'replay', 'compare', 'regression', 'derive', 'walk', 'search', 'quickstart'],
    // The chapter tree lists the sections of this page under the page.
    tree: true,
    // The sections of the commands: the name of a command in the text is a
    // link to its section, apart from its own section.
    commands: ['request', 'run', 'replay', 'compare', 'regression', 'derive', 'walk', 'search', 'quickstart'],
    // The platform switches: the place each switch with a command names, in
    // order, and the number of switches without a command.
    switches: {
      places: ['request', 'run', 'replay', 'compare', 'regression', 'derive', 'walk', 'search', 'quickstart'],
      plain: 1,
    },
  },
  'engine-requirements': {
    sections: ['answers', 'to-build', 'size', 'selection'],
    counterpart: 'size',
    rows: 24,
    // The rows that carry a code name, the rows with a tag, the sub-headings.
    codes: 23,
    tags: 2,
    subHeadings: 3,
    // The connection figure: its boxes in order, the one that is built
    // (dashed), and the label of the first trace.
    connection: {
      en: { boxes: ['DeltaRecon', 'Your connection', 'Your engine'], built: 'Your connection', label: 'protocol' },
      de: { boxes: ['DeltaRecon', 'Ihre Anbindung', 'Ihre Engine'], built: 'Ihre Anbindung', label: 'Protokoll' },
    },
    yardsticks: 1,
    excerpts: 1,
    // A place that differs by language is named per language.
    switches: { places: [{ en: 'engine selection', de: 'Auswahl der Engine' }], plain: 0 },
  },
};

/** The mark a step card puts its number in the place of (src/markup.ts). */
const STEP_MARK = '⟦step⟧';

/** The widths the idea figure is looked at: side by side, then as a stack. */
const NARROW = { width: 320, height: 844 };
const PLATFORMS = ['windows', 'linux'];

const site = await loadRegister();
const pages = await loadPages();
const { exampleFacts, regressionTable, changeTable, unresolvedInterval } = await loadExample();
const release = await loadRelease();
const { failures, expect, report } = expectations('check-prose');
const { checkAxe, checkNoMotion, checkNoSidewaysScroll } = pageChecks({ failures, expect });

// "When something goes wrong" is a page of prose too: its sections are the
// hint groups of the register (src/hints.ts), in its order, and the section
// of the contact block. A step or a section of another page links to its
// group, and the group back; those links cross pages, so no link of the page
// itself leads to a section. scripts/check-hints.mjs holds the groups, the
// hint links and the contact block.
const hints = await loadHints();
prosePages[hints.helpPage] = {
  sections: [...hints.hintGroups.map((group) => group.anchor), hints.contactAnchor],
  counterpart: hints.hintGroups[hints.hintGroups.length - 1].anchor,
};

const captureFile = (platform, lang) => `captures/v${release}/${platform}-${lang}.txt`;
const readCapture = (platform, lang) =>
  readFile(path.join(root, 'src', captureFile(platform, lang)), 'utf8');

/** The rows of the search table of a capture: revision and sum, as printed. */
function searchRows(source) {
  const lines = source.split('\n');
  // The last table whose rows begin with a short hash: the search of step 4.
  const rows = [];
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const row = /^\s{2}([0-9a-f]{7})\s{2,}.*\S\s{2,}([+-]\S+)$/.exec(lines[index]);
    if (row) rows.unshift({ revision: row[1], sum: row[2] });
    else if (rows.length > 0) break;
  }
  return rows;
}

/** Whether a call throws, and with which message. */
function thrown(call) {
  try {
    call();
  } catch (error) {
    return error.message;
  }
  return null;
}

/**
 * The reader of the facts of the example on the capture files, and on
 * capture texts that lack a part. Returns the facts per language.
 */
async function checkExample() {
  const facts = {};
  for (const lang of site.languages) {
    const read = [];
    for (const platform of PLATFORMS) {
      const file = captureFile(platform, lang);
      const source = await readCapture(platform, lang);
      const rows = searchRows(source);
      expect(rows.length > 0, `src/${file}: the check finds no row of the search table`);
      const revisions = rows.map((row) => row.revision);
      let found;
      try {
        found = exampleFacts(source, lang, revisions, file);
      } catch (error) {
        failures.push(`src/${file}: the facts of the example are not read: ${error.message}`);
        continue;
      }
      read.push(JSON.stringify(found));
      facts[lang] = { ...found, rows };
      // The facts, held against the capture in another way than the reader's.
      const lines = source.split('\n');
      const numbered = lines.filter((line) => /^\s*\d+\s+[0-9a-f]{7}\s{2,}\S/.test(line));
      expect(
        found.revisions === numbered.length && found.revisions > 0,
        `src/${file}: ${found.revisions} revisions read, the table of the changes has ${numbered.length} rows`,
      );
      for (const { number, revision } of found.deviating) {
        expect(
          new RegExp(`^\\s*${number}\\s+${revision}\\s`).test(numbered[number - 1] ?? ''),
          `src/${file}: the revision ${revision} is not row ${number} of the table of the changes`,
        );
      }
      expect(
        found.deviating.length === rows.length,
        `src/${file}: ${found.deviating.length} revisions numbered, the search table has ${rows.length} rows`,
      );
      for (const [name, hash] of [
        ['release N', found.releaseN],
        ['the state N+1', found.stateN1],
      ]) {
        expect(
          /^[0-9a-f]{7}$/.test(hash) && new RegExp(`--revision\\s+${hash}[0-9a-f]{33}\\b`).test(source),
          `src/${file}: no command computes the revision ${hash} read for ${name}`,
        );
      }
      expect(found.releaseN !== found.stateN1, `src/${file}: both states are the revision ${found.releaseN}`);
      // The opening sentence names the size of the portfolio; it may wrap.
      const opening = source.replace(/\s+/g, ' ').split(': ')[0];
      const words = lang === 'en' ? 'model points' : 'Modellpunkten';
      expect(
        /^\d[\d.,]*$/.test(found.modelPoints) && opening.endsWith(` ${found.modelPoints} ${words}`),
        `src/${file}: the number of model points read is "${found.modelPoints}", the opening sentence ends "${opening.slice(-40)}"`,
      );

      // Capture texts that lack a part: each must throw and name the part.
      const first = found.deviating[0];
      const row = new RegExp(`^\\s*${first.number}\\s+${first.revision}\\s.*\\n`, 'm');
      const cases = [
        [
          'a table of the changes without a revision of the search table',
          source.replace(row, ''),
          revisions,
          first.revision,
        ],
        [
          'a search table with a revision the table of the changes does not hold',
          source,
          [...revisions, '0000000'],
          '0000000',
        ],
        [
          'no table of the changes',
          lines.filter((line) => !numbered.includes(line)).join('\n'),
          revisions,
          'the table of the changes',
        ],
        ['commands without a revision', source.replaceAll('--revision', '--state'), revisions, 'release N'],
        ['a search table without rows', source, [], 'the search table'],
      ];
      for (const [name, text, deviating, part] of cases) {
        expect(text !== source || deviating !== revisions, `src/${file}: the case "${name}" changes nothing`);
        const message = thrown(() => exampleFacts(text, lang, deviating, file));
        expect(
          message !== null && message.includes(file) && message.includes(part),
          `src/${file}: ${name}: the reader ${message === null ? 'does not throw' : `throws "${message}"`}, expected a message with the file and "${part}"`,
        );
      }
    }
    expect(
      read.length === PLATFORMS.length && new Set(read).size === 1,
      `captures of "${lang}": the facts of the example differ by platform`,
    );
    facts[lang] = { ...facts[lang], ...(await checkTables(lang)) };
  }
  return facts;
}

/**
 * The readers of the two four-column tables and of the interval that is not
 * resolved, on the capture files of a language and on capture texts that
 * lack a part. Returns what the pages must show.
 */
async function checkTables(lang) {
  const read = [];
  let shown = {};
  for (const platform of PLATFORMS) {
    const file = captureFile(platform, lang);
    const source = await readCapture(platform, lang);
    const lines = source.split('\n');
    let regression;
    let changes;
    let interval;
    try {
      regression = regressionTable(source, file);
      changes = changeTable(source, file);
      const message = lines
        .slice(lines.findIndex((line) => /^(Not resolved|Nicht aufgelöst):/.test(line)))
        .join(' ')
        .split(/\s(?:Result|Ergebnis):/)[0];
      interval = unresolvedInterval(message, changes.rows, file);
    } catch (error) {
      failures.push(`src/${file}: the tables of the demo are not read: ${error.message}`);
      continue;
    }
    read.push(JSON.stringify({ regression, changes, interval }));
    shown = { regression, changes, interval };

    // Held against the capture in another way: by the line of the head row.
    const cellsOf = (line) => line.trim().split(/\s{2,}/);
    const blockAfter = (head) => {
      const at = lines.findIndex((line) => line.trim() === head);
      const end = lines.findIndex((line, index) => index > at && line.trim() === '');
      return at === -1 ? [] : lines.slice(at + 1, end);
    };
    const regressionHead = lang === 'en' ? 'Quantity  Model points  Values  Periods' : 'Größe  Modellpunkte  Werte  Perioden';
    const regressionLines = lines.filter((line) => cellsOf(line).join('  ') === regressionHead);
    expect(regressionLines.length === 1, `src/${file}: the check finds no head row "${regressionHead}"`);
    const below = blockAfter(regressionLines[0]?.trim());
    expect(
      regression.head.join('  ') === regressionHead &&
        regression.rows.length === below.length &&
        regression.rows.length > 0 &&
        regression.rows.every(
          (row, index) =>
            cellsOf(below[index]).join('|') === [row.quantity, row.modelPoints, row.values, row.periods].join('|'),
        ),
      `src/${file}: the table of the regression is read as ${regression.rows.length} rows under [${regression.head}], the capture has ${below.length} lines under its head row`,
    );
    const sentence = (text) => {
      const flat = source.replace(/\s+/g, ' ');
      return flat.includes(text);
    };
    expect(
      regression.caption.length > 20 && sentence(regression.caption) && /\d/.test(regression.caption),
      `src/${file}: the sentence above the table of the regression is read as "${regression.caption}"`,
    );
    const numbered = lines.filter((line) => /^\s*\d+\s+[0-9a-f]{7}\s{2,}\S/.test(line));
    expect(
      changes.rows.length === numbered.length &&
        changes.head.length === 4 &&
        changes.rows.every((row, index) => {
          const line = numbered[index];
          return (
            new RegExp(`^\\s*${row.number}\\s+${row.revision}\\s+`).test(line) &&
            line.trimEnd().endsWith(row.description) &&
            line.replace(/\s+/g, ' ').includes(` ${row.revision} ${row.classes} ${row.description.replace(/\s+/g, ' ')}`)
          );
        }),
      `src/${file}: the table of the changes is read as ${changes.rows.length} rows, the capture has ${numbered.length}; or a row is not cut as printed`,
    );
    expect(
      changes.caption.startsWith(`${changes.rows.length} `) && sentence(changes.caption),
      `src/${file}: the sentence above the table of the changes is read as "${changes.caption}"`,
    );
    expect(
      interval.length > 0 &&
        interval.every(
          (entry) =>
            new RegExp(`^\\s*${entry.number}\\s+${entry.revision}\\s`).test(numbered[entry.number - 1] ?? ''),
        ),
      `src/${file}: the interval that is not resolved is read as [${interval.map((entry) => `${entry.number} ${entry.revision}`)}]`,
    );

    // Capture texts that lack a part: each must throw and name the part.
    const regressionAt = lines.indexOf(regressionLines[0]);
    const changesAt = lines.indexOf(numbered[0]) - 1;
    // The lines of the sentence above the table of the regression, as read.
    let sentenceLines = 0;
    while (
      sentenceLines < regressionAt &&
      lines
        .slice(regressionAt - 1 - sentenceLines, regressionAt - 1)
        .map((line) => line.trim())
        .join(' ') !== regression.caption
    ) {
      sentenceLines += 1;
    }
    expect(
      sentenceLines > 0 && sentenceLines < regressionAt,
      `src/${file}: the check does not find the lines of the sentence above the table of the regression`,
    );
    const without = (from, count) => lines.filter((_, index) => index < from || index >= from + count).join('\n');
    const cases = [
      [
        'no table of the regression',
        () => regressionTable(without(regressionAt, below.length + 1), file),
        'the table of the regression',
      ],
      [
        'a table of the regression without its head row',
        () => regressionTable(without(regressionAt, 1), file),
        'the head row of the table of the regression',
      ],
      [
        'a table of the regression without the sentence above it',
        () => regressionTable(without(regressionAt - 1 - sentenceLines, sentenceLines + 1), file),
        'the sentence above the table of the regression',
      ],
      [
        'no table of the changes',
        () => changeTable(lines.filter((line) => !numbered.includes(line)).join('\n'), file),
        'the table of the changes',
      ],
      [
        'a table of the changes without its head row',
        () => changeTable(without(changesAt, 1), file),
        'the head row of the table of the changes',
      ],
      [
        'a row of the table of the changes that leaves its columns',
        () => changeTable(source.replace(numbered[1], numbered[1].replace(/\s{6,}/, ' x ')), file),
        'row 2 of the table of the changes',
      ],
      [
        'a "Not resolved" message with a revision the table of the changes does not hold',
        () => unresolvedInterval('0000000, 1111111', changes.rows, file),
        '0000000',
      ],
      [
        'a "Not resolved" message without a revision',
        () => unresolvedInterval('nothing', changes.rows, file),
        'a revision in a "Not resolved" message',
      ],
      [
        'a "Not resolved" message whose changes do not follow one another',
        () => unresolvedInterval(`${changes.rows[0].revision}, ${changes.rows[2].revision}`, changes.rows, file),
        'an interval',
      ],
    ];
    for (const [name, call, part] of cases) {
      const message = thrown(call);
      expect(
        message !== null && message.includes(file) && message.includes(part),
        `src/${file}: ${name}: the reader ${message === null ? 'does not throw' : `throws "${message}"`}, expected a message with the file and "${part}"`,
      );
    }
  }
  expect(
    read.length === PLATFORMS.length && new Set(read).size === 1,
    `captures of "${lang}": the tables of the demo differ by platform`,
  );
  return shown;
}

function open(browser, origin, entry, viewport, anchor = '') {
  return openPage(browser, `${origin}${entry.address}${anchor}`, { viewport });
}

/** The section headings: every level-2 heading of the content, in order. */
async function checkHeadings(page, name, listed) {
  const headings = await page.evaluate(() =>
    [...document.querySelectorAll('main h2')]
      .filter((heading) => !heading.closest('[data-page-links]'))
      .map((heading) => {
        const links = [...heading.querySelectorAll('a')];
        return {
          text: heading.textContent.trim(),
          id: heading.id,
          section: heading.hasAttribute('data-section-heading'),
          links: links.map((link) => link.getAttribute('href')),
          linked: links.length === 1 && links[0].textContent.trim() === heading.textContent.trim(),
        };
      }),
  );
  for (const heading of headings) {
    expect(
      heading.section && heading.id !== '',
      `${name}: the heading "${heading.text}" is no section heading with an anchor (SectionHeading with "id")`,
    );
    expect(
      heading.linked && heading.links[0] === `#${heading.id}`,
      `${name}: the heading "${heading.text}" is not a link to itself (#${heading.id}); its links are [${heading.links}]`,
    );
  }
  const anchors = headings.map((heading) => heading.id);
  expect(
    JSON.stringify(anchors) === JSON.stringify(listed.sections),
    `${name}: the sections are [${anchors}], expected [${listed.sections}] (prosePages in scripts/check-prose.mjs)`,
  );
  // No "on this page" list: no link of the page but a heading itself leads
  // to a section, apart from a section the entry names as linked from the
  // content, and then only from inside the content.
  const linked = listed.linked ?? [];
  const others = await page.evaluate(
    (ids) =>
      [...document.querySelectorAll('a[href^="#"]')]
        // A link of the list of sections of the tree counts whatever it names.
        .filter((link) => (ids.includes(link.getAttribute('href').slice(1)) || link.closest('#chapters [data-tree-sections]')) && !link.closest('h2'))
        .map((link) => ({
          href: link.getAttribute('href'),
          content: link.closest('main [data-row], main [data-prose], main [data-callout]') !== null,
          tree: link.closest('#chapters [data-tree-sections]') !== null,
        })),
    anchors,
  );
  // The chapter tree lists the sections where the entry says so, and only there.
  const inTree = others.filter((link) => link.tree).map((link) => link.href.slice(1));
  expect(
    JSON.stringify(inTree) === JSON.stringify(listed.tree ? anchors : []),
    `${name}: the chapter tree lists the sections [${inTree}], expected [${listed.tree ? anchors : []}] (prosePages in scripts/check-prose.mjs)`,
  );
  const strangers = others.filter((link) => !link.tree && !(link.content && linked.includes(link.href.slice(1))));
  expect(
    strangers.length === 0,
    `${name}: links to sections outside their headings: [${strangers.map((link) => link.href)}]`,
  );
  for (const anchor of linked) {
    expect(
      others.some((link) => !link.tree && link.href === `#${anchor}`),
      `${name}: no link of the content leads to the section "${anchor}", which prosePages names as linked`,
    );
  }
  // The name of a command in the text is a link to its section, apart from
  // its own section.
  if (listed.commands) {
    const names = await page.evaluate((commands) => {
      const found = [];
      let section = '';
      for (const part of document.querySelectorAll('main h2[data-section-heading], main code, main a[href^="#"]')) {
        if (part.matches('h2')) {
          section = part.id;
        } else if (part.closest('h2, pre, [data-synopsis]')) {
          continue;
        } else if (part.matches('a')) {
          const target = part.getAttribute('href').slice(1);
          const named = part.querySelector('code')?.textContent;
          if (commands.includes(target) && !(named && commands.includes(named) && named !== target)) found.push({ section, command: target, link: target, own: target === section });
        } else if (commands.includes(part.textContent) && !part.closest('.row-name')) {
          const link = part.closest('a')?.getAttribute('href')?.slice(1);
          // In a link to another section the name is recorded here; the link itself above.
          if (link !== part.textContent) found.push({ section, command: part.textContent, link, own: part.textContent === section });
        }
      }
      return found;
    }, listed.commands);
    for (const found of names) {
      if (found.own) {
        expect(found.link === undefined, `${name}: the section "${found.section}" holds a link to itself beside its heading`);
      } else {
        expect(
          found.link === found.command,
          `${name}, section "${found.section}": the name of the command "${found.command}" is no link to its section`,
        );
      }
    }
  }
  // A part that names its step stands in a step card, which a page of prose has not.
  const marked = await page.evaluate((mark) => document.querySelector('main').innerHTML.includes(mark), STEP_MARK);
  expect(!marked, `${name}: a part of the content names a step ("${STEP_MARK}"); outside a step card it needs "place"`);
}

/** What a page of prose shows of its platform switches, in order. */
function switchState(page) {
  return page.evaluate(() => {
    const shown = (element) => Boolean(element) && element.getClientRects().length > 0;
    const height = (element) => (element ? element.getBoundingClientRect().height : 0);
    return {
      chosen: document.documentElement.dataset.platform,
      focus: document.activeElement?.dataset?.platformTab,
      switches: [...document.querySelectorAll('main [data-platform-switch]')].map((element, index) => {
        const list = element.querySelector('[role="tablist"]');
        const tabs = [...element.querySelectorAll('[role="tab"]')];
        const button = element.querySelector('button[data-copy-button]');
        const parts = [...element.querySelectorAll(':scope > [data-platform-part]')];
        const part = parts.find(shown);
        const region = part?.querySelector('pre');
        const text = part?.querySelector('.platform-text, .step-after');
        return {
          index,
          block: element.parentElement === document.querySelector('main'),
          plain: element.hasAttribute('data-plain'),
          label: list?.getAttribute('aria-label') ?? '',
          tabs: tabs.map((tab) => ({
            platform: tab.dataset.platformTab,
            name: tab.textContent.trim().replace(/\s+/g, ' '),
            button: tab.tagName === 'BUTTON',
            selected: tab.getAttribute('aria-selected') === 'true',
            stop: tab.tabIndex === 0,
            panel: document.getElementById(tab.getAttribute('aria-controls') ?? '')?.getAttribute('role') === 'tabpanel',
            height: height(tab),
          })),
          hasFocus: element.contains(document.activeElement),
          parts: parts.map((candidate) => ({ platform: candidate.dataset.platformPart, shown: shown(candidate) })),
          labels: parts.filter((candidate) => shown(candidate.querySelector(':scope > [data-platform-label]'))).length,
          blocks: element.querySelectorAll('pre').length,
          button: button && {
            name: button.getAttribute('aria-label') ?? '',
            height: height(button),
            // After the tab list, before the command.
            placed:
              Boolean(list && region) &&
              Boolean(list.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING) &&
              Boolean(button.compareDocumentPosition(region) & Node.DOCUMENT_POSITION_FOLLOWING),
          },
          region: region && {
            name: region.getAttribute('aria-label') ?? '',
            role: region.getAttribute('role'),
            stop: region.tabIndex === 0,
            scrolls: getComputedStyle(region).overflowX,
            command: region.textContent,
            copy: region.closest('[data-copy]')?.dataset.copy,
          },
          text: text ? text.textContent.trim() : '',
        };
      }),
    };
  });
}

/** The platform switches of a page of prose. */
async function checkSwitches(browser, origin, entry, listed) {
  const t = entry.texts;
  const wanted = listed.places.length + listed.plain;
  const tabNames = { windows: `${t.windows} ${t.windowsShell}`, linux: t.linux };
  const withScript = async (viewport, options = {}) => {
    const context = await browser.newContext({ viewport, ...options });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('html[data-menu]');
    return { context, page, errors };
  };

  /** Every switch shows `platform`, and each is what the entry names. */
  const expectSwitches = (state, name, platform) => {
    expect(state.chosen === platform, `${name}: <html data-platform> is "${state.chosen}", expected "${platform}"`);
    expect(
      state.switches.length === wanted && state.switches.filter((element) => element.plain).length === listed.plain,
      `${name}: ${state.switches.length} platform switches, ${state.switches.filter((element) => element.plain).length} of them without a command; expected ${wanted} and ${listed.plain} (prosePages in scripts/check-prose.mjs)`,
    );
    const places = [...listed.places];
    for (const element of state.switches) {
      const which = `${name}, platform switch ${element.index + 1}`;
      expect(element.block, `${which}: it does not stand between the blocks of the page`);
      expect(
        element.label === t.operatingSystem &&
          element.tabs.length === 2 &&
          element.tabs[0].platform === 'windows' &&
          element.tabs[1].platform === 'linux' &&
          element.tabs.every((tab) => tab.button && tab.panel) &&
          element.tabs[0].name === (element.plain ? t.windows : tabNames.windows) &&
          element.tabs[1].name === tabNames.linux,
        `${which}: not a tab list "${t.operatingSystem}" of the buttons "${tabNames.windows}" and "${tabNames.linux}", each naming its panel: ${JSON.stringify(element.tabs)}`,
      );
      expect(
        element.tabs.filter((tab) => tab.selected).map((tab) => tab.platform).join() === platform &&
          element.tabs.filter((tab) => tab.stop).length === 1,
        `${which}: the selected tab is not "${platform}", or the switch has not one tab stop`,
      );
      expect(
        element.parts.length === 2 && element.parts.every((part) => part.shown === (part.platform === platform)) && element.labels === 0,
        `${which}: it does not show the part of "${platform}" alone, under the tabs: ${JSON.stringify(element.parts)}`,
      );
      if (element.plain) {
        expect(
          element.blocks === 0 && !element.button && element.text !== '',
          `${which}: a switch without a command holds a code block or a copy button, or no text`,
        );
        continue;
      }
      const place = places.shift();
      expect(
        Boolean(element.region) &&
          element.region.name === `${t.command}, ${place}, ${t[platform]}` &&
          element.region.role === 'region' &&
          element.region.stop &&
          element.region.scrolls === 'auto' &&
          element.region.command === element.region.copy,
        `${which}: its command is not the named region "${t.command}, ${place}, ${t[platform]}" that takes focus and scrolls inside its block: ${JSON.stringify(element.region)}`,
      );
      expect(
        Boolean(element.button) && element.button.name === `${t.copyCommand}, ${place}` && element.button.placed,
        `${which}: no copy button "${t.copyCommand}, ${place}" after the tabs and before the command: ${JSON.stringify(element.button)}`,
      );
    }
  };

  // A page whose entry names no switch holds none.
  if (wanted === 0) {
    const name = `${entry.address} (${DESKTOP.width} px, platform switches)`;
    const { context, page } = await withScript(DESKTOP);
    const { switches } = await switchState(page);
    expect(
      switches.length === 0,
      `${name}: ${switches.length} platform switches, and prosePages names none (scripts/check-prose.mjs)`,
    );
    await context.close();
    return;
  }

  // Desktop: Windows first, then a click on "Linux" in a switch in the middle.
  {
    const name = `${entry.address} (${DESKTOP.width} px, platform switches)`;
    const { context, page, errors } = await withScript(DESKTOP, { permissions: ['clipboard-read', 'clipboard-write'] });
    expectSwitches(await switchState(page), `${name}, first visit`, 'windows');
    const used = Math.floor(wanted / 2);
    const list = page.locator('main [data-platform-switch]').nth(used).locator('[role="tablist"]');
    await list.scrollIntoViewIfNeeded();
    const before = (await list.boundingBox()).y;
    await list.locator('[data-platform-tab="linux"]').click();
    const state = await switchState(page);
    expectSwitches(state, `${name}, a click on Linux`, 'linux');
    expect(
      state.focus === 'linux' && state.switches[used]?.hasFocus,
      `${name}, a click on Linux: focus is not on the tab "linux" of the used switch`,
    );
    const after = (await list.boundingBox()).y;
    expect(Math.abs(after - before) <= 1, `${name}, a click on Linux: the used switch moved from ${before} to ${after} px in the window`);
    await page.keyboard.press('ArrowLeft');
    expectSwitches(await switchState(page), `${name}, the key ArrowLeft`, 'windows');
    await page.keyboard.press('End');
    expectSwitches(await switchState(page), `${name}, the key End`, 'linux');
    // The copy button copies the command that is shown.
    const first = (await switchState(page)).switches.find((element) => !element.plain);
    if (first) {
      const button = page.locator('main [data-platform-switch]').nth(first.index).locator('button[data-copy-button]');
      await button.click();
      await page.waitForFunction((index) => document.querySelectorAll('main [data-platform-switch]')[index].querySelector('button[data-copy-button][data-state]') !== null, first.index, { timeout: 5_000 }).catch(() => {});
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      expect(
        copied === first.region?.copy && (await button.textContent()) === t.copied,
        `${name}: the copy button of platform switch ${first.index + 1} copied "${copied}" and reads "${await button.textContent()}", expected "${first.region?.copy}" and "${t.copied}"`,
      );
      await page.waitForFunction(() => document.querySelector('main button[data-copy-button][data-state]') === null, undefined, { timeout: 10_000 }).catch(() => {});
    }
    await checkAxe(page, `${name}, Linux`);
    await checkNoSidewaysScroll(page, `${name}, Linux`);
    expect(errors.length === 0, `${name}: script errors: ${errors.join(' | ')}`);
    await context.close();
  }

  // Phone: tabs and copy button are at least 40 px high.
  {
    const name = `${entry.address} (${PHONE.width} px, platform switches)`;
    const { context, page } = await withScript(PHONE);
    const state = await switchState(page);
    expectSwitches(state, name, 'windows');
    for (const element of state.switches) {
      expect(
        element.tabs.every((tab) => tab.height >= 40) && (!element.button || element.button.height >= 40),
        `${name}, platform switch ${element.index + 1}: a tab or the copy button is below 40 px (${element.tabs.map((tab) => tab.height)}, ${element.button?.height})`,
      );
    }
    await context.close();
  }

  // JavaScript off: both parts, Windows first, each under its label.
  {
    const name = `${entry.address} (${DESKTOP.width} px, JavaScript off)`;
    const context = await browser.newContext({ viewport: DESKTOP, javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(`${origin}${entry.address}`);
    const state = await page.evaluate(() => {
      const shown = (element) => Boolean(element) && element.getClientRects().length > 0;
      return {
        chosen: document.documentElement.dataset.platform,
        tabs: document.querySelectorAll('main [role="tab"], main [role="tablist"], main [role="tabpanel"]').length,
        buttons: [...document.querySelectorAll('main button')].filter(shown).length,
        switches: [...document.querySelectorAll('main [data-platform-switch]')].map((element) => ({
          plain: element.hasAttribute('data-plain'),
          parts: [...element.querySelectorAll(':scope > [data-platform-part]')].map((part) => {
            const label = part.querySelector(':scope > [data-platform-label]');
            const block = part.querySelector('pre');
            return {
              platform: part.dataset.platformPart,
              label: shown(label) ? label.textContent.trim().replace(/\s+/g, ' ') : '',
              labelTop: label?.getBoundingClientRect().top,
              blockTop: shown(block) ? block.getBoundingClientRect().top : -1,
            };
          }),
        })),
      };
    });
    expect(state.chosen === undefined, `${name}: <html> names a platform`);
    expect(
      state.tabs === 0 && state.buttons === 0,
      `${name}: the page holds tabs or a visible button (${state.tabs} tab parts, ${state.buttons} buttons)`,
    );
    expect(state.switches.length === wanted, `${name}: ${state.switches.length} platform switches, expected ${wanted}`);
    state.switches.forEach((element, index) => {
      const [first, second] = element.parts;
      expect(
        element.parts.length === 2 &&
          first.platform === 'windows' &&
          second.platform === 'linux' &&
          first.label === (element.plain ? t.windows : tabNames.windows) &&
          second.label === tabNames.linux &&
          first.labelTop < second.labelTop &&
          (element.plain
            ? first.blockTop === -1 && second.blockTop === -1
            : first.labelTop < first.blockTop && first.blockTop < second.labelTop && second.labelTop < second.blockTop),
        `${name}, platform switch ${index + 1}: not the part of Windows and then of Linux, each under its visible label${element.plain ? ', without a command' : ' above its command'}: ${JSON.stringify(element.parts)}`,
      );
    });
    await context.close();
  }
}

/** The language switch at the address of a section. */
async function checkCounterpart(browser, origin, entry, anchor) {
  const name = `${entry.address}#${anchor}`;
  const { context, page } = await open(browser, origin, entry, DESKTOP, `#${anchor}`);
  await page.locator('body > header a[data-counterpart]').click();
  await page.waitForURL(`${origin}${entry.counterpart}#${anchor}`, { timeout: 10_000 }).catch(() => {});
  const landed = page.url().slice(origin.length);
  expect(
    landed === `${entry.counterpart}#${anchor}`,
    `${name}: the language switch opens ${landed}, expected ${entry.counterpart}#${anchor}`,
  );
  expect(
    (await page.locator(`main h2#${anchor}[data-section-heading]`).count()) === 1,
    `${name}: the counterpart ${entry.counterpart} holds no section "${anchor}"`,
  );
  await context.close();
}

/** Every wide figure: its caption, and no text below 11 px. */
async function checkFigures(page, name) {
  const figures = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-wide-figure]')].map((figure) => {
      const small = [];
      const walker = document.createTreeWalker(figure, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.data.trim() === '' || node.parentElement.getClientRects().length === 0) continue;
        const size = Number.parseFloat(getComputedStyle(node.parentElement).fontSize);
        if (size < 11) small.push(`"${node.data.trim()}" (${size} px)`);
      }
      const box = figure.getBoundingClientRect();
      const main = document.querySelector('main').getBoundingClientRect();
      const style = getComputedStyle(document.querySelector('main'));
      return {
        isFigure: figure.tagName === 'FIGURE',
        caption: figure.querySelector(':scope > figcaption')?.textContent.trim() ?? '',
        label: figure.getAttribute('aria-label'),
        small,
        // Over the full content width.
        full:
          Math.abs(box.left - (main.left + Number.parseFloat(style.paddingLeft))) < 1 &&
          Math.abs(box.right - (main.right - Number.parseFloat(style.paddingRight))) < 1,
      };
    }),
  );
  figures.forEach((figure, index) => {
    const which = `${name}: wide figure ${index + 1}`;
    expect(figure.isFigure && figure.caption !== '', `${which}: no figure with a caption inside`);
    expect(figure.label === null, `${which}: its alternative is an attribute, not text in the page`);
    expect(figure.small.length === 0, `${which}: text below 11 px: ${figure.small.join(', ')}`);
    expect(figure.full, `${which}: it does not span the content width`);
  });
  return figures.length;
}

/** What the idea figure shows and where its parts stand. */
function readIdea(page) {
  return page.evaluate(() => {
    const idea = document.querySelector('main [data-idea]');
    if (!idea) return null;
    const figure = idea.closest('[data-wide-figure]');
    const box = (element) => {
      const { left, right, top, bottom, width, height } = element.getBoundingClientRect();
      return { left, right, top, bottom, width, height };
    };
    const track = idea.querySelector('[data-idea-track]');
    const end = (key) => {
      const element = idea.querySelector(`[data-idea-box="${key}"] .flow-box`);
      return {
        box: box(element),
        text: element.textContent.replace(/\s+/g, ' ').trim(),
        hash: element.querySelector('[translate="no"]')?.textContent.trim(),
        border: getComputedStyle(element).borderTopStyle,
      };
    };
    return {
      inFigure: figure !== null,
      figure: figure ? box(figure) : null,
      caption: figure?.querySelector(':scope > figcaption')?.textContent.replace(/\s+/g, ' ').trim() ?? '',
      before: end('before'),
      after: end('after'),
      track: box(track),
      hidden: track.getAttribute('aria-hidden') === 'true',
      count: idea.querySelector('[data-idea-count]').textContent.trim(),
      deviating: idea.querySelector('[data-idea-deviating]').textContent.trim(),
      squares: [...track.querySelectorAll('[data-idea-square]')].map((square) => ({
        kind: square.dataset.ideaSquare,
        number: square.textContent.trim(),
        box: box(square),
        // A shape that carries meaning is a border, not a background.
        border: getComputedStyle(square).borderTopWidth,
      })),
      bars: [...(figure?.querySelectorAll('[data-bar-row]') ?? [])].map((row) => ({
        label: row.querySelector('.bar-revision').textContent.replace(/\s+/g, ' ').trim(),
        hash: row.querySelector('.bar-revision [translate="no"]')?.textContent.trim(),
        value: row.querySelector('.bar-value').textContent.trim(),
        kind: row.querySelector('[data-bar]').dataset.bar,
      })),
    };
  });
}

/** The idea figure at one width: `stacked` says how its boxes must stand. */
async function checkIdea(page, name, facts, lang, stacked) {
  const idea = await readIdea(page);
  if (!idea) {
    failures.push(`${name}: no idea figure`);
    return;
  }
  expect(idea.inFigure, `${name}: the idea figure stands outside a wide figure`);
  expect(
    idea.before.hash === facts.releaseN && idea.after.hash === facts.stateN1,
    `${name}: the boxes name the revisions ${idea.before.hash} and ${idea.after.hash}, the capture ${facts.releaseN} and ${facts.stateN1}`,
  );
  expect(
    idea.before.border === 'solid' && idea.after.border === 'solid',
    `${name}: the boxes of the idea figure are not outlined`,
  );
  expect(
    Math.abs(idea.before.box.width - (stacked ? idea.track.width : 184)) < 1 &&
      Math.abs(idea.after.box.width - idea.before.box.width) < 1,
    `${name}: the boxes are ${idea.before.box.width} and ${idea.after.box.width} px wide`,
  );

  // The squares: one per revision; those of the search table larger, numbered.
  expect(idea.hidden, `${name}: the squares are not hidden from assistive technology`);
  checkSquares(name, idea.squares, idea.track, facts);
  const numbers = facts.deviating.map((entry) => entry.number);
  expect(
    idea.track.left >= idea.figure.left && idea.track.right <= idea.figure.right,
    `${name}: the trace reaches beyond its figure`,
  );

  // Where the boxes stand.
  const { before, after, track } = idea;
  if (stacked) {
    expect(
      before.box.bottom <= track.top && after.box.top >= track.bottom,
      `${name}: the idea figure is not a stack of box, trace, box`,
    );
    expect(
      Math.abs(before.box.left - after.box.left) < 1 && before.box.left <= track.left + 0.05,
      `${name}: the boxes of the stack do not stand below one another`,
    );
  } else {
    expect(
      before.box.right <= track.left + 0.05 && after.box.left >= track.right - 0.05,
      `${name}: the boxes do not stand left and right of the trace`,
    );
    const middle = (track.top + track.bottom) / 2;
    expect(
      [before.box, after.box].every((box) => box.top < middle && box.bottom > middle),
      `${name}: the trace does not run from box to box`,
    );
  }

  // The words: the counts, the numbers in the caption.
  expect(
    idea.count.startsWith(`${facts.revisions} `),
    `${name}: the line above the trace is "${idea.count}", expected the count ${facts.revisions} first`,
  );
  expect(
    idea.deviating.startsWith(`${facts.deviating.length} `),
    `${name}: the line below the trace is "${idea.deviating}", expected the count ${facts.deviating.length} first`,
  );
  const list = new Intl.ListFormat(lang === 'en' ? 'en-GB' : 'de', { type: 'conjunction' }).format(
    numbers.map(String),
  );
  expect(idea.caption.includes(list), `${name}: the caption does not name the revisions ${list}`);

  // The bars: the revisions of the search table with number and sum.
  expect(
    idea.bars.length === facts.rows.length,
    `${name}: ${idea.bars.length} bars, the search table has ${facts.rows.length} rows`,
  );
  idea.bars.forEach((bar, index) => {
    const row = facts.rows[index];
    const { number } = facts.deviating[index];
    expect(
      bar.label === `${number} · ${row.revision}` && bar.hash === row.revision,
      `${name}: bar ${index + 1} is labelled "${bar.label}", expected "${number} · ${row.revision}"`,
    );
    expect(
      bar.value === row.sum && bar.kind === (row.sum.startsWith('-') ? 'lowers' : 'raises'),
      `${name}: bar ${index + 1} shows "${bar.value}" (${bar.kind}), the capture "${row.sum}"`,
    );
  });
}

/** The squares of a trace: one per revision, in their sizes, inside it. */
function checkSquares(name, squares, track, facts, marked = false) {
  expect(
    squares.length === facts.revisions,
    `${name}: ${squares.length} squares, the capture has ${facts.revisions} revisions`,
  );
  const numbers = facts.deviating.map((entry) => entry.number);
  const unresolved = (facts.interval ?? []).map((entry) => entry.number);
  squares.forEach((square, index) => {
    const number = index + 1;
    const found = numbers.includes(number);
    const size = found ? 11 : 7;
    const kind = found ? 'deviating' : marked && unresolved.includes(number) ? 'unresolved' : 'plain';
    expect(
      square.kind === kind && square.number === (found ? String(number) : ''),
      `${name}: square ${number} is "${square.kind}" with the number "${square.number}"`,
    );
    expect(
      Math.abs(square.box.width - size) < 0.1 && Math.abs(square.box.height - size) < 0.1,
      `${name}: square ${number} is ${square.box.width} × ${square.box.height} px, not ${size} × ${size}`,
    );
    expect(Number.parseFloat(square.border) > 0, `${name}: square ${number} is not drawn as a border`);
    const previous = squares[index - 1];
    expect(
      !previous || square.box.left >= previous.box.right - 0.05,
      `${name}: square ${number} overlaps square ${number - 1}`,
    );
    expect(
      square.box.left >= track.left - 0.05 && square.box.right <= track.right + 0.05,
      `${name}: square ${number} stands outside the trace`,
    );
  });
}

/** The tables of the demo on a page: what they show, and how a row is laid out. */
async function checkDemoTables(page, name, facts, lang, stacked) {
  const tables = await page.evaluate(() => {
    const box = (element) => {
      const { left, right, top, bottom, width, height } = element.getBoundingClientRect();
      return { left, right, top, bottom, width, height };
    };
    const cellsOf = (row) =>
      [...row.children].map((cell) => ({
        text: cell.textContent.trim(),
        role: cell.getAttribute('role'),
        tag: cell.tagName,
        scope: cell.getAttribute('scope'),
        lang: cell.getAttribute('lang'),
        marked: [...cell.querySelectorAll('[lang]')].map((part) => `${part.getAttribute('lang')}:${part.textContent}`),
        translate: cell.getAttribute('translate'),
        box: box(cell),
        shown: cell.getClientRects().length > 0 && getComputedStyle(cell).visibility === 'visible',
      }));
    return [...document.querySelectorAll('main table[data-demo-table], main table[data-result-table]')].map((table) => ({
      kind: table.dataset.demoTable ?? 'search',
      roles: [table, ...table.querySelectorAll('thead, tbody, tr')].map((element) => element.getAttribute('role')).join(' '),
      caption: table.querySelector('caption [data-capture="caption"]')?.textContent.replace(/\s+/g, ' ').trim() ?? '',
      captionShown: (table.querySelector('caption')?.getClientRects().length ?? 0) > 0,
      own: table.querySelector('caption')?.firstChild?.textContent.trim() ?? '',
      box: box(table),
      display: getComputedStyle(table.querySelector('tbody tr')).display,
      head: cellsOf(table.querySelector('thead tr')),
      headBox: box(table.querySelector('thead tr')),
      rows: [...table.querySelectorAll('tbody tr')].map((row) => ({ box: box(row), cells: cellsOf(row) })),
      window: document.documentElement.clientWidth,
    }));
  });
  const expected = {
    regression: {
      head: facts.regression.head,
      caption: facts.regression.caption,
      rows: facts.regression.rows.map((row) => [row.quantity, row.modelPoints, row.values, row.periods]),
      header: 0,
    },
    changes: {
      head: facts.changes.head,
      caption: facts.changes.caption,
      rows: facts.changes.rows.map((row) => [String(row.number), row.revision, row.classes, row.description]),
      header: 1,
    },
    search: { rows: facts.rows.map((row) => [row.revision, null, row.sum]), header: 0 },
  };
  expect(
    tables.map((table) => table.kind).join() === 'regression,changes,search',
    `${name}: the tables are [${tables.map((table) => table.kind)}], expected the three of the demo in its order`,
  );
  for (const table of tables) {
    const which = `${name}: table "${table.kind}"`;
    const listed = expected[table.kind];
    const columns = table.head.length;
    expect(
      table.roles === ['table', 'rowgroup', 'row', 'rowgroup', ...Array(table.rows.length).fill('row')].join(' '),
      `${which}: the roles of table, row groups and rows are not written out`,
    );
    expect(
      table.head.every((cell) => cell.tag === 'TH' && cell.role === 'columnheader' && cell.scope === 'col' && cell.shown),
      `${which}: its head row is not ${columns} visible column headers`,
    );
    expect(
      table.captionShown && table.own !== '' && table.caption !== '',
      `${which}: no caption with the words of the page and the sentence of the demo`,
    );
    if (listed.head) {
      expect(
        JSON.stringify(table.head.map((cell) => cell.text)) === JSON.stringify(listed.head) && columns === 4,
        `${which}: its head row is [${table.head.map((cell) => cell.text)}], the capture prints [${listed.head}]`,
      );
      expect(table.caption === listed.caption, `${which}: its caption holds "${table.caption}", the capture "${listed.caption}"`);
    }
    expect(
      table.rows.length === listed.rows.length,
      `${which}: ${table.rows.length} rows, the capture has ${listed.rows.length}`,
    );
    table.rows.forEach((row, index) => {
      const wanted = listed.rows[index] ?? [];
      const where = `${which}, row ${index + 1}`;
      expect(
        row.cells.length === columns && row.cells.every((cell, at) => wanted[at] === null || cell.text === wanted[at]),
        `${where}: it shows [${row.cells.map((cell) => cell.text)}], the capture [${wanted}]`,
      );
      expect(
        row.cells.every((cell, at) =>
          at === listed.header
            ? cell.tag === 'TH' && cell.role === 'rowheader' && cell.scope === 'row'
            : cell.tag === 'TD' && cell.role === 'cell',
        ),
        `${where}: its header is not column ${listed.header + 1}, or a role is not written out`,
      );
      // A German quantity on an English page, an English description on a
      // German page and a hash carry what they are.
      if (table.kind === 'regression') {
        expect(row.cells[0].lang === (lang === 'en' ? 'de' : null), `${where}: the quantity does not carry its language`);
      }
      if (table.kind === 'changes') {
        const description = row.cells[3];
        expect(
          row.cells[1].translate === 'no' && description.lang === (lang === 'de' ? 'en' : null),
          `${where}: the revision is not marked as not to be translated, or the description does not carry its language`,
        );
        expect(
          !description.text.includes('Bruttobeitrag') || description.marked.includes('de:Bruttobeitrag'),
          `${where}: "Bruttobeitrag" in the description does not carry its language`,
        );
      }
      expect(
        row.cells.every((cell) => cell.shown && cell.box.left >= -0.5 && cell.box.right <= table.window + 0.5),
        `${where}: a cell is not shown or reaches beyond the window`,
      );
      const tops = new Set(row.cells.map((cell) => Math.round(cell.box.top)));
      if (!stacked) {
        expect(tops.size === 1 && table.display === 'table-row', `${where}: its cells do not stand in one line (${table.display})`);
      } else {
        expect(table.display === 'grid' && tops.size === 2, `${where}: it is no record of two lines (${table.display}, ${tops.size} lines)`);
        // Every cell stands on the line of its column name in the head
        // row and, in a four-column table, below it.
        const lineOf = (cells, at) => (Math.round(cells[at].box.top) > Math.min(...cells.map((cell) => Math.round(cell.box.top))) ? 2 : 1);
        expect(
          row.cells.every(
            (cell, at) =>
              lineOf(row.cells, at) === lineOf(table.head, at) &&
              (columns !== 4 || Math.abs(cell.box.left - table.head[at].box.left) < 1),
          ),
          `${where}: a cell does not stand under its column name`,
        );
      }
    });
    expect(
      table.box.left >= -0.5 && table.box.right <= table.window + 0.5,
      `${which}: it reaches beyond the window (${Math.round(table.box.right)} px in ${table.window} px)`,
    );
    if (stacked && columns === 4) {
      const names = new Set(table.head.map((cell) => Math.round(cell.box.top)));
      expect(
        names.size === 2 && table.head.every((cell) => cell.box.right <= table.window + 0.5 && cell.box.width > 0),
        `${which}: its head row is no record of two lines with every column name inside the window`,
      );
    }
  }
}

/** The line of the changes at one width: `stacked` says where its key must stand. */
async function checkLine(page, name, facts, lang, stacked) {
  const line = await page.evaluate(() => {
    const element = document.querySelector('main [data-change-line]');
    if (!element) return null;
    const figure = element.closest('[data-wide-figure]');
    const box = (part) => {
      const { left, right, top, bottom, width, height } = part.getBoundingClientRect();
      return { left, right, top, bottom, width, height };
    };
    const track = element.querySelector('[data-idea-track]');
    const text = (part) => part?.textContent.replace(/\s+/g, ' ').trim() ?? '';
    return {
      inFigure: figure !== null,
      figure: figure ? box(figure) : null,
      caption: text(figure?.querySelector(':scope > figcaption')),
      trace: box(element.querySelector('[data-change-trace]')),
      key: box(element.querySelector('[data-change-key]')),
      keys: Object.fromEntries(
        [...element.querySelectorAll('[data-change-key-text]')].map((part) => [part.dataset.changeKeyText, text(part)]),
      ),
      count: text(element.querySelector('[data-change-count]')),
      track: box(track),
      hidden: track.getAttribute('aria-hidden') === 'true',
      scaled: [element, track, ...element.querySelectorAll('[data-change-trace], [data-idea-square]')].some(
        (part) => getComputedStyle(part).transform !== 'none' || getComputedStyle(part).zoom !== '1',
      ),
      squares: [...track.querySelectorAll('[data-idea-square]')].map((square) => ({
        kind: square.dataset.ideaSquare,
        number: square.textContent.trim(),
        box: box(square),
        border: getComputedStyle(square).borderTopWidth,
      })),
      intervals: [...track.querySelectorAll('[data-idea-interval]')].map((interval) => ({
        name: interval.dataset.ideaInterval,
        label: text(interval),
        labelBox: box(interval.querySelector('span')),
        box: box(interval),
        border: getComputedStyle(interval).borderTopWidth,
        open: getComputedStyle(interval).borderBottomWidth,
      })),
      bars: [...(figure?.querySelectorAll('[data-bar-row]') ?? [])].map((row) => ({
        label: row.querySelector('.bar-revision').textContent.replace(/\s+/g, ' ').trim(),
        value: row.querySelector('.bar-value').textContent.trim(),
      })),
    };
  });
  if (!line) {
    failures.push(`${name}: no line of the changes`);
    return;
  }
  expect(line.inFigure, `${name}: the line of the changes stands outside a wide figure`);
  expect(line.hidden, `${name}: the squares are not hidden from assistive technology`);
  expect(!line.scaled, `${name}: the line of the changes is scaled`);
  checkSquares(name, line.squares, line.track, facts, true);
  expect(
    line.track.left >= line.figure.left && line.track.right <= line.figure.right,
    `${name}: the trace reaches beyond its figure`,
  );

  // The bracket: from the first to the last change of the interval, above them.
  const [first, last] = [facts.interval[0].number, facts.interval.at(-1).number];
  const [from, to] = [line.squares[first - 1]?.box, line.squares[last - 1]?.box];
  const [interval] = line.intervals;
  expect(
    line.intervals.length === 1 && interval.name === `${first}-${last}` && interval.label === `${first}–${last}`,
    `${name}: the brackets are [${line.intervals.map((entry) => `${entry.name} "${entry.label}"`)}], expected one for ${first}–${last}`,
  );
  if (interval && from && to) {
    expect(
      Math.abs(interval.box.left - (from.left - 2)) < 1 && Math.abs(interval.box.right - (to.right + 2)) < 1,
      `${name}: the bracket spans ${interval.box.left} to ${interval.box.right} px, the changes ${first} to ${last} stand from ${from.left} to ${to.right} px`,
    );
    expect(
      interval.box.bottom <= from.top && Number.parseFloat(interval.border) > 0 && Number.parseFloat(interval.open) === 0,
      `${name}: the bracket is not a border above its squares, open below`,
    );
    expect(
      interval.labelBox.bottom <= interval.box.top + 0.5 &&
        interval.labelBox.left >= line.figure.left &&
        interval.labelBox.right <= line.figure.right,
      `${name}: the numbers of the bracket do not stand above it, inside the figure`,
    );
  }

  // The words: the count, the key, the caption.
  const list = new Intl.ListFormat(lang === 'en' ? 'en-GB' : 'de', { type: 'conjunction' }).format(
    facts.deviating.map((entry) => String(entry.number)),
  );
  expect(
    line.count.startsWith(`${facts.revisions} `),
    `${name}: the line above the trace is "${line.count}", expected the count ${facts.revisions} first`,
  );
  expect(
    (line.keys.found ?? '').includes(list),
    `${name}: the key of the filled square is "${line.keys.found}", expected the numbers ${list}`,
  );
  expect(
    new RegExp(`\\b${first}\\b.*\\b${last}\\b`).test(line.keys.unresolved ?? ''),
    `${name}: the key of the bracket is "${line.keys.unresolved}", expected the numbers ${first} and ${last}`,
  );
  expect((line.keys.other ?? '').length > 10, `${name}: the key of the small square is "${line.keys.other}"`);
  expect(
    line.caption.includes(list) && new RegExp(`\\b${first}\\b.*\\b${last}\\b`).test(line.caption),
    `${name}: the caption does not name the revisions ${list} and the changes ${first} and ${last}`,
  );

  // Where the key stands.
  if (stacked) {
    expect(
      line.key.top >= line.trace.bottom - 0.5 && Math.abs(line.key.left - line.trace.left) < 1,
      `${name}: the line of the changes is not a stack of trace and key`,
    );
  } else {
    expect(
      line.key.left >= line.trace.right - 0.5 && line.key.top < line.trace.bottom && line.key.bottom > line.trace.top,
      `${name}: the key does not stand right of the trace`,
    );
  }

  // The bars below: the revisions of the search table with number and sum.
  expect(
    line.bars.length === facts.rows.length &&
      line.bars.every(
        (bar, index) =>
          bar.label === `${facts.deviating[index].number} · ${facts.rows[index].revision}` &&
          bar.value === facts.rows[index].sum,
      ),
    `${name}: the bars are [${line.bars.map((bar) => `${bar.label} ${bar.value}`)}], expected the rows of the search table`,
  );
}

/** The wide flow diagram at one width: `stacked` says how its boxes must stand. */
async function checkFlow(page, name, listed, stacked) {
  const flow = await page.evaluate(() => {
    const figure = document.querySelector('main [data-flow]');
    if (!figure) return null;
    const box = (element) => {
      const { left, right, top, bottom, width, height } = element.getBoundingClientRect();
      return { left, right, top, bottom, width, height };
    };
    const text = (element) => element?.textContent.replace(/\s+/g, ' ').trim() ?? '';
    const list = figure.querySelector('.flow-boxes');
    const end = figure.querySelector('.flow-end');
    const boxes = [...list.children];
    return {
      count: document.querySelectorAll('main [data-flow]').length,
      wide: figure.hasAttribute('data-wide-figure') && figure.tagName === 'FIGURE',
      figure: box(figure),
      counter: getComputedStyle(list).counterReset,
      ordered: list.tagName === 'OL' && boxes.every((item) => item.tagName === 'LI' && item.hasAttribute('data-flow-box')),
      boxes: boxes.map((item) => ({
        title: text(item.querySelector('.flow-title')),
        sub: item.querySelector('.flow-sub') !== null,
        number: getComputedStyle(item, '::before').content,
        // The computed content names the counter, not its value: the box
        // must also count it up, and the list must start it.
        counted: getComputedStyle(item).counterIncrement,
        size: Number.parseFloat(getComputedStyle(item.querySelector('.flow-title')).fontSize),
        border: getComputedStyle(item).borderTopStyle,
        box: box(item),
      })),
      end: { text: text(end), box: box(end), padHidden: end.querySelector('.flow-pad')?.getAttribute('aria-hidden') === 'true' },
      scaled: [figure, list, end, ...boxes].some(
        (part) => getComputedStyle(part).transform !== 'none' || getComputedStyle(part).zoom !== '1',
      ),
      // The parts as text beside the diagram: the names of the first row list.
      rows: [...(document.querySelector('main [data-row-list]')?.querySelectorAll(':scope > [data-row] .row-name') ?? [])].map(text),
    };
  });
  if (!flow) {
    failures.push(`${name}: no flow diagram`);
    return;
  }
  expect(flow.count === 1 && flow.wide, `${name}: the page holds ${flow.count} flow diagrams, expected one wide one (FlowDiagram with "wide")`);
  expect(flow.ordered, `${name}: the boxes of the flow diagram are no ordered list`);
  const titles = flow.boxes.map((entry) => entry.title);
  expect(
    JSON.stringify(titles) === JSON.stringify(listed.boxes),
    `${name}: the boxes of the flow diagram are [${titles}], expected [${listed.boxes}] (prosePages in scripts/check-prose.mjs)`,
  );
  expect(
    JSON.stringify(flow.rows) === JSON.stringify(titles),
    `${name}: the first row list names [${flow.rows}], the flow diagram [${titles}]: the diagram does not stand as text beside itself`,
  );
  expect(
    flow.end.text === listed.end && flow.end.padHidden,
    `${name}: the trace ends in "${flow.end.text}", expected "${listed.end}" after a pad hidden from assistive technology`,
  );
  expect(!flow.scaled, `${name}: the flow diagram is scaled`);
  expect(
    /\bflow\b/.test(flow.counter),
    `${name}: the list of the flow diagram does not start the counter of its boxes (counter-reset: ${flow.counter})`,
  );
  flow.boxes.forEach((entry, index) => {
    const which = `${name}: box ${index + 1} of the flow diagram`;
    const previous = flow.boxes[index - 1];
    expect(
      (entry.number.includes('counter(flow)') || entry.number === `"${index + 1}"`) && /\bflow 1\b/.test(entry.counted),
      `${which} carries no number (content: ${entry.number}, counter-increment: ${entry.counted})`,
    );
    expect(!entry.sub && entry.border === 'solid', `${which} holds a mono line or is not outlined`);
    expect(Math.abs(entry.size - 13) < 0.1, `${which}: its title is ${entry.size} px, not 13 px`);
    expect(
      entry.box.left >= flow.figure.left && entry.box.right <= flow.figure.right + 0.05,
      `${which} reaches beyond its figure`,
    );
    if (!previous) return;
    if (stacked) {
      expect(
        entry.box.top >= previous.box.bottom &&
          Math.abs(entry.box.left - previous.box.left) < 1 &&
          Math.abs(entry.box.width - previous.box.width) < 1,
        `${which} does not stand below box ${index}, at its width`,
      );
    } else {
      expect(
        entry.box.left >= previous.box.right && Math.abs(entry.box.top - previous.box.top) < 1,
        `${which} does not stand right of box ${index}, in its row`,
      );
    }
  });
  const last = flow.boxes.at(-1)?.box;
  if (last) {
    expect(
      stacked
        ? flow.end.box.top >= last.bottom
        : flow.end.box.left >= last.right && flow.end.box.top < last.bottom && flow.end.box.bottom > last.top,
      `${name}: the end of the trace does not stand ${stacked ? 'below' : 'right of'} the last box`,
    );
    expect(
      flow.end.box.left >= flow.figure.left && flow.end.box.right <= flow.figure.right + 0.05,
      `${name}: the end of the trace reaches beyond its figure`,
    );
  }
}

/**
 * Row lists: numbered rows, a hairline above each and below the list; the
 * code name and the tag of a row. `counts` names how many rows the page
 * holds and, where its entry says so, how many code names and tags.
 */
async function checkRowLists(page, name, counts, stacked) {
  const lists = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-row-list]')].map((list) => ({
      ordered: list.tagName === 'OL',
      plain: list.hasAttribute('data-plain'),
      label: (() => {
        const label = list.previousElementSibling?.matches('[data-row-list-label]') ? list.previousElementSibling : null;
        if (!label) return null;
        const style = getComputedStyle(label);
        return {
          text: label.textContent.trim(),
          name: list.getAttribute('aria-label'),
          size: Number.parseFloat(style.fontSize),
          upper: style.textTransform,
          mono: style.fontFamily.includes('JetBrains Mono'),
        };
      })(),
      closed: getComputedStyle(list).borderBottomWidth,
      rows: [...list.querySelectorAll(':scope > [data-row]')].map((row) => {
        const box = (element) => {
          const { left, right, top, bottom } = element.getBoundingClientRect();
          return { left, right, top, bottom };
        };
        const title = row.querySelector('.row-name');
        const codes = [...(title?.querySelectorAll('code') ?? [])];
        const code = codes[0];
        const tag = row.querySelector('[data-row-tag]');
        const style = (element) => getComputedStyle(element);
        return {
          number: getComputedStyle(row, '::before').content,
          rule: getComputedStyle(row).borderTopWidth,
          name: title?.textContent.trim() ?? '',
          codes: codes.length,
          code: code && {
            text: code.textContent,
            // After the name in plain words, which is not empty.
            after: (title.firstElementChild?.textContent.trim() ?? '') !== '' && title.lastElementChild === code,
            translate: code.getAttribute('translate'),
            weight: style(code).fontWeight,
            mono: style(code).fontFamily.includes('JetBrains Mono'),
          },
          tag: tag && {
            text: tag.textContent.trim(),
            size: Number.parseFloat(style(tag).fontSize),
            upper: style(tag).textTransform,
            border: `${style(tag).borderTopWidth} ${style(tag).borderTopStyle}`,
            mono: style(tag).fontFamily.includes('JetBrains Mono'),
            box: box(tag),
            text_box: box(row.querySelector('.row-text')),
            row: box(row),
          },
        };
      }),
    })),
  );
  const rows = lists.flatMap((list) => list.rows);
  if (!stacked) expect(rows.length === counts.rows, `${name}: ${rows.length} rows in row lists, expected ${counts.rows}`);
  for (const [part, held] of [
    ['codes', rows.filter((row) => row.code).length],
    ['tags', rows.filter((row) => row.tag).length],
  ]) {
    if (counts[part] !== undefined) {
      expect(held === counts[part], `${name}: ${held} rows with ${part === 'codes' ? 'a code name' : 'a tag'}, expected ${counts[part]} (prosePages in scripts/check-prose.mjs)`);
    }
  }
  lists.forEach((list, at) => {
    expect(
      list.ordered !== list.plain && list.closed === '1px',
      `${name}: row list ${at + 1} is no ordered list, or no unordered list without numbers, with a hairline below`,
    );
    if (list.label) {
      const { label } = list;
      expect(
        label.text !== '' && label.name === label.text && Math.abs(label.size - 11) < 0.1 && label.upper === 'uppercase' && label.mono,
        `${name}: the label "${label.text}" of row list ${at + 1} is no small mono label in capitals that names its list (${label.size} px, ${label.upper}, name "${label.name}")`,
      );
    }
    list.rows.forEach((row, index) => {
      const which = `${name}: row ${index + 1} of row list ${at + 1}`;
      expect(
        list.plain
          ? row.number === 'none'
          : row.number.includes('counter(row)') || row.number === `"${index + 1}"`,
        list.plain ? `${which} of a list without numbers carries one (${row.number})` : `${which} carries no number (${row.number})`,
      );
      expect(row.rule === '1px' && row.name !== '', `${which} has no hairline or no name`);
      if (row.code) {
        expect(
          row.codes === 1 && row.code.after && row.code.text.trim() !== '',
          `${which}: its code name does not follow a name in plain words, as the one inline code of the name`,
        );
        expect(
          row.code.translate === 'no' && row.code.weight === '400' && row.code.mono,
          `${which}: its code name "${row.code.text}" is translated, or not mono in weight 400 (translate: ${row.code.translate}, weight: ${row.code.weight})`,
        );
      }
      if (row.tag) {
        const { tag } = row;
        expect(
          tag.text !== '' && Math.abs(tag.size - 11) < 0.1 && tag.upper === 'uppercase' && tag.border === '1px solid' && tag.mono,
          `${which}: its tag "${tag.text}" is no small mono label in capitals with a hairline border (${tag.size} px, ${tag.upper}, ${tag.border})`,
        );
        expect(
          stacked
            ? tag.box.top >= tag.text_box.bottom && tag.box.left >= tag.text_box.left - 0.5
            : tag.box.left >= tag.text_box.right - 0.5 && tag.box.top < tag.text_box.bottom && Math.abs(tag.box.right - tag.row.right) < 1,
          `${which}: its tag does not stand ${stacked ? 'below the text' : 'at the right end of the row'}`,
        );
        expect(tag.box.right <= tag.row.right + 0.5, `${which}: its tag reaches beyond the row`);
      }
    });
  });
}

/** Sub-headings: level-3 headings of 18 px, each after a section heading. */
async function checkSubHeadings(page, name, expected) {
  const headings = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-sub-heading]')].map((heading) => {
      const first = document.querySelector('main h2[data-section-heading]');
      const style = getComputedStyle(heading);
      return {
        text: heading.textContent.trim(),
        level: heading.tagName,
        size: Number.parseFloat(style.fontSize),
        weight: style.fontWeight,
        above: style.marginTop,
        block: heading.parentElement === document.querySelector('main'),
        after: Boolean(first && first.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING),
      };
    }),
  );
  if (expected !== undefined) {
    expect(headings.length === expected, `${name}: ${headings.length} sub-headings, expected ${expected} (prosePages in scripts/check-prose.mjs)`);
  }
  for (const heading of headings) {
    const which = `${name}: the sub-heading "${heading.text}"`;
    expect(heading.text !== '' && heading.level === 'H3' && heading.block, `${which} is no level-3 heading between the blocks of the page`);
    expect(
      Math.abs(heading.size - 18) < 0.1 && heading.weight === '600' && heading.above === '32px',
      `${which} is ${heading.size} px in weight ${heading.weight} with ${heading.above} above, expected 18 px, 600 and 32px`,
    );
    expect(heading.after, `${which} stands before the first section heading`);
  }
}

/** The connection figure: three boxes, one of them dashed, one label. */
async function checkConnection(page, name, listed, stacked) {
  const found = await page.evaluate(() => {
    const figures = [...document.querySelectorAll('main [data-connection]')];
    const figure = figures[0];
    if (!figure) return null;
    const box = (element) => {
      const { left, right, top, bottom, width, height } = element.getBoundingClientRect();
      return { left, right, top, bottom, width, height };
    };
    const text = (element) => element?.textContent.replace(/\s+/g, ' ').trim() ?? '';
    const list = figure.querySelector('.connection-boxes');
    const boxes = [...(list?.children ?? [])];
    const labels = [...figure.querySelectorAll('[data-connection-label]')];
    const label = labels[0];
    return {
      count: figures.length,
      wide: figure.tagName === 'FIGURE' && figure.hasAttribute('data-wide-figure'),
      figure: box(figure),
      ordered: list?.tagName === 'OL' && boxes.every((item) => item.tagName === 'LI' && item.hasAttribute('data-connection-box')),
      caption: text(figure.querySelector(':scope > figcaption')),
      boxes: boxes.map((item) => {
        const style = getComputedStyle(item);
        return {
          title: text(item.querySelector('.flow-title')),
          state: text(item.querySelector('.connection-state')),
          sub: text(item.querySelector('.flow-sub')),
          size: Number.parseFloat(getComputedStyle(item.querySelector('.flow-title')).fontSize),
          // The style alone: a border of 1.5 px is drawn, and reported, as
          // whole device pixels.
          border: style.borderTopStyle,
          colour: style.borderTopColor,
          built: item.hasAttribute('data-built'),
          // The trace to the next box and the square it ends in.
          trace: getComputedStyle(item, '::after').content !== 'none',
          square: getComputedStyle(item, '::before').content !== 'none',
          hidden: item.getAttribute('aria-hidden'),
          box: box(item),
        };
      }),
      labels: labels.length,
      label: label && {
        text: text(label),
        first: label.parentElement === boxes[0],
        colour: getComputedStyle(label).color,
        size: Number.parseFloat(getComputedStyle(label).fontSize),
        mono: getComputedStyle(label).fontFamily.includes('JetBrains Mono'),
        box: box(label),
      },
      scaled: [figure, list, ...boxes, ...labels].some(
        (part) => part && (getComputedStyle(part).transform !== 'none' || getComputedStyle(part).zoom !== '1'),
      ),
    };
  });
  if (!found) {
    failures.push(`${name}: no connection figure`);
    return;
  }
  expect(found.count === 1 && found.wide, `${name}: the page holds ${found.count} connection figures, expected one that is a wide figure`);
  expect(found.ordered, `${name}: the boxes of the connection figure are no ordered list`);
  expect(found.caption.length > 40, `${name}: the connection figure has no caption that says what it shows ("${found.caption}")`);
  const titles = found.boxes.map((entry) => entry.title);
  expect(
    JSON.stringify(titles) === JSON.stringify(listed.boxes),
    `${name}: the boxes of the connection figure are [${titles}], expected [${listed.boxes}] (prosePages in scripts/check-prose.mjs)`,
  );
  const dashed = found.boxes.filter((entry) => entry.border === 'dashed').map((entry) => entry.title);
  expect(
    JSON.stringify(dashed) === JSON.stringify([listed.built]) &&
      found.boxes.every((entry) => entry.built === (entry.title === listed.built)) &&
      found.boxes.every((entry) => entry.title === listed.built || entry.border === 'solid'),
    `${name}: the dashed boxes of the connection figure are [${dashed}], expected "${listed.built}" alone, the others solid (${found.boxes.map((entry) => entry.border).join(', ')})`,
  );
  expect(!found.scaled, `${name}: the connection figure is scaled`);
  expect(
    found.labels === 1 && found.label.text === listed.label && found.label.first,
    `${name}: the connection figure carries ${found.labels} labels (${found.label?.text}), expected "${listed.label}" alone, on the first trace`,
  );
  if (found.label) {
    expect(
      found.label.colour === RING && Math.abs(found.label.size - 11) < 0.1 && found.label.mono,
      `${name}: the label of the trace is not mono 11 px in teal-text (${found.label.size} px, ${found.label.colour})`,
    );
  }
  found.boxes.forEach((entry, index) => {
    const which = `${name}: box ${index + 1} of the connection figure`;
    const previous = found.boxes[index - 1];
    const last = index === found.boxes.length - 1;
    expect(entry.state !== '' && entry.sub !== '', `${which} lacks one of its two small lines`);
    expect(
      Math.abs(entry.size - 13) < 0.1 && entry.colour === 'rgb(30, 37, 71)' && entry.hidden === null,
      `${which}: its title is ${entry.size} px, its outline ${entry.colour}, or it is hidden from assistive technology`,
    );
    expect(entry.trace === !last && entry.square === !last, `${which}: ${last ? 'a trace leaves the last box' : 'no trace with its square leads to the next box'}`);
    expect(
      entry.box.left >= found.figure.left && entry.box.right <= found.figure.right + 0.05,
      `${which} reaches beyond its figure`,
    );
    if (!previous) return;
    if (stacked) {
      expect(
        entry.box.top >= previous.box.bottom &&
          Math.abs(entry.box.left - previous.box.left) < 1 &&
          Math.abs(entry.box.width - previous.box.width) < 1,
        `${which} does not stand below box ${index}, at its width`,
      );
    } else {
      expect(
        entry.box.left >= previous.box.right && Math.abs(entry.box.top - previous.box.top) < 1 && Math.abs(entry.box.height - previous.box.height) < 1,
        `${which} does not stand right of box ${index}, in its row and at its height`,
      );
    }
  });
  const [first, second] = found.boxes;
  if (found.label && first && second) {
    const label = found.label.box;
    expect(
      stacked
        ? label.top >= first.box.bottom && label.bottom <= second.box.top
        : label.left >= first.box.right - 0.5 && label.right <= second.box.left + 0.5 && label.bottom <= (first.box.top + first.box.bottom) / 2,
      `${name}: the label of the trace does not stand ${stacked ? 'between the first two boxes of the stack' : 'between the first two boxes, above the trace'}`,
    );
    expect(label.left >= found.figure.left && label.right <= found.figure.right + 0.05, `${name}: the label of the trace reaches beyond its figure`);
  }
}

/** The yardstick box: border, tag, the line with the number, the text. */
async function checkYardsticks(page, name, expected, stacked) {
  const boxes = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-yardstick]')].map((box) => {
      const style = getComputedStyle(box);
      const tag = box.querySelector('.yardstick-tag');
      const size = box.querySelector('.yardstick-size');
      const text = box.querySelector('.yardstick-text');
      return {
        block: box.parentElement === document.querySelector('main'),
        border: `${style.borderTopWidth} ${style.borderTopStyle} ${style.borderTopColor}`,
        padding: `${style.paddingTop} ${style.paddingRight}`,
        width: box.getBoundingClientRect().width,
        tag: tag && { text: tag.textContent.trim(), colour: getComputedStyle(tag).color, upper: getComputedStyle(tag).textTransform },
        size: size && {
          text: size.textContent.replace(/\s+/g, ' ').trim(),
          number: size.querySelector('[data-yardstick-lines]')?.textContent.trim() ?? '',
          px: Number.parseFloat(getComputedStyle(size).fontSize),
          weight: getComputedStyle(size).fontWeight,
        },
        text: text?.textContent.trim() ?? '',
        codes: [...(text?.querySelectorAll('code') ?? [])].map((code) => code.getAttribute('translate')),
        heading: box.querySelector('h1, h2, h3, h4') !== null,
      };
    }),
  );
  expect(boxes.length === expected, `${name}: ${boxes.length} yardstick boxes, expected ${expected} (prosePages in scripts/check-prose.mjs)`);
  boxes.forEach((box, index) => {
    const which = `${name}: yardstick box ${index + 1}`;
    expect(box.block && box.width <= 820.5, `${which} is no block of the page of at most 820 px (${box.width} px)`);
    expect(box.border === '1px solid rgb(30, 37, 71)', `${which}: its border is "${box.border}", expected 1 px in navy`);
    expect(box.padding === (stacked ? '16px 16px' : '20px 24px'), `${which}: its padding is ${box.padding}`);
    expect(
      Boolean(box.tag) && box.tag.text !== '' && box.tag.colour === RING && box.tag.upper === 'uppercase',
      `${which}: no tag in teal-text and capitals (${box.tag?.text}, ${box.tag?.colour})`,
    );
    expect(
      Boolean(box.size) && /^\d/.test(box.size.number) && box.size.text.startsWith(`${box.size.number} `) && box.size.text.length > box.size.number.length + 3 &&
        Math.abs(box.size.px - 22) < 0.1 && box.size.weight === '600',
      `${which}: its line "${box.size?.text}" does not begin with the number of lines, in 22 px and weight 600`,
    );
    expect(
      box.text.length > 20 && box.codes.length > 0 && box.codes.every((translate) => translate === 'no'),
      `${which}: its text names no file as inline code that is not translated`,
    );
    expect(!box.heading, `${which} holds a heading`);
  });
}

/** Code excerpts: head row, the code as a named region, caption, no copy button. */
async function checkExcerpts(page, name, expected, stacked) {
  const read = () =>
    page.evaluate(() =>
      [...document.querySelectorAll('main [data-code-excerpt]')].map((figure) => {
        const head = figure.querySelector('[data-code-excerpt-head]');
        const pre = figure.querySelector('pre');
        const code = pre?.querySelector('code');
        const parts = [...(head?.children ?? [])];
        const style = pre && getComputedStyle(pre);
        return {
          isFigure: figure.tagName === 'FIGURE',
          width: figure.getBoundingClientRect().width,
          file: figure.dataset.file,
          head: head && {
            parts: parts.map((part) => part.textContent.replace(/\s+/g, ' ').trim()),
            fileKept: parts[0]?.getAttribute('translate'),
            ground: getComputedStyle(head).backgroundColor,
            colour: getComputedStyle(head).color,
            size: Number.parseFloat(getComputedStyle(head).fontSize),
            // Left and right in one row, or one below the other where it wraps.
            apart: parts.length === 2 && (parts[1].getBoundingClientRect().left >= parts[0].getBoundingClientRect().right || parts[1].getBoundingClientRect().top >= parts[0].getBoundingClientRect().bottom),
            joined: pre ? Math.abs(head.getBoundingClientRect().bottom - pre.getBoundingClientRect().top) < 0.5 : false,
          },
          region: pre && {
            role: pre.getAttribute('role'),
            label: pre.getAttribute('aria-label') ?? '',
            stop: pre.tabIndex === 0,
            translate: pre.getAttribute('translate'),
            overflow: style.overflowX,
            space: style.whiteSpace,
            top: style.borderTopWidth,
            ligatures: style.fontVariantLigatures,
            plain: code !== null && code.children.length === 0 && pre.children.length === 1,
            lines: code?.textContent.split('\n').length ?? 0,
            scroll: pre.scrollWidth,
            client: pre.clientWidth,
            left: pre.scrollLeft,
            focused: document.activeElement === pre,
            ring: `${style.outlineWidth} ${style.outlineStyle} ${style.outlineColor}`,
          },
          caption: figure.querySelector(':scope > figcaption')?.textContent.trim() ?? '',
          buttons: figure.querySelectorAll('button, [data-copy], [data-copy-button]').length,
        };
      }),
    );
  const excerpts = await read();
  expect(excerpts.length === expected, `${name}: ${excerpts.length} code excerpts, expected ${expected} (prosePages in scripts/check-prose.mjs)`);
  for (const [index, excerpt] of excerpts.entries()) {
    const which = `${name}: code excerpt ${index + 1}`;
    expect(excerpt.isFigure && excerpt.caption !== '' && excerpt.width <= 820.5, `${which} is no figure with a caption, at most 820 px wide`);
    expect(
      Boolean(excerpt.head) && excerpt.head.parts.length === 2 && excerpt.head.parts[0] === excerpt.file && excerpt.head.fileKept === 'no' && excerpt.head.apart,
      `${which}: its head row does not hold the file and, right of or below it, lines and release ([${excerpt.head?.parts}])`,
    );
    if (excerpt.head) {
      expect(
        excerpt.head.ground === 'rgb(245, 247, 250)' && excerpt.head.colour === 'rgb(58, 64, 96)' && Math.abs(excerpt.head.size - 12) < 0.1 && excerpt.head.joined,
        `${which}: its head row is not 12 px in text-secondary on bg-subtle, joined to the code (${excerpt.head.size} px, ${excerpt.head.colour}, ${excerpt.head.ground})`,
      );
    }
    expect(excerpt.buttons === 0, `${which} holds a button or a command to copy`);
    const { region } = excerpt;
    if (!region) {
      failures.push(`${which} holds no code`);
      continue;
    }
    expect(
      region.role === 'region' && region.stop && region.label.startsWith(`${excerpt.file}, `),
      `${which}: its code is no region that takes focus and is named after its file (role: ${region.role}, name: "${region.label}")`,
    );
    expect(
      region.translate === 'no' && region.plain && region.lines > 0 && region.ligatures === 'none',
      `${which}: its code is translated, coloured or marked up, or has ligatures`,
    );
    expect(
      region.overflow === 'auto' && region.space === 'pre' && region.top === '0px',
      `${which}: its code wraps, does not scroll inside its box, or has a top border below the head row (${region.overflow}, ${region.space}, ${region.top})`,
    );
    // Focus by keyboard shows the ring; where the code is wider than its
    // box, the arrow key scrolls it.
    const pre = page.locator('main [data-code-excerpt] pre').nth(index);
    await pre.scrollIntoViewIfNeeded();
    await pre.evaluate((element) => element.previousElementSibling?.scrollIntoView());
    await page.keyboard.press('Tab');
    await pre.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    const focused = (await read())[index].region;
    expect(
      focused.focused && focused.ring === `2px solid ${RING}`,
      `${which}: Tab does not reach its code, or it shows no focus ring (${focused.ring})`,
    );
    if (stacked) {
      expect(region.scroll > region.client, `${which}: its code is not wider than its box at this width (${region.scroll} px in ${region.client} px); the check of the sideways scroll needs a long line`);
      await page.keyboard.press('ArrowRight');
      // The browser scrolls after the key, not with it.
      const scrolled = await pre
        .evaluate((element) => new Promise((resolve) => {
          const until = performance.now() + 2000;
          const look = () => (element.scrollLeft > 0 || performance.now() > until ? resolve(element.scrollLeft) : requestAnimationFrame(look));
          look();
        }));
      expect(scrolled > 0, `${which}: the arrow key does not scroll its code sideways`);
    }
  }
}

/** The path block: the stages and pages of the register. */
async function checkPathBlock(page, name, entry) {
  const stages = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-path-block] > li')].map((stage) => ({
      label: stage.querySelector('.path-stage')?.textContent.replace(/\s+/g, ' ').trim(),
      name: stage.querySelector('.path-name')?.textContent.trim(),
      sentence: [...stage.querySelector('.path-text').childNodes]
        .filter((node) => node.nodeName !== 'A')
        .map((node) => node.textContent)
        .join('')
        .replace(/[\s,]+$/, '')
        .trim(),
      links: [...stage.querySelectorAll('.path-text a')].map((link) => ({
        name: link.textContent.trim(),
        address: link.getAttribute('href'),
        underline: getComputedStyle(link).textDecorationLine,
      })),
    })),
  );
  expect(
    stages.length === site.stages.length,
    `${name}: the path block holds ${stages.length} stages, the register ${site.stages.length}`,
  );
  site.stages.forEach((stage, index) => {
    const shown = stages[index];
    if (!shown) return;
    const which = `${name}: path block, stage ${stage.number}`;
    expect(
      shown.label === `${site.texts[entry.lang].stage} ${stage.number}` && shown.name === stage.name[entry.lang],
      `${which}: it is "${shown.label}", "${shown.name}"`,
    );
    expect(shown.sentence.length > 10, `${which}: no sentence ("${shown.sentence}")`);
    const expected = site
      .pagesOf(stage)
      .map((page) => ({ name: page.name[entry.lang], address: `${BASE}${site.pagePath(page, entry.lang)}` }))
      .filter((link) => link.address !== entry.address);
    expect(
      JSON.stringify(shown.links.map(({ name, address }) => ({ name, address }))) === JSON.stringify(expected),
      `${which}: its links are [${shown.links.map((link) => `${link.name} ${link.address}`)}], the register gives [${expected.map((link) => `${link.name} ${link.address}`)}]`,
    );
    expect(
      shown.links.every((link) => link.underline.includes('underline')),
      `${which}: a link is not underlined`,
    );
  });
}

async function checkProsePage(browser, origin, entry, listed, facts) {
  const at = (viewport) => `${entry.address} (${viewport.width} px)`;
  const counts = { rows: listed.rows ?? 0, codes: listed.codes, tags: listed.tags };

  // Desktop.
  {
    const { context, page } = await open(browser, origin, entry, DESKTOP);
    const name = at(DESKTOP);
    await checkHeadings(page, name, listed);
    const figures = await checkFigures(page, name);
    expect(!(listed.idea || listed.line || listed.flow || listed.connection) || figures > 0, `${name}: no wide figure`);
    if (listed.idea) await checkIdea(page, name, facts, entry.lang, false);
    if (listed.tables) await checkDemoTables(page, name, facts, entry.lang, false);
    if (listed.line) await checkLine(page, name, facts, entry.lang, false);
    if (listed.flow) await checkFlow(page, name, listed.flow[entry.lang], false);
    if (listed.connection) await checkConnection(page, name, listed.connection[entry.lang], false);
    await checkRowLists(page, name, counts, false);
    await checkSubHeadings(page, name, listed.subHeadings);
    await checkYardsticks(page, name, listed.yardsticks ?? 0, false);
    await checkExcerpts(page, name, listed.excerpts ?? 0, false);
    if (listed.path) await checkPathBlock(page, name, entry);
    await checkNoMotion(page, name);
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    await context.close();
  }

  // Phone, and the narrowest width: the figures as a stack, the tables as records.
  for (const viewport of [PHONE, NARROW]) {
    const { context, page } = await open(browser, origin, entry, viewport);
    const name = at(viewport);
    await checkFigures(page, name);
    if (listed.idea) await checkIdea(page, name, facts, entry.lang, true);
    if (listed.tables) await checkDemoTables(page, name, facts, entry.lang, true);
    if (listed.line) await checkLine(page, name, facts, entry.lang, true);
    if (listed.flow) await checkFlow(page, name, listed.flow[entry.lang], true);
    if (listed.connection) await checkConnection(page, name, listed.connection[entry.lang], true);
    await checkRowLists(page, name, counts, true);
    await checkYardsticks(page, name, listed.yardsticks ?? 0, true);
    await checkExcerpts(page, name, listed.excerpts ?? 0, true);
    await checkNoSidewaysScroll(page, name);
    if (viewport === PHONE) await checkAxe(page, name);
    await context.close();
  }

  if (listed.counterpart) await checkCounterpart(browser, origin, entry, listed.counterpart);

  // A page of prose holds platform switches only where its entry names them.
  const switches = listed.switches ?? { places: [], plain: 0 };
  await checkSwitches(browser, origin, entry, {
    ...switches,
    places: switches.places.map((place) => (typeof place === 'string' ? place : place[entry.lang])),
  });
}

const { origin: reported, stop } = startPreview();
let browser;
let checked = 0;
try {
  const facts = await checkExample();
  const origin = await reported;
  browser = await chromium.launch();

  // Which pages are pages of prose: those that hold section headings or list
  // sections in the chapter tree (frontmatter `sections`).
  const found = [];
  {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    for (const entry of pages) {
      await page.goto(`${origin}${entry.address}`);
      const marks = await page.locator('main [data-section-heading], #chapters [data-tree-sections]').count();
      if (marks > 0) found.push(entry);
    }
    await context.close();
  }
  for (const id of Object.keys(prosePages)) {
    for (const lang of site.languages) {
      expect(
        found.some((entry) => entry.id === id && entry.lang === lang),
        `the page "${id}" (${lang}) holds no section headings`,
      );
    }
  }
  for (const entry of found) {
    const listed = prosePages[entry.id];
    if (!listed) {
      failures.push(`${entry.address}: a page of prose without an entry in prosePages (scripts/check-prose.mjs)`);
      continue;
    }
    // An error on one page is a failure of that page; the others still run.
    try {
      await checkProsePage(browser, origin, entry, listed, facts[entry.lang]);
      checked += 1;
    } catch (error) {
      failures.push(`${entry.address}: ${error.stack ?? error.message}`);
    }
  }
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(`the facts of the example and ${checked} pages of prose pass`);
