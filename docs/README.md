# DeltaRecon user documentation

The documentation website of DeltaRecon: an Astro project (Astro 5, MDX,
Tailwind 4) with the Pagefind search. It is published under
`/deltarecon/docs` on degelmann-solutions.de, with German pages under `/de/`
and English pages under `/en/`.

The text a reader sees or hears on the pages is German and English. Code,
comments and configuration are English (see `AGENTS.md` at the repository
root).

## Commands

Run them in `docs/`. Node 20 and npm are required.

| Command | What it does |
|---|---|
| `npm ci` | Installs the pinned dependencies from `package-lock.json`. |
| `npm run local` | Builds the site with its search index and serves it. When port 4321 is free, the pages are at `http://localhost:4321/deltarecon/docs/de/` and `/en/`; otherwise the server takes the next free port. The command prints the address it serves on. |
| `npm run build` | Builds the site to `dist/` and writes the search index to `dist/pagefind/`. |
| `npm run check` | Builds the site, then runs the three checks below in Chromium. Every page entry runs it. |
| `npx astro check` | Type-checks the project. |

The checks need the Chromium of Playwright. On a machine without it:

```
npx playwright install chromium
```

The search works only on a built site (`npm run local`), because Pagefind
indexes the build output.

## Checks

`npm run check` runs three scripts one after the other. Each starts
`astro preview` on a port of its own (`scripts/harness.mjs`), reads the page
register, and names every failed expectation with its page.

| Script | What it asserts |
|---|---|
| `scripts/check-site.mjs` | For every page: language, release number, link to the counterpart, reading with JavaScript off (no search field), that no request leaves the local origin, and that every file a page loads (typeface, logo, script) is served. For the start page of each language: the search per language and a missing search index. |
| `scripts/check-head.mjs` | The built pages are exactly the pages of the register. For every page: title "page name – DeltaRecon documentation", a description of its own, canonical address, `alternate` links for `de` and `en`, Open Graph title, description, address, type, locale and image, and one JSON-LD block that parses and names the page. Titles and descriptions are unique. A page and its counterpart hold the same anchors in their content; the stubs have none, so this takes effect with the first written page, which sets the anchors of its headings itself. |
| `scripts/check-a11y.mjs` | For every page, at desktop and phone width, with the menu closed and open: axe reports no violation of the A and AA rules of WCAG 2.0 to 2.2. Keyboard: the skip link comes first and leads to main, Tab reaches every control in reading order, each with a visible focus ring. The menu below 1280 px: focus on the close button, which says that the menu is open, the page behind inert and the skip link out of the page, the top bar in one row at 320 px, Tab stays inside, Escape and the close button return focus to the menu button. The language switch keeps the anchor the page was loaded with and one set afterwards. With JavaScript off the menu button is a link to the chapter tree at the end of the page. No page scrolls sideways at 1280, 390 and 320 px. For the start page of each language also at 900 px: axe, the menu, no sideways scrolling at 900 and 600 px, an open menu that ends at 1280 px with focus kept in the page, and the search field moving between top bar and menu at 600 px. Axe does not run with JavaScript off or on the open search box. An error on one page is reported for that page; the others are still checked. |

The accessibility check writes eight screenshots to `screenshots/` (not under
version control): the start page of each language at desktop width, at 900 px,
at phone width, and with the menu open. Lay them beside the mock of the Overview page
when the frame changes.

What no script checks: the looks on hover, a Windows contrast theme, a screen
reader, and zoom to 400 %.

## Page register

`src/site.ts` is the register of the site: the four stages, the ten pages in
path order with their name and address per language, the addresses outside
the documentation, and the texts of the page frame in both languages. Chapter
tree, page links, page head, language switch and head data read it. A page
name stands there and in no other file; rename a page there.

The frame is `src/layouts/Page.astro` with the parts under `src/components/`.
The design tokens are the `@theme` block of `src/styles/global.css`.

## Adding or writing a page

A page is one file per language under `src/pages/de/` and `src/pages/en/`.
Its frontmatter names the register entry; title, stage line, tree entry and
page links follow from it.

```
---
layout: ../../layouts/Page.astro
lang: en
page: quick-start
lead: "One sentence under the title."
description: "The description of the page for search engines and shared links."
---
```

- The file stands at the address the register gives the page: `slug`
  `quick-start` in `en` is `src/pages/en/quick-start.mdx`; an empty slug is
  `index.mdx`. The build fails when file and register disagree.
- `description` is the page's own and differs from every other page.
- A step page lists its steps, and the chapter tree shows them under the
  page: `steps: [{ anchor: step-1, title: "Download the package" }]`. The
  anchor is the same in both languages.
- A new page needs an entry in `pages` of `src/site.ts` (at its place on the
  path) and both files. `npm run check` fails when a page of the register is
  not built or a built page is not in the register.
- Only the start pages hold the words "Baustelle" (German) and "scaffold"
  (English); the search check looks for them. Whoever replaces the start
  page's text gives `scripts/check-site.mjs` two other words.

## Typeface and logo

`public/fonts/` and `public/logo.svg` are copies from the repository of the
company website; the licence files of the typefaces
stand beside them. The mark of DeltaRecon beside the product title,
`src/components/ProductMark.astro`, is a copy of
`src/assets/deltarecon/logo-signet.svg` of that repository; when the mark
changes there, copy its paths here and into `public/favicon.svg`, the same
mark on a navy disc. A page requests nothing from another
origin.

## Release number

The release the documentation applies to stands in `src/release.json` and in
no other file under `docs/`. `src/release.ts` reads it and derives the tag.
Renew the number by hand when a release is published.
