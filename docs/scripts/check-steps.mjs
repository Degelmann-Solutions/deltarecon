// Checks the step pages of the built site in Chromium: the step cards on
// their trace, the platform switch, the copy button, the blocks that scroll
// sideways, the result table and its bar figure, the path end. Run after the
// build: `npm run check`.
//
// A step page is a page that holds a list of step cards. What a page must
// show stands in `stepPages` below, written out per language, so that a
// changed text or anchor fails here until both places agree. A step page
// without an entry there fails.
//
// The step list of the frontmatter (src/site.ts, `stepFaults`): a step
// without an anchor or a title and an anchor that stands twice are named.
//
// Desktop (1280 px), for every step page of both languages:
//   - the cards: one per step in order, the counter "Step n of m", the tag
//     "optional" on the optional steps only, the pad hidden from assistive
//     technology, the trace on every card, a figure or a flow diagram in
//     every card; the step title is a link to its step; a card with a part
//     of one platform holds a platform switch;
//   - a link of the content to GitHub opens in a new tab and says so in
//     hidden text, a link to another site is a plain link; the step of the
//     download holds one link to the page of the release on GitHub, named by
//     its tag;
//   - the chapter tree lists the steps as links with the titles of the cards;
//   - an address with the anchor of a step opens with that step at the top
//     of the window, without a highlight;
//   - the path end: the square on the axis of the pads, the closing line,
//     then the page links;
//   - the platform switch: Windows on the first visit; a click on "Linux"
//     shows Linux in every switch and every part of the page, the used
//     switch keeps its place in the window and focus; the arrow keys, Home
//     and End move and select; one tab stop per switch; the choice is there
//     again after a reload, on another page, and before the scripts of the
//     page run; without storage it holds for the page and no error shows;
//   - the copy button: after the tabs and before the command; a click puts
//     the command into the clipboard, without prompt and output; "Copied"
//     shows for at least 2 s and is announced, focus stays; a refused copy
//     shows and announces the failure text;
//   - every block that scrolls sideways takes focus and is a named region;
//     the terminal block shows its ring inside;
//   - the result table (caption, column headers, the revision as the header
//     of its row) and the bar figure, which shows the sums of the table:
//     the bar of the largest sum spans half the track, the others in
//     proportion to their sums;
//   - nothing in the content moves: no transition, no animation;
//   - axe with Windows and with Linux chosen; no sideways scrolling.
// Phone (390 px): one column, the figure below the text, the flow diagram
// as a stack, the result table as stacked records with its head row, code
// and terminal scrolling inside their block, tabs and copy button at least
// 40 px high, the step list left out of the menu, the scroll position kept
// when the menu opens and closes; axe in both platform states. An element
// that reaches beyond the window is named.
// JavaScript off (1280 and 390 px): both platforms' parts visible, Windows
// first, each under its label; no tabs, no button, no copy button; no
// sideways scrolling.
//
// Writes to screenshots/ (not under version control): of each step page a
// desktop and a phone screenshot per language, `<page>-desktop-<lang>.png`
// and `<page>-phone-<lang>.png`. Lay them beside the mock of the Quick start.
// Exits non-zero and names page and part of every failed expectation.
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import {
  DESKTOP,
  PHONE,
  RING_ON_NAVY,
  expectations,
  loadPages,
  loadRegister,
  loadRelease,
  pageChecks,
  root,
  startPreview,
} from './harness.mjs';

/** What each step page must show. */
const stepPages = {
  'quick-start': {
    anchors: ['download', 'check', 'unpack', 'start', 'demo', 'result'],
    optional: ['check'],
    // The steps that hold a platform switch; those among them whose switch
    // holds no command (may be left out: none); the step with a terminal
    // block; the step with the link to the page of the release.
    switches: ['download', 'check', 'unpack', 'start'],
    plain: ['download'],
    terminal: 'start',
    release: 'download',
    table: 'result',
    closing: {
      en: 'With the table of step 6 on your screen, stage 1 is complete.',
      de: 'Mit der Tabelle aus Schritt 6 auf Ihrem Bildschirm ist Etappe 1 abgeschlossen.',
    },
  },
};

/** The texts of the step components, written out per language. */
const words = {
  en: {
    counter: (number, total) => `Step ${number} of ${total}`,
    optional: 'optional',
    system: 'Operating system',
    tabs: { windows: 'Windows PowerShell', linux: 'Linux' },
    labels: { windows: 'Windows', linux: 'Linux' },
    copy: 'Copy',
    copyName: (number) => `Copy command, step ${number}`,
    copied: 'Copied',
    failed: 'Not copied. Please select the command by hand.',
    command: (number, platform) => `Command, step ${number}, ${platform}`,
    terminal: { windows: 'Terminal session, PowerShell', linux: 'Terminal session, Linux' },
    steps: 'Steps of this page',
    newTab: 'opens in a new tab',
  },
  de: {
    counter: (number, total) => `Schritt ${number} von ${total}`,
    optional: 'optional',
    system: 'Betriebssystem',
    tabs: { windows: 'Windows PowerShell', linux: 'Linux' },
    labels: { windows: 'Windows', linux: 'Linux' },
    copy: 'Kopieren',
    copyName: (number) => `Befehl kopieren, Schritt ${number}`,
    copied: 'Kopiert',
    failed: 'Nicht kopiert. Bitte markieren Sie den Befehl von Hand.',
    command: (number, platform) => `Befehl, Schritt ${number}, ${platform}`,
    terminal: { windows: 'Terminalsitzung, PowerShell', linux: 'Terminalsitzung, Linux' },
    steps: 'Schritte dieser Seite',
    newTab: 'öffnet in neuem Tab',
  },
};

const PLATFORMS = ['windows', 'linux'];
const STORAGE_KEY = 'deltarecon-docs-platform';
const shots = path.join(root, 'screenshots');
const site = await loadRegister();
const pages = await loadPages();
/** The tag of the release and its page on GitHub, written out here. */
const releaseTag = `v${await loadRelease()}`;
const releaseAddress = `${site.outside.repository}/releases/tag/${releaseTag}`;
/** A sum as the demo prints it, without its sign, as a number. */
const amountOf = (sum, lang) =>
  Number(
    (lang === 'en' ? sum.replaceAll(',', '') : sum.replaceAll('.', '').replace(',', '.')).replace(/^[-+]/, ''),
  );
