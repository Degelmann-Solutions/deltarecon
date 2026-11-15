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

/** A list in words, as the language writes it: "2, 6, 12 and 30". */
export function listOf(items: readonly (string | number)[], lang: Lang): string {
  return new Intl.ListFormat(lang === 'en' ? 'en-GB' : 'de', { type: 'conjunction' }).format(
    items.map(String),
  );
}
