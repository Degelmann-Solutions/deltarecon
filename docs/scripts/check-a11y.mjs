// Checks accessibility and keyboard operation of every page of the page
// register in Chromium. Run after the build: `npm run check`.
//
// Desktop (1280 px), for every page:
//   - axe finds no violation of the A and AA rules of WCAG 2.0 to 2.2;
//   - the frame: title, current page and stage in the chapter tree, stage
//     line, page links (names, sides), no sideways scrolling;
//   - keyboard: the skip link is the first stop, visible on focus, and leads
//     to main; Tab reaches every control in reading order, each with a
//     visible focus ring;
//   - the language switch leads to the counterpart and keeps the anchor, the
//     one the page was loaded with and one set afterwards.
// Phone (390 px), for every page:
//   - the top bar holds menu button, logo and language switch only;
//   - no sideways scrolling, also at 320 px; axe with the menu closed and open;
//   - the menu: tree on the full screen, focus on the close button, which
//     says "open", the page behind inert and the skip link out of the page,
//     Tab stays inside, Escape and the close button close it and return focus
//     to the menu button; search field and release badge inside; at 320 px
//     its top bar is one row.
// Phone, JavaScript off, for every page:
//   - the menu button is a link that jumps to the chapter tree at the end of
//     the page; the language switch opens the counterpart without the anchor.
// Between (900 px), for the start page of each language: axe, the menu, no
// sideways scrolling (also at 600 px); an open menu ends when the window
// reaches the tree breakpoint, with focus in the page; the search field moves
// between top bar and menu at the phone breakpoint.
//
// The search result list, for the start page of each language: axe with the
// list open, with hits and with no match, in the top bar (1280 px) and in the
// menu on the phone; its place (under the field, 360 px wide in the top bar;
// in the flow at full width in the menu, the tree below it); the hits follow
// the field in tab order with a focus ring; the list closes when focus leaves
// the search in the top bar; Escape in the field closes the list and leaves
// the menu open; no sideways scrolling with the list open at 600 and 320 px.
// The page-not-found page of each language: axe at desktop and phone width
// and with the menu open, the frame without stage line, page links and
// current page, the two blocks with their languages, skip link, tab order,
// language switch, the menu, no sideways scrolling.
// The root page, held by a browser that names no language: axe at desktop
// and phone width, tab order, no sideways scrolling.
//
// Writes to screenshots/ (not under version control): a desktop (1280 px), a
// between (900 px), a phone and an open-menu screenshot of the start page of
// each language; the search result list in the top bar and in the menu, with
// hits and with no match; the page-not-found page of each language and the
// root page, each at desktop and phone width.
// Exits non-zero and names page and control of every failed expectation.
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import axe from '@axe-core/playwright';
import { chromium } from 'playwright';
import {
  expectations,
  loadOtherPages,
  loadPages,
  root,
  searchTexts,
  startPreview,
} from './harness.mjs';

const AxeBuilder = axe.AxeBuilder ?? axe.default ?? axe;
const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const DESKTOP = { width: 1280, height: 800 };
const BETWEEN = { width: 900, height: 800 };
const PHONE = { width: 390, height: 844 };
// Two anchors every page has in both languages.
const ANCHOR = '#main';
const LATER_ANCHOR = '#chapters';
// A word that only the start page of that language holds (harness.mjs).
const ownWords = { de: searchTexts.de.ownWord, en: searchTexts.en.ownWord };
// Navy, the border of the search field and of the search result list.
const NAVY = 'rgb(30, 37, 71)';
// The focus ring on light grounds: 2 px in teal-text.
const RING = 'rgb(23, 121, 130)';

const shots = path.join(root, 'screenshots');
const pages = await loadPages();
const { notFound, rootPage } = await loadOtherPages();
const { failures, expect, report } = expectations('check-a11y');

async function open(browser, origin, entry, viewport, { javaScript = true, anchor = '' } = {}) {
  const context = await browser.newContext({ viewport, javaScriptEnabled: javaScript });
  const page = await context.newPage();
  await page.goto(`${origin}${entry.address}${anchor}`, { waitUntil: 'networkidle' });
  if (javaScript) {
    // The search field and the menu button are in the page.
    await page.waitForSelector('[data-search] input', { state: 'attached' });
    await page.waitForSelector('html[data-menu]');
  }
  return { context, page };
}

/**
 * Waits until the page has answered a new window width; the scripts hear of
 * it after the resize. A state that never comes is left to the expectation
 * that follows.
 */
async function settle(page, state) {
  await page.waitForFunction(state, undefined, { timeout: 3_000 }).catch(() => {});
}

async function checkAxe(page, name) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  for (const violation of violations) {
    for (const node of violation.nodes) {
      failures.push(`${name}: axe rule "${violation.id}" (${violation.help}): ${node.html}`);
    }
  }
}

async function checkNoSidewaysScroll(page, name) {
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(scroll <= client, `${name}: the page scrolls sideways (${scroll} px in ${client} px)`);
}

