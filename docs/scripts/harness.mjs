// What the check scripts share: the preview server, the page register, the
// glossary register, the list of failed expectations, and the checks of an
// open page that hold for every page of the site (`pageChecks`).
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axe from '@axe-core/playwright';
import ts from 'typescript';

const AxeBuilder = axe.AxeBuilder ?? axe.default ?? axe;
/** The rules axe runs: A and AA of WCAG 2.0 to 2.2. */
export const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
/** The window widths of the checks: desktop, between, phone. */
export const DESKTOP = { width: 1280, height: 800 };
export const BETWEEN = { width: 900, height: 800 };
export const PHONE = { width: 390, height: 844 };
/** The focus ring: teal-text on light grounds, teal on the navy terminal block. */
export const RING = 'rgb(23, 121, 130)';
export const RING_ON_NAVY = 'rgb(101, 194, 203)';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const PORT = 4399;
/** The base of the site (astro.config.mjs, `base`), with a closing slash. */
export const BASE = '/deltarecon/docs/';

/** Starts `astro preview` and resolves with the origin it reports. */
export function startPreview() {
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
  const stop = () => {
    server.removeAllListeners('exit');
    server.kill();
  };
  return { origin, stop };
}

/**
 * Loads a register under src/. Node does not run TypeScript, so the file is
 * turned into JavaScript in memory; it imports nothing but types, which the
 * conversion drops.
 */
