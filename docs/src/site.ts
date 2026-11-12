// The page register of the documentation: the four stages, the ten pages in
// path order with their names and addresses per language, the texts of the
// page frame, of the Glossary and of the step components, `languageOf`, the language of a page
// address, and the page-not-found page, which stands outside the path
// (`notFoundPage`, `onPath`). Chapter tree, page links, page head, language switch and head
// data read it, and so do the Glossary (components/Glossary.astro) and the
// glossary link (components/Term.astro); a page name stands here and in no
// other file.
//
// This file imports nothing, so that the check scripts can load it (see
// scripts/harness.mjs).

export type Lang = 'de' | 'en';

export const languages: readonly Lang[] = ['de', 'en'];

export interface Stage {
  number: number;
  name: Record<Lang, string>;
}

export interface Page {
  /** The key a page file names in its frontmatter (`page:`). */
  id: string;
  /** Number of the stage; `null` for the page below the four stages. */
  stage: number | null;
  name: Record<Lang, string>;
  /** Last part of the address; empty for the root of the language. */
  slug: Record<Lang, string>;
}

/**
 * A step of a step page, as the page names it in its frontmatter. The step
 * card, its counter and the chapter tree read title and anchor from there.
 */
export interface Step {
  /** Anchor of the step, the same in both languages. */
  anchor: string;
  title: string;
  /** A step the reader may skip; its card says "optional". */
  optional?: boolean;
}

/** What an anchor of a step looks like: small letters, digits and hyphens. */
export const stepAnchor = /^[a-z][a-z0-9-]*$/;

/**
 * What is wrong with the step list of a page, one sentence per fault: a step
 * without an anchor or a title, an anchor twice. Empty when the list holds.
 */
export function stepFaults(steps: unknown): string[] {
  if (!Array.isArray(steps)) return ['"steps" is not a list'];
  const faults: string[] = [];
  const seen = new Set<string>();
  steps.forEach((step, index) => {
    const name = `step ${index + 1}`;
    const anchor: unknown = step?.anchor;
    const title: unknown = step?.title;
    if (typeof anchor !== 'string' || !stepAnchor.test(anchor)) {
      faults.push(`${name} has no anchor of small letters, digits and hyphens`);
    } else if (seen.has(anchor)) {
      faults.push(`${name} repeats the anchor "${anchor}"`);
    } else {
      seen.add(anchor);
    }
    if (typeof title !== 'string' || title.trim() === '') {
      faults.push(`${name}${typeof anchor === 'string' ? ` ("${anchor}")` : ''} has no title`);
    }
  });
  return faults;
}

export const stages: readonly Stage[] = [
  { number: 1, name: { en: 'Get it running', de: 'Zum Laufen bringen' } },
  { number: 2, name: { en: 'Understand', de: 'Verstehen' } },
  { number: 3, name: { en: 'Work with it', de: 'Damit arbeiten' } },
  { number: 4, name: { en: 'Connect your engine', de: 'Ihre Engine anbinden' } },
];

/** The ten pages in path order. */
export const pages: readonly Page[] = [
  {
    id: 'overview',
    stage: 1,
    name: { en: 'Overview', de: 'Überblick' },
    slug: { en: '', de: '' },
  },
  {
    id: 'quick-start',
    stage: 1,
    name: { en: 'Quick start', de: 'Quick Start' },
    slug: { en: 'quick-start', de: 'quick-start' },
  },
  {
    id: 'understand-the-results',
    stage: 2,
    name: { en: 'Understand the results', de: 'Die Ergebnisse verstehen' },
    slug: { en: 'understand-the-results', de: 'ergebnisse-verstehen' },
  },
  {
    id: 'how-deltarecon-works',
    stage: 2,
    name: { en: 'How DeltaRecon works', de: 'So arbeitet DeltaRecon' },
    slug: { en: 'how-deltarecon-works', de: 'so-arbeitet-deltarecon' },
  },
  {
    id: 'glossary',
    stage: 2,
    name: { en: 'Glossary', de: 'Glossar' },
    slug: { en: 'glossary', de: 'glossar' },
  },
  {
    id: 'own-calculations',
    stage: 3,
    name: {
      en: 'Your own calculations on the reference model',
      de: 'Eigene Rechnungen am Referenzmodell',
    },
    slug: { en: 'own-calculations', de: 'eigene-rechnungen' },
  },
  {
    id: 'single-commands',
    stage: 3,
    name: { en: 'Single commands', de: 'Einzelne Befehle' },
    slug: { en: 'single-commands', de: 'einzelne-befehle' },
  },
  {
    id: 'engine-requirements',
    stage: 4,
    name: { en: 'What your engine must provide', de: 'Was Ihre Engine mitbringen muss' },
    slug: { en: 'engine-requirements', de: 'anforderungen-an-die-engine' },
  },
  {
    id: 'build-an-adapter',
    stage: 4,
    name: {
      en: 'Build an adapter step by step',
      de: 'Schritt für Schritt einen Adapter bauen',
    },
    slug: { en: 'build-an-adapter', de: 'adapter-bauen' },
  },
  {
    id: 'when-something-goes-wrong',
    stage: null,
    name: { en: 'When something goes wrong', de: 'Wenn etwas schiefgeht' },
    slug: { en: 'when-something-goes-wrong', de: 'wenn-etwas-schiefgeht' },
  },
];

