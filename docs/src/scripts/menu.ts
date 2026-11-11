// The menu below the tree breakpoint. The delivered page holds a link to the
// chapter tree, which stands at the end of the page. This script swaps the
// link for the menu button and the close button and sets `data-menu` on
// <html> ("closed" or "open"); the stylesheet does the rest (global.css,
// `menu-closed:` and `menu-open:`).
//
// Open: the chapter tree fills the screen under the top bar, the content and
// the footer are out of the page and inert, focus is on the close button and
// Tab stays inside. Escape and the close button close the menu and return
// focus to the menu button. The button in view says whether the menu is open:
// the menu button while it is closed, the close button while it is open.

const root = document.documentElement;
const link = document.querySelector<HTMLAnchorElement>('[data-menu-link]');
const menuButton = document.querySelector<HTMLButtonElement>('[data-menu-button]');
const closeButton = document.querySelector<HTMLButtonElement>('[data-menu-close]');
const header = menuButton?.closest('header');
const tree = document.getElementById('chapters');
const behind = document.querySelectorAll<HTMLElement>('[data-behind-menu]');
// The tree breakpoint of the stylesheet (`--breakpoint-tree`).
const column = window.matchMedia('(min-width: 80rem)');

if (link && menuButton && closeButton && header && tree) {
  let scrollPosition = 0;
  const isOpen = (): boolean => root.dataset.menu === 'open';

  const setOpen = (open: boolean): void => {
    root.dataset.menu = open ? 'open' : 'closed';
    menuButton.setAttribute('aria-expanded', String(open));
    closeButton.setAttribute('aria-expanded', String(open));
    behind.forEach((element) => {
      element.inert = open;
    });
  };

  const open = (): void => {
    scrollPosition = window.scrollY;
    setOpen(true);
    window.scrollTo(0, 0);
    closeButton.focus();
  };

  const close = (returnFocus: boolean): void => {
    setOpen(false);
    // Focus first and without scrolling, so the position before the menu holds.
    if (returnFocus) menuButton.focus({ preventScroll: true });
    window.scrollTo(0, scrollPosition);
  };

  /** What takes focus in the open menu, in order: top bar, then tree. */
  const focusable = (): HTMLElement[] =>
    [header, tree]
      .flatMap((part) => [...part.querySelectorAll<HTMLElement>('a[href], button, input')])
      .filter((element) => element.getClientRects().length > 0);

  menuButton.addEventListener('click', open);
  closeButton.addEventListener('click', () => close(true));

  document.addEventListener('keydown', (event) => {
    if (!isOpen()) return;
    if (event.key === 'Escape') {
      // Escape in the search field belongs to the search; on a hit under the
      // field it closes the menu like anywhere else.
      if (event.target instanceof HTMLInputElement && event.target.closest('[data-search]')) {
        return;
      }
      close(true);
      return;
    }
    if (event.key !== 'Tab') return;
    const stops = focusable();
    const first = stops[0];
    const last = stops[stops.length - 1];
    const active = document.activeElement;
    if (!first || !last) return;
    if (event.shiftKey && (active === first || !stops.includes(active as HTMLElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !stops.includes(active as HTMLElement))) {
      event.preventDefault();
      first.focus();
    }
  });

  // From the tree breakpoint up the tree is a column; an open menu ends.
  // Both buttons leave the page there, so focus that was in the menu's top
  // bar or tree moves to the current page of the tree.
  column.addEventListener('change', () => {
    if (!column.matches || !isOpen()) return;
    close(false);
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || active.getClientRects().length === 0) {
      tree.querySelector<HTMLElement>('a[aria-current="page"]')?.focus({ preventScroll: true });
    }
  });

  // A page that the browser restores from its back/forward cache comes back
  // as it was left; a menu left open by following a link is closed.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted && isOpen()) close(false);
  });

  link.hidden = true;
  menuButton.hidden = false;
  closeButton.hidden = false;
  setOpen(false);
}
