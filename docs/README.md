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
| `npm run check` | Builds the site, then runs the eight checks below in Chromium. Every page entry runs it. The last of them reads Git and needs the tag of the release and the branch `main` in the local clone. |
| `npm run check:apache` | Builds the site, then checks in an Apache what only Apache shows: unknown addresses and the root address. Needs Docker; not part of `npm run check`. |
| `npm run check:release -- --search <folder>` | Holds the capture files, the built step pages and the page of single commands against the published release. Needs `../dist/release-v<version>/` and the search folder of a run of the demo; not part of `npm run check` (see "Captures and the release check"). |
| `npm run check:first-run` | Builds the site, then runs the commands of the last step of "Build an adapter step by step" on the engine of `../examples/toy_engine/`, with `uv run deltarecon` in the checkout. Needs `uv`; not part of `npm run check` (see "The first run of the adapter page"). |
| `npx astro check` | Type-checks the project. |

The checks need the Chromium of Playwright. On a machine without it:

```
npx playwright install chromium
```

The search works only on a built site (`npm run local`), because Pagefind
indexes the build output.

## Checks

`npm run check` runs eight scripts one after the other; three more,
`scripts/check-apache.mjs`, `scripts/check-release.mjs` and
`scripts/check-first-run.mjs`, run on their own (below). Each of the eight starts `astro preview` (`scripts/harness.mjs`),
reads the page register, and names every failed expectation with its page.
`scripts/harness.mjs` also holds what several scripts run on an open page:
axe and the check for sideways scrolling (`pageChecks`).

