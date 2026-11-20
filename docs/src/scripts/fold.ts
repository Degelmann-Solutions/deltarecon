// Folds in print. A closed fold (components/Fold.astro) hides what it holds,
// also on paper. Before the browser prints, every fold of the page is
// opened, so that the printed page holds the whole text. The folds stay
// open afterwards. This is no print design: nothing else changes in print.
//
// Without JavaScript a closed fold stays closed in print.

window.addEventListener('beforeprint', () => {
  document.querySelectorAll<HTMLDetailsElement>('details[data-fold]').forEach((fold) => {
    fold.open = true;
  });
});

// This file is a module of its own; its names are not global.
export {};
