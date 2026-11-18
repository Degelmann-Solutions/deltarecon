// Small helpers of the components: markup built as a string, the language of
// a page, a list in words, and the number of the step a component stands in.
import { languageOf, type Lang } from './site';

/**
 * Stands where a component names the step it is in ("Command, step 2"). The
 * step card (components/StepCard.astro) puts its number in the place of the
 * mark, so a page never types a step number.
 */
export const STEP_MARK = '⟦step⟧';

/** The language of the page a component is rendered on. */
export function pageLanguage(pathname: string): Lang {
  const lang = languageOf(pathname);
  if (!lang) throw new Error(`${pathname}: a component stands on a page of no language.`);
  return lang;
}

export function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

/** Words of the program that are German in both languages. */
const german = /Bruttobeitrag/g;

/**
 * Text of the program as markup: on an English page a German word carries
 * its language (EXPERIENCE.md, Accessibility Floor, Language).
 */
export function outputHtml(text: string, lang: Lang): string {
  const escaped = escapeHtml(text);
  return lang === 'en' ? escaped.replace(german, '<span lang="de">$&</span>') : escaped;
}

/**
 * The quantities of the reference model, as the program prints them: German
 * in both languages (contracts/v3/domain/liability_cashflow.md). A name that
 * holds another stands before it.
 */
const quantities = [
  'Kosten 2. Ordnung ohne Provisionen',
  'garantierte Erlebensfallleistung',
  'garantierte Todesfallleistung',
  'garantierter Rückkaufswert',
  'kalkulatorische Kosten',
  'Beitragsverrechnung',
  'Anzahl Verträge',
  'Netto-Cashflow',
  'Bruttobeitrag',
  'Zahlbeitrag',
  'Provisionen',
];
/** A quantity name, a full hash (a revision, a SHA-256), or a path. */
const marked = new RegExp(
  `(${quantities.map((name) => name.replaceAll('.', '\\.')).join('|')})` +
    '|(\\b(?:[0-9a-f]{64}|[0-9a-f]{40})\\b|(?:[A-Za-z]:)?[\\w.\\\\/-]*[\\\\/][\\w.\\\\/-]+)',
  'g',
);

/**
 * A line a single command prints, as markup. The single commands print
 * English only: a quantity name is German and carries its language, a hash
 * and a path are marked as not to be translated (EXPERIENCE.md,
 * Accessibility Floor, Language).
 */
export function commandOutputHtml(text: string): string {
  let html = '';
  let at = 0;
  for (const match of text.matchAll(marked)) {
    html += escapeHtml(text.slice(at, match.index));
    html += match[1]
      ? `<span lang="de">${escapeHtml(match[1])}</span>`
      : `<span translate="no">${escapeHtml(match[0])}</span>`;
    at = match.index + match[0].length;
  }
  return html + escapeHtml(text.slice(at));
}

/** A list in words, as the language writes it: "2, 6, 12 and 30". */
export function listOf(items: readonly (string | number)[], lang: Lang): string {
  return new Intl.ListFormat(lang === 'en' ? 'en-GB' : 'de', { type: 'conjunction' }).format(
    items.map(String),
  );
}