/** Whether a printed sum begins with a minus sign. */
const isLowering = (sum) => sum.startsWith('-');
const { failures, expect, report } = expectations('check-steps');
const { checkAxe, checkNoSidewaysScroll } = pageChecks({ failures, expect });

async function open(browser, origin, entry, viewport, options = {}) {
  const { javaScript = true, anchor = '', setup, permissions = [] } = options;
  const context = await browser.newContext({ viewport, javaScriptEnabled: javaScript, permissions });
  if (setup) await context.addInitScript(setup);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`${origin}${entry.address}${anchor}`, { waitUntil: 'networkidle' });
  if (javaScript) await page.waitForSelector('html[data-menu]');
  return { context, page, errors };
}

/** The step list of the frontmatter: what `stepFaults` names. */
function checkStepFaults() {
  const whole = { anchor: 'download', title: 'Download the package' };
  const cases = [
    ['a whole list', [whole, { anchor: 'check', title: 'Check', optional: true }], []],
    ['a step without an anchor', [whole, { title: 'Check' }], ['step 2 has no anchor']],
    ['an anchor with a capital letter', [{ anchor: 'Download', title: 'x' }], ['step 1 has no anchor']],
    ['a step without a title', [whole, { anchor: 'check', title: ' ' }], ['step 2 ("check") has no title']],
    ['an anchor twice', [whole, { ...whole }], ['step 2 repeats the anchor "download"']],
    ['no list', 'download', ['"steps" is not a list']],
  ];
  for (const [name, steps, expected] of cases) {
    const faults = site.stepFaults(steps);
    expect(
      faults.length === expected.length &&
        expected.every((fault, index) => faults[index].includes(fault)),
      `step list "${name}": the faults are [${faults.join('; ')}], expected [${expected.join('; ')}]`,
    );
  }
}

/** What the page shows of each platform: the chosen one, the tabs, the parts. */
function platformState(page) {
  return page.evaluate(() => {
    const shown = (element) => element.getClientRects().length > 0;
    const parts = (platform) => [...document.querySelectorAll(`main [data-platform-part="${platform}"]`)];
    return {
      chosen: document.documentElement.dataset.platform,
      selected: [...document.querySelectorAll('main [role="tab"][aria-selected="true"]')].map(
        (tab) => tab.dataset.platformTab,
      ),
      stops: [...document.querySelectorAll('main [role="tablist"]')].map(
        (list) => list.querySelectorAll('[role="tab"][tabindex="0"]').length,
      ),
      windows: parts('windows').map(shown),
      linux: parts('linux').map(shown),
      focus: document.activeElement?.dataset?.platformTab,
      focusList: document.activeElement?.closest('[data-platform-switch]')?.parentElement?.closest('[data-step]')?.id,
    };
  });
}

/** Expects every switch and every part of the page to show `platform`. */
async function expectPlatform(page, name, platform, switches) {
  const state = await platformState(page);
  const other = platform === 'windows' ? 'linux' : 'windows';
  expect(state.chosen === platform, `${name}: <html data-platform> is "${state.chosen}", expected "${platform}"`);
  expect(
    state.selected.length === switches && state.selected.every((tab) => tab === platform),
    `${name}: the selected tabs are [${state.selected}], expected ${switches} times "${platform}"`,
  );
  expect(
    state.stops.every((count) => count === 1),
    `${name}: a switch has not exactly one tab stop (${state.stops})`,
  );
  expect(
    state[platform].length > 0 && state[platform].every(Boolean) && !state[other].some(Boolean),
    `${name}: not every part of "${platform}" is shown, or a part of "${other}" is`,
  );
  return state;
}

