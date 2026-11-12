// The way back from the Glossary. A reader who came from a page of the
// documentation, by a glossary link, gets a link "Back to the previous
// page" in the entry the address points at. A click goes back in the
// history, so the reader lands where they were; the `href` is the page they
// came from, for the case that going back is not possible. The link goes
// when the address changes, like the linked state of the entry. Without this
// script there is no such link.

/** The page the reader came from, if it is a page of the documentation. */
function previousPage(): URL | undefined {
  try {
    const from = new URL(document.referrer);
    const base = import.meta.env.BASE_URL.replace(/\/?$/, '/');
    const inside = from.origin === window.location.origin && from.pathname.startsWith(base);
    return inside && from.pathname !== window.location.pathname ? from : undefined;
  } catch {
    return undefined;
  }
}

const from = previousPage();
// The entry the address points at. It is read from the address: while the
// page loads, `:target` may not be set yet.
const anchor = decodeURIComponent(window.location.hash.slice(1));
const named = anchor ? document.getElementById(anchor) : null;
const entry = named?.matches('[data-glossary-entry]') ? named : null;
const text = entry?.dataset.backText;
if (from && entry && text) {
  const line = document.createElement('p');
  line.className = 'mt-2 text-caption';
  line.dataset.glossaryBack = '';
  const link = document.createElement('a');
  link.className = 'inline-link py-[5px]';
  link.href = from.href;
  link.textContent = text;
  link.addEventListener('click', (event) => {
    if (window.history.length > 1) {
      event.preventDefault();
      window.history.back();
    }
  });
  line.append(link);
  (entry.querySelector('dd') ?? entry).append(line);
  window.addEventListener('hashchange', () => line.remove(), { once: true });
}

// This file is a module of its own; its names are not global.
export {};