| Script | What it asserts |
|---|---|
| `scripts/check-site.mjs` | For every page and for the two page-not-found pages: language, release number, link to the counterpart, the four links of the footer, of which the two to GitHub open in a new tab and say so in hidden text, reading with JavaScript off (no search field), that no request leaves the local origin, and that every file a page loads (typeface, logo, script) is served. For the start page of each language, the search: nothing shown at the load; the hits of a word of the language with the number of matches, each hit with page name, stage line and an excerpt with the match marked; no hit and the no-match text for a word of the other language and for a word of the page-not-found page; for a page that has a word of its own (`pageWords` in `scripts/harness.mjs`), that page as the one hit of its word and no hit for the word of its counterpart; an emptied field; Escape, which closes the list and keeps focus and term, in the field and on a hit; a slow search index, which shows the loading text once a term is typed; a missing search index, which puts the "not available" text into the page at the load and shows it with focus in the field and after a term is typed. For the page-not-found pages: the search finds the start page. For the root page: it stays with JavaScript off and offers both languages, and leads on with JavaScript. |
| `scripts/check-head.mjs` | The built pages are exactly the pages of the register and the three pages outside the path. For every page of the register: title "page name – DeltaRecon documentation", a description of its own, canonical address, `alternate` links for `de` and `en`, Open Graph title, description, address, type, locale and image, and one JSON-LD block that parses and names the page. Titles and descriptions are unique. A page and its counterpart hold the same anchors in their content; a written page sets the anchors of its headings itself; the two Glossaries are the first pages whose anchors are compared. An anchor that belongs to one language, as a letter label of the Glossary, is marked `data-language-own` and left out. For the three pages outside the path: language, a title of its own, `noindex`, and no canonical address. The two `.htaccess` files of the build name the addresses the register gives the page-not-found pages. |
| `scripts/check-a11y.mjs` | For every page, at desktop and phone width, with the menu closed and open: axe reports no violation of the A and AA rules of WCAG 2.0 to 2.2. Keyboard: the skip link comes first and leads to main, Tab reaches every control in reading order, each at least 24 × 24 px and with a visible focus ring, teal-text on light grounds and teal inside the navy terminal block of a step page; a control with `tabindex="-1"`, as the tab of a platform switch that is not selected, is no stop. The menu below 1280 px: focus on the close button, which says that the menu is open, the page behind inert and the skip link out of the page, the top bar in one row at 320 px, Tab stays inside, Escape and the close button return focus to the menu button. The language switch keeps the anchor the page was loaded with and one set afterwards. With JavaScript off the menu button is a link to the chapter tree at the end of the page. No page scrolls sideways at 1280, 390 and 320 px. For the start page of each language also at 900 px: axe, the menu, no sideways scrolling at 900 and 600 px, an open menu that ends at 1280 px with focus kept in the page, and the search field moving between top bar and menu at 600 px. For the start page of each language, the search result list: axe with the list open, with hits and with no match, in the top bar and in the menu on the phone; its place and look; the hits after the field in tab order, each with a focus ring; the list closed when focus leaves the search in the top bar; Escape in the field, which leaves the menu open; no sideways scrolling with the list open at 600 and 320 px. For the page-not-found pages: axe, the frame without stage line, page links and current page, the two blocks with their languages, skip link, tab order, language switch, menu. For the root page, in a browser that names no language: axe, tab order, no sideways scrolling. Axe does not run with JavaScript off. For the Glossary of each language, at desktop and phone width: Tab reaches every letter of the letter index, each at least 32 × 32 px, and axe runs also at an entry address, arrived at from the Quick start, where the entry shows its linked state and the link back to that page. An error on one page is reported for that page; the others are still checked. |
| `scripts/check-glossary.mjs` | First it proves itself on pages it sets itself (an unlinked term, a term linked twice, an exempt passage and more): each must fail or pass as expected. The glossary register: every entry has a term and an explanation in both languages. The Glossary of each language, with JavaScript on and off: the letter index, the entries in the alphabetical order of the language as a description list, each with term, counterpart, language code and `lang`; both Glossaries hold the same entries; at every entry address that entry and no other shows the linked state, which ends when the address changes. Every other page: the first occurrence of a term in the content is its glossary link, no entry is linked twice, and a glossary link leads to its entry on the Glossary of the page's language with a dotted underline. "Appears in" lists exactly the pages that link the term. The way back: after a click on a glossary link of a page the entry holds the link "Back to the previous page", a click on it returns to that page, the link is there again after going forward to the entry, and it goes when the address changes; opened directly, or with a Glossary of either language, another site or an address outside the documentation as the page before, the entry holds none. |
| `scripts/check-steps.mjs` | First the step list of the frontmatter (`stepFaults` in `src/site.ts`): a step without an anchor or a title and an anchor that stands twice are named. Then every step page, which is every page that holds step cards; what a page must show stands in `stepPages` and `words` at the top of the script, written out per language, and a step page without an entry there fails. Desktop: one card per step in order with counter, the tag "optional" on the optional steps only, pad, trace and a figure or flow diagram; the step title is a link to its step; the chapter tree lists the steps with the titles of the cards; an address with the anchor of a step opens with that step at the top of the window, without a highlight; the path end with its marker on the axis of the pads, the closing line and the page links. A card with a part of one platform holds a platform switch. A link of the content to GitHub opens in a new tab with its hidden text, a link to another site is a plain link; the step of the download holds exactly one link to the page of the release on GitHub (`<repository>/releases/tag/v<version>`), named by its tag. The platform switch, also the one without a command (a hairline under its active tab, no code block, no copy button): Windows on the first visit; a click on "Linux" changes every switch and every part of the page while the used switch keeps its place in the window and focus; arrow keys, Home and End; one tab stop per switch; the choice after a reload, on another page, and before the scripts of the page run; without storage it holds for the page and no error shows. The copy button: after the tabs and before the command; the clipboard holds the command without prompt and output; "Copied" for at least 2 s, announced, focus kept; a refused copy shows and announces the failure text. Every block that scrolls sideways takes focus and is a named region; the terminal block shows its ring inside. A code excerpt in a card ("Build an adapter step by step"): in the steps and in the number the entry of the page names (`excerpts`), a figure with a caption over the full card width below the columns, its code a region named after its file that Tab reaches, with the focus ring, without a copy button; at 390 px inside the window, its code scrolling inside its box with the arrow key. A code block that is no command (`documents`: the compare request of that page) carries the name the entry gives it, and its copy button is named after it. A page whose entry names no excerpt and no such block must hold none. The result table and the bar figure, which shows the sums of the table: the bar of the largest sum spans half the track, the others in proportion to their sums. No transition and no animation in the content. Axe with Windows and with Linux chosen. Phone: one column, the figure below the text, the flow diagram as a stack, the result table as stacked records with its head row, code and terminal scrolling inside their block, tabs and copy button at least 40 px high, no text of a figure below 11 px, the step list left out of the menu, the scroll position kept when the menu opens and closes; an element that reaches beyond the window is named, also at 320 px. A page of sessions of single commands ("Your own calculations on the reference model"): one terminal block per platform in each step, named with its step; its copy button copies every command of the session, one per line; the output carries the language `en` on the page of either language and a command none; where the output of a step is cut, one mark stands in the place of the lines left out, with their number, in the language of the page, on a line of its own, in the typeface of the text between two dashed rules. A page whose entry names no result table and no flow diagram must hold none. JavaScript off, at 1280 and 390 px: both platforms' parts visible, Windows first, each under its label; no tabs, no button, no copy button. |
| `scripts/check-prose.mjs` | First the reader of the facts of the example (`src/example.ts`) on the four capture files: the number of revisions, the number of each revision of the search table, the revisions of the two states and the number of model points, each held against the capture in a second way; and it must throw, with the file and the part, on a capture text whose table of the changes lacks a revision of the search table or its rows, whose commands name no revision, and on a search table without rows. Then the readers of the two four-column tables of the demo and of the interval of a "Not resolved" message, in the same file: head row, rows and the sentence above each table, held against the capture in a second way. The reader of the table of the regression must throw on a capture text without the table, without its head row and without the sentence above it; the reader of the table of the changes on one without the table, without its head row and with a row that leaves the columns of its head row; the reader of the interval on a message whose revisions the table of the changes does not hold, that names none, or whose changes do not follow one another. Then every page of prose, which is every page that holds section headings; what a page must show stands in `prosePages` at the top of the script, and a page of prose without an entry there fails. Every level-2 heading of the content is a section heading with the anchor the script names, in order, and a link to itself; no other link leads to a section, apart from a section the entry of the page names as linked from the content (`linked`; the options several commands share on "Single commands"), which the content must then link. No part of the content names a step that is not there. The platform switches of a page of prose are those its entry names (`switches`), each a block between the blocks of the page: a tab list of two buttons, the copy button after it, the command as a named region with the place the page gives it ("Command, request, Windows"); Windows on the first visit, a click on "Linux" and the arrow keys change every switch while the used one keeps focus and place, the copy button copies the command that is shown, a switch without a command holds no code block and no copy button; axe with Linux chosen; tabs and copy button at least 40 px high at 390 px; with JavaScript off both parts under their labels, Windows first, without tabs and buttons. A page of prose whose entry names no switch must hold none. The language switch at the address of a section opens the counterpart at that section. A wide figure spans the content width and holds its caption as text; no text of a figure is below 11 px. The idea figure: the boxes name the revisions of the two states; one square per revision, 7 px, those of the search table 11 px with their number, drawn as borders and hidden from assistive technology; the two lines of text begin with the counts and the caption names the numbers; at 1280 px the boxes stand left and right of the trace, at 390 and 320 px the figure is a stack of box, trace, box, and the squares keep their size, do not overlap and stay inside the figure. The bars below it carry "number · revision" and the sum of the capture of the language. A row list numbers its rows; the code name of a row follows its name as inline code that is not translated, in weight 400, and the tag of a row is a small mono label in capitals with a hairline border, at 1280 px at the right end of the row and at 390 and 320 px below its text; where the entry of the page names the numbers of code names and tags (`codes`, `tags`), the page holds as many. A sub-heading is a level-3 heading of 18 px after a section heading, as many as the entry names (`subHeadings`). The connection figure: one per page, a wide figure and an ordered list of the three boxes the script names per language, each with its two small lines; only the box the script names as built is dashed, the others are solid; the first trace carries the one label, in teal-text; at 1280 px the boxes stand side by side with the label between the first two, above the trace, at 390 and 320 px they are a stack with the label between the first two; nothing is scaled and nothing reaches beyond the figure. The yardstick box: a block of the page with a navy border, its tag, the line that begins with the number of lines in 22 px, and a text that names a file as inline code. A code excerpt: a figure with a caption and a head row that names its file first; its code is a region named after its file that Tab reaches, with the focus ring, not translated, without markup (uncoloured), and scrolls sideways inside its box, at 390 and 320 px with the arrow key; it holds no copy button. A page whose entry names no yardstick box and no code excerpt must hold none. The tables of the demo: for the two of `DemoTable`, head row, rows and the sentence above as the capture of the language prints them; for the table of the search, revision and sum of each row as the capture prints them, and a caption that is not empty. For all three: the roles written out, a header per row, a quantity, a description and "Bruttobeitrag" with their language, a hash marked as not to be translated; at 1280 px a row is one line, at 390 and 320 px every row and the head row are records of two lines, each cell on the line of its column name and, in a four-column table, below it, and no cell reaches beyond the window. The line of the changes: one square per change, those of the search table 11 px with their number, a bracket from the first to the last change of the interval that is not resolved with their numbers above it, the key and the caption with the numbers; at 1280 px the key stands right of the trace, at 390 and 320 px below it; nothing is scaled; the bars below it as under the idea figure. The wide flow diagram: one per page, a wide figure and an ordered list of the boxes the script names per language, in their order, each numbered, outlined, with a title of 13 px and no mono line; the trace ends in a pad hidden from assistive technology and the words the script names; the first row list of the page names the same parts in the same order; at 1280 px the boxes stand side by side from left to right with the end right of them, at 390 and 320 px as a stack with the end below; nothing is scaled and nothing reaches beyond the figure. The path block shows the four stages of the register, each with a sentence and a link to each of its pages but the page itself, by name and address of the register. No transition and no animation; no sideways scrolling at 1280, 390 and 320 px; axe at 1280 and 390 px. |
| `scripts/check-hints.mjs` | The hint list and the contact block of "When something goes wrong" and the hint links that lead to it, in both languages (see "The help page"). First the register of the hint groups (`groupFaults` in `src/hints.ts`): anchors of small letters, digits and hyphens, each once; pages of the page register in path order; one group per step or section. Then it proves itself on the facts it has read from the built pages, altered in one place each: a group whose step is not there, a hint link without a group, a group whose step carries no hint link, a group and a hint link in one language only, groups out of order and a heading that is not the title of the step must each be named with the group, the step or the page. On the built pages: the help page shows exactly the groups of the register, in its order; a group names a step or a section that its page holds, carries the label of page and step ("Quick start · step 1", for a section the word "section") outside its heading, the title of the step card or the heading of the section as a section heading with the anchor of the group, at least one hint with a level-3 title and a text, and one link to its step by that title; a step or a section with a group carries exactly one hint link, inside it, in the words of the language, to its group on the help page of the language, and no other step or section carries one; both languages hold the same groups and the same hint links. Followed in the browser: every hint link opens the help page of its language at its group, and the link of the group leads back to the step or section. The contact block: the last block of the page under the last section heading, its title a level-3 heading; e-mail, phone and address are those of `contact` in `src/site.ts`, the e-mail the one link (`mailto:`); the list of what to tell names the release of `src/release.json`; the page holds no form. The looks at 1280, 390 and 320 px: the group label in mono 12 px capitals, the group heading 22 px and on the phone 20 px, 4 px below its label; a hint with a hairline above and 16 px padding, at 1280 px in two columns, the left 260 px wide and 36 px from the right, at 390 and 320 px in one column; a quoted message in the white mono box; the contact block with a 1 px navy border, 24 px padding and on the phone 16 px, the e-mail in mono, underlined and at least 24 px high, the values 18 px beside their labels and on the phone 16 px below them, the address 14 px; no sideways scrolling. Axe, the section headings and the language switch of the page are checked by the scripts above, as for every page of prose. |
| `scripts/check-excerpts.mjs` | What the built pages show of the repository's code, held against the tag of the release (`v<version>` of `src/release.json`), which it reads with the `git` program. First it proves itself on texts it sets itself: an altered excerpt, a range that does not hold the code, a member the protocol does not hold, a member a complete page leaves out or names twice, a file that differs on `main`, a wrong number of lines and a tag the clone does not hold must each fail and name what the message is to name. Then, on every page of the register: the code of a code excerpt is, character for character, the lines its head row names of its file at the tag, and the head row names file, lines and tag; a row marked as a member of the protocol (`member`) names a method or an annotated attribute of that class in `degelmann/deltarecon/protocol.py` at the tag, or, where the row carries a tag such as "optional", an operation the comment of the class describes; a row marked as a name of the engine selection (`selection`) names, with the first word of its code name, a name that stands in `degelmann/deltarecon/engine_selection.py` at the tag; on a page with such rows every code name of a row carries one of the two marks; on a page the script names as complete (`COMPLETE`: "Build an adapter step by step") every member of `Engine` and of `Session` at the tag, the operations their comments describe included, has exactly one row marked as that member, so a member the page leaves out or names twice fails; a number of lines (`data-lines-of`) is that of its file at the tag, and the number of a yardstick box the sum over its files, each of which its text names as inline code. Once: the two files are the same on `main` as at the tag. It fails, with the name of the tag, when the local clone does not hold the tag, and when no built page holds an excerpt, a member row or a yardstick box. It does not read what a row says about a member, and on a page that is not named as complete not whether it lists every member of the protocol. |

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
width; and the Glossary of each language at desktop and phone width, plain
and at an entry address (`glossary-`). Lay the first group beside the mock of
the Overview page when the frame or a component of a page of prose changes,
and the last beside the mock of the Glossary when the Glossary changes. The
check of the step pages writes, per step page and language, `<page>-desktop-<lang>.png` and
`<page>-phone-<lang>.png` (`quick-start-desktop-en.png`); lay them beside the
mock of the Quick start when a step component changes. The check of the hints
writes `help-desktop-<lang>.png` and `help-phone-<lang>.png`; lay them beside
the mock of "When something goes wrong" when a component of the help page
changes.