/** The step cards, the tree, the path end: what a page delivers. */
async function checkCards(page, name, entry, expected) {
  const w = words[entry.lang];
  const cards = await page.evaluate(() =>
    [...document.querySelectorAll('main ol[data-steps] > li[data-step]')].map((card) => {
      const pad = card.querySelector('.step-pad');
      const title = card.querySelector('h2');
      const link = title?.querySelector('a');
      const trace = getComputedStyle(card, '::before');
      return {
        anchor: card.id,
        counter: card.querySelector('[data-step-counter]')?.textContent.trim(),
        counterInHeading: card.querySelector('h2 [data-step-counter]') !== null,
        optional: card.querySelector('[data-step-optional]')?.textContent.trim(),
        pad: pad?.textContent.trim(),
        padHidden: pad?.getAttribute('aria-hidden') === 'true',
        padCentre: pad ? pad.getBoundingClientRect().left + pad.getBoundingClientRect().width / 2 : -1,
        title: title?.textContent.trim().replace(/\s+/g, ' '),
        href: link?.getAttribute('href'),
        trace: `${trace.borderLeftStyle} ${trace.borderLeftColor}`,
        figure: card.querySelector('[data-step-figure], [data-flow]') !== null,
        state: card.querySelector('input, [aria-checked], [data-state]') !== null,
        // A part of one platform outside a switch, a file of one platform.
        onePlatform: card.querySelector('[data-platform-only], [data-file-list] li[data-platform-part]') !== null,
        switch: card.querySelector('[data-platform-switch]') !== null,
        ground: getComputedStyle(card.querySelector('.step-card')).backgroundColor,
      };
    }),
  );
  expect(
    cards.map((card) => card.anchor).join() === expected.anchors.join(),
    `${name}: the step cards are [${cards.map((card) => card.anchor)}], expected [${expected.anchors}]`,
  );
  cards.forEach((card, index) => {
    const at = `${name}, step "${card.anchor}"`;
    const counter = w.counter(index + 1, expected.anchors.length);
    expect(card.counter === counter && !card.counterInHeading, `${at}: the counter is "${card.counter}", expected "${counter}" outside the heading`);
    const optional = expected.optional.includes(card.anchor) ? w.optional : undefined;
    expect(card.optional === optional, `${at}: the tag is "${card.optional}", expected "${optional}"`);
    expect(card.pad === String(index + 1) && card.padHidden, `${at}: the pad does not show ${index + 1} hidden from assistive technology`);
    expect(card.href === `#${card.anchor}` && card.title !== '', `${at}: the step title is not a link to #${card.anchor}`);
    expect(card.trace === 'solid rgb(23, 121, 130)', `${at}: no trace in teal-text beside the card (${card.trace})`);
    expect(card.figure, `${at}: the card holds neither a step figure nor a flow diagram`);
    expect(!card.state, `${at}: the card carries a state mark`);
    expect(
      !card.onePlatform || card.switch,
      `${at}: the card holds a part of one platform and no platform switch; the reader cannot change the platform there`,
    );
  });

  // A link to GitHub opens in a new tab and says so; a link to another
  // site is a plain link.
  const outside = await page.evaluate(() =>
    [...document.querySelectorAll('main a[href^="http"]')].map((link) => ({
      href: link.getAttribute('href'),
      host: new URL(link.href).hostname,
      step: link.closest('[data-step]')?.id,
      newTab: link.target === '_blank' && link.rel === 'noopener',
      hidden: link.querySelector('.sr-only')?.textContent.trim() ?? '',
      text: link.textContent.trim().replace(/\s+/g, ' '),
    })),
  );
  for (const link of outside) {
    expect(
      link.host === 'github.com' ? link.newTab && link.hidden === `(${w.newTab})` : !link.newTab && link.hidden === '',
      link.host === 'github.com'
        ? `${name}: the link to ${link.href} does not open in a new tab with the hidden text "(${w.newTab})"`
        : `${name}: the link to ${link.href}, which is not on GitHub, is not a plain link`,
    );
  }
  // The page of the release: one link, in its step, named by the tag.
  if (expected.release) {
    const links = outside.filter((link) => link.step === expected.release && link.href === releaseAddress);
    expect(
      links.length === 1 && links[0].text.includes(releaseTag),
      `${name}, step "${expected.release}": not exactly one link to ${releaseAddress} whose text names ${releaseTag}: ${JSON.stringify(outside.filter((link) => link.step === expected.release))}`,
    );
  }

  // The chapter tree lists the steps under the current page.
  const tree = await page.evaluate(
    (label) =>
      [...document.querySelectorAll(`#chapters ol[aria-label="${label}"] a`)].map((link) => ({
        href: link.getAttribute('href'),
        title: link.textContent.trim().replace(/\s+/g, ' '),
        shown: link.getClientRects().length > 0,
      })),
    w.steps,
  );
  expect(
    tree.length === cards.length &&
      tree.every((link, index) => link.href === `#${cards[index].anchor}` && link.title === cards[index].title && link.shown),
    `${name}: the chapter tree does not list the steps as links with the titles of the cards: ${JSON.stringify(tree)}`,
  );

  // The path end: marker on the axis of the pads, closing line, page links.
  const end = await page.evaluate(() => {
    const block = document.querySelector('main [data-path-end]');
    const marker = block?.querySelector('.path-end-marker')?.getBoundingClientRect();
    const steps = document.querySelector('main ol[data-steps]');
    const links = document.querySelector('main [data-page-links]');
    return block && marker && steps && links
      ? {
          line: block.querySelector('p')?.textContent.trim().replace(/\s+/g, ' '),
          lines: block.querySelectorAll('p').length,
          heading: block.querySelector('h1, h2, h3, h4') !== null,
          size: `${marker.width} × ${marker.height}`,
          centre: marker.left + marker.width / 2,
          afterSteps: marker.top >= steps.getBoundingClientRect().bottom - 1,
          beforeLinks: links.getBoundingClientRect().top >= block.getBoundingClientRect().bottom,
        }
      : null;
  });
  expect(end !== null, `${name}: no path end with marker and page links after the steps`);
  if (end) {
    expect(end.line === expected.closing[entry.lang] && end.lines === 1 && !end.heading, `${name}: the closing line is "${end.line}", expected the paragraph "${expected.closing[entry.lang]}"`);
    expect(end.size === '14 × 14', `${name}: the marker of the path end is ${end.size} px, expected 14 × 14`);
    expect(Math.abs(end.centre - cards[0].padCentre) < 1, `${name}: the marker of the path end is not on the axis of the pads (${end.centre} and ${cards[0].padCentre})`);
    expect(end.afterSteps && end.beforeLinks, `${name}: the path end does not stand between the last step and the page links`);
  }
  return cards;
}

/** Nothing in the content moves. */
async function checkNoMotion(page, name) {
  const moving = await page.evaluate(() =>
    [...document.querySelectorAll('main *')]
      .filter((element) => {
        const style = getComputedStyle(element);
        return (
          style.transitionDuration.split(',').some((part) => Number.parseFloat(part) > 0) ||
          style.animationName !== 'none'
        );
      })
      .map((element) => element.outerHTML.slice(0, 80)),
  );
  expect(moving.length === 0, `${name}: a transition or an animation on ${moving.join(' | ')}`);
}