async function loadSource(file) {
  const source = await readFile(path.join(root, 'src', file), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
}

/** Loads the page register, src/site.ts. */
export function loadRegister() {
  return loadSource('site.ts');
}

/** Loads the glossary register, src/glossary.ts. */
export function loadGlossary() {
  return loadSource('glossary.ts');
}

/** Loads the register of the hint groups, src/hints.ts. */
export function loadHints() {
  return loadSource('hints.ts');
}

/** Loads the reader of the facts of the example, src/example.ts. */
export function loadExample() {
  return loadSource('example.ts');
}

/** The release number the documentation applies to. */
export async function loadRelease() {
  return JSON.parse(await readFile(path.join(root, 'src/release.json'), 'utf8')).version;
}

/**
 * The pages of the register, each with what a check compares against:
 * language, address, counterpart, names and neighbours on the path. Title and
 * stage line are written out here from the register's data, not taken from
 * the functions the pages render with, so a changed format fails a check.
 */
export async function loadPages() {
  const site = await loadRegister();
  return site.languages.flatMap((lang) =>
    site.pages.map((page) => {
      const other = site.otherLanguage(lang);
      const previous = site.previousPage(page);
      const next = site.nextPage(page);
      const stage = site.stageOf(page);
      return {
        id: page.id,
        lang,
        name: page.name[lang],
        address: `${BASE}${site.pagePath(page, lang)}`,
        counterpart: `${BASE}${site.pagePath(page, other)}`,
        otherLang: other,
        title: `${page.name[lang]} – ${site.texts[lang].documentation}`,
        stageLine: stage
          ? `${site.texts[lang].stage} ${stage.number} · ${stage.name[lang]}`
          : site.texts[lang].helpKind,
        stageName: stage?.name[lang],
        previous: previous && {
          name: `${site.texts[lang].previous}: ${previous.name[lang]}`,
          address: `${BASE}${site.pagePath(previous, lang)}`,
        },
        next: next && {
          name: `${site.texts[lang].next}: ${next.name[lang]}`,
          address: `${BASE}${site.pagePath(next, lang)}`,
        },
        isRoot: page === site.pages[0],
        locale: site.locales[lang],
        otherLocale: site.locales[other],
        previewImage: site.outside.previewImage,
        productPage: site.outside.productPage,
        start: `${BASE}${site.pagePath(site.pages[0], lang)}`,
        texts: site.texts[lang],
      };
    }),
  );
}

/**
 * The three pages outside the path: the page-not-found page of each language
 * and the root page, which offers both languages. Titles and link texts are
 * written out here, as in `loadPages`.
 */
export async function loadOtherPages() {
  const site = await loadRegister();
  const start = (lang) => `${BASE}${site.pagePath(site.pages[0], lang)}`;
  const overview = { de: 'Zum Überblick', en: 'To the Overview' };
  const notFound = site.languages.map((lang) => {
    const other = site.otherLanguage(lang);
    return {
      id: site.notFoundPage.id,
      lang,
      otherLang: other,
      name: site.notFoundPage.name[lang],
      otherName: site.notFoundPage.name[other],
      address: `${BASE}${site.pagePath(site.notFoundPage, lang)}`,
      counterpart: `${BASE}${site.pagePath(site.notFoundPage, other)}`,
      title: `${site.notFoundPage.name[lang]} – ${site.texts[lang].documentation}`,
      // The link of each block to the Overview of its language, own block first.
      overviewLinks: [lang, other].map((language) => ({
        lang: language,
        name: overview[language],
        address: start(language),
      })),
      isRoot: false,
      texts: site.texts[lang],
    };
  });
  const rootPage = {
    address: BASE,
    lang: 'en',
    title: `${site.texts.en.documentation} · ${site.texts.de.documentation}`,
    names: site.languages.map((lang) => ({ lang, name: site.texts[lang].documentation })),
    links: [
      { lang: 'de', name: 'Dokumentation auf Deutsch', address: start('de') },
      { lang: 'en', name: 'Documentation in English', address: start('en') },
    ],
  };
  return { notFound, rootPage };
}

/**
 * The texts of the search, written out per language, so that a changed text
 * fails a check. `engine` stands on several pages of each language: in the
 * name of one page and in the text of another.
 */
export const searchTexts = {
  de: {
    label: 'Suche',
    loading: 'Die Suche wird geladen …',
    unavailable: 'Die Suche ist nicht verfügbar.',
    noMatch: (term) => `Keine Treffer für „${term}“.`,
    count: (number) => `${number} Treffer`,
    // A word that only the start page holds; one that several pages hold;
    // one that only the page-not-found page holds.
    ownWord: 'Veränderungsanalyse',
    sharedWord: 'Engine',
    notFoundWord: 'Tippfehler',
  },
  en: {
    label: 'Search',
    loading: 'The search is loading …',
    unavailable: 'The search is not available.',
    noMatch: (term) => `No matches for “${term}”.`,
    count: (number) => (number === 1 ? '1 match' : `${number} matches`),
    ownWord: 'balance',
    sharedWord: 'engine',
    notFoundWord: 'renamed',
  },
};

/**
 * A word that only one page of a language holds and no page of the other
 * language, per page of the register that has one: the search must find
 * that page by it, and nothing in the other language. The start pages have
 * theirs in `searchTexts` (`ownWord`).
 */
export const pageWords = {
  'understand-the-results': { en: 'bracket', de: 'Stornosatz' },
  'how-deltarecon-works': { en: 'middle', de: 'Durchlauf' },
  'tolerance-profile': { en: 'whoever', de: 'kaufmännisch' },
  'single-commands': { en: 'launcher', de: 'Umgebungsvariable' },
  'engine-requirements': { en: 'yardstick', de: 'Maßstab' },
  'build-an-adapter': { en: 'lookup', de: 'Kleinbuchstaben' },
  'when-something-goes-wrong': { en: 'phone', de: 'Telefon' },
};

/**
 * Runs in the page: where it loses text. `beyond` are the innermost elements
 * that reach beyond the window and stand in no box that scrolls or clips
 * sideways. `clipped` are the elements that cut text off: `overflow` is
 * `hidden` or `clip` on an axis, the content is more than 1 px larger than
 * the box on that axis, and text of the element reaches out of the box. A
 * box that scrolls (`overflow: auto`: code, terminal, wide tables) cuts
 * nothing off. Left out: text that is hidden from view on purpose (a box of
 * 1 × 1 px, as `.sr-only`), and the one line that the design cuts off with
 * an ellipsis (the excerpt of a search hit, DESIGN.md, Search result list).
 */
function lostText() {
  const describe = (element) => element.outerHTML.replace(/\s+/g, ' ').slice(0, 100);
  const cuts = (value) => value === 'hidden' || value === 'clip';
  const scrolls = (value) => value === 'auto' || value === 'scroll';
  const root = document.documentElement;
  const elements = [...document.body.querySelectorAll('*')];

  const wide = elements.filter((element) => {
    const box = element.getBoundingClientRect();
    if (box.width === 0 || box.right <= root.clientWidth + 1) return false;
    for (let outer = element.parentElement; outer && outer !== document.body; outer = outer.parentElement) {
      if (getComputedStyle(outer).overflowX !== 'visible') return false;
    }
    return true;
  });
  const beyond = wide
    .filter((element) => !wide.some((other) => other !== element && element.contains(other)))
    .slice(0, 3)
    .map(describe);

  const clipped = [];
  for (const element of elements) {
    const style = getComputedStyle(element);
    const x = cuts(style.overflowX) && element.scrollWidth - element.clientWidth > 1;
    const y = cuts(style.overflowY) && element.scrollHeight - element.clientHeight > 1;
    if (!x && !y) continue;
    const box = element.getBoundingClientRect();
    if (box.width <= 1 && box.height <= 1) continue;
    if (style.textOverflow === 'ellipsis' && style.whiteSpace === 'nowrap') continue;
    const inner = {
      left: box.left + element.clientLeft,
      top: box.top + element.clientTop,
      right: box.left + element.clientLeft + element.clientWidth,
      bottom: box.top + element.clientTop + element.clientHeight,
    };
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let lost = false;
    for (let node = walker.nextNode(); node && !lost; node = walker.nextNode()) {
      if (node.textContent.trim() === '') continue;
      // Text in a box of its own that scrolls, or that is hidden from view
      // on purpose, is not cut off by this element.
      let own = true;
      for (let outer = node.parentElement; outer && outer !== element; outer = outer.parentElement) {
        const between = getComputedStyle(outer);
        const size = outer.getBoundingClientRect();
        if (
          (x && scrolls(between.overflowX)) ||
          (y && scrolls(between.overflowY)) ||
          (size.width <= 1 && size.height <= 1)
        ) {
          own = false;
          break;
        }
      }
      if (!own) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      lost = [...range.getClientRects()].some(
        (rect) =>
          rect.width > 0 &&
          rect.height > 0 &&
          ((x && (rect.right > inner.right + 1 || rect.left < inner.left - 1)) ||
            (y && (rect.bottom > inner.bottom + 1 || rect.top < inner.top - 1))),
      );
    }
    if (lost) clipped.push(describe(element));
  }
  return { scroll: root.scrollWidth, client: root.clientWidth, beyond, clipped: clipped.slice(0, 5) };
}

/** The four values of WCAG 1.4.12 (Text Spacing), forced on every element. */
const TEXT_SPACING = `
  * { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
  p { margin-bottom: 2em !important; }
`;
/** The font sizes Chromium starts with, and twice those. */
const FONT_SIZES = { standard: 16, fixed: 13 };
const FONT_SIZES_200 = { standard: 32, fixed: 26 };

/**
 * The checks of an open page that hold for every page of the site, bound to
 * the list of failed expectations of the script:
 *   - `checkAxe`: no violation of the WCAG rules;
 *   - `checkNoSidewaysScroll`;
 *   - `checkNoMotion`: no transition, no animation and no smooth scrolling
 *     on any element of the page, `::before` and `::after` included;
 *   - `checkTextResize`: with text at 200 % the page does not scroll sideways
 *     and cuts no text off;
 *   - `checkTextSpacing`: the same with the text spacing of WCAG 1.4.12;
 *   - `checkNotTranslated`: every `pre`, `code` and `kbd` is marked
 *     `translate="no"`, itself or by an ancestor;
 *   - `checkOtherLanguage`: on an English page the German quantity name
 *     "Bruttobeitrag" carries its language, wherever it is not part of a
 *     command or of code (`code`, the command of a terminal session), which
 *     are marked as not to be translated and carry no language
 *     (EXPERIENCE.md, Accessibility Floor, Language).
 * `checkFloor` runs the last five in a row and leaves the page as it was;
 * with `resize: false` it leaves the text at 200 % out, which is looked at
 * at desktop width only.
 */
export function pageChecks({ failures, expect }) {
  const expectNothingLost = async (page, name) => {
    const found = await page.evaluate(lostText);
    expect(
      found.scroll <= found.client,
      `${name}: the page scrolls sideways (${found.scroll} px in ${found.client} px); beyond the window: ${found.beyond.join(' | ')}`,
    );
    expect(found.clipped.length === 0, `${name}: text is cut off in ${found.clipped.join(' | ')}`);
  };
  const checks = {
    async checkAxe(page, name) {
      const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze();
      for (const violation of violations) {
        for (const node of violation.nodes) {
          failures.push(`${name}: axe rule "${violation.id}" (${violation.help}): ${node.html}`);
        }
      }
    },
    async checkNoSidewaysScroll(page, name) {
      const { scroll, client } = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
      }));
      expect(scroll <= client, `${name}: the page scrolls sideways (${scroll} px in ${client} px)`);
    },
    async checkNoMotion(page, name) {
      const moving = await page.evaluate(() => {
        const found = [];
        for (const element of document.querySelectorAll('*')) {
          for (const part of [null, '::before', '::after']) {
            const style = getComputedStyle(element, part);
            const what = [
              style.transitionDuration.split(',').some((duration) => Number.parseFloat(duration) > 0) &&
                'a transition',
              style.animationName !== 'none' && 'an animation',
              part === null && style.scrollBehavior === 'smooth' && 'smooth scrolling',
            ].filter(Boolean);
            if (what.length > 0) {
              found.push(
                `${what.join(' and ')} on ${element.outerHTML.replace(/\s+/g, ' ').slice(0, 80)}${part ?? ''}`,
              );
            }
          }
        }
        return found;
      });
      expect(moving.length === 0, `${name}: ${moving.slice(0, 5).join(' | ')}`);
    },
    /**
     * Text at 200 %: the font sizes of the browser are doubled, as a reader
     * sets them. Type sizes and breakpoints are in `rem`, so the root font
     * size is then 32 px and the layout that of half the window width.
     */
    async checkTextResize(page, name) {
      const session = await page.context().newCDPSession(page);
      const settle = (size) =>
        page.waitForFunction(
          (expected) => Number.parseFloat(getComputedStyle(document.documentElement).fontSize) === expected,
          size,
          { timeout: 3_000 },
        );
      try {
        await session.send('Page.setFontSizes', { fontSizes: FONT_SIZES_200 });
        await settle(FONT_SIZES_200.standard);
        await expectNothingLost(page, `${name}, text at 200 %`);
      } catch (error) {
        failures.push(`${name}, text at 200 %: ${error.message}`);
      } finally {
        await session.send('Page.setFontSizes', { fontSizes: FONT_SIZES });
        await settle(FONT_SIZES.standard).catch(() => {});
        await session.detach();
      }
    },
    async checkTextSpacing(page, name) {
      const style = await page.addStyleTag({ content: TEXT_SPACING });
      try {
        await expectNothingLost(page, `${name}, text spacing overridden`);
      } finally {
        await style.evaluate((element) => element.remove());
      }
    },
    async checkNotTranslated(page, name) {
      const open = await page.evaluate(() =>
        [...document.querySelectorAll('pre, code, kbd')]
          .filter((element) => element.closest('[translate]')?.getAttribute('translate') !== 'no')
          .map((element) => element.outerHTML.replace(/\s+/g, ' ').slice(0, 80)),
      );
      expect(
        open.length === 0,
        `${name}: ${open.length} of pre, code and kbd not marked translate="no": ${open.slice(0, 5).join(' | ')}`,
      );
    },
    async checkOtherLanguage(page, name, lang) {
      if (lang !== 'en') return;
      const bare = await page.evaluate(() => {
        const found = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          const parent = node.parentElement;
          if (!node.textContent.includes('Bruttobeitrag') || parent.closest('script, style')) continue;
          if (parent.closest('code, [data-terminal-command]')) continue;
          if (parent.closest('[lang]')?.getAttribute('lang') !== 'de') {
            found.push(parent.outerHTML.replace(/\s+/g, ' ').slice(0, 100));
          }
        }
        return found;
      });
      expect(
        bare.length === 0,
        `${name}: "Bruttobeitrag" stands ${bare.length} times outside an element with lang="de": ${bare.slice(0, 5).join(' | ')}`,
      );
    },
    /** The rules of the floor that hold on every page, at the open width. */
    async checkFloor(page, name, lang, { resize = true } = {}) {
      await checks.checkNoMotion(page, name);
      await checks.checkNotTranslated(page, name);
      await checks.checkOtherLanguage(page, name, lang);
      await checks.checkTextSpacing(page, name);
      if (resize) await checks.checkTextResize(page, name);
    },
  };
  return checks;
}

/** Collects failed expectations; `report` prints them and ends the script. */
export function expectations(script) {
  const failures = [];
  return {
    failures,
    expect(condition, message) {
      if (!condition) failures.push(message);
    },
    report(passed) {
      if (failures.length > 0) {
        console.error(`${script}: ${failures.length} failed`);
        for (const failure of failures) console.error(`  - ${failure}`);
        process.exit(1);
      }
      console.log(`${script}: ${passed}`);
    },
  };
}