What no script checks: the looks on hover, a Windows contrast theme, a screen
reader, and zoom to 400 %.

## Page register

`src/site.ts` is the register of the site: the four stages, the eleven pages in
path order with their name and address per language, the addresses outside
the documentation, the texts of the page frame, of the Glossary and of the
step components in both languages (the components of a page of prose need
none of their own, apart from the words "lines … to …" of the head row of a
code excerpt; the path block takes the word for "Stage" from the frame), the words of a hint link and of a hint group and the labels of the contact block, the contact details (`contact`, see "The help page"), the check of a step list (`stepFaults`), and the page-not-found page, which stands outside the path
(`notFoundPage`, `onPath()`). Chapter
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
- A step page lists its steps in the frontmatter; see "Step pages".
- A page of prose may list its sections in the frontmatter (`sections:`, each
  with `anchor`, `title` and, for a title that is a name of the program,
  `code: true`). The chapter tree then lists them under the page, as points
  without numbers, in the column only. "Single commands" does so; the prose
  check (`tree` in `prosePages`) holds the list against the section headings
  and fails on a page of prose that lists sections without that entry.
- A new page needs an entry in `pages` of `src/site.ts` (at its place on the
  path) and both files. `npm run check` fails when a page of the register is
  not built or a built page is not in the register.
- Only the start pages hold the words "Veränderungsanalyse" (German) and
  "balance" (English); the search checks look for them (`ownWord` of
  `searchTexts` in `scripts/harness.mjs`). No other page of the language
  may hold the word of its start page, and no page the word of the other
  language. Whoever takes such a word out of a start page gives `searchTexts`
  another. Try a new word in the built search of both languages first: the
  search also finds a word that begins like a part of a name, so
  "reconciliation" finds "DeltaRecon" on German pages and cannot be the word.
  The same list names a word that several pages of a language hold in
  their name or text ("Engine", "engine"; at least two pages must keep it) and a word that only the page-not-found page holds
  ("Tippfehler", "renamed"); no page of the path may hold the latter.
- A page may have a word of its own as well (`pageWords` in
  `scripts/harness.mjs`; "bracket" and "Stornosatz" for Understand the
  results, "middle" and "Durchlauf" for How DeltaRecon works, "whoever" and
  "kaufmännisch" for Write a tolerance profile, "launcher" and
  "Umgebungsvariable" for Single commands, "yardstick" and "Maßstab" for
  What your engine must provide, "lookup" and "Kleinbuchstaben" for Build an
  adapter step by step, "phone" and "Telefon" for When something goes wrong): only that page of its language holds it, and the search of the
  other language finds nothing for it. The search falls back to the
  beginning of a word, so "decrement" finds German pages by "de"; try a word
  in both languages before it is set. For the same reason a page keeps a
  command with a one-letter option out of the search index: with
  `git ls-tree -r` and `--no-renames` indexed, the adapter page was the one
  hit of "renamed", the word of the page-not-found page. It writes the Git
  commands of its callout as `<code data-pagefind-ignore="index">` (`git` at
  the top of both page files).

## Step pages

A page with instructions is a list of step cards on one trace. The Quick
start is the first; `src/pages/en/quick-start.mdx` is the pattern.

**The step list.** The frontmatter names the steps once per language; the
card, its counter and the chapter tree read title and number from there:

```
steps:
  - { anchor: download, title: "Download the package" }
  - { anchor: check, title: "Check the archive", optional: true }
```

The anchor is the address of the step and is the same in both languages.
The build fails, with page and step, on a step without an anchor or a title,
on an anchor that stands twice, and on a card whose anchor the list does not
hold.

**The page.**

```
<Steps>
<StepCard steps={frontmatter.steps} anchor="check">

Text of the step.

<PlatformSwitch windows={['Get-FileHash …']} linux={['sha256sum …']}>
  <div slot="after-windows">

What the reader sees on Windows.

  </div>
</PlatformSwitch>

<StepFigure slot="figure">
  <FileList label="…" files={[{ name: 'SHA256SUMS', note: 'for step 2' }]} />
  <p slot="caption">The caption.</p>
</StepFigure>

<div slot="wide">
<Callout tag="Hint" title="…">

Text.

</Callout>
</div>

<HintLink slot="hint" step="check" />

</StepCard>
</Steps>

<PathEnd>The closing line.</PathEnd>
```

The content of a card is its text column. `slot="figure"` is the right
column; `slot="wide"` stands below both at the full card width;
`slot="hint"` is the hint link of the step, the last line of the card (see
"The help page"). A card without a figure has one column. Text between blank lines is a paragraph.
A wide part that holds several blocks one below the other (row list, code
excerpt, callout, text) is written `<div slot="wide" class="step-parts">`,
which sets them 16 px apart.

**The components**, all under `src/components/`; their looks are in
`src/styles/global.css`, their texts in `texts` of `src/site.ts`.

