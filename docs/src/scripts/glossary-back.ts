// The way back from the Glossary. A reader who came from a page of the
// documentation, by a glossary link, gets a link "Back to the previous
// page" in the entry the address points at. The `href` is the page they came
// from. A plain click goes back in the history instead, so the reader lands
// where they were, but only where the entry before this one is known to be
// that page: the entry of the arrival is marked in the history, and a click
// goes back when the mark is on the current entry. Everywhere else (a reload
// at a later anchor, a Glossary opened in a new tab) the `href` does the
// work, as it does for a click with a modifier key or another button. A
// reader who came from a Glossary, also the one of the other language by the
// language switch, gets no link. The link goes when the address changes,
// like the linked state of the entry. Without this script there is no such
// link.

/** The name of the mark on the history entry of the arrival. */
const MARK = 'glossaryBack';

const withoutSlash = (pathname: string): string => pathname.replace(/\/$/, '');

/** The addresses of the Glossaries: this page and its counterparts. */
function glossaries(): Set<string> {
  const counterparts = document.querySelectorAll<HTMLAnchorElement>('a[data-counterpart]');
  return new Set(
    [window.location.pathname, ...[...counterparts].map((link) => link.pathname)].map(withoutSlash),
  );
}

/** The page the reader came from, if it is a page of the documentation but a Glossary. */
function previousPage(): URL | undefined {
  try {
    const from = new URL(document.referrer);
    const base = import.meta.env.BASE_URL.replace(/\/?$/, '/');
    const inside = from.origin === window.location.origin && from.pathname.startsWith(base);
    return inside && !glossaries().has(withoutSlash(from.pathname)) ? from : undefined;
  } catch {
    return undefined;
  }
}

/** The entry the address points at. */
function linkedEntry(): HTMLElement | null {
  // It is read from the address: while the page loads, `:target` may not be
  // set yet. An address that cannot be decoded names no entry.
  let anchor = '';
  try {
    anchor = decodeURIComponent(window.location.hash.slice(1));
  } catch {
    return null;
  }
  const named = anchor ? document.getElementById(anchor) : null;
  return named?.matches('[data-glossary-entry]') ? named : null;
}

const from = previousPage();
const entry = linkedEntry();
// The Glossary writes the text of the link once (Glossary.astro).
const text = document.querySelector<HTMLElement>('[data-back-text]')?.dataset.backText;
if (from && entry && text) {
  // The arrival: this load is a navigation from the page before, which is
  // then the entry before this one. A reload or a move in the history marks
  // nothing; the mark of the arrival stays on its entry.
  const [load] = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
  if (load?.type === 'navigate' && window.history.length > 1) {
    window.history.replaceState({ ...window.history.state, [MARK]: true }, '');
  }
  const line = document.createElement('p');
  line.className = 'mt-2 text-caption';
  line.dataset.glossaryBack = '';
  const link = document.createElement('a');
  link.className = 'inline-link py-[5px]';
  link.href = from.href;
  link.textContent = text;
  link.addEventListener('click', (event) => {
    // Another button or a modifier key: the browser follows the `href`.
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    if (window.history.state?.[MARK] !== true) return;
    event.preventDefault();
    window.history.back();
  });
  line.append(link);
  (entry.querySelector('dd') ?? entry).append(line);
  window.addEventListener('hashchange', () => line.remove(), { once: true });
}

// This file is a module of its own; its names are not global.
export {};
