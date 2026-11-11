// What the check scripts share: the preview server, the page register, and
// the list of failed expectations.
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

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
 * Loads the page register, src/site.ts. Node does not run TypeScript, so the
 * file is turned into JavaScript in memory; it imports nothing.
 */
export async function loadRegister() {
  const source = await readFile(path.join(root, 'src/site.ts'), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
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
        previewImage: site.outside.previewImage,
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
    ownWord: 'Baustelle',
    sharedWord: 'Engine',
    notFoundWord: 'Tippfehler',
  },
  en: {
    label: 'Search',
    loading: 'The search is loading …',
    unavailable: 'The search is not available.',
    noMatch: (term) => `No matches for “${term}”.`,
    count: (number) => (number === 1 ? '1 match' : `${number} matches`),
    ownWord: 'scaffold',
    sharedWord: 'engine',
    notFoundWord: 'renamed',
  },
};

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