| Component | What it is |
|---|---|
| `Steps`, `StepCard` | The list and one card: pad, counter ("Step 2 of 6"), the word "optional", the title as a link to the step. |
| `PlatformSwitch` | The command of a step for Windows and Linux (`windows`, `linux`: the command lines), with the sentences that hold for one platform in the slots `after-windows` and `after-linux`. A slot must not carry the name of a property. On a page of prose, where no step card gives the number of a step, `place` says where the command stands (`place="request"`: "Command, request, Windows", "Copy command, request"); see "Pages of prose". Without `windows` and `linux` it holds no command: the tabs stand above the sentences, without code block and copy button, and the Windows tab names no shell. The build fails for a switch with the command of one platform only, and for a switch without commands that lacks the sentences of a platform. |
| `PlatformPart` | Content of one platform outside a switch (`os="windows"`): a sentence, a callout, a terminal block. Every sentence that holds for one platform only stands in a part or in a slot of a switch. Only in a card that holds a platform switch; a card with content of one platform and no command gets a `PlatformSwitch` without commands, or the reader cannot change the platform there. |
| `CodeBlock` | A command that does not differ by platform. `PlatformSwitch` builds its own. With `label` it is a block that is no command, as a document the reader copies into a file: `label` is its whole name ("Compare request, smallest example"), and its copy button is named "Copy: <label>". |
| `RowList`, `Row`, `CodeExcerpt` | The row list and the code excerpt of a page of prose (see "Pages of prose"), in the wide part of a card. The excerpt takes the full card width. |
| `TerminalBlock` | A session: prompt, command, and output from a capture (`lines={session('windows', 'en')}`). With `entries` in place of `command` and `lines` it is a session of single commands, each with the prompt and what it printed; the block then names its step ("Terminal session, step 2, PowerShell"), its copy button copies every command, one per line, and the output carries `lang="en"` on a German page, a quantity name `lang="de"`, a hash and a path `translate="no"` (`commandOutputHtml` in `src/markup.ts`). |
| `CommandSession` | The terminal session of a step of single commands, once per platform, from the captures of the step (`step`, `commands`: the command lines the page types, the same it gives the platform switch). The build fails when they are not the commands of the capture. `cut` leaves a run of lines out and puts one line of page text in its place, the mark of a cut; see "Captures and the release check". |
| `StepFigure` | The frame of a step figure with its caption (`slot="caption"`). Into it: `FileList`, `BarFigure`, `ArchiveCheckFigure` (the small diagram of the archive check). |
| `KeyCap` | A step figure of its own kind: a key and one sentence. |
| `FlowDiagram`, `FlowBox` | A sequence as boxes on one trace; in the text column of a card without a figure. Horizontal from 1280 px, a stack below. `code` and `writes` of a box are its mono line; a box without them has none. With `wide` the diagram is a wide figure of a page of prose, see "Pages of prose". |
| `SummaryList` | Sub-steps as a numbered list; the second line of a row is output from a capture, and `lineLang` names its language where that is not the language of the page. |
| `ResultTable` | The table of the demo's search, from the capture; the content is what the page says before the caption of the program. |
| `Callout` | A term or an expected outcome in plain words, or a hint. `quote` is a message of the program from a capture, and `quoteLang` names its language where that is not the language of the page. |
| `HintLink` | The hint link of a step, in the slot `hint` of its card (`step`: the anchor of the step): one line that leads to the group of the step on "When something goes wrong". Only a step that has a group in the register of the hint groups carries one; see "The help page". |
| `PathEnd` | The marker under the last step and the closing line. The page links follow by themselves. |

A component that names its step ("Command, step 2", "Copy command, step 2")
writes `STEP_MARK` (`src/markup.ts`); the card puts its number there. A page
never types a step number into a component.

**A link to another site** (GitHub) opens in a new tab and says so to
assistive technology. A page writes it with `src/components/OutsideLink.astro`,
never as a plain link:

```
import OutsideLink from '../../components/OutsideLink.astro';

Open the release <OutsideLink href={releasePage} hreflang="en">{tag}</OutsideLink> on GitHub.
```

It sets `target="_blank"` and `rel="noopener"` and adds the hidden text
"(opens in a new tab)" in the page language (`newTab` in `texts`), which is
kept out of the search index; `hreflang` names the language of the page it
leads to. The footer uses it for licence and repository. A link to the
company website is a plain link.

**Platform.** The delivered page holds both platforms' parts one after the
other, Windows first, each under its label; that is the page without
JavaScript. An inline script in the head (`src/layouts/Page.astro`) sets
`data-platform` on `<html>`: Windows, or what the reader chose before
(`localStorage`, key `deltarecon-docs-platform`). The stylesheet shows the
parts of that platform; `src/scripts/platform.ts` turns the labels of each
switch into tabs, and applies the remembered choice again when the browser
shows a page it kept (going back to it). `src/scripts/copy.ts` puts in the copy buttons; the
delivered page has none.

**Glossary terms.** Both platforms' parts count as content, shown or not:
link a term in one of them only. Output from a capture cannot hold a
glossary link, so the text of the page links a term before the output that
names it (the Quick start does so before its flow diagram and its table).

**A new step page** needs an entry in `stepPages` of
`scripts/check-steps.mjs` (anchors, optional steps, the steps with a switch,
the steps whose switch holds no command, the steps with a terminal block,
the step with the link to the page of the release, the step with the result
table and whether the page holds a flow diagram, where it has them, and the
closing line per language; for a page of sessions of single commands
`sessions` and, where an output is cut, the step, the number of lines left
out and the mark per language; the number of code excerpts per step, as
`excerpts`, and a code block that is no command with its step and its name
per language, as `documents`).

## Pages of prose

A page that explains is prose under section headings, with wide figures and
lists. The Overview is the first; `src/pages/en/index.mdx` is the pattern. A
page imports the components it uses.

```
<SectionHeading id="what-you-get">What you get</SectionHeading>

<Prose>

A paragraph with a <Term id="record">record</Term>.

</Prose>

<RowList>
  <Row name="Where the results differ">The second line of the row.</Row>
  <Row name="The engine selection" code="--engine" tag="optional">The second line.</Row>
</RowList>

<WideFigure label="Sum of the deviation, by revision">
  <IdeaFigure … />
  <BarFigure slot="second" numbered />
  <p slot="caption">What the figure shows, in words.</p>
</WideFigure>
```

**The components**, all under `src/components/`; their looks are in
`src/styles/global.css`, one section each.

