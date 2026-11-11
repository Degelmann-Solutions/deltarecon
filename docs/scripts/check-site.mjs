// Checks the built site in Chromium. Run after the build: `npm run check`.
//
// Starts `astro preview` on a port of its own, reads the address the server
// reports, and asserts for both languages:
//   - the stub page: language, release number, link to the counterpart;
//   - the same with JavaScript off, and that no search field is in the page;
//   - the search finds a word of its own language and not one of the other;
//   - a missing search index leaves the page readable and shows a status;
//   - no request leaves the local origin.
// Exits non-zero and names every failed expectation.
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 4399;
const BASE = '/deltarecon/docs/';

// A word that only the page of that language holds.
const pages = {
  de: { ownWord: 'Baustelle', counterpart: 'en' },
  en: { ownWord: 'scaffold', counterpart: 'de' },
};

const { version } = JSON.parse(await readFile(path.join(root, 'src/release.json'), 'utf8'));

const failures = [];
function expect(condition, message) {
  if (!condition) failures.push(message);
}

/** Starts the preview server and resolves with the origin it reports. */
function startPreview() {
  const server = spawn(
    process.execPath,
    [path.join(root, 'node_modules/astro/astro.js'), 'preview', '--port', String(PORT)],
    { cwd: root, env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' } },
  );
  const origin = new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(
      () => reject(new Error(`preview reported no address within 30 s:\n${output}`)),
      30_000,
    );
    const read = (chunk) => {
      output += chunk;
      // Drop colour codes, then take the first address the server prints.
      const match = /https?:\/\/[\w.\-[\]:]+/.exec(output.replace(/\u001b\[[0-9;]*m/g, ''));
      if (match) {
        clearTimeout(timer);
        resolve(new URL(match[0]).origin);
      }
    };
    server.stdout.on('data', read);
    server.stderr.on('data', read);
    server.on('error', reject);
    server.on('exit', (code) => reject(new Error(`preview ended with code ${code}:\n${output}`)));
  });
  return { server, origin };
}

/** Opens a page in a context of its own and records what the checks need. */
async function open(browser, origin, lang, { javaScript = true, blockIndex = false } = {}) {
  const context = await browser.newContext({ javaScriptEnabled: javaScript });
  const page = await context.newPage();
  const name = `/${lang}/ (JavaScript ${javaScript ? 'on' : 'off'}${blockIndex ? ', index missing' : ''})`;
  const scriptErrors = [];
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return;
    expect(url.origin === origin, `${name}: request to a third party: ${request.url()}`);
  });
  if (blockIndex) {
    await page.route('**/pagefind/**', (route) => route.fulfill({ status: 404, body: 'Not found' }));
  }
  const response = await page.goto(`${origin}${BASE}${lang}/`, { waitUntil: 'networkidle' });
  expect(response?.status() === 200, `${name}: status ${response?.status()}, expected 200`);
  return { context, page, name, scriptErrors };
}

/** The stub page: language, text, release number, link to the counterpart. */
async function checkStub(page, name, lang) {
  const { ownWord, counterpart } = pages[lang];
  expect(
    (await page.getAttribute('html', 'lang')) === lang,
    `${name}: <html lang> is not "${lang}"`,
  );
  const text = await page.innerText('body');
  expect(text.includes(ownWord), `${name}: the page text lacks "${ownWord}"`);
  expect(text.includes(version), `${name}: the page does not show the release number ${version}`);
  const link = page.locator(`a[href="${BASE}${counterpart}/"]`);
  expect((await link.count()) === 1, `${name}: no link to ${BASE}${counterpart}/`);
  if ((await link.count()) === 1) {
    expect(await link.isVisible(), `${name}: the link to the counterpart is not visible`);
  }
}

/** Types a term and returns the addresses of the hits listed for it. */
async function search(page, term) {
  await page.fill('input[type="search"]', term);
  const list = page.locator(`[data-search-results="${term}"]`);
  await list.waitFor({ state: 'attached', timeout: 10_000 });
  return list.locator('a').evaluateAll((links) => links.map((a) => a.getAttribute('href')));
}

async function checkLanguage(browser, origin, lang) {
  const other = pages[lang].counterpart;

  // JavaScript on: stub page and search.
  {
    const { context, page, name, scriptErrors } = await open(browser, origin, lang);
    await checkStub(page, name, lang);
    expect((await page.locator('input[type="search"]').count()) === 1, `${name}: no search field`);
    expect(
      (await page.locator('label[for]').count()) === 1,
      `${name}: the search field has no label`,
    );
    try {
      await page.waitForSelector('[data-search-status="ready"]', {
        state: 'attached',
        timeout: 10_000,
      });
      const own = await search(page, pages[lang].ownWord);
      expect(
        own.length === 1 && own[0] === `${BASE}${lang}/`,
        `${name}: search for "${pages[lang].ownWord}" gave [${own}], expected [${BASE}${lang}/]`,
      );
      const foreign = await search(page, pages[other].ownWord);
      expect(
        foreign.length === 0,
        `${name}: search for "${pages[other].ownWord}" gave [${foreign}], expected no hit`,
      );
    } catch (error) {
      failures.push(`${name}: the search did not answer: ${error.message}`);
    }
    expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
    await context.close();
  }

  // JavaScript off: readable, no search field.
  {
    const { context, page, name } = await open(browser, origin, lang, { javaScript: false });
    await checkStub(page, name, lang);
    expect(
      (await page.locator('input').count()) === 0,
      `${name}: a search field is in the page without JavaScript`,
    );
    await context.close();
  }

  // Search index missing: readable, plain status, no uncaught error.
  {
    const { context, page, name, scriptErrors } = await open(browser, origin, lang, {
      blockIndex: true,
    });
    await checkStub(page, name, lang);
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

const { server, origin: reported } = startPreview();
let browser;
try {
  const origin = await reported;
  browser = await chromium.launch();
  for (const lang of Object.keys(pages)) {
    await checkLanguage(browser, origin, lang);
  }
} catch (error) {
  failures.push(error.message);
} finally {
  await browser?.close();
  server.removeAllListeners('exit');
  server.kill();
}

if (failures.length > 0) {
  console.error(`check-site: ${failures.length} failed`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`check-site: both pages pass (release ${version})`);
