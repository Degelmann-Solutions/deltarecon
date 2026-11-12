// Checks the head data of every built page. Run after the build:
// `npm run check`.
//
// The built pages (every index.html under dist/, outside the search index)
// must be exactly the 20 pages of the page register. For each page it
// asserts, in Chromium with JavaScript off:
//   - the title "page name – DeltaRecon documentation", unique on the site;
//   - a description of its own, unique on the site;
//   - the canonical address, and `alternate` links for `de` and `en`, each
//     the absolute address of a page of the register;
//   - Open Graph title, description, address, type, locale and image;
//   - one JSON-LD block that parses and names the page.
// Exits non-zero and names page and field of every failed expectation.
import { readdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import { BASE, expectations, loadPages, root, startPreview } from './harness.mjs';

const SITE = 'https://degelmann-solutions.de';

const pages = await loadPages();
const { failures, expect, report } = expectations('check-head');

/** Addresses of the built pages, from the files under dist/. */
async function builtAddresses() {
  const dist = path.join(root, 'dist');
  const files = await readdir(dist, { recursive: true });
  return files
    .map((file) => file.split(path.sep).join('/'))
    .filter((file) => file.endsWith('.html') && !file.startsWith('pagefind/'))
    .map((file) => `${BASE}${file.replace(/index\.html$/, '')}`);
}

/** Reads the head data of the open page. */
function readHead(page) {
  return page.evaluate(() => {
    const attribute = (selector, name) =>
      [...document.head.querySelectorAll(selector)].map((element) => element.getAttribute(name));
    return {
      title: document.title,
      description: attribute('meta[name="description"]', 'content'),
      canonical: attribute('link[rel="canonical"]', 'href'),
      alternates: [...document.head.querySelectorAll('link[rel="alternate"][hreflang]')].map(
        (link) => [link.getAttribute('hreflang'), link.getAttribute('href')],
      ),
      og: Object.fromEntries(
        ['title', 'description', 'url', 'type', 'locale', 'image'].map((name) => [
          name,
          attribute(`meta[property="og:${name}"]`, 'content'),
        ]),
      ),
      jsonLd: [...document.querySelectorAll('script[type="application/ld+json"]')].map(
        (script) => script.textContent,
      ),
    };
  });
}

function checkHead(entry, head, seen) {
  const name = entry.address;
  const field = (label, values, expected) => {
    expect(
      values.length === 1 && values[0] === expected,
      `${name}: ${label} is [${values.join(' | ')}], expected "${expected}"`,
    );
  };
  const canonical = `${SITE}${entry.address}`;

  expect(head.title === entry.title, `${name}: title is "${head.title}", expected "${entry.title}"`);
  expect(!seen.titles.has(head.title), `${name}: title "${head.title}" stands on another page too`);
  seen.titles.add(head.title);

  const description = head.description[0] ?? '';
  expect(
    head.description.length === 1 && description.trim().length >= 30,
    `${name}: description is missing, doubled or shorter than 30 characters`,
  );
  expect(
    !seen.descriptions.has(description),
    `${name}: description stands on another page too: "${description}"`,
  );
  seen.descriptions.add(description);

  field('canonical', head.canonical, canonical);
  const alternates = Object.fromEntries(head.alternates);
  expect(
    head.alternates.length === 2,
    `${name}: ${head.alternates.length} alternate links, expected 2 (de, en)`,
  );
  expect(
    alternates[entry.lang] === canonical,
    `${name}: alternate ${entry.lang} is "${alternates[entry.lang]}", expected "${canonical}"`,
  );
  expect(
    alternates[entry.otherLang] === `${SITE}${entry.counterpart}`,
    `${name}: alternate ${entry.otherLang} is "${alternates[entry.otherLang]}", expected "${SITE}${entry.counterpart}"`,
  );

  field('og:title', head.og.title, entry.title);
  field('og:description', head.og.description, description);
  field('og:url', head.og.url, canonical);
  field('og:type', head.og.type, 'website');
  field('og:locale', head.og.locale, entry.locale);
  field('og:image', head.og.image, entry.previewImage);

  expect(head.jsonLd.length === 1, `${name}: ${head.jsonLd.length} JSON-LD blocks, expected 1`);
  if (head.jsonLd.length === 1) {
    let data;
    try {
      data = JSON.parse(head.jsonLd[0]);
    } catch (error) {
      failures.push(`${name}: JSON-LD does not parse: ${error.message}`);
      return;
    }
    expect(data['@context'] === 'https://schema.org', `${name}: JSON-LD @context is not schema.org`);
    expect(data['@type'] === 'WebPage', `${name}: JSON-LD @type is "${data['@type']}", expected "WebPage"`);
    expect(data.name === entry.name, `${name}: JSON-LD name is "${data.name}", expected "${entry.name}"`);
    expect(data.url === canonical, `${name}: JSON-LD url is "${data.url}", expected "${canonical}"`);
    expect(data.description === description, `${name}: JSON-LD description differs from the description`);
    expect(data.inLanguage === entry.lang, `${name}: JSON-LD inLanguage is "${data.inLanguage}"`);
    expect(data.isPartOf?.['@type'] === 'WebSite', `${name}: JSON-LD isPartOf is not a WebSite`);
    expect(
      data.about?.['@type'] === 'SoftwareApplication' && data.about?.name === 'DeltaRecon',
      `${name}: JSON-LD about is not the SoftwareApplication DeltaRecon`,
    );
    expect(Boolean(data.publisher?.name), `${name}: JSON-LD names no publisher`);
  }
}

// The built pages and the register name the same addresses.
const built = await builtAddresses();
const registered = new Set(pages.map((entry) => entry.address));
for (const address of built) {
  expect(registered.has(address), `${address}: built, but not in the page register`);
}
for (const address of registered) {
  expect(built.includes(address), `${address}: in the page register, but not built`);
}

const { origin: reported, stop } = startPreview();
let browser;
try {
  const origin = await reported;
  browser = await chromium.launch();
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  const seen = { titles: new Set(), descriptions: new Set() };
  // The anchors of the content of each page, by address.
  const anchors = new Map();
  for (const entry of pages) {
    // An error on one page is a failure of that page; the others still run.
    try {
      const response = await page.goto(`${origin}${entry.address}`);
      if (response?.status() !== 200) {
        failures.push(`${entry.address}: status ${response?.status()}, expected 200`);
        continue;
      }
      checkHead(entry, await readHead(page), seen);
      anchors.set(
        entry.address,
        await page.$$eval('main [id]:not([data-language-own])', (elements) =>
          elements.map((element) => element.id).sort(),
        ),
      );
    } catch (error) {
      failures.push(`${entry.address}: ${error.stack ?? error.message}`);
    }
  }
  // The language switch keeps the anchor, so a page and its counterpart hold
  // the same anchors. The two Glossaries are the first pages whose anchors
  // are compared; the stubs have none in their content. A heading gets its
  // text, which differs by language, so such a page sets its anchors itself.
  // An anchor that belongs to one language, as a letter label of the Glossary
  // (the letters differ by language), is marked `data-language-own` and left
  // out.
  for (const entry of pages) {
    const own = anchors.get(entry.address);
    const other = anchors.get(entry.counterpart);
    if (!own || !other) continue;
    const missing = own.filter((id) => !other.includes(id));
    expect(
      missing.length === 0,
      `${entry.address}: anchors missing on the counterpart ${entry.counterpart}: ${missing.join(', ')}`,
    );
  }
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}

report(`the head data of all ${pages.length} pages pass`);