/**
 * The page-not-found page. It stands outside the path and so not in `pages`:
 * no stage line, no page links, no entry in the chapter tree, and neither
 * search engines nor the search of the site list it.
 */
export const notFoundPage: Page = {
  id: 'page-not-found',
  stage: null,
  name: { en: 'Page not found', de: 'Seite nicht gefunden' },
  slug: { en: 'page-not-found', de: 'seite-nicht-gefunden' },
};

/** Addresses outside the documentation. They are links, never requests. */
export const outside = {
  company: 'https://degelmann-solutions.de/',
  productPage: 'https://degelmann-solutions.de/deltarecon',
  imprint: 'https://degelmann-solutions.de/impressum',
  privacy: 'https://degelmann-solutions.de/datenschutz',
  licence: 'https://github.com/Degelmann-Solutions/deltarecon/blob/main/LICENSE',
  repository: 'https://github.com/Degelmann-Solutions/deltarecon',
  /** The brand card of the company website, the preview image of every page. */
  previewImage: 'https://degelmann-solutions.de/og-image.png',
} as const;

export const company = 'Degelmann Solutions';
export const product = 'DeltaRecon';

/** Each language in its own words, for the language switch. */
export const languageNames: Record<Lang, string> = { de: 'Deutsch', en: 'English' };

/** Locale of a language in the Open Graph data. */
export const locales: Record<Lang, string> = { de: 'de_DE', en: 'en_GB' };

export interface FrameTexts {
  documentation: string;
  skipLink: string;
  menu: string;
  close: string;
  productPage: string;
  language: string;
  chapters: string;
  treeHeading: string;
  stage: string;
  /** The page kind the stage line names on the page below the four stages. */
  helpKind: string;
  steps: string;
  pageLinks: string;
  previous: string;
  next: string;
  imprint: string;
  privacy: string;
  licence: string;
  repository: string;
  /** The Glossary: label of the letter index, tag of a linked entry, pages of a term. */
  letters: string;
  linkedTerm: string;
  appearsIn: string;
  /** The step page: the counter "Step n of m" and the tag of a step that may be skipped. */
  step: string;
  stepOf: string;
  optional: string;
  /** The platform switch: its label and the names of its parts. */
  operatingSystem: string;
  windows: string;
  linux: string;
  /** The shell of each platform, as tab and terminal bar name it. */
  windowsShell: string;
  linuxShell: string;
  /** Names of the blocks that scroll sideways. */
  command: string;
  terminalSession: string;
  /** Where a terminal session runs. */
  packageFolder: string;
  /** The copy button: its word, its name, and what it says afterwards. */
  copy: string;
  copyCommand: string;
  copied: string;
  copyFailed: string;
}

