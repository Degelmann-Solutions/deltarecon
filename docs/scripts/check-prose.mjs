// Checks the pages of prose of the built site in Chromium: section headings,
// the wide figure with the idea figure and its bars, the row list, the path
// block. Run after the build: `npm run check`.
//
// A page of prose is a page that holds section headings. What a page must
// show stands in `prosePages` below, so that a changed anchor fails here
// until both places agree. A page of prose without an entry there fails.
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
//     page holds no "on this page" list;
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
//   - a row list numbers its rows and closes with a hairline;
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
  expectations,
  loadExample,
  loadPages,
  loadRegister,
  loadRelease,
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
};

/** The widths the idea figure is looked at: side by side, then as a stack. */
const NARROW = { width: 320, height: 844 };
const PLATFORMS = ['windows', 'linux'];

const site = await loadRegister();
const pages = await loadPages();
const { exampleFacts, regressionTable, changeTable, unresolvedInterval } = await loadExample();
const release = await loadRelease();
const { failures, expect, report } = expectations('check-prose');
const { checkAxe, checkNoSidewaysScroll } = pageChecks({ failures, expect });

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

async function open(browser, origin, entry, viewport, anchor = '') {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await page.goto(`${origin}${entry.address}${anchor}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('html[data-menu]');
  return { context, page };
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
  // No "on this page" list: no link of the page but a heading itself leads to a section.
  const others = await page.evaluate(
    (ids) =>
      [...document.querySelectorAll('a[href^="#"]')]
        .filter((link) => ids.includes(link.getAttribute('href').slice(1)) && !link.closest('h2'))
        .map((link) => link.getAttribute('href')),
    anchors,
  );
  expect(others.length === 0, `${name}: links to sections outside their headings: [${others}]`);
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

/** Row lists: numbered rows, a hairline above each and below the list. */
async function checkRowLists(page, name, expected) {
  const lists = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-row-list]')].map((list) => ({
      ordered: list.tagName === 'OL',
      closed: getComputedStyle(list).borderBottomWidth,
      rows: [...list.querySelectorAll(':scope > [data-row]')].map((row) => ({
        number: getComputedStyle(row, '::before').content,
        rule: getComputedStyle(row).borderTopWidth,
        name: row.querySelector('.row-name')?.textContent.trim() ?? '',
      })),
    })),
  );
  const rows = lists.flatMap((list) => list.rows).length;
  expect(rows === expected, `${name}: ${rows} rows in row lists, expected ${expected}`);
  lists.forEach((list, at) => {
    expect(list.ordered && list.closed === '1px', `${name}: row list ${at + 1} is no ordered list with a hairline below`);
    list.rows.forEach((row, index) => {
      expect(
        row.number.includes('counter(row)') || row.number === `"${index + 1}"`,
        `${name}: row ${index + 1} of row list ${at + 1} carries no number (${row.number})`,
      );
      expect(row.rule === '1px' && row.name !== '', `${name}: row ${index + 1} of row list ${at + 1} has no hairline or no name`);
    });
  });
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

/** Nothing in the content moves. */
async function checkNoMotion(page, name) {
  const moving = await page.evaluate(() =>
    [...document.querySelectorAll('main *')]
      .filter((element) => {
        const style = getComputedStyle(element);
        return (
          style.animationName !== 'none' ||
          style.transitionDuration.split(',').some((duration) => Number.parseFloat(duration) > 0)
        );
      })
      .map((element) => element.className || element.tagName),
  );
  expect(moving.length === 0, `${name}: these parts of the content move: ${[...new Set(moving)].join(', ')}`);
}

async function checkProsePage(browser, origin, entry, listed, facts) {
  const at = (viewport) => `${entry.address} (${viewport.width} px)`;

  // Desktop.
  {
    const { context, page } = await open(browser, origin, entry, DESKTOP);
    const name = at(DESKTOP);
    await checkHeadings(page, name, listed);
    const figures = await checkFigures(page, name);
    expect(!(listed.idea || listed.line) || figures > 0, `${name}: no wide figure`);
    if (listed.idea) await checkIdea(page, name, facts, entry.lang, false);
    if (listed.tables) await checkDemoTables(page, name, facts, entry.lang, false);
    if (listed.line) await checkLine(page, name, facts, entry.lang, false);
    await checkRowLists(page, name, listed.rows ?? 0);
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
    await checkNoSidewaysScroll(page, name);
    if (viewport === PHONE) await checkAxe(page, name);
    await context.close();
  }

  if (listed.counterpart) await checkCounterpart(browser, origin, entry, listed.counterpart);
}

const { origin: reported, stop } = startPreview();
let browser;
let checked = 0;
try {
  const facts = await checkExample();
  const origin = await reported;
  browser = await chromium.launch();

  // Which pages are pages of prose: those that hold section headings.
  const found = [];
  {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    for (const entry of pages) {
      await page.goto(`${origin}${entry.address}`);
      if ((await page.locator('main [data-section-heading]').count()) > 0) found.push(entry);
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
