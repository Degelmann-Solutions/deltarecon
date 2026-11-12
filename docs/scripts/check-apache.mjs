// Checks what only Apache shows: the status and the page of an unknown
// address, and the root address. Run as `npm run check:apache`, which builds
// first. It needs Docker and is not part of `npm run check`.
//
// Starts the image httpd:2.4 on a free local port with `AllowOverride All`.
// The server root holds a stand-in for the company website: an `.htaccess`
// with the hosting's rule `ErrorDocument 404 /404.html` and that page. The
// build, dist/, is mounted read-only under /deltarecon/docs. In Chromium it
// asserts:
//   - an unknown address under de/ answers 404 with the German
//     page-not-found page, every other unknown address under the
//     documentation 404 with the English one; every file such a page loads
//     is served, and its search works;
//   - an unknown address outside the documentation answers 404 with the
//     stand-in page, so the rules of the documentation hold inside its folder
//     only;
//   - the root address, with and without the closing slash, leads on by the
//     languages of the browser, in their order, and to English where none is
//     German or English; with JavaScript off it stays, with status 200, and
//     offers both languages;
//   - an address under de/ or en/ is not redirected, whatever the browser
//     asks for.
// The container is stopped and removed in every outcome.
// Exits non-zero and names every failed expectation.
import { spawnSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import { access, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright';
import {
  BASE,
  expectations,
  loadOtherPages,
  loadPages,
  root,
  searchTexts,
} from './harness.mjs';

const IMAGE = 'httpd:2.4';
const HTDOCS = '/usr/local/apache2/htdocs';
const STAND_IN = 'Stand-in for the page-not-found page of the company website';

const pages = await loadPages();
const { notFound, rootPage } = await loadOtherPages();
const { failures, expect, report } = expectations('check-apache');
const start = (lang) => pages.find((entry) => entry.isRoot && entry.lang === lang);
const notFoundOf = (lang) => notFound.find((entry) => entry.lang === lang);

function docker(...args) {
  return spawnSync('docker', args, { encoding: 'utf8' });
}

/** Ends the script with a plain message; nothing has been started yet. */
function stopWith(message) {
  console.error(`check-apache: ${message}`);
  process.exit(1);
}

const dist = path.join(root, 'dist');
await access(path.join(dist, 'index.html')).catch(() =>
  stopWith('no build under dist/. Run `npm run check:apache`, which builds first.'),
);
const version = docker('version', '--format', '{{.Server.Version}}');
if (version.error || version.status !== 0) {
  stopWith(
    'Docker is not available. This check runs Apache in Docker; install and start Docker, then run it again.' +
      (version.stderr ? `\n${version.stderr.trim()}` : ''),
  );
}

// The stand-in for the company website and the server setting, in a folder
// of their own outside the working tree.
const work = await mkdtemp(path.join(os.tmpdir(), 'deltarecon-docs-apache-'));
const site = path.join(work, 'htdocs');
await mkdir(path.join(site, 'deltarecon', 'docs'), { recursive: true });
await writeFile(path.join(site, '.htaccess'), 'ErrorDocument 404 /404.html\n');
await writeFile(
  path.join(site, '404.html'),
  `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>404</title></head><body><p>${STAND_IN}</p></body></html>\n`,
);
await writeFile(
  path.join(work, 'check.conf'),
  `ServerName localhost\n<Directory "${HTDOCS}">\n    AllowOverride All\n</Directory>\n`,
);

const container = `deltarecon-docs-apache-${process.pid}`;
let removed = false;
function removeContainer() {
  if (removed) return;
  removed = true;
  docker('rm', '--force', '--volumes', container);
}
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    removeContainer();
    rmSync(work, { recursive: true, force: true });
    process.exit(1);
  });
}

/** Starts the container and resolves with the origin it answers on. */
async function startApache() {
  const run = docker(
    'run',
    '--detach',
    '--name',
    container,
    '--publish',
    '127.0.0.1::80',
    '--volume',
    `${site}:${HTDOCS}:ro`,
    '--volume',
    `${dist}:${HTDOCS}${BASE.replace(/\/$/, '')}:ro`,
    '--volume',
    `${path.join(work, 'check.conf')}:/usr/local/apache2/conf/extra/check.conf:ro`,
    IMAGE,
    'httpd-foreground',
    '-c',
    'Include conf/extra/check.conf',
  );
  if (run.status !== 0) throw new Error(`docker run failed:\n${run.stderr}`);
  const port = docker('port', container, '80/tcp');
  const match = /:(\d+)\s*$/m.exec(port.stdout);
  if (port.status !== 0 || !match) {
    throw new Error(`the container names no port:\n${port.stdout}${port.stderr}`);
  }
  const origin = `http://127.0.0.1:${match[1]}`;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const answer = await fetch(`${origin}${BASE}`);
      if (answer.status === 200) return origin;
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(
    `Apache did not answer ${origin}${BASE} with 200 within 20 s:\n${docker('logs', container).stderr}`,
  );
}