/** The element that has focus: what names it, where it is, how it looks. */
function focused(page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!element || element === document.body) return null;
    const style = getComputedStyle(element);
    const box = element.getBoundingClientRect();
    const text = (element.getAttribute('aria-label') ?? element.textContent ?? '').trim();
    const label = element.labels?.[0]?.textContent?.trim();
    return {
      description: `<${element.tagName.toLowerCase()}> "${(label ?? text).replace(/\s+/g, ' ')}"`,
      stop: element.dataset.stop === undefined ? -1 : Number(element.dataset.stop),
      outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`,
      ring:
        style.outlineStyle === 'solid' &&
        Number.parseFloat(style.outlineWidth) >= 2 &&
        style.outlineColor,
      width: box.width,
      height: box.height,
      inView:
        box.top >= -1 &&
        box.left >= -1 &&
        box.bottom <= window.innerHeight + 1 &&
        box.right <= window.innerWidth + 1,
      inMain: element.closest('main') !== null,
      inMenu: element.closest('header, #chapters') !== null,
      isSkipLink: element.matches('a.skip-link[href="#main"]'),
      isMenuButton: element.matches('button[data-menu-button]'),
      isCloseButton: element.matches('button[data-menu-close]'),
    };
  });
}

/**
 * Numbers every control that takes focus, in the order of the page. `within`
 * limits them to parts of the page.
 */
function markStops(page, within = 'body') {
  return page.evaluate((scope) => {
    const stops = [
      ...document.querySelectorAll(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ].filter(
      (element) =>
        element.closest(scope) !== null &&
        element.getClientRects().length > 0 &&
        getComputedStyle(element).visibility !== 'hidden' &&
        !element.closest('[inert]'),
    );
    stops.forEach((element, index) => {
      element.dataset.stop = String(index);
    });
    return stops.map((element) =>
      (element.getAttribute('aria-label') ?? element.textContent ?? element.tagName)
        .trim()
        .replace(/\s+/g, ' '),
    );
  }, within);
}

/** Frame, names and marks of a page, at desktop width. */
async function checkFrame(page, name, entry) {
  expect((await page.title()) === entry.title, `${name}: title is "${await page.title()}"`);
  for (const [part, selector] of [
    ['top bar', 'body > header'],
    ['chapter tree', '#chapters nav'],
    ['page title', 'main h1'],
    ['page links', 'main nav[data-page-links]'],
    ['footer', 'body > footer'],
  ]) {
    const found = page.locator(selector);
    expect(
      (await found.count()) === 1 && (await found.first().isVisible()),
      `${name}: the ${part} is not in the page once and visible`,
    );
  }
  expect(
    (await page.locator('#chapters').count()) === 1 && (await page.locator('#chapters nav').count()) === 1,
    `${name}: the chapter tree does not exist exactly once`,
  );
  expect(
    (await page.locator('h1').count()) === 1 &&
      (await page.locator('h1').innerText()).trim() === entry.name,
    `${name}: the one level-1 heading is not "${entry.name}"`,
  );

  // Current page and stage in the chapter tree; the stage line.
  const current = page.locator('#chapters a[aria-current="page"]');
  expect((await current.count()) === 1, `${name}: not exactly one tree entry is the current page`);
  if ((await current.count()) === 1) {
    expect(
      (await current.getAttribute('href')) === entry.address &&
        (await current.innerText()).trim() === entry.name,
      `${name}: the current tree entry is not "${entry.name}" at ${entry.address}`,
    );
  }
  const stage = page.locator('#chapters [data-current-stage] h2');
  if (entry.stageName) {
    expect(
      (await stage.count()) === 1 && (await stage.innerText()).includes(entry.stageName),
      `${name}: the stage "${entry.stageName}" is not marked in the tree`,
    );
  } else {
    expect((await stage.count()) === 0, `${name}: a stage is marked, but the page has none`);
  }
  const stageLine = (await page.locator('[data-stage-line]').innerText()).trim();
  expect(entry.stageLine !== '', `${name}: the register gives no stage line`);
  expect(stageLine === entry.stageLine, `${name}: stage line is "${stageLine}", expected "${entry.stageLine}"`);

  // Page links: which exist, their names, their sides.
  const links = page.locator('main nav[data-page-links]');
  const expected = [entry.previous, entry.next].filter(Boolean);
  expect(
    (await links.getByRole('link').count()) === expected.length,
    `${name}: ${await links.getByRole('link').count()} page links, expected ${expected.length}`,
  );
  const middle = await links.evaluate((nav) => {
    const box = nav.getBoundingClientRect();
    return box.left + box.width / 2;
  });
  for (const [side, target] of [
    ['previous', entry.previous],
    ['next', entry.next],
  ]) {
    if (!target) continue;
    const link = links.getByRole('link', { name: target.name, exact: true });
    if ((await link.count()) !== 1) {
      failures.push(`${name}: no page link named "${target.name}"`);
      continue;
    }
    expect(
      (await link.getAttribute('href')) === target.address,
      `${name}: page link "${target.name}" does not lead to ${target.address}`,
    );
    const box = await link.boundingBox();
    expect(
      side === 'previous' ? box.x + box.width <= middle : box.x >= middle,
      `${name}: page link "${target.name}" is not on its side`,
    );
  }
}

/** Skip link: first stop, visible on focus, leads to main. */
async function checkSkipLink(page, name) {
  await page.keyboard.press('Tab');
  const first = await focused(page);
  expect(first?.isSkipLink, `${name}: the first stop is ${first?.description}, not the skip link`);
  expect(
    first && first.width > 40 && first.height >= 24 && first.inView,
    `${name}: the skip link is not visible on focus`,
  );
  await page.keyboard.press('Enter');
  expect(new URL(page.url()).hash === '#main', `${name}: the skip link does not lead to #main`);
  await page.keyboard.press('Tab');
  const next = await focused(page);
  expect(next?.inMain, `${name}: after the skip link, Tab lands on ${next?.description}, outside main`);
}