/** Blocks that scroll sideways: focus, name, the ring of the terminal block. */
async function checkRegions(page, name, entry, expected, cards) {
  const w = words[entry.lang];
  const regions = await page.evaluate(() =>
    [...document.querySelectorAll('main pre')].map((block) => ({
      step: block.closest('[data-step]')?.id,
      part: block.closest('[data-platform-part]')?.dataset.platformPart,
      terminal: block.closest('[data-terminal]') !== null,
      tabindex: block.getAttribute('tabindex'),
      role: block.getAttribute('role'),
      name: block.getAttribute('aria-label'),
      overflow: getComputedStyle(block).overflowX,
    })),
  );
  expect(regions.length > 0, `${name}: the page holds no code or terminal block`);
  for (const region of regions) {
    const number = cards.findIndex((card) => card.anchor === region.step) + 1;
    const wanted = region.terminal
      ? w.terminal[region.part]
      : w.command(number, w.labels[region.part]);
    expect(
      region.tabindex === '0' && region.role === 'region' && region.overflow === 'auto',
      `${name}: the block "${region.name}" does not take focus as a region that scrolls sideways`,
    );
    expect(region.name === wanted, `${name}: a block of step "${region.step}" is named "${region.name}", expected "${wanted}"`);
  }
  const terminal = page.locator('main [data-terminal] pre:visible').first();
  await terminal.focus();
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  const ring = await terminal.evaluate((block) => {
    const style = getComputedStyle(block);
    return { focus: block === document.activeElement, outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`, offset: style.outlineOffset };
  });
  expect(
    ring.focus && ring.outline === `solid 2px ${RING_ON_NAVY}` && ring.offset === '-4px',
    `${name}: the terminal block does not show a 2 px teal ring inside itself on keyboard focus (${ring.outline}, offset ${ring.offset})`,
  );
}

/** The result table and the bar figure beside it. */
async function checkTable(page, name, entry, expected) {
  const table = await page.evaluate((anchor) => {
    const card = document.getElementById(anchor);
    const element = card?.querySelector('table[data-result-table]');
    if (!element) return null;
    return {
      caption: element.querySelector('caption')?.textContent.trim() ?? '',
      head: [...element.querySelectorAll('thead th[scope="col"]')].length,
      rows: [...element.querySelectorAll('tbody tr')].map((row) => ({
        header: row.querySelector('th[scope="row"]')?.textContent.trim(),
        cells: row.children.length,
        sum: row.querySelector('.result-num')?.textContent.trim(),
      })),
      bars: [...card.querySelectorAll('[data-bar-row]')].map((row) => {
        const bar = row.querySelector('[data-bar]');
        const track = row.querySelector('.bar-track').getBoundingClientRect();
        const box = bar.getBoundingClientRect();
        const style = getComputedStyle(bar);
        return {
          revision: row.querySelector('.bar-revision').textContent.trim(),
          value: row.querySelector('.bar-value').textContent.trim(),
          kind: bar.dataset.bar,
          width: box.width,
          track: track.width,
          side: box.left + box.width / 2 < track.left + track.width / 2 ? 'left' : 'right',
          filled: Number.parseFloat(style.borderTopWidth) + Number.parseFloat(style.borderBottomWidth) >= box.height - 0.5,
          hidden: row.querySelector('.bar-track').getAttribute('aria-hidden') === 'true',
        };
      }),
    };
  }, expected.table);
  expect(table !== null, `${name}: step "${expected.table}" holds no result table`);
  if (!table) return;
  expect(table.caption !== '' && table.head === 3, `${name}: the result table has no caption or not three column headers`);
  expect(
    table.rows.length > 0 && table.rows.every((row) => row.header && row.cells === 3),
    `${name}: a row of the result table has not its revision as its header and three cells`,
  );
  expect(
    table.bars.length === table.rows.length &&
      table.bars.every((bar, index) => bar.revision === table.rows[index].header && bar.value === table.rows[index].sum),
    `${name}: the bar figure does not show the revisions and sums of the table: ${JSON.stringify(table.bars)}`,
  );
  // The proportion: the bar of the largest sum spans half the track, and a
  // bar above the least width is to it as its sum is to the largest.
  const amounts = table.bars.map((bar) => amountOf(bar.value, entry.lang));
  const largest = Math.max(...amounts);
  const longest = table.bars[amounts.indexOf(largest)];
  expect(
    amounts.every((amount) => Number.isFinite(amount)),
    `${name}: a value of the bar figure is not a sum: ${JSON.stringify(table.bars.map((bar) => bar.value))}`,
  );
  if (longest && largest > 0) {
    expect(
      Math.abs(longest.width - longest.track / 2) <= 1,
      `${name}: the bar of ${longest.revision}, the largest sum, is ${longest.width} px wide, expected half the track of ${longest.track} px`,
    );
    table.bars.forEach((bar, index) => {
      const wanted = (longest.width * amounts[index]) / largest;
      expect(
        // Below the least width of 8 px a bar is not drawn to scale.
        (wanted <= 8 && bar.width <= 9) || Math.abs(bar.width - wanted) <= 1,
        `${name}: the bar of ${bar.revision} (${bar.value}) is ${bar.width} px wide, expected ${wanted.toFixed(1)} px: its share of the longest bar (${longest.width} px for ${longest.value})`,
      );
    });
  }
  for (const bar of table.bars) {
    const lowers = isLowering(bar.value);
    expect(
      bar.hidden && bar.kind === (lowers ? 'lowers' : 'raises') && bar.filled === !lowers && bar.side === (lowers ? 'left' : 'right'),
      `${name}: the bar of ${bar.revision} (${bar.value}) is not ${lowers ? 'outlined, left of' : 'filled, right of'} the zero line`,
    );
    // Only an outlined bar has a least width: it must never look filled.
    if (lowers) {
      expect(bar.width >= 8, `${name}: the outlined bar of ${bar.revision} is ${bar.width} px wide, below 8 px`);
    }
  }
}

/** The platform switch: the choice of the page, place and focus, the keys. */
async function checkSwitch(browser, origin, entry, expected, cards) {
  const name = `${entry.address} (${DESKTOP.width} px, platform switch)`;
  const w = words[entry.lang];
  const count = expected.switches.length;
  const { context, page, errors } = await open(browser, origin, entry, DESKTOP);

  await expectPlatform(page, `${name}, first visit`, 'windows', count);
  const lists = await page.evaluate(() =>
    [...document.querySelectorAll('main [role="tablist"]')].map((list) => ({
      step: list.closest('[data-step]')?.id,
      label: list.getAttribute('aria-label'),
      tabs: [...list.querySelectorAll('[role="tab"]')].map((tab) => ({
        name: tab.textContent.trim().replace(/\s+/g, ' '),
        button: tab.tagName === 'BUTTON',
        panel: document.getElementById(tab.getAttribute('aria-controls'))?.getAttribute('aria-labelledby') === tab.id,
      })),
    })),
  );
  expect(
    lists.map((list) => list.step).join() === expected.switches.join(),
    `${name}: the switches stand in the steps [${lists.map((list) => list.step)}], expected [${expected.switches}]`,
  );
  for (const list of lists) {
    // A switch without a command names no shell.
    const names = expected.plain.includes(list.step) ? w.labels : w.tabs;
    expect(
      list.label === w.system &&
        list.tabs.map((tab) => tab.name).join() === PLATFORMS.map((platform) => names[platform]).join() &&
        list.tabs.every((tab) => tab.button && tab.panel),
      `${name}, step "${list.step}": not a tab list "${w.system}" of the buttons "${names.windows}" and "${names.linux}", each naming its panel: ${JSON.stringify(list)}`,
    );
  }
  // Under a switch without a command a hairline closes the tab row, and
  // the sentences of the platform follow; no code block, no copy button.
  const plain = await page.evaluate(() =>
    [...document.querySelectorAll('main [data-platform-switch][data-plain]')].map((element) => {
      const row = element.querySelector('.platform-tabs');
      const tab = element.querySelector('[role="tab"][aria-selected="true"]').getBoundingClientRect();
      const text = [...element.querySelectorAll('.platform-text')].find((part) => part.getClientRects().length > 0);
      return {
        step: element.closest('[data-step]')?.id,
        hairline: getComputedStyle(row).borderBottomStyle === 'solid' && tab.bottom <= row.getBoundingClientRect().bottom - 0.5,
        gap: text ? text.getBoundingClientRect().top - row.getBoundingClientRect().bottom : -1,
        blocks: element.querySelectorAll('pre, button[data-copy-button]').length,
      };
    }),
  );
  expect(
    plain.map((element) => element.step).join() === expected.plain.join(),
    `${name}: the switches without a command stand in the steps [${plain.map((element) => element.step)}], expected [${expected.plain}]`,
  );
  for (const element of plain) {
    expect(
      element.hairline && element.gap >= 8 && element.blocks === 0,
      `${name}, step "${element.step}": the switch without a command has no hairline under its active tab, no room above its text (${element.gap} px), or it holds a code block or a copy button`,
    );
  }

  // The switch in the middle of the page is the one the reader uses.
  const used = expected.switches[Math.floor(count / 2)];
  const list = page.locator(`#${used} [role="tablist"]`);
  const tab = (platform) => list.locator(`[data-platform-tab="${platform}"]`);
  await list.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, 150));
  const place = async () => (await list.boundingBox()).y;
  const expectKept = async (way, platform, before) => {
    const state = await expectPlatform(page, `${name}, ${way}`, platform, count);
    expect(
      state.focus === platform && state.focusList === used,
      `${name}, ${way}: focus is not on the tab "${platform}" of the used switch`,
    );
    const after = await place();
    expect(Math.abs(after - before) <= 1, `${name}, ${way}: the used switch moved from ${before} to ${after} px in the window`);
  };
  let before = await place();
  await tab('linux').click();
  await expectKept('a click on Linux', 'linux', before);
  expect(
    (await page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)) === 'linux',
    `${name}: the choice is not in the storage of the browser`,
  );
  for (const [key, platform] of [
    ['ArrowLeft', 'windows'],
    ['ArrowLeft', 'linux'],
    ['Home', 'windows'],
    ['End', 'linux'],
    ['ArrowRight', 'windows'],
    ['ArrowRight', 'linux'],
  ]) {
    before = await place();
    await page.keyboard.press(key);
    await expectKept(`the key ${key}`, platform, before);
  }
  await checkAxe(page, `${name}, Linux`);
  await checkNoSidewaysScroll(page, `${name}, Linux`);
  await checkRegions(page, `${name}, Linux`, entry, expected, cards);

  // Remembered: after a reload, on another page, and before the scripts run.
  await page.reload({ waitUntil: 'networkidle' });
  await expectPlatform(page, `${name}, after a reload`, 'linux', count);
  const other = pages.find((candidate) => candidate.lang === entry.lang && candidate.isRoot);
  await page.goto(`${origin}${other.address}`, { waitUntil: 'networkidle' });
  expect(
    (await page.evaluate(() => document.documentElement.dataset.platform)) === 'linux',
    `${name}: the choice is not applied on ${other.address}`,
  );
  const early = await context.newPage();
  await early.route('**/*.js', (route) => route.abort());
  await early.goto(`${origin}${entry.address}`, { waitUntil: 'load' });
  const first = await platformState(early);
  expect(
    first.chosen === 'linux' && first.linux.every(Boolean) && !first.windows.some(Boolean) && first.selected.length === 0,
    `${name}: before the scripts of the page run, the remembered platform is not the one shown`,
  );
  await early.close();
  expect(errors.length === 0, `${name}: script errors: ${errors.join(' | ')}`);
  await context.close();

  // Without storage the choice holds for the page; no error, no message.
  {
    const at = `${name}, storage not available`;
    const blocked = await open(browser, origin, entry, DESKTOP, {
      setup: () => {
        const refuse = () => {
          throw new DOMException('The storage is not available.', 'SecurityError');
        };
        Storage.prototype.getItem = refuse;
        Storage.prototype.setItem = refuse;
      },
    });
    await expectPlatform(blocked.page, `${at}, first visit`, 'windows', count);
    await blocked.page.locator(`#${used} [data-platform-tab="linux"]`).click();
    await expectPlatform(blocked.page, `${at}, a click on Linux`, 'linux', count);
    await blocked.page.reload({ waitUntil: 'networkidle' });
    await expectPlatform(blocked.page, `${at}, after a reload`, 'windows', count);
    expect(blocked.errors.length === 0, `${at}: script errors: ${blocked.errors.join(' | ')}`);
    expect(
      (await blocked.page.locator('main [role="alert"], main dialog').count()) === 0,
      `${at}: the page shows a message`,
    );
    await blocked.context.close();
  }
}

