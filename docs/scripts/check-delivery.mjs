// Checks what the build writes for the company website: the sitemap and the
// delivery record (scripts/write-delivery.mjs). Run after the build:
// `npm run check`.
//
// The sitemap, dist/sitemap.xml:
//   - is well-formed XML with the root element `urlset`;
//   - lists exactly the 22 addresses of the page register, each once, as
//     absolute addresses;
//   - gives each address two `xhtml:link` alternates, `de` and `en`: the page
//     itself and its counterpart;
//   - every address it lists is a built page.
// The delivery record, dist/delivery.json:
//   - `commit` is the commit `git rev-parse HEAD` names;
//   - `changed` is a boolean; the actual writer also runs in clean, tracked-
//     dirty and untracked Git fixtures, including hidden-untracked config.
//     Hardcoded-false and dropped-option mutations must fail these checks;
//   - `pages` is the page register, in its order: language, absolute address
//     and page name; each description is the one the head of the built page
//     holds, which Chromium reads from the built file.
// It starts no server: it reads the files under dist/.
// Exits non-zero and names every failed expectation.
import { execFileSync } from 'node:child_process';
import { access, copyFile, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { BASE, expectations, loadPages, root } from './harness.mjs';

const SITE = 'https://degelmann-solutions.de';
const dist = path.join(root, 'dist');

const pages = await loadPages();
const { failures, expect, report } = expectations('check-delivery');

/** The built file of an address of the documentation. */
const fileOf = (address) => path.join(dist, address.slice(BASE.length), 'index.html');

/** Runs in the page: the entries of the sitemap, or why it does not parse. */
function readSitemap(text) {
  const parsed = new DOMParser().parseFromString(text, 'application/xml');
  const fault = parsed.querySelector('parsererror');
  if (fault) return { fault: fault.textContent.replace(/\s+/g, ' ').trim() };
  const XHTML = 'http://www.w3.org/1999/xhtml';
  return {
    rootName: parsed.documentElement.localName,
    namespace: parsed.documentElement.namespaceURI,
    urls: [...parsed.documentElement.children].map((url) => ({
      name: url.localName,
      locs: [...url.children].filter((child) => child.localName === 'loc').map((loc) => loc.textContent),
      alternates: [...url.children]
        .filter((child) => child.localName === 'link' && child.namespaceURI === XHTML)
        .map((link) => [link.getAttribute('rel'), link.getAttribute('hreflang'), link.getAttribute('href')]),
    })),
  };
}

function checkSitemap(sitemap) {
  const name = 'dist/sitemap.xml';
  if (sitemap.fault) {
    failures.push(`${name}: not well-formed XML: ${sitemap.fault}`);
    return;
  }
  expect(
    sitemap.rootName === 'urlset' && sitemap.namespace === 'http://www.sitemaps.org/schemas/sitemap/0.9',
    `${name}: the root element is "${sitemap.rootName}" of "${sitemap.namespace}", expected "urlset" of the sitemap protocol`,
  );
  const listed = [];
  for (const url of sitemap.urls) {
    if (url.name !== 'url' || url.locs.length !== 1) {
      failures.push(`${name}: an entry is a "${url.name}" with ${url.locs.length} addresses, expected a "url" with one`);
      continue;
    }
    listed.push(url.locs[0]);
  }
  const expected = pages.map((entry) => `${SITE}${entry.address}`);
  for (const address of listed) {
    expect(expected.includes(address), `${name}: lists ${address}, which is no page of the register`);
  }
  expect(new Set(listed).size === listed.length, `${name}: lists an address more than once`);
  for (const entry of pages) {
    const address = `${SITE}${entry.address}`;
    const url = sitemap.urls.find((candidate) => candidate.locs[0] === address);
    if (!url) {
      failures.push(`${name}: does not list ${address}, a page of the register`);
      continue;
    }
    const versions = { [entry.lang]: address, [entry.otherLang]: `${SITE}${entry.counterpart}` };
    const alternates = url.alternates.map(([rel, lang, href]) => `${rel} ${lang} ${href}`).sort();
    const wanted = ['de', 'en'].map((lang) => `alternate ${lang} ${versions[lang]}`).sort();
    expect(
      alternates.length === wanted.length && alternates.every((alternate, index) => alternate === wanted[index]),
      `${name}: ${address} names the versions [${alternates.join(' | ')}], expected [${wanted.join(' | ')}]`,
    );
  }
  return listed;
}

async function checkBuilt(listed) {
  for (const address of listed) {
    if (!address.startsWith(`${SITE}${BASE}`)) {
      failures.push(`dist/sitemap.xml: ${address} is not an address of the documentation`);
      continue;
    }
    const file = fileOf(address.slice(SITE.length));
    await access(file).catch(() =>
      failures.push(`dist/sitemap.xml: ${address} is listed, but ${path.relative(root, file)} is not built`),
    );
  }
}

function checkRecord(record, descriptions) {
  const name = 'dist/delivery.json';
  let head;
  try {
    head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
  } catch (error) {
    failures.push(`${name}: git rev-parse HEAD failed: ${error.message}`);
  }
  expect(record.commit === head, `${name}: commit is "${record.commit}", expected "${head}" (HEAD)`);
  expect(
    typeof record.changed === 'boolean',
    `${name}: changed is ${JSON.stringify(record.changed)}, expected true or false`,
  );
  if (!Array.isArray(record.pages)) {
    failures.push(`${name}: pages is not a list`);
    return;
  }
  expect(
    record.pages.length === pages.length,
    `${name}: holds ${record.pages.length} pages, expected the ${pages.length} of the register`,
  );
  pages.forEach((entry, index) => {
    const page = record.pages[index] ?? {};
    const wanted = {
      lang: entry.lang,
      address: `${SITE}${entry.address}`,
      title: entry.name,
      description: descriptions.get(entry.address),
    };
    for (const [field, value] of Object.entries(wanted)) {
      expect(
        page[field] === value,
        `${name}: pages[${index}].${field} is ${JSON.stringify(page[field])}, expected ${JSON.stringify(value)}`,
      );
    }
    const more = Object.keys(page).filter((field) => !(field in wanted));
    expect(more.length === 0, `${name}: pages[${index}] holds the fields ${more.join(', ')} beyond the four`);
  });
}

/** Exercise the actual producer in isolated repositories. */
async function checkProducer() {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'deltarecon-delivery-'));
  const fixture = path.join(temporary, 'docs');
  // User signing, hooks and ignore settings must not alter the fixtures.
  const env = { ...process.env, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: os.devNull };
  const git = (...args) => execFileSync('git', args, { cwd: temporary, encoding: 'utf8', env }).trim();
  try {
    await mkdir(path.join(fixture, 'scripts'), { recursive: true });
    await mkdir(path.join(fixture, 'src'));
    for (const file of ['scripts/write-delivery.mjs', 'scripts/harness.mjs', 'astro.config.mjs', 'src/site.ts']) {
      await copyFile(path.join(root, file), path.join(fixture, file));
    }
    await symlink(path.join(root, 'node_modules'), path.join(fixture, 'node_modules'),
      process.platform === 'win32' ? 'junction' : 'dir');
    await writeFile(path.join(temporary, '.gitignore'), 'docs/node_modules/\ndocs/dist/\n');
    await writeFile(path.join(temporary, 'tracked.txt'), 'original\n');
    for (const entry of pages) {
      const folder = path.join(fixture, 'dist', entry.address.slice(BASE.length));
      await mkdir(folder, { recursive: true });
      await writeFile(path.join(folder, 'index.html'), '<meta name="description" content="Fixture description">');
    }
    git('init', '--quiet');
    git('add', '.');
    git('-c', 'user.name=Delivery fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'Fixture');
    const original = await readFile(path.join(fixture, 'scripts/write-delivery.mjs'), 'utf8');
    const writer = path.join(fixture, 'scripts/write-delivery.mjs');
    async function states(source) {
      await writeFile(writer, source);
      // Commit each writer so its mutation cannot dirty its own test.
      git('add', 'docs/scripts/write-delivery.mjs');
      git('-c', 'user.name=Delivery fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '--allow-empty', '-m', 'Writer under test');
      const revision = git('rev-parse', 'HEAD');
      const faults = [];
      async function check(expected, state) {
        execFileSync(process.execPath, [writer], { cwd: fixture, stdio: 'pipe', env });
        const record = JSON.parse(await readFile(path.join(fixture, 'dist/delivery.json'), 'utf8'));
        if (record.commit !== revision) faults.push(`${state}: wrong commit`);
        if (record.changed !== expected) faults.push(`${state}: changed is ${record.changed}, expected ${expected}`);
      }
      await check(false, 'clean');
      await writeFile(path.join(temporary, 'tracked.txt'), 'changed\n');
      await check(true, 'tracked-dirty');
      git('checkout', '--', 'tracked.txt');
      await writeFile(path.join(temporary, 'untracked.txt'), 'untracked\n');
      await check(true, 'untracked');
      git('config', 'status.showUntrackedFiles', 'no');
      await check(true, 'untracked hidden by config');
      git('config', '--unset', 'status.showUntrackedFiles');
      await rm(path.join(temporary, 'untracked.txt'));
      return faults;
    }
    const faults = await states(original);
    expect(faults.length === 0, `delivery producer: ${faults.join('; ')}`);
    const expression = "git('status', '--porcelain', '--untracked-files=normal').trim() !== ''";
    for (const [name, source, expectedFault] of [
      ['hardcoded false', original.replace(expression, 'false'), 'tracked-dirty'],
      ['dropped untracked option', original.replace(", '--untracked-files=normal'", ''), 'untracked hidden by config'],
    ]) {
      expect(source !== original, `delivery producer: ${name} mutation was not applied`);
      const found = await states(source);
      expect(found.some((fault) => fault.startsWith(`${expectedFault}:`)), `delivery producer: ${name} mutation escaped the ${expectedFault} assertion`);
      console.log(`check-delivery: ${name} mutation detected: ${found.join('; ')}`);
    }
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

let browser;
try {
  await checkProducer();
  browser = await chromium.launch();
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();

  let sitemapText;
  try {
    sitemapText = await readFile(path.join(dist, 'sitemap.xml'), 'utf8');
  } catch (error) {
    failures.push(`dist/sitemap.xml: not in the build: ${error.message}`);
  }
  if (sitemapText !== undefined) {
    const listed = checkSitemap(await page.evaluate(readSitemap, sitemapText));
    if (listed) await checkBuilt(listed);
  }

  // The description of each built page, as a browser reads its head.
  const descriptions = new Map();
  for (const entry of pages) {
    try {
      await page.goto(pathToFileURL(fileOf(entry.address)).href, { waitUntil: 'domcontentloaded' });
      const found = await page.$$eval('head meta[name="description"]', (elements) =>
        elements.map((element) => element.getAttribute('content')),
      );
      expect(found.length === 1, `${entry.address}: the built page holds ${found.length} descriptions, expected 1`);
      descriptions.set(entry.address, found[0]);
    } catch (error) {
      failures.push(`${entry.address}: the built page does not open: ${error.message}`);
    }
  }

  let record;
  try {
    record = JSON.parse(await readFile(path.join(dist, 'delivery.json'), 'utf8'));
  } catch (error) {
    failures.push(`dist/delivery.json: not in the build, or not JSON: ${error.message}`);
  }
  if (record !== undefined) {
    if (record === null || typeof record !== 'object') {
      failures.push('dist/delivery.json: is not an object');
    } else {
      checkRecord(record, descriptions);
    }
  }
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
}

report(`the sitemap and the delivery record name the ${pages.length} pages of the register`);
