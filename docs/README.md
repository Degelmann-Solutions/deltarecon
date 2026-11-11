# DeltaRecon user documentation

The documentation website of DeltaRecon: an Astro project (Astro 5, MDX,
Tailwind 4) with the Pagefind search. It is published under
`/deltarecon/docs` on degelmann-solutions.de, with German pages under `/de/`
and English pages under `/en/`. The root address offers both languages, and
an unknown address gets a page-not-found page (see "Pages outside the path").

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
| `npm run check:apache` | Builds the site, then checks in an Apache what only Apache shows: unknown addresses and the root address. Needs Docker; not part of `npm run check`. |
| `npx astro check` | Type-checks the project. |

The checks need the Chromium of Playwright. On a machine without it:

```
npx playwright install chromium
```

The search works only on a built site (`npm run local`), because Pagefind
indexes the build output.

## Checks

`npm run check` runs three scripts one after the other; a fourth,
`scripts/check-apache.mjs`, runs on its own (below). Each of the three starts
`astro preview` on a port of its own (`scripts/harness.mjs`), reads the page
register, and names every failed expectation with its page.

| Script | What it asserts |
|---|---|
| `scripts/check-site.mjs` | For every page and for the two page-not-found pages: language, release number, link to the counterpart, reading with JavaScript off (no search field), that no request leaves the local origin, and that every file a page loads (typeface, logo, script) is served. For the start page of each language, the search: nothing shown at the load; the hits of a word of the language with the number of matches, each hit with page name, stage line and an excerpt with the match marked; no hit and the no-match text for a word of the other language and for a word of the page-not-found page; an emptied field; Escape, which closes the list and keeps focus and term, in the field and on a hit; a slow search index, which shows the loading text once a term is typed; a missing search index, which shows the "not available" text at the load and after a term is typed. For the page-not-found pages: the search finds the start page. For the root page: it stays with JavaScript off and offers both languages, and leads on with JavaScript. |
| `scripts/check-head.mjs` | The built pages are exactly the pages of the register and the three pages outside the path. For every page of the register: title "page name – DeltaRecon documentation", a description of its own, canonical address, `alternate` links for `de` and `en`, Open Graph title, description, address, type, locale and image, and one JSON-LD block that parses and names the page. Titles and descriptions are unique. A page and its counterpart hold the same anchors in their content; the stubs have none, so this takes effect with the first written page, which sets the anchors of its headings itself. For the three pages outside the path: language, a title of its own, `noindex`, and no canonical address. The two `.htaccess` files of the build name the addresses the register gives the page-not-found pages. |
| `scripts/check-a11y.mjs` | For every page, at desktop and phone width, with the menu closed and open: axe reports no violation of the A and AA rules of WCAG 2.0 to 2.2. Keyboard: the skip link comes first and leads to main, Tab reaches every control in reading order, each with a visible focus ring. The menu below 1280 px: focus on the close button, which says that the menu is open, the page behind inert and the skip link out of the page, the top bar in one row at 320 px, Tab stays inside, Escape and the close button return focus to the menu button. The language switch keeps the anchor the page was loaded with and one set afterwards. With JavaScript off the menu button is a link to the chapter tree at the end of the page. No page scrolls sideways at 1280, 390 and 320 px. For the start page of each language also at 900 px: axe, the menu, no sideways scrolling at 900 and 600 px, an open menu that ends at 1280 px with focus kept in the page, and the search field moving between top bar and menu at 600 px. For the start page of each language, the search result list: axe with the list open, with hits and with no match, in the top bar and in the menu on the phone; its place and look; the hits after the field in tab order, each with a focus ring; the list closed when focus leaves the search in the top bar; Escape in the field, which leaves the menu open; no sideways scrolling with the list open at 600 and 320 px. For the page-not-found pages: axe, the frame without stage line, page links and current page, the two blocks with their languages, skip link, tab order, language switch, menu. For the root page, in a browser that names no language: axe, tab order, no sideways scrolling. Axe does not run with JavaScript off. An error on one page is reported for that page; the others are still checked. |

`npm run check:apache` runs `scripts/check-apache.mjs` after the build. The
preview server of the other checks knows no `.htaccess`, so this script
starts the image `httpd:2.4` in Docker on a free local port, with
`AllowOverride All`, the build mounted read-only under `/deltarecon/docs`,
and at the server root a stand-in for the company website (its rule
`ErrorDocument 404 /404.html` and that page). It asserts in Chromium:

- an unknown address under `/de/` answers 404 with the German page-not-found
  page, every other unknown address under the documentation 404 with the
  English one; the files of the page load and its search works;
- an unknown address outside the documentation gets the stand-in page;
- the root address, with and without the closing slash, leads on by the
  languages of the browser, and stays with JavaScript off;
- an address under `/de/` or `/en/` is not redirected.

It stops and removes its container in every outcome. Without Docker it ends
with a message that says so. Run it when the page-not-found pages, the root
page or an `.htaccess` file change.

The accessibility check writes its screenshots to `screenshots/` (not under
version control): the start page of each language at desktop width, at
900 px, at phone width, and with the menu open (`desktop-`, `between-`,
`phone-`, `menu-`); the search result list in the top bar and in the menu,
with hits and with no match (`search-list-`); the page-not-found page of each
language (`not-found-`) and the root page (`root-`), each at desktop and phone
width. Lay the first group beside the mock of the Overview page when the
frame changes.

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

## Pages outside the path

Three built pages are not among the ten of the register's path. Search
engines are asked not to list them (`noindex`), and the search of the site
does not index them.

- **The page-not-found pages**, `src/pages/de/seite-nicht-gefunden.astro` and
  `src/pages/en/page-not-found.astro`, both built by
  `src/layouts/NotFound.astro`. Each holds two blocks, its own language
  first. The frame is in the page's language and shows no stage line, no page
  links and no current page; the language switch leads to the other
  page-not-found page. Name and address stand in the register as
  `notFoundPage`.
- **The two `.htaccess` files**, `public/.htaccess` and
  `public/de/.htaccess`, which the build copies to `dist/`. Each holds one
  `ErrorDocument 404` rule: an unknown address under `/de/` gets the German
  page, every other unknown address under the documentation the English one.
  Apache delivers such a page at any address, so every address on it carries
  the base of the site. When the address of a page-not-found page changes in
  the register, change the rule too; `npm run check` fails otherwise.
- **The root page**, `src/pages/index.astro`. It offers both languages, each
  link in its own language. A script in its head leads on by the languages
  of the browser, in their order: the first that is German or English
  decides, and languages of which none is German or English lead to English.
  Where no language can be read, and without JavaScript, the page stays.
  Nothing is remembered, and no other page redirects.

## Search

`src/components/Search.astro` holds the search field, the search result list
and their texts in both languages; the look of the list is in
`src/styles/global.css`. A hit shows the page name, the stage line of its
page (from the register, by the address of the hit) and a one-line excerpt.
The stage line of a page is not searched text (`data-pagefind-ignore` in
`PageHead.astro`). The check scripts hold the texts a second time
(`searchTexts` in `scripts/harness.mjs`), so a changed text fails a check
until both places agree.

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
  (English); the search checks look for them. Whoever replaces the start
  page's text gives `searchTexts` in `scripts/harness.mjs` two other words.
  The same list names a word that several pages of a language hold in
  their name or text ("Engine", "engine"; at least two pages must keep it) and a word that only the page-not-found page holds
  ("Tippfehler", "renamed"); no page of the path may hold the latter.

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
