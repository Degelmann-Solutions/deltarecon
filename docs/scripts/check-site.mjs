// Checks the built site in Chromium. Run after the build: `npm run check`.
//
// Starts `astro preview` on a port of its own, reads the address the server
// reports, and asserts for every page of the page register and for the
// page-not-found page of each language:
//   - language, release number, link to the counterpart;
//   - the same with JavaScript off, and that no search field is in the page;
//   - no request leaves the local origin, and every file the page loads
//     (typeface, logo, script) is served;
// for the start page of each language, the search:
//   - nothing is shown or said at the load of the page;
//   - a word of its own language gives its hits and the number of matches;
//     each hit shows the page name as a link, the stage line of that page and
//     an excerpt with the matched word marked;
//   - a word of the other language, and a word of the page-not-found page,
//     give no hit and the no-match text with the term;
//   - an emptied field empties and hides the list;
//   - Escape closes the list, keeps focus and term in the field; typing and
//     focusing the field open it again; Escape on a hit closes the list and
//     puts focus into the field;
//   - a slow search index shows the loading text once a term is typed, then
//     the answer;
//   - a missing search index leaves the page readable and shows the
//     "not available" text, at the load and after a term is typed;
// for the page-not-found pages: the search finds the start page;
// for the root page: with JavaScript off it stays and offers both languages,
// each link in its own language; with JavaScript it leads on to a language.
// Exits non-zero and names every failed expectation.
import { chromium } from 'playwright';
import {
  expectations,
  loadOtherPages,
  loadPages,
  loadRelease,
  searchTexts,
  startPreview,
} from './harness.mjs';

const version = await loadRelease();
const pages = await loadPages();
const { notFound, rootPage } = await loadOtherPages();
const { failures, expect, report } = expectations('check-site');

/** Opens a page in a context of its own and records what the checks need. */
async function open(
  browser,
  origin,
  entry,
  { javaScript = true, blockIndex = false, slowIndex = 0, waitUntil = 'networkidle' } = {},
) {
  const context = await browser.newContext({ javaScriptEnabled: javaScript });
  const page = await context.newPage();
  const note = blockIndex ? ', index missing' : slowIndex ? ', index slow' : '';
  const name = `${entry.address} (JavaScript ${javaScript ? 'on' : 'off'}${note})`;
  const scriptErrors = [];
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return;
    expect(url.origin === origin, `${name}: request to a third party: ${request.url()}`);
  });
  page.on('response', (answer) => {
    // The missing index is the case under test there.
    if (blockIndex && new URL(answer.url()).pathname.includes('/pagefind/')) return;
    expect(answer.status() < 400, `${name}: ${answer.url()} answered ${answer.status()}`);
  });
  page.on('requestfailed', (request) => {
    if (blockIndex && new URL(request.url()).pathname.includes('/pagefind/')) return;
    failures.push(`${name}: ${request.url()} failed: ${request.failure()?.errorText}`);
  });
  if (blockIndex) {
    await page.route('**/pagefind/**', (route) => route.fulfill({ status: 404, body: 'Not found' }));
  }
  if (slowIndex) {
    await page.route('**/pagefind/pagefind.js', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, slowIndex));
      await route.continue().catch(() => {});
    });
  }
  const response = await page.goto(`${origin}${entry.address}`, { waitUntil });
  expect(response?.status() === 200, `${name}: status ${response?.status()}, expected 200`);
  return { context, page, name, scriptErrors };
}

/** Every page: language, page name, release number, link to the counterpart. */
async function checkPage(page, name, entry) {
  expect(
    (await page.getAttribute('html', 'lang')) === entry.lang,
    `${name}: <html lang> is not "${entry.lang}"`,
  );
  const text = await page.innerText('body');
  expect(text.includes(entry.name), `${name}: the page text lacks the page name "${entry.name}"`);
  if (entry.isRoot) {
    const { ownWord } = searchTexts[entry.lang];
    expect(text.includes(ownWord), `${name}: the page text lacks "${ownWord}"`);
  }
  expect(text.includes(version), `${name}: the page does not show the release number ${version}`);
  const link = page.locator(`a[data-counterpart][href="${entry.counterpart}"]`);
  expect((await link.count()) === 1, `${name}: not exactly one link to ${entry.counterpart}`);
  if ((await link.count()) === 1) {
    expect(await link.isVisible(), `${name}: the link to the counterpart is not visible`);
    expect(
      (await link.getAttribute('hreflang')) === entry.otherLang,
      `${name}: the link to the counterpart does not carry hreflang="${entry.otherLang}"`,
    );
  }
}