/** The copy button: what it copies, what it says, where it stands. */
async function checkCopy(browser, origin, entry, expected, cards) {
  const name = `${entry.address} (${DESKTOP.width} px, copy button)`;
  const w = words[entry.lang];
  const numberOf = (anchor) => cards.findIndex((card) => card.anchor === anchor) + 1;
  const { context, page, errors } = await open(browser, origin, entry, DESKTOP, {
    permissions: ['clipboard-read', 'clipboard-write'],
  });
  for (const platform of PLATFORMS) {
    if (platform === 'linux') {
      await page.locator('main [data-platform-tab="linux"]').first().click();
      // The buttons of the first round still read "Copied".
      await page.waitForFunction(
        () => document.querySelector('main button[data-copy-button][data-state]') === null,
        undefined,
        { timeout: 10_000 },
      );
    }
    const buttons = await page.evaluate(() =>
      [...document.querySelectorAll('main button[data-copy-button]')]
        .map((button) => {
          delete button.dataset.check;
          return button;
        })
        .filter((button) => button.getClientRects().length > 0)
        .map((button, index) => {
          button.dataset.check = String(index);
          const holder = button.closest('[data-platform-switch], [data-copy]');
          const command = holder.matches('[data-copy]')
            ? holder
            : [...holder.querySelectorAll('[data-copy]')].find((block) => block.getClientRects().length > 0);
          const block = command.querySelector('pre');
          const tab = holder.querySelector('[role="tab"][aria-selected="true"]');
          const after = (first, second) =>
            Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
          return {
            step: button.closest('[data-step]')?.id,
            name: button.getAttribute('aria-label'),
            text: button.textContent.trim(),
            command: command.dataset.copy,
            shown: block.textContent,
            terminal: command.matches('[data-terminal]'),
            typed: command.querySelector('[data-terminal-command]')?.textContent,
            order: (!tab || after(tab, button)) && after(button, block),
            // The button never lies over the command text.
            clear: button.getBoundingClientRect().bottom <= block.getBoundingClientRect().top + 1,
            height: button.getBoundingClientRect().height,
          };
        }),
    );
    const steps = [...expected.switches.filter((step) => !expected.plain.includes(step)), expected.terminal];
    expect(
      buttons.map((button) => button.step).join() === steps.join(),
      `${name}, ${platform}: the copy buttons stand in the steps [${buttons.map((button) => button.step)}], expected [${steps}]`,
    );
    for (const [index, button] of buttons.entries()) {
      const at = `${name}, ${platform}, step "${button.step}"`;
      const wanted = button.terminal
        ? `${w.copyName(numberOf(button.step))}, ${w.labels[platform]}`
        : w.copyName(numberOf(button.step));
      expect(button.text === w.copy && button.name === wanted, `${at}: the button reads "${button.text}" and is named "${button.name}", expected "${w.copy}" and "${wanted}"`);
      expect(button.order && button.clear, `${at}: the button does not stand after the tabs and before the command, above its text`);
      expect(button.height >= 24, `${at}: the button is ${button.height} px high, below 24 px`);
      if (button.terminal) {
        expect(
          button.command === button.typed && button.shown.includes(button.command) && button.shown.trim() !== button.command,
          `${at}: the command of the terminal block is not the typed command without prompt and output`,
        );
      } else {
        expect(button.command === button.shown, `${at}: the command to copy is not the command the block shows`);
      }
      await page.evaluate(() => navigator.clipboard.writeText('nothing copied yet'));
      const control = page.locator(`main button[data-check="${index}"]`);
      await control.click();
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      expect(copied === button.command, `${at}: the clipboard holds "${copied}", expected "${button.command}"`);
      const said = await control.evaluate((element) => ({
        text: element.textContent.trim(),
        status: element.parentElement.querySelector('[role="status"]')?.textContent.trim(),
        focus: element === document.activeElement,
      }));
      expect(
        said.text === w.copied && said.status === w.copied && said.focus,
        `${at}: after a click the button reads "${said.text}", announces "${said.status}" and ${said.focus ? 'keeps' : 'loses'} focus; expected "${w.copied}"`,
      );
    }
  }
  // "Copied" for at least 2 s, then the button as before.
  const control = page.locator('main button[data-copy-button]:visible').first();
  await control.click();
  await page.waitForTimeout(2000);
  expect((await control.innerText()).trim().toLowerCase() === w.copied.toLowerCase(), `${name}: "${w.copied}" shows for less than 2 s`);
  await page.waitForTimeout(1500);
  const rested = await control.evaluate((element) => ({
    text: element.textContent.trim(),
    status: element.parentElement.querySelector('[role="status"]')?.textContent.trim(),
    focus: element === document.activeElement,
  }));
  expect(
    rested.text === w.copy && rested.status === '' && rested.focus,
    `${name}: 3.5 s after a click the button reads "${rested.text}", expected "${w.copy}" with focus kept`,
  );
  expect(errors.length === 0, `${name}: script errors: ${errors.join(' | ')}`);
  await context.close();

  // The browser refuses: the failure text, shown and announced.
  const refused = await open(browser, origin, entry, DESKTOP, {
    setup: () => {
      Object.defineProperty(Clipboard.prototype, 'writeText', {
        value: () => Promise.reject(new DOMException('Write permission denied.', 'NotAllowedError')),
      });
    },
  });
  for (const button of await refused.page.locator('main button[data-copy-button]:visible').all()) {
    await button.click();
    const said = await button.evaluate((element) => ({
      text: element.textContent.trim(),
      status: element.parentElement.querySelector('[role="status"]')?.textContent.trim(),
      focus: element === document.activeElement,
    }));
    expect(
      said.text === w.failed && said.status === w.failed && said.focus,
      `${name}, copying refused: the button reads "${said.text}" and announces "${said.status}", expected "${w.failed}"`,
    );
  }
  await checkAxe(refused.page, `${name}, copying refused`);
  await checkNoSidewaysScroll(refused.page, `${name}, copying refused`);
  expect(refused.errors.length === 0, `${name}, copying refused: script errors: ${refused.errors.join(' | ')}`);
  await refused.context.close();
}