/** Tab reaches every control in the order of the page, each with a ring. */
async function checkTabOrder(page, name) {
  const stops = await markStops(page);
  for (let index = 0; index < stops.length; index += 1) {
    await page.keyboard.press('Tab');
    const at = await focused(page);
    if (!at || at.stop !== index) {
      failures.push(
        `${name}: Tab ${index + 1} lands on ${at?.description ?? 'nothing'}, expected "${stops[index]}"`,
      );
      return;
    }
    expect(at.ring === RING, `${name}: ${at.description} has no focus ring (outline: ${at.outline})`);
    expect(
      at.width >= 24 && at.height >= 24,
      `${name}: ${at.description} is ${at.width} × ${at.height} px, below 24 × 24`,
    );
    expect(at.inView, `${name}: ${at.description} is outside the window when it has focus`);
  }
}

/** The language switch leads to the counterpart; `anchor` is what it keeps. */
async function checkLanguageSwitch(page, name, entry, origin, anchor) {
  const link = page.locator('a[data-counterpart]:visible');
  expect((await link.count()) === 1, `${name}: not exactly one visible link to the counterpart`);
  if ((await link.count()) !== 1) return;
  const names = { de: 'DE – Deutsch', en: 'EN – English' };
  expect(
    (await page.getByRole('link', { name: names[entry.otherLang], exact: true }).count()) === 1,
    `${name}: no language link named "${names[entry.otherLang]}"`,
  );
  expect(
    (await page.getByRole('link', { name: names[entry.lang], exact: true }).getAttribute('aria-current')) === 'true',
    `${name}: the active language is not marked as current`,
  );
  expect(
    (await link.getAttribute('lang')) === entry.otherLang,
    `${name}: the link to the counterpart does not carry its language`,
  );
  await link.click();
  await page.waitForLoadState('load');
  const expected = `${origin}${entry.counterpart}${anchor}`;
  expect(page.url() === expected, `${name}: the language switch opens ${page.url()}, expected ${expected}`);
}