/** What the search shows: the box, the status line, the hits. */
function searchState(page) {
  return page.evaluate(() => {
    const panel = document.querySelector('[data-search] .search-panel');
    const status = document.querySelector('[data-search] [role="status"]');
    const field = document.querySelector('[data-search] input');
    const box = panel?.getBoundingClientRect();
    const text = (element) => (element?.textContent ?? '').trim().replace(/\s+/g, ' ');
    return {
      hasStatus: status !== null,
      statusInTree: Boolean(status && getComputedStyle(status).display !== 'none'),
      status: text(status),
      state: status?.dataset.searchStatus,
      shown: Boolean(panel && !panel.hasAttribute('data-empty') && box.width > 1 && box.height > 1),
      focusInField: document.activeElement === field,
      value: field?.value,
      hits: [...document.querySelectorAll('[data-search-results] > li')].map((item) => ({
        links: item.querySelectorAll('a').length,
        address: item.querySelector('a')?.getAttribute('href'),
        name: text(item.querySelector('a')),
        stage: text(item.querySelector('.search-hit-stage')),
        excerpt: text(item.querySelector('.search-hit-excerpt')),
        marked: [...item.querySelectorAll('.search-hit-excerpt mark')].map((mark) => text(mark)),
        visible: item.getClientRects().length > 0,
      })),
    };
  });
}

/** Types a term and returns what the search shows once it has answered. */
async function search(page, term) {
  await page.fill('input[type="search"]', term);
  await page
    .locator(`[data-search-results="${term}"]`)
    .waitFor({ state: 'attached', timeout: 15_000 });
  return searchState(page);
}

/** The hits of a term: their number, and name, stage line and excerpt of each. */
function checkHits(name, term, shown, expected, lang) {
  const texts = searchTexts[lang];
  expect(
    shown.hits.length === expected.length &&
      expected.every((entry) => shown.hits.some((hit) => hit.address === entry.address)),
    `${name}: search for "${term}" gave [${shown.hits.map((hit) => hit.address)}], expected [${expected.map((entry) => entry.address)}]`,
  );
  expect(
    shown.shown && shown.status === texts.count(shown.hits.length),
    `${name}: search for "${term}": status is "${shown.status}" (list ${shown.shown ? 'shown' : 'not shown'}), expected "${texts.count(shown.hits.length)}"`,
  );
  for (const hit of shown.hits) {
    const entry = expected.find((candidate) => candidate.address === hit.address);
    if (!entry) continue;
    expect(
      hit.visible && hit.links === 1 && hit.name === entry.name,
      `${name}: search for "${term}": the hit ${hit.address} is named "${hit.name}", expected the one link "${entry.name}"`,
    );
    expect(
      hit.stage === entry.stageLine,
      `${name}: search for "${term}": the hit ${hit.address} shows the stage line "${hit.stage}", expected "${entry.stageLine}"`,
    );
    expect(
      hit.excerpt !== '' &&
        hit.marked.some((word) => word.toLowerCase().includes(term.toLowerCase())),
      `${name}: search for "${term}": the excerpt of ${hit.address} is "${hit.excerpt}" with [${hit.marked}] marked`,
    );
  }
}