| Component | What it is |
|---|---|
| `SectionHeading` | A level-2 heading with an address of its own; the heading is a link to itself. `command` marks the section as the section of a command of the package (`data-command`), for the release check. `id` is the anchor, the same in both languages, so that the language switch keeps the position. The build fails, with the page, on a heading without an `id` of small letters, digits and hyphens. A page of prose writes no `##` heading: its anchor would follow its text, which differs by language. |
| `SubHeading` | A level-3 heading that divides a section; `id` is optional and, where given, small letters, digits and hyphens. |
| `Prose` | Paragraphs, at most 720 px wide. Text between blank lines is a paragraph; links are inline links or glossary links. |
| `WideFigure` | A figure over the content width. The drawing is its content, the caption the slot `caption`; the caption is the text alternative of the figure and says in words what the drawing shows. A second part below a hairline is the slot `second` with the property `label`. The build fails without a caption and when only one of `second` and `label` is there. |
| `IdeaFigure` | The idea of DeltaRecon in one picture, inside a wide figure: two outlined boxes and between them one square per revision. Squares, their numbers and the two short hashes come from the captures (`example` of `src/captures.ts`); the page gives the words (`before`, `after`, `revision`, `count`, `deviating`). The boxes stand beside the trace where the wide figure is at least 640 px wide inside, and as a stack otherwise; the trace is never scaled. |
| `ChangeLine` | The line of the changes, inside a wide figure: every change as one square on a trace, the revisions of the search table filled and numbered, a bracket over the interval the search reports as not resolved, and beside the trace a key that says in words what each shape stands for. The page gives the words (`count`, `found`, `unresolved`, `other`). The key stands right of the trace where the wide figure is at least 640 px wide inside, and below it otherwise; the trace is never scaled. |
| `RevisionTrack` | The trace both figures draw, from the captures; a page does not use it directly. With `marked` it adds the bracket. |
| `DemoTable` | One of the two four-column tables of the demo, from the capture: `table="regression"` (step 2) or `table="changes"` (step 3). The content is what the page says before the sentence of the program. It shares the looks of `ResultTable`, the table of the search, which a page of prose uses as a step page does. Below the phone breakpoint a row is a record of two lines, and the head row has the same two lines, so that each column name stands above its values. A table that stands in a page of prose is at most 820 px wide. |
| `FlowDiagram` with `wide` | A sequence of four parts as a wide figure: the flow diagram of a step card with the frame and the caption of a wide figure. It is a figure itself and does not stand inside `WideFigure`; the build fails without a caption. Its boxes stand for parts of an explanation and carry no mono line (`<FlowBox>Two recorded results</FlowBox>`). Horizontal from 1280 px, four boxes in one row, and a stack below; never scaled. A row list after it names the same parts in the same order and says what each is, so that the diagram stands as text beside itself; a page keeps the names in one list (`parts`) for both. |
| `BarFigure` with `numbered` | The bars of the search table as the second part of that figure: each label begins with the number of its revision ("2 · 936e50d"). Without `numbered` it is the bar figure of a step card. |
| `RowList`, `Row` | Numbered rows; the list gives the numbers. A row has a `name` in plain words, a `code` name after it, a `tag` at its right end (on the phone below the text), and its content as the second line. Write a row on one line, so that its content is no paragraph of its own. `option` marks the row as the row of the option its `code` names (`data-option`), for the release check; the build fails on such a row without `code`. `member="Session"` or `member="Engine"` marks the row as the row of the member of the protocol its `code` names (`data-member`), and `selection` as the row of a name of the engine selection, the first word of its `code`; the excerpt check holds both against the tag of the release (see "Code of the repository on a page"). On the list, `label` puts the kind of its rows above it as a small mono label, which is also the name of the list ("Reads", "Writes": the files of a command), and `plain` leaves the numbers out, for rows that name a number of their own (the exit statuses); the list is then an unordered list. |
| `Member`, `Part` | A member card: one member of the protocol as a block of its own, on the page "Build an adapter step by step". `<Member name="…" code="describe" of="Engine">` shows the name in plain words, the name in the code (marked `data-member`, as a row with `member` is) and the signature of the member as it stands at the tag (`signatures` of `src/excerpts.ts`, copied like an excerpt, without the indentation its lines share); `tag` puts a word such as "optional" at the right end; a card without `of` is no member and names its signature by `signature`. Its content says what the reader programs. `<Part label="You are given">` is one part of it under a small label: what the member is given, what it gives back, what it reports. The excerpt check holds signature and member against the tag. |
| `Fold` | A part that the reader opens: a `details` element with the line that opens it (`summary`), closed when the page opens. It works without a script. What it holds is content like any other for the glossary check and the excerpt check; the step check opens every fold before it looks at the excerpts inside. On a member card it holds how the reference model does it. |
| `Sample` | What a member takes or gives at the reference model, as lines under a small label: `<Sample id="describe" label="Call and result" />`. The lines stand in `src/adapterSamples.ts`, once for both languages, read from a call of the reference model of the release; no check holds them, so whoever renews the release calls the members again. No copy button; kept out of the search index, because its values are words of the program. |
| `Synopsis` | The usage line of a command of the package under a small label, as the help of the command prints it: `<Synopsis command="request" />`. The lines stand in `src/synopsis.ts`, once for both languages. It is a pattern and no command to run: no copy button. The build fails on a command the file does not hold; the release check holds each against the released help. |
| `PlatformSwitch` with `place` | The platform switch of a step page as a block of a page of prose, between prose and row lists and at most 820 px wide. With `windows` and `linux` it needs `place`, a word for where the command stands, which names the command and its copy button in the place of a step; without commands it holds the sentences of each platform alone. `PlatformPart` stays a part of a step card. |
| `ConnectionFigure` | Where the adapter sits and what the reader builds: three outlined boxes on one trace, of which only the box marked `built` is dashed; the first trace carries the one label (`trace`). The page gives the words of each box (`state`, the small line above the title that says whether the box exists or is built; `title`; `sub`) and the caption (slot `caption`), which is the text alternative. It is a wide figure itself and does not stand inside `WideFigure`. Side by side from 1280 px and a stack below; never scaled. The build fails without a caption, with other than three boxes, with other than one box that is built, and without the label. |
| `YardstickBox` | The size of the connection of the reference model: a box with a navy border, a mono tag (`tag`), the line with the number of lines, and one or two sentences (the content) that name each file as inline code. `files` are the paths of the files of the connection; the box adds up their lines (`lineCount` of `src/excerpts.ts`) and prints the sum, in the number format of the language, before `unit`, the words of the page ("lines in one file"). It states no effort. The build fails without files, `tag`, `unit` or content, and for a file `src/excerpts.ts` holds no number of lines for. |
| `CodeExcerpt` | A short piece of the repository's code with its origin: a figure with a head row (the file left; the lines and the tag of the release right), the code, uncoloured, and a caption (slot `caption`). `id` names the excerpt in `src/excerpts.ts`; a page types no line of code. The code scrolls sideways inside its box, takes focus and is a region named after its file and lines; it has no copy button. `unindexed` keeps the code out of the search index, for an excerpt with names of one letter, which the search would offer as a hit for every word that begins with that letter. The build fails on an `id` the register does not hold, on an excerpt whose code has another number of lines than its range, and without a caption. |
| `PathBlock` | The four stages with their pages, from the register: stage number, stage name and a link to each page of the stage but the page the block stands on. The page gives one sentence per stage in the slots `stage-1` to `stage-4`, each a `<span>` on one line. The build fails on a stage without its sentence. |

**Numbers of the example.** A page types no number of revisions, hash, sum
or number of model points of the example. It reads them: `example(lang)` of `src/captures.ts` gives the number
of revisions, the number of each revision of the search table, the short
hashes of the two states and the number of model points; `listOf` of
`src/markup.ts` writes a list in words ("2, 6, 12 and 30"). The Overview
types what no part of `captures.ts` gives: the number of steps and of tables
of the demo, the projection years of the search, and the column names of the
three tables. No check holds these against the captures; whoever takes a new
release's captures compares them by hand.

Understand the results reads more: `regressionTable`, `changeTable`,
`searchCounts` and `unresolved`, and one row of a table by its key with
`quantityOf(lang, 'Anzahl Verträge')`, `changeOf(lang, '936e50d')` and
`searchRowOf(lang, '936e50d')`. The key is typed; the number, the
description and the sum that the page shows are read, and the build fails
when the capture does not hold the key. What the captures do not hold (how
many model points are new business or single premium, the sum of the four
sums and the whole deviation) stands in `typed` at the top of each of the
two page files, in the number format of the language; the plan of the page
names the source of each. No check holds these against a run; whoever takes
a new release's captures renews them from that run.

**A link to a page of the documentation** takes name and address from the
register, so that a renamed page needs no edit:

```
import { findPage, pageAddress } from '../../site';

export const quickStart = findPage('quick-start');

Start with the <a href={pageAddress(quickStart, 'en')}>{quickStart.name.en}</a>.
```

**Glossary terms.** The words of a figure and of a list row count as content.
Link a term in the prose before the figure or the row that names it, or in
the row itself; a property of a component (`name`, `count`, `label`) cannot
hold a glossary link.

**A new page of prose** needs an entry in `prosePages` of
`scripts/check-prose.mjs` (the anchors of its sections in order, the section
the language switch is tried at, whether it holds the idea figure and the
path block, the number of its rows, whether it holds the tables of the demo
and the line of the changes, and for a wide flow diagram the titles of its
boxes and the words its trace ends in, per language; a section that the
content links to, as `linked`; and its platform switches, as `switches`: the
place of each switch with a command, in order, and the number of switches
without one; a place that differs by language is written per language,
`{ en: 'engine selection', de: 'Auswahl der Engine' }`; for a connection
figure the titles of its boxes, the title of the box that is built and the
label of its trace, per language; the numbers of yardstick boxes, code
excerpts and sub-headings, and of the rows with a code name and with a tag).
"When something goes wrong" needs no entry typed there: the script builds it
from the register of the hint groups.

