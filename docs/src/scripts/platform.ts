// The platform switch. The delivered page holds, per switch, two labelled
// parts one after the other, Windows then Linux. This script turns the
// labels into tabs after the standard tabs pattern: real buttons, one tab
// stop per switch, Left and Right arrow and Home and End move and select,
// the selected tab is announced, each tab names its panel.
//
// A choice applies to the whole page: it is the attribute `data-platform` of
// <html>, and the stylesheet shows the parts of that platform (global.css).
// The switch the reader used keeps its place in the window and keeps focus.
// The choice is remembered in the storage of the browser under one key. An
// inline script in the head of the page (layouts/Page.astro) applies a
// remembered choice before the page is first shown; where the storage is
// not available, the choice holds for the page.

type Platform = 'windows' | 'linux';

/** The key of the remembered choice; the inline script in the head reads it too. */
const KEY = 'deltarecon-docs-platform';
const order: readonly Platform[] = ['windows', 'linux'];
const root = document.documentElement;
const tabs: HTMLButtonElement[] = [];

const chosen = (): Platform => (root.dataset.platform === 'linux' ? 'linux' : 'windows');

/** Every tab says whether its platform is the chosen one. */
function mark(): void {
  const platform = chosen();
  for (const tab of tabs) {
    const selected = tab.dataset.platformTab === platform;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
}

/** Chooses a platform for the page; `used` is the tab list the reader used. */
function choose(platform: Platform, used: HTMLElement): void {
  const before = used.getBoundingClientRect().top;
  root.dataset.platform = platform;
  try {
    window.localStorage.setItem(KEY, platform);
  } catch {
    // No storage: the choice holds for this page.
  }
  mark();
  // Parts above the used switch may have changed their height.
  window.scrollBy(0, used.getBoundingClientRect().top - before);
  used
    .querySelector<HTMLElement>(`[data-platform-tab="${platform}"]`)
    ?.focus({ preventScroll: true });
}

root.dataset.platform = chosen();

document.querySelectorAll<HTMLElement>('[data-platform-switch]').forEach((element, index) => {
  const parts = order.flatMap((platform) => {
    const part = element.querySelector<HTMLElement>(`:scope > [data-platform-part="${platform}"]`);
    const label = part?.querySelector<HTMLElement>(':scope > [data-platform-label]');
    return part && label ? [{ platform, part, label }] : [];
  });
  if (parts.length !== order.length) return;

  const row = document.createElement('div');
  row.className = 'platform-tabs';
  const list = document.createElement('div');
  list.className = 'platform-tablist';
  list.setAttribute('role', 'tablist');
  list.setAttribute('aria-label', element.dataset.label ?? '');
  row.append(list);

  for (const { platform, part, label } of parts) {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'platform-tab';
    tab.id = `platform-tab-${index}-${platform}`;
    tab.dataset.platformTab = platform;
    tab.setAttribute('role', 'tab');
    tab.innerHTML = label.innerHTML;
    part.id = `platform-panel-${index}-${platform}`;
    part.setAttribute('role', 'tabpanel');
    part.setAttribute('aria-labelledby', tab.id);
    tab.setAttribute('aria-controls', part.id);
    tab.addEventListener('click', () => choose(platform, list));
    tabs.push(tab);
    list.append(tab);
  }

  list.addEventListener('keydown', (event) => {
    const at = order.indexOf(chosen());
    const to: Record<string, number> = {
      ArrowRight: (at + 1) % order.length,
      ArrowLeft: (at + order.length - 1) % order.length,
      Home: 0,
      End: order.length - 1,
    };
    const next = to[event.key];
    if (next === undefined) return;
    event.preventDefault();
    choose(order[next], list);
  });

  element.prepend(row);
  // The tabs stand for the labels now.
  element.dataset.tabs = '';
});

mark();

// This file is a module of its own; its names are not global.
export {};