/** The search on the start page of a language. */
async function checkSearch(page, name, entry) {
  const texts = searchTexts[entry.lang];
  const ofLanguage = pages.filter((candidate) => candidate.lang === entry.lang);

  // At the load of the page: the status element is there, empty and unseen.
  await page.waitForSelector('[data-search-status="ready"]', { state: 'attached', timeout: 10_000 });
  const atLoad = await searchState(page);
  expect(
    atLoad.hasStatus && atLoad.status === '' && !atLoad.shown,
    `${name}: at the load the search shows "${atLoad.status}" or its list`,
  );
  expect(
    atLoad.statusInTree,
    `${name}: the empty status element is "display: none", so its text would not be announced`,
  );
  expect(
    (await page.getByRole('searchbox', { name: texts.label, exact: true }).count()) === 1 &&
      (await page.getAttribute('input[type="search"]', 'placeholder')) === texts.label,
    `${name}: label and placeholder of the search field are not "${texts.label}"`,
  );

  // Hits: one page, then several pages.
  checkHits(name, texts.ownWord, await search(page, texts.ownWord), [entry], entry.lang);
  const shared = await search(page, texts.sharedWord);
  expect(
    shared.hits.length > 1 &&
      shared.hits.every((hit) => ofLanguage.some((candidate) => candidate.address === hit.address)),
    `${name}: search for "${texts.sharedWord}" gave [${shared.hits.map((hit) => hit.address)}], expected several pages of "${entry.lang}"`,
  );
  checkHits(
    name,
    texts.sharedWord,
    shared,
    ofLanguage.filter((candidate) => shared.hits.some((hit) => hit.address === candidate.address)),
    entry.lang,
  );

  // No match: a word of the other language, a word of the page-not-found page.
  for (const term of [searchTexts[entry.otherLang].ownWord, texts.notFoundWord]) {
    const none = await search(page, term);
    expect(
      none.hits.length === 0 && none.shown && none.status === texts.noMatch(term),
      `${name}: search for "${term}" gave ${none.hits.length} hits and the status "${none.status}", expected "${texts.noMatch(term)}"`,
    );
  }

  // Field emptied: list and status empty, the box not shown.
  const emptied = await search(page, '');
  expect(
    emptied.hits.length === 0 && emptied.status === '' && !emptied.shown,
    `${name}: with the field emptied the search still shows "${emptied.status}", ${emptied.hits.length} hits or its box`,
  );

  // Escape closes the list; focus and term stay. Typing opens it again, and
  // so does focusing the field.
  await search(page, texts.ownWord);
  await page.keyboard.press('Escape');
  const escaped = await searchState(page);
  expect(
    !escaped.shown && escaped.hits.every((hit) => !hit.visible),
    `${name}: Escape in the search field does not close the list`,
  );
  expect(
    escaped.focusInField && escaped.value === texts.ownWord,
    `${name}: after Escape focus is ${escaped.focusInField ? '' : 'not '}in the field, which holds "${escaped.value}"`,
  );
  await page.evaluate(() => {
    const field = document.querySelector('[data-search] input');
    field.blur();
    field.focus();
  });
  const refocused = await searchState(page);
  expect(
    refocused.shown && refocused.hits.length === 1 && refocused.hits[0].visible,
    `${name}: focusing the field with a term does not open the list again`,
  );
  // Escape on a hit: the list closes, focus goes into the field.
  await page.locator('[data-search-results] a').first().focus();
  await page.keyboard.press('Escape');
  const fromHit = await searchState(page);
  expect(
    !fromHit.shown && fromHit.focusInField && fromHit.value === texts.ownWord,
    `${name}: Escape on a hit does not close the list with focus and term in the field`,
  );
  const shorter = texts.ownWord.slice(0, -1);
  await page.keyboard.press('End');
  await page.keyboard.press('Backspace');
  await page
    .locator(`[data-search-results="${shorter}"]`)
    .waitFor({ state: 'attached', timeout: 15_000 });
  const retyped = await searchState(page);
  expect(
    retyped.shown && retyped.value === shorter,
    `${name}: typing after Escape does not open the list again`,
  );
}