/** The menu below the tree breakpoint. */
async function checkMenu(page, name, { phone, screenshot, hitWord }) {
  const button = page.locator('button[data-menu-button]');
  const close = page.locator('button[data-menu-close]');
  const tree = page.locator('#chapters');
  const main = page.locator('main');
  const state = () =>
    page.evaluate(() => ({
      inert: [...document.querySelectorAll('main, body > footer')].every((part) => part.inert),
      active: [...document.querySelectorAll('main, body > footer')].some((part) => part.inert),
      expanded: document.querySelector('[data-menu-button]')?.getAttribute('aria-expanded'),
      closeExpanded: document.querySelector('[data-menu-close]')?.getAttribute('aria-expanded'),
      skipLink: document.querySelector('.skip-link').getClientRects().length > 0,
    }));

  expect(
    (await button.isVisible()) && !(await close.isVisible()) && !(await tree.isVisible()),
    `${name}: closed menu: the menu button is not visible, or close button or tree are`,
  );
  expect((await state()).expanded === 'false', `${name}: the menu button does not say "closed"`);

  await button.click();
  const opened = await state();
  expect(
    (await tree.isVisible()) && !(await main.isVisible()),
    `${name}: open menu: the tree is not visible, or the content still is`,
  );
  expect(opened.inert, `${name}: open menu: content and footer are not inert`);
  expect(opened.expanded === 'true', `${name}: open menu: the menu button does not say "open"`);
  expect(
    opened.closeExpanded === 'true' && (await close.getAttribute('aria-controls')) === 'chapters',
    `${name}: open menu: the close button, the one in view, does not say "open"`,
  );
  expect(!opened.skipLink, `${name}: open menu: the skip link is still in the page`);
  expect((await focused(page))?.isCloseButton, `${name}: open menu: focus is not on the close button`);
  const cover = await page.evaluate(() => {
    const header = document.querySelector('body > header').getBoundingClientRect();
    const box = document.getElementById('chapters').getBoundingClientRect();
    return (
      header.top === 0 &&
      Math.abs(box.top - header.bottom) < 1 &&
      box.left === 0 &&
      Math.abs(box.width - window.innerWidth) < 1 &&
      box.bottom >= window.innerHeight
    );
  });
  expect(cover, `${name}: open menu: the tree does not fill the screen under its top bar`);
  await checkNoSidewaysScroll(page, `${name}, open menu`);

  const field = page.locator('#chapters input[type="search"]');
  const badge = page.locator('#chapters [data-release]');
  if (phone) {
    expect(await field.isVisible(), `${name}: open menu: no search field in the menu`);
    expect(await badge.isVisible(), `${name}: open menu: no release badge in the menu`);
  } else {
    expect((await field.count()) === 0, `${name}: open menu: a search field stands in the menu`);
  }
  for (const [part, selector] of [
    ['logo', 'body > header img'],
    ['language switch', 'body > header a[data-counterpart]'],
    ['product-page link', '#chapters nav > a'],
    ['mark of DeltaRecon', '#chapters svg[data-product-mark][aria-hidden="true"]'],
  ]) {
    expect(await page.locator(selector).isVisible(), `${name}: open menu: no ${part}`);
  }

  await checkAxe(page, `${name}, open menu`);
  if (screenshot) await page.screenshot({ path: screenshot, fullPage: true });

  // Tab stays inside: one round leads back to the close button.
  const stops = await markStops(page, 'header, #chapters');
  for (let index = 1; index <= stops.length; index += 1) {
    await page.keyboard.press('Tab');
    const at = await focused(page);
    if (!at?.inMenu) {
      failures.push(`${name}: open menu: Tab leaves the menu and lands on ${at?.description ?? 'nothing'}`);
      break;
    }
    expect(at.ring === RING, `${name}: open menu: ${at.description} has no focus ring (outline: ${at.outline})`);
    if (index === stops.length) {
      expect(at.isCloseButton, `${name}: open menu: a round of Tab ends on ${at.description}`);
    }
  }
  await page.keyboard.press('Shift+Tab');
  expect((await focused(page))?.inMenu, `${name}: open menu: Shift+Tab leaves the menu`);

  // Escape in the search field belongs to the search: the menu stays open.
  if (phone) {
    await field.focus();
    await page.keyboard.press('Escape');
    expect(
      (await tree.isVisible()) && (await field.evaluate((input) => input === document.activeElement)),
      `${name}: open menu: Escape in the search field closes the menu or moves focus`,
    );
    await close.focus();
  }

  // Escape on a search hit closes the menu like anywhere else.
  if (phone && hitWord) {
    await field.fill(hitWord);
    const hit = page.locator(`#chapters [data-search-results="${hitWord}"] a`).first();
    try {
      await hit.waitFor({ state: 'visible', timeout: 10_000 });
      await hit.focus();
      await page.keyboard.press('Escape');
      expect(
        !(await tree.isVisible()) && (await focused(page))?.isMenuButton,
        `${name}: open menu: Escape on a search hit does not close the menu`,
      );
    } catch (error) {
      failures.push(`${name}: open menu: the search gave no hit for "${hitWord}": ${error.message}`);
    }
    if (!(await tree.isVisible())) await button.click();
    await field.fill('');
    await close.focus();
  }

  // Escape, then the close button: both close and return focus.
  for (const [way, act] of [
    ['Escape', () => page.keyboard.press('Escape')],
    ['the close button', () => close.click()],
  ]) {
    await act();
    const closed = await state();
    expect(
      !(await tree.isVisible()) && (await main.isVisible()) && !closed.active,
      `${name}: ${way} does not close the menu`,
    );
    expect(
      closed.expanded === 'false' && closed.closeExpanded === 'false',
      `${name}: after ${way} a button still says "open"`,
    );
    expect(closed.skipLink, `${name}: after ${way} the skip link is not back in the page`);
    expect((await focused(page))?.isMenuButton, `${name}: ${way} does not return focus to the menu button`);
    if (way === 'Escape') await button.click();
  }
}

/** Types a term and waits until the list answers it. */
async function searchFor(page, term) {
  await page.locator('input[type="search"]').fill(term);
  await page
    .locator(`[data-search-results="${term}"]`)
    .waitFor({ state: 'attached', timeout: 15_000 });
}

/** Where the search result list stands, and how it looks. */
function listBox(page) {
  return page.evaluate(() => {
    const panel = document.querySelector('[data-search] .search-panel');
    const field = document.querySelector('[data-search] input').getBoundingClientRect();
    const box = panel.getBoundingClientRect();
    const style = getComputedStyle(panel);
    const tree = document.querySelector('#chapters nav').getBoundingClientRect();
    return {
      shown: !panel.hasAttribute('data-empty') && box.width > 1 && box.height > 1,
      left: box.left - field.left,
      gap: box.top - field.bottom,
      width: box.width,
      fieldWidth: field.width,
      right: box.right,
      window: document.documentElement.clientWidth,
      treeBelow: tree.top >= box.bottom,
      position: style.position,
      background: style.backgroundColor,
      border: `${style.borderTopStyle} ${style.borderTopWidth} ${style.borderTopColor}`,
      status: panel.querySelector('[role="status"]').textContent.trim(),
      hits: panel.querySelectorAll('li').length,
      oneLine: [...panel.querySelectorAll('.search-hit-excerpt')].every(
        (line) => line.getBoundingClientRect().height < 30,
      ),
      bold: [...panel.querySelectorAll('.search-hit-excerpt mark')].every(
        (mark) => Number(getComputedStyle(mark).fontWeight) >= 600,
      ),
    };
  });
}