export const texts: Record<Lang, FrameTexts> = {
  en: {
    documentation: 'DeltaRecon documentation',
    skipLink: 'Skip to the content',
    menu: 'Menu',
    close: 'Close',
    productPage: 'DeltaRecon product page',
    language: 'Language',
    chapters: 'Chapters',
    treeHeading: 'Your path through the documentation',
    stage: 'Stage',
    helpKind: 'Help',
    steps: 'Steps of this page',
    pageLinks: 'Previous and next page',
    previous: 'Previous',
    next: 'Next',
    imprint: 'Imprint',
    privacy: 'Privacy',
    licence: 'Licence',
    repository: 'Repository',
    letters: 'Letters',
    linkedTerm: 'Linked term',
    appearsIn: 'Appears in',
    step: 'Step',
    stepOf: 'of',
    optional: 'optional',
    operatingSystem: 'Operating system',
    windows: 'Windows',
    linux: 'Linux',
    windowsShell: 'PowerShell',
    linuxShell: 'Terminal',
    command: 'Command',
    terminalSession: 'Terminal session',
    packageFolder: 'package folder',
    copy: 'Copy',
    copyCommand: 'Copy command',
    copied: 'Copied',
    copyFailed: 'Not copied. Please select the command by hand.',
  },
  de: {
    documentation: 'DeltaRecon-Dokumentation',
    skipLink: 'Zum Inhalt springen',
    menu: 'Menü',
    close: 'Schließen',
    productPage: 'Produktseite von DeltaRecon',
    language: 'Sprache',
    chapters: 'Kapitel',
    treeHeading: 'Ihr Weg durch die Dokumentation',
    stage: 'Etappe',
    helpKind: 'Hilfe',
    steps: 'Schritte dieser Seite',
    pageLinks: 'Vorherige und nächste Seite',
    previous: 'Zurück',
    next: 'Weiter',
    imprint: 'Impressum',
    privacy: 'Datenschutz',
    licence: 'Lizenz',
    repository: 'Repository',
    letters: 'Buchstaben',
    linkedTerm: 'Verlinkter Begriff',
    appearsIn: 'Kommt vor in',
    step: 'Schritt',
    stepOf: 'von',
    optional: 'optional',
    operatingSystem: 'Betriebssystem',
    windows: 'Windows',
    linux: 'Linux',
    windowsShell: 'PowerShell',
    linuxShell: 'Terminal',
    command: 'Befehl',
    terminalSession: 'Terminalsitzung',
    packageFolder: 'Paketordner',
    copy: 'Kopieren',
    copyCommand: 'Befehl kopieren',
    copied: 'Kopiert',
    copyFailed: 'Nicht kopiert. Bitte markieren Sie den Befehl von Hand.',
  },
};

export function otherLanguage(lang: Lang): Lang {
  return lang === 'de' ? 'en' : 'de';
}

export function findPage(id: string): Page {
  const page = pages.find((entry) => entry.id === id);
  if (!page) {
    throw new Error(`No page "${id}" in the page register (src/site.ts).`);
  }
  return page;
}

/** Whether a page is one of the ten on the path. */
export function onPath(page: Page): boolean {
  return pages.includes(page);
}

export function stageOf(page: Page): Stage | undefined {
  return stages.find((stage) => stage.number === page.stage);
}

export function pagesOf(stage: Stage): Page[] {
  return pages.filter((page) => page.stage === stage.number);
}

/** The page before `page` on the path, if there is one. */
export function previousPage(page: Page): Page | undefined {
  return pages[pages.indexOf(page) - 1];
}

/** The page after `page` on the path, if there is one. */
export function nextPage(page: Page): Page | undefined {
  return pages[pages.indexOf(page) + 1];
}

/** Address of a page below the base of the site, for example `de/glossar/`. */
export function pagePath(page: Page, lang: Lang): string {
  const slug = page.slug[lang];
  return slug === '' ? `${lang}/` : `${lang}/${slug}/`;
}

/** Address of a page on the host, with the base of the site. */
export function pageAddress(page: Page, lang: Lang): string {
  return `${import.meta.env.BASE_URL.replace(/\/?$/, '/')}${pagePath(page, lang)}`;
}

/** The language of a page address on the host, from its first part below the base. */
export function languageOf(pathname: string): Lang | undefined {
  const base = import.meta.env.BASE_URL.replace(/\/?$/, '/');
  return languages.find((lang) => pathname.startsWith(`${base}${lang}/`));
}

/** The stage line of the page head: the stage, or the page kind. */
export function stageLine(page: Page, lang: Lang): string {
  const stage = stageOf(page);
  return stage
    ? `${texts[lang].stage} ${stage.number} · ${stage.name[lang]}`
    : texts[lang].helpKind;
}

/** Title of a page: "page name – DeltaRecon documentation". */
export function pageTitle(page: Page, lang: Lang): string {
  return `${page.name[lang]} – ${texts[lang].documentation}`;
}

/** The counter of a step card: "Step 2 of 6". */
export function stepCounter(number: number, total: number, lang: Lang): string {
  return `${texts[lang].step} ${number} ${texts[lang].stepOf} ${total}`;
}

/**
 * The place a block of a step page names itself by: "step 2", or
 * "step 2, Windows" for the part of one platform.
 */
export function stepPlace(step: number | string, lang: Lang, platform?: 'windows' | 'linux'): string {
  // Inside a name the English word is written small; the German noun is not.
  const word = lang === 'en' ? texts[lang].step.toLowerCase() : texts[lang].step;
  const place = `${word} ${step}`;
  return platform ? `${place}, ${texts[lang][platform]}` : place;
}