async function checkEntry(browser, origin, entry) {
  // JavaScript on: the page; on the start page also the search.
  {
    const { context, page, name, scriptErrors } = await open(browser, origin, entry);
    await checkPage(page, name, entry);
    expect((await page.locator('input[type="search"]').count()) === 1, `${name}: no search field`);
    expect(
      (await page.locator('label[for]').count()) === 1,
      `${name}: the search field has no label`,
    );
    if (entry.isRoot) {
      try {
        await checkSearch(page, name, entry);
      } catch (error) {
        failures.push(`${name}: the search did not answer: ${error.message}`);
      }
    }
    expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
    await context.close();
  }

  // JavaScript off: readable, no search field.
  {
    const { context, page, name } = await open(browser, origin, entry, { javaScript: false });
    await checkPage(page, name, entry);
    expect(
      (await page.locator('input').count()) === 0,
      `${name}: a search field is in the page without JavaScript`,
    );
    await context.close();
  }

  if (!entry.isRoot) return;
  const texts = searchTexts[entry.lang];

  // Search index slow: nothing at the load; the loading text once a term is
  // typed; then the answer.
  {
    const { context, page, name, scriptErrors } = await open(browser, origin, entry, {
      slowIndex: 2_500,
      waitUntil: 'load',
    });
    try {
      await page.waitForSelector('[data-search] input', { state: 'attached' });
      const atLoad = await searchState(page);
      expect(
        atLoad.state === 'loading' && atLoad.status === '' && !atLoad.shown,
        `${name}: at the load the search is "${atLoad.state}" and shows "${atLoad.status}"`,
      );
      await page.fill('input[type="search"]', texts.ownWord);
      const typed = await searchState(page);
      expect(
        typed.shown && typed.status === texts.loading && typed.value === texts.ownWord,
        `${name}: with a term typed before the index answered the status is "${typed.status}", expected "${texts.loading}"`,
      );
      await page
        .locator(`[data-search-results="${texts.ownWord}"]`)
        .waitFor({ state: 'attached', timeout: 30_000 });
      checkHits(name, texts.ownWord, await searchState(page), [entry], entry.lang);
    } catch (error) {
      failures.push(`${name}: the search did not answer: ${error.message}`);
    }
    expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
    await context.close();
  }

  // Search index missing: readable, the "not available" status at the load
  // and after a term is typed, no uncaught error.
  {
    const { context, page, name, scriptErrors } = await open(browser, origin, entry, {
      blockIndex: true,
    });
    await checkPage(page, name, entry);
    try {
      const status = page.locator('[data-search-status="unavailable"]');
      await status.waitFor({ state: 'visible', timeout: 10_000 });
      const expected = await page.getAttribute('[data-search]', 'data-unavailable');
      const shown = (await status.innerText()).trim();
      expect(
        shown !== '' && shown === expected,
        `${name}: status is "${shown}", expected "${expected}"`,
      );
      expect(
        shown === texts.unavailable,
        `${name}: status is "${shown}", expected "${texts.unavailable}"`,
      );
      const typed = await search(page, texts.ownWord);
      expect(
        typed.shown && typed.status === texts.unavailable && typed.hits.length === 0,
        `${name}: status is "${typed.status}", expected "${texts.unavailable}"`,
      );
      expect(typed.value === texts.ownWord, `${name}: the field does not keep the typed term`);
    } catch (error) {
      failures.push(`${name}: no "not available" status: ${error.message}`);
    }
    expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
    await context.close();
  }
}

/** A page-not-found page: the frame in its language, and a search that works. */
async function checkNotFound(browser, origin, entry) {
  {
    const { context, page, name, scriptErrors } = await open(browser, origin, entry);
    await checkPage(page, name, entry);
    expect((await page.locator('input[type="search"]').count()) === 1, `${name}: no search field`);
    try {
      const start = pages.find((candidate) => candidate.isRoot && candidate.lang === entry.lang);
      await page.waitForSelector('[data-search-status="ready"]', { state: 'attached', timeout: 10_000 });
      const { ownWord } = searchTexts[entry.lang];
      checkHits(name, ownWord, await search(page, ownWord), [start], entry.lang);
    } catch (error) {
      failures.push(`${name}: the search did not answer: ${error.message}`);
    }
    expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
    await context.close();
  }
  {
    const { context, page, name } = await open(browser, origin, entry, { javaScript: false });
    await checkPage(page, name, entry);
    expect(
      (await page.locator('input').count()) === 0,
      `${name}: a search field is in the page without JavaScript`,
    );
    await context.close();
  }
}

/** The root page: stays without JavaScript, leads on with it. */
async function checkRoot(browser, origin, entry) {
  {
    const { context, page, name } = await open(browser, origin, entry, { javaScript: false });
    expect(page.url() === `${origin}${entry.address}`, `${name}: the page does not stay (${page.url()})`);
    expect(
      (await page.getAttribute('html', 'lang')) === entry.lang,
      `${name}: <html lang> is not "${entry.lang}"`,
    );
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
    expect((await page.locator('input').count()) === 0, `${name}: a field is in the page`);
    await context.close();
  }
  // With JavaScript, in a browser that asks for English (the default of the
  // check), the page leads on to the English start page. The Apache check
  // covers the other languages.
  {
    const context = await browser.newContext({ locale: 'en-GB' });
    const page = await context.newPage();
    const name = `${entry.address} (JavaScript on)`;
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return;
      expect(url.origin === origin, `${name}: request to a third party: ${request.url()}`);
    });
    await page.goto(`${origin}${entry.address}`);
    const target = `${origin}${entry.links.find((link) => link.lang === 'en').address}`;
    await page.waitForURL(target, { timeout: 10_000 }).catch(() => {});
    expect(page.url() === target, `${name}: ends at ${page.url()}, expected ${target}`);
    await context.close();
  }
}

const { origin: reported, stop } = startPreview();
let browser;
try {
  const origin = await reported;
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
  `all ${pages.length} pages, the ${notFound.length} page-not-found pages and the root page pass (release ${version})`,
);