/** The search result list on the start page of a language. */
async function checkSearchList(browser, origin, entry) {
  const texts = searchTexts[entry.lang];
  const noMatchTerm = searchTexts[entry.otherLang].ownWord;
  const shot = (kind) => path.join(shots, `search-list-${kind}-${entry.lang}.png`);

  // In the top bar.
  {
    const name = `${entry.address} (${DESKTOP.width} px, search result list)`;
    const { context, page } = await open(browser, origin, entry, DESKTOP);
    await searchFor(page, texts.sharedWord);
    const list = await listBox(page);
    expect(list.shown && list.hits > 1, `${name}: the list is not open with several hits`);
    expect(
      list.position === 'absolute' &&
        Math.abs(list.left) < 1 &&
        list.gap >= 0 &&
        list.gap <= 4 &&
        Math.abs(list.width - 360) < 1,
      `${name}: the list is not 360 px wide directly under the field (left ${list.left}, gap ${list.gap}, width ${list.width})`,
    );
    expect(
      list.background === 'rgb(255, 255, 255)' && list.border === `solid 1px ${NAVY}`,
      `${name}: the list is not a white box with a 1 px navy border (${list.background}, ${list.border})`,
    );
    expect(list.status === texts.count(list.hits), `${name}: status is "${list.status}"`);
    expect(list.oneLine && list.bold, `${name}: an excerpt is not one line with its match in bold`);
    await checkAxe(page, name);
    await checkNoSidewaysScroll(page, name);
    await page.screenshot({ path: shot('desktop') });

    // The hits follow the field in tab order, each with a focus ring; focus
    // does not move on its own.
    const before = await focused(page);
    expect(
      before?.description.startsWith('<input>'),
      `${name}: with the list open, focus is on ${before?.description}, not in the field`,
    );
    for (let index = 0; index < list.hits; index += 1) {
      await page.keyboard.press('Tab');
      const at = await focused(page);
      const inList = await page.evaluate(
        () => document.activeElement.closest('[data-search-results]') !== null,
      );
      expect(inList, `${name}: Tab ${index + 1} after the field lands on ${at?.description}, not on a hit`);
      expect(at?.ring === RING, `${name}: hit ${at?.description} has no focus ring (outline: ${at?.outline})`);
      expect(
        at && at.width >= 24 && at.height >= 24 && at.inView,
        `${name}: hit ${at?.description} is below 24 × 24 px or outside the window`,
      );
    }
    // Focus leaves the search: the list closes and covers nothing.
    await page.keyboard.press('Tab');
    const after = await listBox(page);
    expect(!after.shown, `${name}: the list stays open when focus leaves the search`);
    expect(
      (await focused(page))?.inView,
      `${name}: the element after the search is outside the window when it has focus`,
    );

    // No match.
    await searchFor(page, noMatchTerm);
    const none = await listBox(page);
    expect(
      none.shown && none.hits === 0 && none.status === texts.noMatch(noMatchTerm),
      `${name}: no match: status is "${none.status}" with ${none.hits} hits`,
    );
    await checkAxe(page, `${name}, no match`);
    await page.screenshot({ path: shot('desktop-no-match') });

    // At the phone breakpoint the list stays inside the window.
    await page.setViewportSize({ width: 600, height: 800 });
    await settle(page, () => document.querySelector('body > header input[type="search"]') !== null);
    await searchFor(page, '');
    await searchFor(page, texts.sharedWord);
    const narrow = await listBox(page);
    expect(
      narrow.shown && narrow.right <= narrow.window,
      `${name}: at 600 px the list ends at ${narrow.right} px in a window of ${narrow.window} px`,
    );
    await checkNoSidewaysScroll(page, `${entry.address} (600 px, search result list)`);
    await context.close();
  }

  // In the menu on the phone.
  {
    const name = `${entry.address} (${PHONE.width} px, menu, search result list)`;
    const { context, page } = await open(browser, origin, entry, PHONE);
    const tree = page.locator('#chapters');
    await page.locator('button[data-menu-button]').click();
    await searchFor(page, texts.sharedWord);
    const list = await listBox(page);
    expect(list.shown && list.hits > 1, `${name}: the list is not open with several hits`);
    expect(
      list.position === 'static' &&
        Math.abs(list.left) < 1 &&
        list.gap >= 0 &&
        list.gap <= 4 &&
        Math.abs(list.width - list.fieldWidth) < 1,
      `${name}: the list does not stand in the flow under the field at its width (left ${list.left}, gap ${list.gap}, width ${list.width} of ${list.fieldWidth})`,
    );
    expect(list.treeBelow, `${name}: the list does not push the chapter tree down`);
    expect(
      list.background === 'rgb(255, 255, 255)' && list.border === `solid 1px ${NAVY}`,
      `${name}: the list is not a white box with a 1 px navy border (${list.background}, ${list.border})`,
    );
    expect(list.oneLine && list.bold, `${name}: an excerpt is not one line with its match in bold`);
    await checkAxe(page, name);
    await checkNoSidewaysScroll(page, name);
    await page.screenshot({ path: shot('menu'), fullPage: true });

    // Escape in the field: the list closes, the menu stays, focus stays.
    await page.keyboard.press('Escape');
    const escaped = await listBox(page);
    expect(
      !escaped.shown &&
        (await tree.isVisible()) &&
        (await page.locator('input[type="search"]').evaluate((input) => input === document.activeElement)) &&
        (await page.locator('input[type="search"]').inputValue()) === texts.sharedWord,
      `${name}: Escape in the field does not close the list alone, with focus and term kept`,
    );

    // No match.
    await searchFor(page, noMatchTerm);
    const none = await listBox(page);
    expect(
      none.shown && none.hits === 0 && none.status === texts.noMatch(noMatchTerm),
      `${name}: no match: status is "${none.status}" with ${none.hits} hits`,
    );
    await checkAxe(page, `${name}, no match`);
    await page.screenshot({ path: shot('menu-no-match'), fullPage: true });

    // 320 px, the list open with hits and with no match.
    await page.setViewportSize({ width: 320, height: 640 });
    await checkNoSidewaysScroll(page, `${entry.address} (320 px, menu, search result list, no match)`);
    await searchFor(page, texts.sharedWord);
    expect((await listBox(page)).shown, `${name}: at 320 px the list is not open`);
    await checkNoSidewaysScroll(page, `${entry.address} (320 px, menu, search result list)`);
    await checkAxe(page, `${entry.address} (320 px, menu, search result list)`);
    await context.close();
  }
}