## The help page

"When something goes wrong" is the last page of the path: hints for what
looks like an error, grouped by page and step in the order of the path, and
at its end the contact block. `src/pages/en/when-something-goes-wrong.mdx`
is the pattern.

```
<HintGroup id="quick-start-result">

<Hint title="A block “Not resolved” follows the table" quote={notResolved('en')}>
<p slot="before">A sentence that stands before the quoted message.</p>

What it means and what to do.

</Hint>

</HintGroup>

<SectionHeading id={contactAnchor}>If none of this helps</SectionHeading>

<ContactBlock tag="Contact" title="Write to us or call">

So that we can help, please tell us:

- the release, for example {tag}

</ContactBlock>
```

**The register of the hint groups**, `src/hints.ts`, names every group: its
anchor on the help page (the same in both languages; `<page>-<step>`), the
page it belongs to, and the step or the section of that page by its anchor.
Its order is the order of the groups on the help page: the pages in path
order, the steps or sections of a page in their order. Both directions read
it, so they cannot differ: `HintGroup` builds a group from its entry, and
`HintLink` gives a step or a section the link to its group. The words of
both stand in `texts` of `src/site.ts` (`hintLinkStep`, `hintToStep` and so
on).

**The components**, all under `src/components/`; their looks are in
`src/styles/global.css` under "Help".

| Component | What it is |
|---|---|
| `HintGroup` | One group: the label with page and step ("Quick start · step 1"; for a section "Single commands · section"), which stands outside the heading; the title as a section heading with the anchor of the group; the hints; and a link to the step or section by its title. `id` is the anchor of the entry in the register. The title of a step is read from the step list in the frontmatter of its page. A page of prose names its sections in its text only, so the group of a section takes its title from the slot `title` (`<span slot="title"><code translate="no">run</code>: compute a request</span>`), and the check holds it against the heading of the section. The build fails on a group the register does not hold, on a page the page register does not hold, on a step its page does not hold, on a group of a section without the slot `title`, and on a group without hints. |
| `Hint` | One hint: what the reader sees as a level-3 heading (`title`, or the slot `title` for a title with inline code), and what it means and what to do as its content. Two columns from 600 px, the left 260 px wide; one column on the phone. `quote` is a message of the program from a capture, in the white mono box of the callout above the text, and `quoteLang` names its language where that is not the language of the page; the slot `before` holds a sentence that stands before the message. A page types no message. |
| `HintLink` | The hint link: `<HintLink slot="hint" step="download" />` as the last line of a step card, `<HintLink section="start" />` at the end of a section of a page of prose. The build fails on a step or a section without a group in the register, and on a hint link in the card of another step. The line is kept out of the search index. |
| `ContactBlock` | The contact block with its navy border: a mono tag (`tag`), the title as a level-3 heading (`title`), e-mail, phone and address, and as its content the short list of what to tell. The e-mail is a link; phone and address are text. On the phone each label stands above its value. |

**The contact details** are those of the imprint of the company website
(`outside.imprint`): provider and address, e-mail and phone, exactly as the
imprint states them. The build cannot read the repository of the website, so
they are typed once, in `contact` of `src/site.ts`, from
`src/config/site.ts` of that repository, which its page
`src/pages/impressum.astro` shows. When the imprint changes, change them
there and nowhere else. The page states no other contact detail and promises
no time of an answer.

**What a hint may say.** A hint says what the reader sees, then what it
means and what to do, and says so where the case is expected and no error.
It states only what the page of its step, the README of the release
(`git show v<version>:README.md`), the guides of the package, the release
notes or the program at the tag say; the plan of the page lists every hint
with its source. A quoted message comes from a capture (`notResolved` of
`src/captures.ts`, `refusal` of `src/ownCalculations.ts`). The first
occurrence of a glossary term is a `<Term>`; a message from a capture cannot
hold one, so the slot `before` links a term that the message names.

**Adding a group or a hint.** A hint of a step that has a group goes into
that group on the page of both languages. A new group needs an entry in
`hintGroups` of `src/hints.ts` at its place in the order, a `<HintGroup>`
with at least one hint on the help page of both languages at the same
place, and the hint link in the step (`slot="hint"`) or at the end of the
section, in both languages. `scripts/check-hints.mjs` names what is missing:
a group whose step is not there, a group without a hint link in its step, a
hint link without a group, and a group or a hint link that one language
lacks (see "Checks"). When a step is renamed or moved, the label and the
heading of its group follow by themselves; when its anchor changes, change
`target` in the register.

**Keeping it true to a new release**, after the captures are renewed: read
every hint against its source as the plan of the page lists it, and the
traceback faults against the callout of the known limits on "Build an
adapter step by step".

## Code of the repository on a page

"What your engine must provide" and "Build an adapter step by step" show
code and sizes of the repository as they stand at the tag of the release,
`v<version>` of `src/release.json`. A page types none of it. `src/excerpts.ts` holds it, and the build reads
nothing from Git:

- `excerpts`: each excerpt under a key, with its file (the path in the
  repository), its first and last line, and the code. `CodeExcerpt` shows it
  with that origin in its head row.
- `files` and the number of lines of each file a page states the size of.
  `lineCount(file)` gives the number, `inWords(number, lang)` writes it as
  the language does ("1,170", "1.170"). The yardstick box reads it; in
  running text a page marks the number with the file it counts, so that the
  check finds it:
  `<span data-lines-of={files.protocol}>{inWords(lineCount(files.protocol), 'en')}</span>`.

**Adding an excerpt.** Copy the lines, do not type them:

```
git show v<version>:<file> | sed -n '<first>,<last>p'
```

Put them into `excerpts` of `src/excerpts.ts` under a new key, between the
two line breaks of the template, with `file`, `first` and `last`, and write
`<CodeExcerpt id="<key>">` with a caption on the page of each language.
Keep an excerpt short (at most about 15 lines) and choose lines that hold
one long line or none: the code does not wrap. A backtick in the copied
lines is written `${'`'}`, since the code stands in a template.

**Naming a member of the protocol.** A row that names a member of
`degelmann/deltarecon/protocol.py` carries `member` with the class,
`<Row name="Project one model point" code="project" member="Session">`. An
operation that the protocol describes in a comment and does not declare
(`project_many`, `project_target`) needs a `tag` on its row, as "optional".
A row that names an option or a variable of
`degelmann/deltarecon/engine_selection.py` carries `selection`. On a page
with such rows a row of another kind (a member of the compare request)
carries no `code`; it names its member in its content.

**The page that walks through the protocol.** "Build an adapter step by
step" names every member of `Engine` and `Session` in exactly one row, in
the step that describes it. `COMPLETE` at the top of
`scripts/check-excerpts.mjs` names the page; the check fails for a member
it leaves out or names twice. What a row says about a member comes from the
docstring of the member in `protocol.py`; the plan of the page lists each
statement with its source.

`scripts/check-excerpts.mjs`, the last script of `npm run check`, holds all
of this against `git show v<version>:<file>` and fails when
`protocol.py` or `engine_selection.py` on `main` differs from the tag (see
"Checks"). It needs the tag and the branch `main` in the local clone:
`git fetch --tags` brings a missing tag.

**Keeping it true to a new release**, after `src/release.json` holds the new
number: run `npm run check`. The excerpt check names every excerpt whose
lines moved or changed, every number of lines that changed and every member
the protocol no longer holds. Copy the excerpts anew, renew the numbers in
`src/excerpts.ts`, and read both page files against
`git diff v<old>..v<new> -- degelmann/deltarecon/protocol.py degelmann/deltarecon/engine_selection.py`:
on "What your engine must provide" the check does not notice a member that
is new; on "Build an adapter step by step" it names it. On that page read
also the callout of the Git commands and the callout of the known limits
against `git diff v<old>..v<new> -- degelmann/deltarecon/engines/reference_model.py`
and `_bmad-output/initiative-ready-for-actuaries/deferred-work.md`, and run
`npm run check:first-run`.

