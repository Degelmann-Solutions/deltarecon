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
// lacks one fails the build.
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
};

/** The widths the idea figure is looked at: side by side, then as a stack. */
const NARROW = { width: 320, height: 844 };
const PLATFORMS = ['windows', 'linux'];

const site = await loadRegister();
const pages = await loadPages();
const { exampleFacts } = await loadExample();
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
  }
  return facts;
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
  expect(
    idea.squares.length === facts.revisions,
    `${name}: ${idea.squares.length} squares, the capture has ${facts.revisions} revisions`,
  );
  const numbers = facts.deviating.map((entry) => entry.number);
  idea.squares.forEach((square, index) => {
    const number = index + 1;
    const marked = numbers.includes(number);
    const size = marked ? 11 : 7;
    expect(
      square.kind === (marked ? 'deviating' : 'plain') && square.number === (marked ? String(number) : ''),
      `${name}: square ${number} is "${square.kind}" with the number "${square.number}"`,
    );
    expect(
      Math.abs(square.box.width - size) < 0.1 && Math.abs(square.box.height - size) < 0.1,
      `${name}: square ${number} is ${square.box.width} × ${square.box.height} px, not ${size} × ${size}`,
    );
    expect(Number.parseFloat(square.border) > 0, `${name}: square ${number} is not drawn as a border`);
    const previous = idea.squares[index - 1];
    expect(
      !previous || square.box.left >= previous.box.right - 0.05,
      `${name}: square ${number} overlaps square ${number - 1}`,
    );
    expect(
      square.box.left >= idea.track.left - 0.05 && square.box.right <= idea.track.right + 0.05,
      `${name}: square ${number} stands outside the trace`,
    );
  });
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
    expect(!listed.idea || figures > 0, `${name}: no wide figure`);
    if (listed.idea) await checkIdea(page, name, facts, entry.lang, false);
    await checkRowLists(page, name, listed.rows ?? 0);
    if (listed.path) await checkPathBlock(page, name, entry);
    await checkNoMotion(page, name);
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    await context.close();
  }

  // Phone, and the narrowest width: the idea figure as a stack.
  for (const viewport of [PHONE, NARROW]) {
    const { context, page } = await open(browser, origin, entry, viewport);
    const name = at(viewport);
    await checkFigures(page, name);
    if (listed.idea) await checkIdea(page, name, facts, entry.lang, true);
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