/** A page-not-found page: the frame without the marks of a page on the path. */
async function checkNotFound(browser, origin, entry) {
  const at = (width, note = '') => `${entry.address} (${width} px${note})`;
  const shot = (kind) => path.join(shots, `not-found-${kind}-${entry.lang}.png`);

  // Desktop.
  {
    const name = at(DESKTOP.width);
    const { context, page } = await open(browser, origin, entry, DESKTOP);
    expect((await page.title()) === entry.title, `${name}: title is "${await page.title()}"`);
    for (const [part, selector] of [
      ['top bar', 'body > header'],
      ['chapter tree', '#chapters nav'],
      ['search field', 'body > header input[type="search"]'],
      ['footer', 'body > footer'],
    ]) {
      const found = page.locator(selector);
      expect(
        (await found.count()) === 1 && (await found.first().isVisible()),
        `${name}: the ${part} is not in the page once and visible`,
      );
    }
    expect(
      (await page.locator('h1').count()) === 1 &&
        (await page.locator('h1').innerText()).trim() === entry.name,
      `${name}: the one level-1 heading is not "${entry.name}"`,
    );
    for (const [part, selector] of [
      ['stage line', '[data-stage-line]'],
      ['page links', 'nav[data-page-links]'],
      ['current page in the tree', '#chapters a[aria-current="page"]'],
      ['current stage in the tree', '#chapters [data-current-stage]'],
    ]) {
      expect((await page.locator(selector).count()) === 0, `${name}: the page has a ${part}`);
    }
    // Two blocks: the page's language first; the other carries its language.
    const blocks = await page.evaluate(() =>
      [...document.querySelectorAll('main [data-not-found-block]')].map((block) => ({
        lang: block.closest('[lang]').getAttribute('lang'),
        own: block.closest('[lang]') === document.documentElement,
        heading: block.querySelector('h2')?.textContent.trim(),
      })),
    );
    expect(
      blocks.length === 2 &&
        blocks[0].own &&
        blocks[0].lang === entry.lang &&
        !blocks[1].own &&
        blocks[1].lang === entry.otherLang &&
        blocks[1].heading === entry.otherName,
      `${name}: not two blocks, "${entry.lang}" first and "${entry.otherLang}" marked with its language: ${JSON.stringify(blocks)}`,
    );
    for (const link of entry.overviewLinks) {
      const found = page.locator('main').getByRole('link', { name: link.name, exact: true });
      expect(
        (await found.count()) === 1 && (await found.getAttribute('href')) === link.address,
        `${name}: no link "${link.name}" to ${link.address}`,
      );
    }
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    await page.screenshot({ path: shot('desktop'), fullPage: true });
    await checkSkipLink(page, name);
    await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
    await checkTabOrder(page, name);
    await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
    await checkLanguageSwitch(page, name, entry, origin, '');
    await context.close();
  }

  // Phone.
  {
    const name = at(PHONE.width);
    const { context, page } = await open(browser, origin, entry, PHONE);
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    await page.screenshot({ path: shot('phone'), fullPage: true });
    await checkMenu(page, name, { phone: true });
    await page.setViewportSize({ width: 320, height: 640 });
    await checkNoSidewaysScroll(page, at(320));
    await context.close();
  }
}

/**
 * The root page. A browser that names a language is led on, so the check
 * uses one that names none: the page then stays, as the page says it does.
 */