/** A context whose browser asks for `languages`, in that order. */
async function contextFor(browser, origin, languages, { javaScript = true } = {}) {
  const context = await browser.newContext({
    locale: languages[0],
    javaScriptEnabled: javaScript,
    extraHTTPHeaders: { 'Accept-Language': languages.join(', ') },
  });
  // Playwright's `locale` sets one language; a list of several is set here.
  if (languages.length > 1) {
    await context.addInitScript((list) => {
      Object.defineProperty(Object.getPrototypeOf(navigator), 'languages', {
        get: () => list,
      });
    }, languages);
  }
  const page = await context.newPage();
  const problems = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return;
    if (url.origin !== origin) problems.push(`request to a third party: ${request.url()}`);
  });
  return { context, page, problems };
}

/** An unknown address under the documentation: 404 and the page of `lang`. */
async function checkUnknown(browser, origin, address, lang) {
  const name = `${address} (unknown address)`;
  const entry = notFoundOf(lang);
  const { context, page, problems } = await contextFor(browser, origin, ['en-GB']);
  const scriptErrors = [];
  page.on('pageerror', (error) => scriptErrors.push(error.message));
  page.on('response', (answer) => {
    // The address itself answers 404; that is the case under test.
    if (answer.url() === `${origin}${address}`) return;
    if (answer.status() >= 400) problems.push(`${answer.url()} answered ${answer.status()}`);
  });
  page.on('requestfailed', (request) => {
    problems.push(`${request.url()} failed: ${request.failure()?.errorText}`);
  });
  const response = await page.goto(`${origin}${address}`, { waitUntil: 'networkidle' });
  expect(response?.status() === 404, `${name}: status ${response?.status()}, expected 404`);
  expect(page.url() === `${origin}${address}`, `${name}: the address changed to ${page.url()}`);
  expect(
    (await page.getAttribute('html', 'lang')) === lang && (await page.title()) === entry.title,
    `${name}: not the page-not-found page of "${lang}" (title "${await page.title()}")`,
  );
  expect(
    (await page.locator('h1').count()) === 1 &&
      (await page.locator('h1').innerText()).trim() === entry.name,
    `${name}: the level-1 heading is not "${entry.name}"`,
  );
  expect(
    !(await page.innerText('body')).includes(STAND_IN),
    `${name}: shows the stand-in page of the website`,
  );
  // Every address on the page carries the base: links, typeface, logo.
  const relative = await page.evaluate(
    (base) =>
      [...document.querySelectorAll('a[href], link[href], img[src], script[src]')]
        .map((element) => element.getAttribute('href') ?? element.getAttribute('src'))
        .filter((target) => !/^(https?:|#)/.test(target) && !target.startsWith(base)),
    BASE,
  );
  expect(relative.length === 0, `${name}: addresses without the base: ${relative.join(', ')}`);
  for (const link of entry.overviewLinks) {
    const found = page.locator(`main a[href="${link.address}"]`);
    expect(
      (await found.count()) === 1 && (await found.innerText()).trim() === link.name,
      `${name}: no link "${link.name}" to ${link.address}`,
    );
  }
  expect(
    (await page.locator(`a[data-counterpart][href="${entry.counterpart}"]`).count()) === 1,
    `${name}: the language switch does not lead to ${entry.counterpart}`,
  );
  expect(
    await page.evaluate(() => document.fonts.ready.then(() => document.fonts.check('16px Inter'))),
    `${name}: the typeface is not loaded`,
  );
  // The search works at the unknown address.
  const { ownWord, count } = searchTexts[lang];
  try {
    await page.waitForSelector('[data-search-status="ready"]', { state: 'attached', timeout: 10_000 });
    await page.fill('input[type="search"]', ownWord);
    const list = page.locator(`[data-search-results="${ownWord}"]`);
    await list.waitFor({ state: 'attached', timeout: 15_000 });
    const hits = await list.locator('a').evaluateAll((links) => links.map((a) => a.getAttribute('href')));
    const status = (await page.locator('[data-search] [role="status"]').innerText()).trim();
    expect(
      hits.length === 1 && hits[0] === start(lang).address && status === count(1),
      `${name}: search for "${ownWord}" gave [${hits}] and "${status}", expected [${start(lang).address}] and "${count(1)}"`,
    );
  } catch (error) {
    failures.push(`${name}: the search did not answer: ${error.message}`);
  }
  for (const problem of problems) failures.push(`${name}: ${problem}`);
  expect(scriptErrors.length === 0, `${name}: uncaught script error: ${scriptErrors}`);
  await context.close();
}

/** An unknown address outside the documentation: the website's own rule. */
async function checkOutside(browser, origin, address) {
  const name = `${address} (outside the documentation)`;
  const { context, page } = await contextFor(browser, origin, ['en-GB']);
  const response = await page.goto(`${origin}${address}`);
  expect(response?.status() === 404, `${name}: status ${response?.status()}, expected 404`);
  const text = await page.innerText('body');
  expect(text.includes(STAND_IN), `${name}: does not show the stand-in page of the website`);
  expect(
    notFound.every((entry) => !text.includes(entry.name)),
    `${name}: shows a page-not-found page of the documentation`,
  );
  await context.close();
}

/** The root address in a browser that asks for `languages`: ends at `lang`. */
async function checkRootLeadsOn(browser, origin, address, languages, lang) {
  const name = `${address} (languages ${languages.join(', ')})`;
  const { context, page, problems } = await contextFor(browser, origin, languages);
  const seen = await page.evaluate(() => navigator.languages.join(', '));
  await page.goto(`${origin}${address}`);
  const target = `${origin}${start(lang).address}`;
  await page.waitForURL(target, { timeout: 10_000 }).catch(() => {});
  expect(page.url() === target, `${name}: ends at ${page.url()}, expected ${target}`);
  const asked = await page.evaluate(() => navigator.languages.join(', '));
  expect(
    asked === languages.join(', '),
    `${name}: the browser of the check asks for "${asked}" (before the load "${seen}")`,
  );
  expect(
    (await page.getAttribute('html', 'lang')) === lang,
    `${name}: the page it ends at is not in "${lang}"`,
  );
  for (const problem of problems) failures.push(`${name}: ${problem}`);
  await context.close();
}

/** The root address with JavaScript off: stays, 200, both links. */
async function checkRootStays(browser, origin, languages) {
  const name = `${rootPage.address} (JavaScript off, languages ${languages.join(', ')})`;
  const { context, page, problems } = await contextFor(browser, origin, languages, {
    javaScript: false,
  });
  page.on('response', (answer) => {
    if (answer.status() >= 400) problems.push(`${answer.url()} answered ${answer.status()}`);
  });
  const response = await page.goto(`${origin}${rootPage.address}`, { waitUntil: 'networkidle' });
  expect(response?.status() === 200, `${name}: status ${response?.status()}, expected 200`);
  expect(page.url() === `${origin}${rootPage.address}`, `${name}: does not stay (${page.url()})`);
  expect((await page.title()) === rootPage.title, `${name}: title is "${await page.title()}"`);
  for (const link of rootPage.links) {
    const found = page.getByRole('link', { name: link.name, exact: true });
    expect(
      (await found.count()) === 1 &&
        (await found.isVisible()) &&
        (await found.getAttribute('href')) === link.address &&
        (await found.getAttribute('lang')) === link.lang,
      `${name}: no visible link "${link.name}" to ${link.address} that carries lang="${link.lang}"`,
    );
  }
  for (const problem of problems) failures.push(`${name}: ${problem}`);
  await context.close();
}

/** A page of a language in a browser that asks for the other: it stays. */
async function checkStays(browser, origin, entry, languages) {
  const name = `${entry.address} (languages ${languages.join(', ')})`;
  const { context, page } = await contextFor(browser, origin, languages);
  const response = await page.goto(`${origin}${entry.address}`, { waitUntil: 'networkidle' });
  expect(response?.status() === 200, `${name}: status ${response?.status()}, expected 200`);
  expect(
    response?.request().redirectedFrom() === null && page.url() === `${origin}${entry.address}`,
    `${name}: redirected to ${page.url()}`,
  );
  expect(
    (await page.getAttribute('html', 'lang')) === entry.lang,
    `${name}: the page is not in "${entry.lang}"`,
  );
  await context.close();
}

let browser;
try {
  const origin = await startApache();
  browser = await chromium.launch();
  const each = async (name, check) => {
    try {
      await check();
    } catch (error) {
      failures.push(`${name}: ${error.stack ?? error.message}`);
    }
  };
  const bare = BASE.replace(/\/$/, '');

  for (const [address, lang] of [
    [`${BASE}de/gibt-es-nicht/`, 'de'],
    [`${BASE}de/a/b/`, 'de'],
    [`${BASE}en/nope/`, 'en'],
    [`${BASE}nope`, 'en'],
  ]) {
    await each(address, () => checkUnknown(browser, origin, address, lang));
  }
  await each('/nope', () => checkOutside(browser, origin, '/nope'));

  for (const [languages, lang] of [
    [['de-DE', 'en'], 'de'],
    [['en-GB'], 'en'],
    [['fr-FR'], 'en'],
    [['fr-FR', 'de-DE', 'en'], 'de'],
  ]) {
    for (const address of [BASE, bare]) {
      await each(address, () => checkRootLeadsOn(browser, origin, address, languages, lang));
    }
  }
  for (const languages of [['de-DE', 'en'], ['fr-FR']]) {
    await each(BASE, () => checkRootStays(browser, origin, languages));
  }

  const quickStart = (lang) => pages.find((entry) => entry.id === 'quick-start' && entry.lang === lang);
  await each('de/quick-start', () => checkStays(browser, origin, quickStart('de'), ['en-GB']));
  await each('en/quick-start', () => checkStays(browser, origin, quickStart('en'), ['de-DE']));
  await each('de/', () => checkStays(browser, origin, start('de'), ['fr-FR']));
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  removeContainer();
  await rm(work, { recursive: true, force: true });
}

report('unknown addresses, the root address and the language pages pass on Apache (httpd:2.4)');