/** Elements of the content that reach beyond the window. */
function beyondWindow(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('main *')]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        // What stands inside a block that scrolls sideways may be wider.
        return box.width > 0 && box.right > document.documentElement.clientWidth + 1 && !element.closest('pre');
      })
      .map((element) => element.outerHTML.slice(0, 80)),
  );
}

/** The phone: one column, stacked records, blocks that scroll inside. */
async function checkPhone(browser, origin, entry, expected, kind) {
  const name = `${entry.address} (${PHONE.width} px)`;
  const { context, page, errors } = await open(browser, origin, entry, PHONE);
  const layout = await page.evaluate((tableStep) => {
    const box = (element) => element.getBoundingClientRect();
    const cards = [...document.querySelectorAll('main [data-step]')].map((card) => {
      const text = card.querySelector('.step-text');
      const figure = card.querySelector('.step-columns > [data-step-figure]');
      return { anchor: card.id, below: !figure || box(figure).top >= box(text).bottom, left: !figure || Math.abs(box(figure).left - box(text).left) < 1 };
    });
    const boxes = [...document.querySelectorAll('main [data-flow-box]')].map(box);
    const table = document.querySelector(`#${tableStep} table[data-result-table]`);
    const rows = table
      ? [...table.querySelectorAll('tbody tr')].map((row) => {
          const [revision, description, sum] = [...row.children].map(box);
          return Math.abs(revision.top - sum.top) < 4 && description.top >= revision.bottom - 1 && sum.left > revision.right;
        })
      : [];
    const head = table?.querySelector('thead tr');
    return {
      cards,
      flowStacked: boxes.every((flow, index) => index === 0 || flow.top >= boxes[index - 1].bottom),
      flowBoxes: boxes.length,
      rows,
      headShown: Boolean(head) && box(head).height > 0 && [...head.children].every((cell) => box(cell).width > 0),
      tableScrolls: table ? table.parentElement.scrollWidth > table.parentElement.clientWidth : true,
      blocks: [...document.querySelectorAll('main pre')]
        .filter((block) => block.getClientRects().length > 0)
        .map((block) => ({
          name: block.getAttribute('aria-label'),
          inside: box(block).right <= document.documentElement.clientWidth,
          scrolls: block.scrollWidth > block.clientWidth,
          terminal: block.closest('[data-terminal]') !== null,
        })),
      controls: [...document.querySelectorAll('main [role="tab"], main button[data-copy-button]')]
        .filter((control) => control.getClientRects().length > 0)
        .map((control) => ({ name: control.textContent.trim(), height: box(control).height })),
      textSizes: [...document.querySelectorAll('main [data-step-figure] *, main [data-flow] *')]
        .filter((element) => [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.data.trim() !== ''))
        .map((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
    };
  }, expected.table);
  for (const card of layout.cards) {
    expect(card.below && card.left, `${name}, step "${card.anchor}": the figure does not stand below the text in one column`);
  }
  expect(layout.flowBoxes > 0 && layout.flowStacked, `${name}: the flow diagram is not a vertical stack`);
  expect(
    layout.rows.length > 0 && layout.rows.every(Boolean) && layout.headShown && !layout.tableScrolls,
    `${name}: the result table is not stacked records (revision and sum on one line, description below) with a visible head row, or it scrolls sideways`,
  );
  for (const block of layout.blocks) {
    expect(block.inside, `${name}: the block "${block.name}" reaches beyond the window`);
    if (block.terminal) expect(block.scrolls, `${name}: the terminal block "${block.name}" does not scroll inside itself`);
  }
  for (const control of layout.controls) {
    expect(control.height >= 40, `${name}: "${control.name}" is ${control.height} px high, below 40 px`);
  }
  expect(
    layout.textSizes.every((size) => size >= 11),
    `${name}: text in a figure is below 11 px (${Math.min(...layout.textSizes)} px)`,
  );
  const beyond = await beyondWindow(page);
  expect(beyond.length === 0, `${name}: beyond the window: ${beyond.join(' | ')}`);
  await checkNoSidewaysScroll(page, name);
  await checkAxe(page, `${name}, Windows`);
  await page.screenshot({ path: path.join(shots, `${kind}-phone-${entry.lang}.png`), fullPage: true });

  // The menu: the step list is left out; the scroll position is kept.
  await page.evaluate(() => window.scrollTo(0, 700));
  const before = await page.evaluate(() => window.scrollY);
  // The button is clicked where the page stands; a pointer would first
  // scroll to the top bar, which does not stay in view.
  await page.locator('button[data-menu-button]').evaluate((button) => button.click());
  expect(
    (await page.locator(`#chapters ol[aria-label="${words[entry.lang].steps}"]`).isVisible()) === false,
    `${name}: the menu shows the step list`,
  );
  expect((await page.evaluate(() => window.scrollY)) === 0, `${name}: the open menu does not stand at its top`);
  await page.locator('button[data-menu-close]').click();
  const after = await page.evaluate(() => window.scrollY);
  expect(before === 700 && after === before, `${name}: after opening and closing the menu the page stands at ${after} px, expected ${before}`);

  await page.locator('main [data-platform-tab="linux"]').first().click();
  await checkAxe(page, `${name}, Linux`);
  await checkNoSidewaysScroll(page, `${name}, Linux`);
  const beyondLinux = await beyondWindow(page);
  expect(beyondLinux.length === 0, `${name}, Linux: beyond the window: ${beyondLinux.join(' | ')}`);
  await page.setViewportSize({ width: 320, height: 640 });
  const narrow = await beyondWindow(page);
  expect(narrow.length === 0, `${entry.address} (320 px): beyond the window: ${narrow.join(' | ')}`);
  await checkNoSidewaysScroll(page, `${entry.address} (320 px, Linux)`);
  expect(errors.length === 0, `${name}: script errors: ${errors.join(' | ')}`);
  await context.close();
}

/** JavaScript off: both platforms under their labels, nothing that needs a script. */
async function checkWithoutScript(browser, origin, entry, expected, viewport) {
  const name = `${entry.address} (${viewport.width} px, JavaScript off)`;
  const w = words[entry.lang];
  const { context, page } = await open(browser, origin, entry, viewport, { javaScript: false });
  const state = await page.evaluate(() => {
    const shown = (element) => element.getClientRects().length > 0;
    return {
      chosen: document.documentElement.dataset.platform,
      tabs: document.querySelectorAll('[role="tab"], [role="tablist"], [role="tabpanel"]').length,
      buttons: [...document.querySelectorAll('main button')].filter(shown).length,
      switches: [...document.querySelectorAll('main [data-platform-switch]')].map((element) => ({
        step: element.closest('[data-step]')?.id,
        parts: [...element.querySelectorAll(':scope > [data-platform-part]')].map((part) => {
          const label = part.querySelector(':scope > [data-platform-label]');
          const block = part.querySelector('pre');
          return {
            platform: part.dataset.platformPart,
            label: label && shown(label) ? label.textContent.trim().replace(/\s+/g, ' ') : '',
            labelTop: label?.getBoundingClientRect().top,
            blockTop: block && shown(block) ? block.getBoundingClientRect().top : -1,
          };
        }),
      })),
      only: [...document.querySelectorAll('main [data-platform-only]')].map((part) => {
        const label = part.querySelector(':scope > [data-platform-label]');
        return { platform: part.dataset.platformPart, shown: shown(part), label: label && shown(label) ? label.textContent.trim() : '' };
      }),
      rows: [...document.querySelectorAll('main [data-file-list] li[data-platform-part]')].map((row) => ({
        platform: row.dataset.platformPart,
        shown: shown(row),
        note: row.querySelector('.platform-note')?.textContent ?? '',
        noteShown: Boolean(row.querySelector('.platform-note')) && shown(row.querySelector('.platform-note')),
      })),
    };
  });
  expect(state.chosen === undefined, `${name}: <html> names a platform`);
  expect(state.tabs === 0 && state.buttons === 0, `${name}: the page holds tabs or a visible button (${state.tabs} tab parts, ${state.buttons} buttons)`);
  expect(
    state.switches.map((element) => element.step).join() === expected.switches.join(),
    `${name}: the switches stand in the steps [${state.switches.map((element) => element.step)}], expected [${expected.switches}]`,
  );
  for (const element of state.switches) {
    const [first, second] = element.parts;
    const plain = expected.plain.includes(element.step);
    const names = plain ? w.labels : w.tabs;
    expect(
      element.parts.length === 2 &&
        first.platform === 'windows' &&
        second.platform === 'linux' &&
        first.label === names.windows &&
        second.label === names.linux &&
        first.labelTop < second.labelTop &&
        (plain
          ? first.blockTop === -1 && second.blockTop === -1
          : first.labelTop < first.blockTop && first.blockTop < second.labelTop && second.labelTop < second.blockTop),
      `${name}, step "${element.step}": not the part of Windows and then of Linux, each under its visible label${plain ? ', without a command' : ' above its command'}: ${JSON.stringify(element.parts)}`,
    );
  }
  expect(
    state.only.length > 0 && state.only.every((part) => part.shown && part.label === w.labels[part.platform]),
    `${name}: a part of one platform is not visible under the name of its platform: ${JSON.stringify(state.only)}`,
  );
  expect(
    state.rows.every((row) => row.shown && row.noteShown && row.note.includes(w.labels[row.platform])),
    `${name}: a row of a file list does not name its platform`,
  );
  const beyond = await beyondWindow(page);
  expect(beyond.length === 0, `${name}: beyond the window: ${beyond.join(' | ')}`);
  await checkNoSidewaysScroll(page, name);
  await context.close();
}

async function checkStepPage(browser, origin, entry, expected) {
  const name = `${entry.address} (${DESKTOP.width} px)`;
  const kind = entry.id;

  // Desktop: what the page delivers, in its first state.
  let cards;
  {
    const { context, page, errors } = await open(browser, origin, entry, DESKTOP);
    cards = await checkCards(page, name, entry, expected);
    await checkRegions(page, name, entry, expected, cards);
    await checkTable(page, name, entry, expected);
    await checkNoMotion(page, name);
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, `${name}, Windows`);
    const columns = await page.evaluate(() =>
      [...document.querySelectorAll('main .step-columns > [data-step-figure]')].map((figure) => {
        const text = figure.parentElement.querySelector('.step-text').getBoundingClientRect();
        const box = figure.getBoundingClientRect();
        return { right: box.left >= text.right, width: box.width, text: text.width };
      }),
    );
    // The text column: content-max 992 less the content padding (2 × 48),
    // the step indent (64), the card padding (2 × 28) and its border (2),
    // the gap (36) and the figure column (264).
    expect(
      columns.length > 0 && columns.every((figure) => figure.right && Math.abs(figure.width - 264) < 1 && figure.text >= 474),
      `${name}: a step figure does not stand right of the text in a column of 264 px, or the text column is below 474 px: ${JSON.stringify(columns)}`,
    );
    await page.screenshot({ path: path.join(shots, `${kind}-desktop-${entry.lang}.png`), fullPage: true });
    expect(errors.length === 0, `${name}: script errors: ${errors.join(' | ')}`);
    await context.close();
  }

  // An address with the anchor of a step: that step at the top of the window.
  {
    const anchor = expected.anchors[Math.floor(expected.anchors.length / 2)];
    const at = `${entry.address}#${anchor} (${DESKTOP.width} px)`;
    const { context, page } = await open(browser, origin, entry, DESKTOP, { anchor: `#${anchor}` });
    const arrived = await page.evaluate((id) => {
      const card = document.getElementById(id);
      const grounds = [...document.querySelectorAll('main [data-step]')].map((step) => {
        const style = getComputedStyle(step.querySelector('.step-card'));
        return `${getComputedStyle(step).backgroundColor} ${style.backgroundColor} ${style.borderColor} ${style.outlineStyle}`;
      });
      return {
        top: card.getBoundingClientRect().top,
        target: card.matches(':target'),
        plain: new Set(grounds).size === 1,
      };
    }, anchor);
    expect(arrived.target && Math.abs(arrived.top) <= 1, `${at}: the step stands ${arrived.top} px from the top of the window`);
    expect(arrived.plain, `${at}: the step the address points at looks different from the others`);
    await context.close();
  }

  await checkSwitch(browser, origin, entry, expected, cards);
  await checkCopy(browser, origin, entry, expected, cards);
  await checkPhone(browser, origin, entry, expected, kind);
  await checkWithoutScript(browser, origin, entry, expected, DESKTOP);
  await checkWithoutScript(browser, origin, entry, expected, PHONE);
}

checkStepFaults();
const { origin: reported, stop } = startPreview();
let browser;
let checked = 0;
try {
  const origin = await reported;
  await mkdir(shots, { recursive: true });
  browser = await chromium.launch();
  // Which pages are step pages: every page that holds step cards.
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  const found = [];
  for (const entry of pages) {
    await page.goto(`${origin}${entry.address}`);
    if ((await page.locator('main [data-steps]').count()) > 0) found.push(entry);
  }
  await context.close();
  for (const id of Object.keys(stepPages)) {
    for (const lang of site.languages) {
      expect(
        found.some((entry) => entry.id === id && entry.lang === lang),
        `the page "${id}" (${lang}) holds no step cards`,
      );
    }
  }
  for (const entry of found) {
    const listed = stepPages[entry.id];
    if (!listed) {
      failures.push(`${entry.address}: a step page without an entry in stepPages (scripts/check-steps.mjs)`);
      continue;
    }
    // An entry without `plain`: no switch of the page is without a command.
    const expected = { plain: [], ...listed };
    // An error on one page is a failure of that page; the others still run.
    try {
      await checkStepPage(browser, origin, entry, expected);
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

report(`the step list and ${checked} step pages pass; screenshots in screenshots/`);