async function checkRoot(browser, origin, entry) {
  for (const [viewport, kind] of [
    [DESKTOP, 'desktop'],
    [PHONE, 'phone'],
  ]) {
    const name = `${entry.address} (${viewport.width} px)`;
    const context = await browser.newContext({ viewport });
    await context.addInitScript(() => {
      const none = { get: () => undefined };
      Object.defineProperty(Object.getPrototypeOf(navigator), 'languages', none);
      Object.defineProperty(Object.getPrototypeOf(navigator), 'language', none);
    });
    const page = await context.newPage();
    await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
    expect(
      page.url() === `${origin}${entry.address}`,
      `${name}: a browser that names no language is led on to ${page.url()}`,
    );
    expect((await page.title()) === entry.title, `${name}: title is "${await page.title()}"`);
    expect(
      (await page.locator('header img').isVisible()) &&
        (await page.locator('header img').getAttribute('alt')) !== '',
      `${name}: no logo with a text alternative`,
    );
    expect((await page.locator('h1').count()) === 1, `${name}: not exactly one level-1 heading`);
    for (const { lang, name: documentation } of entry.names) {
      const found = page.locator(`h1 [lang="${lang}"]`);
      expect(
        (await found.count()) === 1 && (await found.innerText()).trim() === documentation,
        `${name}: the heading does not name "${documentation}" marked as "${lang}"`,
      );
    }
    for (const link of entry.links) {
      const found = page.getByRole('link', { name: link.name, exact: true });
      expect(
        (await found.count()) === 1 &&
          (await found.isVisible()) &&
          (await found.getAttribute('href')) === link.address &&
          (await found.getAttribute('lang')) === link.lang,
        `${name}: no visible link "${link.name}" to ${link.address} that carries lang="${link.lang}"`,
      );
    }
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    await page.screenshot({ path: path.join(shots, `root-${kind}.png`), fullPage: true });
    await checkTabOrder(page, name);
    if (viewport === PHONE) {
      await page.setViewportSize({ width: 320, height: 640 });
      await checkNoSidewaysScroll(page, `${entry.address} (320 px)`);
    }
    await context.close();
  }
}

