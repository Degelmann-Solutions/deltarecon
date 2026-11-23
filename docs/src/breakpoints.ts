// The two breakpoints of the site, once for the scripts of the pages and the
// checks. The stylesheet cannot read them: a media query takes no custom
// property, so `--breakpoint-tablet`, `--breakpoint-tree` and the widths of the
// `@media` rules in src/styles/global.css repeat them, and
// scripts/check-site.mjs fails when one of them differs from this file.

/** The phone breakpoint (600 px): `tablet:` holds from it up. */
export const tablet = '37.5rem';
/** The tree breakpoint (1280 px): from it up the chapter tree is a column. */
export const tree = '80rem';
