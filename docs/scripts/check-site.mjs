// Checks the built site in Chromium. Run after the build: `npm run check`.
//
// Starts `astro preview` on a port of its own, reads the address the server
// reports, and asserts for every page of the page register:
//   - language, release number, link to the counterpart;
//   - the same with JavaScript off, and that no search field is in the page;
//   - no request leaves the local origin, and every file the page loads
//     (typeface, logo, script) is served;
// and for the start page of each language:
//   - the search finds a word of its own language and not one of the other;
//   - a missing search index leaves the page readable and shows a status.
// Exits non-zero and names every failed expectation.
import { chromium } from 'playwright';
import { expectations, loadPages, loadRelease, startPreview } from './harness.mjs';

// A word that only the start page of that language holds.
const ownWords = { de: 'Baustelle', en: 'scaffold' };

const version = await loadRelease();
const pages = await loadPages();
const { failures, expect, report } = expectations('check-site');

/** Opens a page in a context of its own and records what the checks need. */
async function open(browser, origin, entry, { javaScript = true, blockIndex = false } = {}) {
  const context = await browser.newContext({ javaScriptEnabled: javaScript });
  const page = await context.newPage();
  const name = `${entry.address} (JavaScript ${javaScript ? 'on' : 'off'}${blockIndex ? ', index missing' : ''})`;
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
  const response = await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
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
    const ownWord = ownWords[entry.lang];
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

/** Types a term and returns the addresses of the hits listed for it. */
async function search(page, term) {
  await page.fill('input[type="search"]', term);
  const list = page.locator(`[data-search-results="${term}"]`);
  await list.waitFor({ state: 'attached', timeout: 10_000 });
  return list.locator('a').evaluateAll((links) => links.map((a) => a.getAttribute('href')));
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
      const ownWord = ownWords[entry.lang];
      const foreignWord = ownWords[entry.otherLang];
      try {
        await page.waitForSelector('[data-search-status="ready"]', {
          state: 'attached',
          timeout: 10_000,
        });
        const own = await search(page, ownWord);
        expect(
          own.length === 1 && own[0] === entry.address,
          `${name}: search for "${ownWord}" gave [${own}], expected [${entry.address}]`,
        );
        const foreign = await search(page, foreignWord);
        expect(
          foreign.length === 0,
          `${name}: search for "${foreignWord}" gave [${foreign}], expected no hit`,
        );
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

  // Search index missing: readable, plain status, no uncaught error.
  if (entry.isRoot) {
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
    } catch (error) {
      failures.push(`${name}: no "not available" status: ${error.message}`);
    }
    expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
    await context.close();
  }
}

const { origin: reported, stop } = startPreview();
let browser;
try {
  const origin = await reported;
  browser = await chromium.launch();
  for (const entry of pages) {
    // An error on one page is a failure of that page; the others still run.
    try {
      await checkEntry(browser, origin, entry);
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

report(`all ${pages.length} pages pass (release ${version})`);