## The first run of the adapter page

The last step of "Build an adapter step by step" shows `request` and `run`
with the reader's engine: the words between `<` and `>` stand for what the
reader puts in (`firstRun` at the top of both page files), and below them
the smallest compare request (`compareRequest`), typed from
`contracts/v3/compare.md` at the tag. The page shows and names no engine
other than the reference model.

`npm run check:first-run` (`scripts/check-first-run.mjs`) builds the site
and holds that step against the program. It reads the commands from the
built page of each language, puts the engine of `../examples/toy_engine/`
in the places of the words (`toy_engine:ToyEngine`, the stage `toy_premium`,
the revisions `r1` and `r2`), and runs them from the repository root with
`uv run deltarecon`, writing into a temporary folder outside the repository,
which it removes. It asserts:

- the step holds `request` and then `run` per platform, and the Windows
  command is the Linux command apart from the name of the program and the
  path separators;
- both commands end with exit status 0, for each of the two revisions, and
  the folder of a run then holds every file the file list of the step
  names; a command that fails is printed with its output;
- the compare request of the page, filled in for the two runs, is one that
  `compare` reads: the comparison has the outcome `compared`;
- the page does not name the engine the script runs.

It runs the program of the checkout, not the released package, and needs
`uv`; so it is a script of its own. Run it when the last step of the page,
the command line of `request`, `run` or `compare`, or the compare contract
changes, and record commit, command and outcome in the plan of the story.
The script fails for a word between `<` and `>` it has nothing to put in
the place of; a new word gets an entry at the top of the script.

## Captures and the release check

No page types program output. `src/captures/v<version>/` holds the standard
output of the guided demo of the released package, one file per platform and
language (`windows-en.txt`, `windows-de.txt`, `linux-en.txt`,
`linux-de.txt`), in UTF-8 with LF line ends. `src/captures.ts` reads them at
build time and gives the parts a page shows: `session` (the opening up to
the commands of the first step, what the reader sees before the demo first
waits for Enter), `afterLines` (the paragraph after each step), `caption`,
`searchTable`, `notResolved`, and `example`: the facts of the example a page
of prose shows, which `src/example.ts` reads from the same text (the number
of revisions from the table of the changes, the number of each revision of
the search table in it, the revisions of the two states from the commands of
steps 1 and 2, the number of model points). `src/example.ts` also reads
`regressionTable` and `changeTable`, the two four-column tables of steps 2
and 3, each with its head row, its rows and the sentence the demo prints
above it, and `unresolved`, the changes each "Not resolved" message names
with their numbers in the table of the changes; `searchCounts` gives how
many states there are and how many the search computed, from the sentence
above the table of the search. The build fails, with file and
part, when a
file or a part is missing, and when the Windows and the Linux capture of a
language differ in a part that does not depend on the platform. These four
files and the captures of the page of own calculations (below) are the only
run output under version control.

**Renewing them at a release**, after `src/release.json` holds the new
number and the SHA-256 of both archives (from `SHA256SUMS` of the release):

1. Unpack the two archives of `../dist/release-v<version>/` into fresh
   folders, the Linux one on Linux and the Windows one on a Windows host.
2. In each package folder run the starter once per language and keep its
   standard output: `./quickstart --lang en --no-pause > linux-en.txt`, and
   in cmd `quickstart.cmd --lang en --no-pause < NUL > windows-en.txt`; the
   same with `de`. Each must end with exit status 0.
3. Convert the Windows files to UTF-8 with LF line ends (the demo writes
   code page 1252 and CRLF there). Their last line is the line of `pause`
   that the starter prints; it stays.
4. Put the four files into `src/captures/v<version>/` and remove the folder
   of the release before.
5. Run `npm run check` and then, with the folder `search/` of one of the
   runs, `npm run check:release -- --search <demo folder>/search`.

`npm run check:release` (`scripts/check-release.mjs`) is the proof that the
page describes the release. It fails without `../dist/release-v<version>/`
and without `--search`, and names a missing file of the release folder
(`SHA256SUMS`, the release notes, a guide of a package), a missing pin, a
`search.result.json` of another shape and a build that does not start.
Before any build it compares the capture files: the
Windows and the Linux file of a language line by line, with path separators
and the time stamp of the demo folder set aside, and the one line more of the
Windows file only where it is the line of `pause`; the table of the search,
the counts above it and the "Not resolved" message of every file against the
`search.result.json` of the search folder, whose SHA-256 must be the one
`../measurements/quick-start-search.SHA256SUMS` names. A difference is named
with file and line. Then it builds the site and asserts on the Quick start of
both languages:

- every command stands in a guide of the release: for steps 1 to 3 in
  `release-notes.md` (a line of a code block or inline code; `<zip>` stands
  for the Windows archive, and an option may follow a command when the same
  paragraph of the notes names both), else in the README of the release,
  which the notes point to and which holds the full `Expand-Archive` command
  (`git show v<version>:README.md`, so the check needs Git and the tag of
  the release); from step 4 on in the guide of the page's language in the
  package of the platform (`README.txt`, `LIESMICH.txt`), else as a line of
  a code block of the release notes (the `cd` into the package folder). The
  command of a terminal block is a command of the guide with
  `--lang <language>`;
- names of archives and package folders and every SHA-256 on the page are
  those of `SHA256SUMS`, and `src/release.json` holds the same sums; the
  file list of the package folder (the step with the anchor `unpack`) names,
  per platform, exactly the entries of the unpacked package of the release
  folder, a folder with a closing slash;
- output on the page stands in the capture of the language, the terminal
  session of each of the two platforms line by line; table and bar figure show the revisions and sums of
  `search.result.json`.

**The captures of "Your own calculations on the reference model".** The page
shows the single commands a reader types after the quick start, and their
output. Its captures stand in `src/captures/v<version>/own-calculations/`,
where the reader of the demo captures does not see them:

- `order.txt` names the steps of the captures in the order they run: the
  anchors of the seven steps of the page, then `repeat`, the command of the
  second step once more, which the package refuses.
- `<step>-windows.txt` and `<step>-linux.txt` hold, per command of the step,
  the line `command: <the command as typed>`, what it printed (standard
  output and standard error), and the line `exit status: <n>`; UTF-8 with LF
  line ends.

`src/ownCalculations.ts` reads them at build time. `sessionOf(step,
platform, commands)` gives the session of a step and fails the build, with
step and platform, when `commands`, the lines the page types, are not those
of the capture; `cut` puts the mark of a cut in the place of a run of lines;
`statusOf`, `outputOf`, `runsOf`, `contributionsOf` and `beyondDemo` give
the facts the text of the page names (an exit status, the counts of a
search, what a search finds beyond the table of the demo), and `refusal`
the message of the refused command with "…" in the place of the path it
names. The build also fails when the Windows and the Linux capture of a
step differ in more than what varies by run: the path separators, the time
stamp of the demo folder, and the folder the package was unpacked into,
which only the refusal names. The page types the command lines (`commands`
at the top of each page file), the names of the files in its file lists,
and no output.

**Renewing them at a release**, after the captures of the demo:

1. Unpack the two archives into fresh folders, the Linux one on Linux and
   the Windows one on a Windows host, and run the guided demo once in each
   package folder: `./quickstart --lang en --no-pause`, and in PowerShell
   `.\quickstart.cmd --lang en --no-pause`.
2. On Linux, in the package folder:
   `bash <docs>/scripts/capture-own-calculations.sh <docs>/src/captures/v<version>/own-calculations <new folder>`.
   The script reads the `command:` lines of the present captures, runs them
   in their order in one shell, as a reader types them, and writes each
   step's file anew into the new folder, which must not exist.