async function checkEntry(browser, origin, entry) {
  const at = (width, note = '') => `${entry.address} (${width} px${note})`;
  const shot = (kind) => (entry.isRoot ? path.join(shots, `${kind}-${entry.lang}.png`) : undefined);

  // Desktop.
  {
    const name = at(DESKTOP.width);
    const { context, page } = await open(browser, origin, entry, DESKTOP);
    await checkFrame(page, name, entry);
    await checkNoSidewaysScroll(page, name);
    for (const selector of ['[data-menu-button]', '[data-menu-link]', '[data-menu-close]']) {
      expect(
        !(await page.locator(selector).isVisible()),
        `${name}: ${selector} shows from the tree breakpoint up`,
      );
    }
    await checkAxe(page, name);
    if (entry.isRoot) await page.screenshot({ path: shot('desktop'), fullPage: true });
    await checkSkipLink(page, name);
    await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
    await checkTabOrder(page, name);
    await context.close();
  }

  // Desktop, loaded with an anchor: the language switch keeps it, and the one
  // set afterwards.
  {
    const name = at(DESKTOP.width);
    const { context, page } = await open(browser, origin, entry, DESKTOP, { anchor: ANCHOR });
    const target = () => page.locator('a[data-counterpart]:visible').getAttribute('href');
    expect(
      (await target()) === `${entry.counterpart}${ANCHOR}`,
      `${name}: loaded with ${ANCHOR}, the language switch leads to ${await target()}`,
    );
    await page.evaluate((anchor) => {
      window.location.hash = anchor;
    }, LATER_ANCHOR);
    await page.waitForFunction(
      (anchor) => document.querySelector('a[data-counterpart]')?.getAttribute('href')?.endsWith(anchor),
      LATER_ANCHOR,
      { timeout: 5_000 },
    ).catch(() => {});
    await checkLanguageSwitch(page, name, entry, origin, LATER_ANCHOR);
    await context.close();
  }

  // Phone.
  {
    const name = at(PHONE.width);
    const { context, page } = await open(browser, origin, entry, PHONE);
    for (const [part, selector, visible] of [
      ['menu button', 'body > header button[data-menu-button]', true],
      ['logo', 'body > header img', true],
      ['language switch', 'body > header a[data-counterpart]', true],
      ['product title', 'body > header > span:not([data-release])', false],
      ['release badge', 'body > header [data-release]', false],
      ['search field', 'body > header input', false],
      ['product-page link', 'body > header a[href$="/deltarecon"]', false],
    ]) {
      const shown = (await page.locator(selector).count()) > 0 && (await page.locator(selector).first().isVisible());
      expect(shown === visible, `${name}: top bar: the ${part} is ${shown ? 'shown' : 'not shown'}`);
    }
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    if (entry.isRoot) await page.screenshot({ path: shot('phone'), fullPage: true });
    await checkMenu(page, name, {
      phone: true,
      screenshot: shot('menu'),
      hitWord: entry.isRoot ? ownWords[entry.lang] : undefined,
    });
    await page.setViewportSize({ width: 320, height: 640 });
    await checkNoSidewaysScroll(page, at(320));
    // The open menu at 320 px: its top bar is one row.
    await page.locator('button[data-menu-button]').click();
    const bar = await page.evaluate(() => ({
      height: document.querySelector('body > header').getBoundingClientRect().height,
    }));
    expect(bar.height <= 57, `${at(320, ', open menu')}: the top bar is ${bar.height} px high, not one row`);
    expect(
      (await page.getByRole('button', { name: entry.texts.close, exact: true }).count()) === 1,
      `${at(320, ', open menu')}: the close button is not named "${entry.texts.close}"`,
    );
    await checkNoSidewaysScroll(page, at(320, ', open menu'));
    await checkAxe(page, at(320, ', open menu'));
    await page.keyboard.press('Escape');
    await context.close();
  }

  // Phone, JavaScript off.
  {
    const name = at(PHONE.width, ', JavaScript off');
    const { context, page } = await open(browser, origin, entry, PHONE, {
      javaScript: false,
      anchor: ANCHOR,
    });
    const link = page.locator('body > header a[data-menu-link]');
    expect(
      (await link.isVisible()) && (await link.getAttribute('href')) === '#chapters',
      `${name}: the menu button is not a link to the chapter tree`,
    );
    expect(
      (await page.locator('button:visible').count()) === 0,
      `${name}: a button that needs a script is visible`,
    );
    const order = await page.evaluate(() => {
      const tree = document.getElementById('chapters').getBoundingClientRect();
      const main = document.querySelector('main').getBoundingClientRect();
      const footer = document.querySelector('body > footer').getBoundingClientRect();
      return tree.top >= main.bottom && footer.top >= tree.bottom;
    });
    expect(order, `${name}: the chapter tree does not stand at the end of the page, before the footer`);
    await checkNoSidewaysScroll(page, name);
    await link.click();
    expect(new URL(page.url()).hash === '#chapters', `${name}: the menu link does not jump to the tree`);
    expect(
      await page.locator('#chapters a[aria-current="page"]').isVisible(),
      `${name}: the chapter tree is not readable`,
    );
    await page.goto(`${origin}${entry.address}${ANCHOR}`);
    await checkLanguageSwitch(page, name, entry, origin, '');
    await context.close();
  }

  // Between phone and tree breakpoint: the start pages.
  if (entry.isRoot) {
    const name = at(BETWEEN.width);
    const { context, page } = await open(browser, origin, entry, BETWEEN);
    for (const [part, selector] of [
      ['menu button', 'body > header button[data-menu-button]'],
      ['mark of DeltaRecon', 'body > header svg[data-product-mark][aria-hidden="true"]'],
      ['release badge', 'body > header [data-release]'],
      ['search field', 'body > header input'],
      ['product-page link', 'body > header a[href$="/deltarecon"]'],
    ]) {
      expect(await page.locator(selector).isVisible(), `${name}: top bar: no ${part}`);
    }
    await checkNoSidewaysScroll(page, name);
    await checkAxe(page, name);
    await page.screenshot({ path: shot('between'), fullPage: true });
    await checkMenu(page, name, { phone: false });

    // An open menu ends when the window reaches the tree breakpoint.
    await page.locator('button[data-menu-button]').click();
    await page.setViewportSize(DESKTOP);
    await settle(page, () => document.documentElement.dataset.menu === 'closed');
    const widened = await page.evaluate(() => ({
      menu: document.documentElement.dataset.menu,
      inert: [...document.querySelectorAll('main, body > footer')].some((part) => part.inert),
    }));
    expect(
      widened.menu === 'closed' && !widened.inert && (await page.locator('main').isVisible()),
      `${name}: an open menu stays open at ${DESKTOP.width} px`,
    );
    expect(
      (await focused(page)) !== null,
      `${name}: focus is lost when an open menu ends at ${DESKTOP.width} px`,
    );

    await page.setViewportSize({ width: 600, height: 800 });
    await settle(page, () => document.querySelector('body > header input[type="search"]') !== null);
    await checkNoSidewaysScroll(page, at(600));
    // The search field moves into the menu below the phone breakpoint, and back.
    const inBar = page.locator('body > header input[type="search"]');
    const inMenu = page.locator('#chapters input[type="search"]');
    expect(
      (await inBar.count()) === 1 && (await inMenu.count()) === 0,
      `${at(600)}: the search field is not in the top bar`,
    );
    await page.setViewportSize(PHONE);
    await settle(page, () => document.querySelector('#chapters input[type="search"]') !== null);
    expect(
      (await inBar.count()) === 0 && (await inMenu.count()) === 1,
      `${name}: narrowed to ${PHONE.width} px, the search field is not in the menu`,
    );
    await page.setViewportSize(BETWEEN);
    await settle(page, () => document.querySelector('body > header input[type="search"]') !== null);
    expect(
      (await inBar.count()) === 1 && (await inMenu.count()) === 0,
      `${name}: widened again, the search field is not back in the top bar`,
    );
    await context.close();
  }

  // The search result list: the start pages.
  if (entry.isRoot) await checkSearchList(browser, origin, entry);
}

const { origin: reported, stop } = startPreview();
let browser;
try {
  const origin = await reported;
  await mkdir(shots, { recursive: true });
  browser = await chromium.launch();
  // An error on one page is a failure of that page; the others still run.
  const each = async (entry, check) => {
    try {
      await check(browser, origin, entry);
    } catch (error) {
      failures.push(`${entry.address}: ${error.stack ?? error.message}`);
    }
  };
  for (const entry of pages) await each(entry, checkEntry);
  for (const entry of notFound) await each(entry, checkNotFound);
  await each(rootPage, checkRoot);
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(
  `all ${pages.length} pages, the ${notFound.length} page-not-found pages, the root page and the search result list pass; screenshots in screenshots/`,
);