3. On the Windows host, in Windows PowerShell in the package folder, with a
   copy of the capture folder and of the script on the host:
   `powershell -NoProfile -ExecutionPolicy Bypass -File capture-own-calculations.ps1 -Source <copy of the capture folder> -Target <new folder>`.
   It does the same for the `-windows.txt` files and writes UTF-8 with LF
   line ends.
4. Put the files of both new folders into the capture folder, with
   `order.txt`. A command that changed with the release is changed in the
   `command:` line of its capture before the scripts run, and in both page
   files after.
5. Run `npm run check` and `npm run check:release` as above. Where the
   output changed, read both pages against it: the text names what the
   output shows, the file lists name what the commands wrote, and
   `stepPages` of `scripts/check-steps.mjs` names the number of lines the
   cut leaves out.

For this page `npm run check:release` holds, before the build, the captures
of the two platforms against each other, with file and line, and that a
command which starts the launcher is the same on both apart from the name
of the launcher and the path separators. On the built page of both
languages it asserts:

- every command that starts the launcher names a command of the released
  `deltarecon`, and every option it gives stands in the help of that command
  (`deltarecon --help` and `deltarecon <command> --help` of the unpacked
  Linux package of the release folder; the check runs it, so it needs Linux
  on x86-64). The commands of this page stand in no guide;
- the commands of the platform switch and of the terminal session of each
  step are those of the capture of that step and platform, and the session
  shows the output of the capture line by line, where the mark of a cut
  stands for as many lines as it names;
- a quoted message and the lines of the summary list stand in a capture of
  the page, and a capture that is no step of the page is quoted on it.

**The page "Single commands".** The page describes every command of the
released `deltarecon`: one section per command, in the order of the help,
and a last section for the options several commands share. Its text comes
from the README of the release (`git show v<version>:README.md`), the help
of the released package and the guides of the package; the plan of the page
names the source of each statement. The check reads the page by four
marks, not by its wording:

- `<SectionHeading id="request" command="request">` marks the section of a
  command;
- `<Row … code="--revision" option>` marks the row of an option, and
  `shared([...])` at the top of each page file writes the options of a
  command that the last section describes, each marked `data-option` and
  `data-shared`, with the link to that section;
- the example of a command is a `PlatformSwitch` with `place`, its lines
  typed in `commands` at the top of each page file;
- `<Synopsis command="request" />` under the heading of a command shows its
  usage line.

The name of a command, written in backticks, is a link to the section of
that command: the page maps inline code so (`components` at the top of each
page file). In its own section a command is written as
`<code translate="no">request</code>`, which the map leaves alone, so that
no section links to itself. The prose check holds both (`commands` in
`prosePages`).

On the built page of both languages `npm run check:release` asserts, against
`deltarecon --help` and `deltarecon <command> --help` of the unpacked Linux
package:

- the sections of commands are the commands of the help, in its order, each
  under the anchor of its name: a command that is missing and a section of a
  command the help does not name fail;
- the options marked in the section of a command are the options of its
  help, without `--help`, each once: an option that is missing and an option
  the help does not name fail, with command and option;
- the last section marks only options that at least two commands take, and
  the section of a command names exactly these of its options as shared and
  links there;
- every example stands in the section of its command, once per platform,
  and is a line of the guide of the page's language in the package of the
  platform; the example of `walk`, which no guide holds, starts the launcher
  of the platform, gives only options of the help of `walk` and is the same
  on both platforms apart from the launcher and the path separators; so
  does the example of `compare`, which runs the compare request that the
  example of `replay` wrote;
- the synopsis of a command stands in its section, once, and is the usage
  line of its help, word for word, without `[-h]`.

**The page "Write a tolerance profile".** Its statements come from the
contract of the comparison at the tag of the release
(`contracts/v3/compare.md`: the members of a profile, the tolerance rule and
its worked values) and from the messages of the released package. The
profile of the package stands in `src/toleranceProfile.ts`, line for line;
`npm run check:release` holds it against the file of the unpacked Linux
package. The example profile and the command that uses it stand in the same
file; no check runs them.

The check does not read what a row says about an option, which options are
tagged as required, or the file lists.

**Keeping it true to a new release**, after `src/release.json` and the
captures are renewed: run `npm run check:release -- --search <folder>`. It names every command
and option that the new help has and the page lacks, and every one the page
still describes and the help has dropped. For each, read
`deltarecon <command> --help` of the new package and the README at the new
tag, and change both page files: the row of the option, the tag "required"
where the usage line of the help shows the option without brackets, the
list of shared options, and the text and the file rows of a command whose
description in the README changed (`git diff v<old>..v<new> -- README.md`
shows them). An example changes with the guides of the package. The example
of `walk` is run once in the unpacked Linux package, after the six commands
of the guide, and must end with exit status 0; record commit, command and
outcome in the plan of the story.

Record commit, command and outcome of a run where the story or the epic asks
for it.

## Glossary and glossary links

`src/glossary.ts` is the glossary register: every entry with its anchor (the
same in both languages) and, per language, its term, the word forms the check
looks for, and its explanation. The Glossary page
(`src/components/Glossary.astro`), the glossary link and the check read it. A
term stands there and in no other file; an explanation may hold inline code
and a word marked with its language.

A page links a term at its first occurrence with the glossary link,
`src/components/Term.astro`:

```
import Term from '../../components/Term.astro';

A <Term id="deviation">deviation</Term> between two releases.
```

- `id` is the anchor of the entry. Without content the link prints the term
  of the register (`<Term id="deviation" />`); with content it prints that
  word form. The build fails on an unknown entry and names page and entry.
- Only the first occurrence of a term on a page is a link. The check fails
  when the first occurrence is plain text, and when an entry is linked twice.
- The check looks for the term and the `forms` of its entry as whole words:
  English without regard to case, German in the case as written. Add a
  missing plural or case to `forms`.
- What counts is the content after the page head, without the page links,
  headings, `code`, `pre` and other links. The lead is plain text and cannot
  hold a link. No glossary link belongs in a heading. Content that is not
  shown counts like content that is: with JavaScript off it may be visible.
- A word that equals a term and is not meant as it is marked as exempt:
  `It <span data-no-term>records</span> which state is computed.`
  Several entries are everyday words with a second sense ("run" as a verb,
  "Abschnitt" for a section of the page, the release on GitHub): mark that
  sense as exempt, and link the first occurrence in the sense of the entry.
  A link on a very short word is too small a target for the accessibility
  check; take the word before it into the link ("a run").
- Some components exempt their text themselves, because it is a label or
  shows what the program prints and cannot hold a link: the name of a row
  (`Row`), a file list, the mono line of a flow box, a summary list, the
  tables of the demo and of the search, the quoted message of a callout, and
  the words "To the step" of a hint group.
- An entry may name the page that says more about its term (`more` in the
  register, the id of the page); the Glossary then links to it in a line
  "More on this", and the check holds the link.
- The Glossary lists under "Appears in" the pages whose source holds a
  `<Term>` for the entry; nothing is to be kept by hand.
- A reader who came to an entry from a page of the documentation finds a
  link "Back to the previous page" in it (`src/scripts/glossary-back.ts`,
  text `backToPage` in `texts`). A plain click goes back in the history
  where the entry before is that page; otherwise, and with a modifier key or
  another button, the link leads to the page by its address. A reader who
  came from a Glossary, also by the language switch, gets no link. The link
  goes when the address changes. Without JavaScript it is not in the page.
- A new entry needs term and explanation in both languages. The letters of
  the Glossary follow from the terms.

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

The release the documentation applies to stands in `src/release.json` and,
beside it, only in the name of the folder of its captures
(`src/captures/v<version>/`). `src/release.json` also holds the SHA-256 of
the archive of each platform. `src/release.ts` reads it and derives the tag,
the address of the release page, and the names of the archives and package
folders. Renew number and sums by hand when a release is published, and the
captures with them (see "Captures and the release check").
