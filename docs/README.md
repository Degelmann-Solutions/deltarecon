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
| `npm run check` | Builds the site, then checks both pages in Chromium (`scripts/check-site.mjs`): language, release number, link to the counterpart, reading with JavaScript off, the search per language, a missing search index, and that no request leaves the local origin. |
| `npx astro check` | Type-checks the project. |

The check needs the Chromium of Playwright. On a machine without it:

```
npx playwright install chromium
```

The search works only on a built site (`npm run local`), because Pagefind
indexes the build output.

## Release number

The release the documentation applies to stands in `src/release.json` and in
no other file under `docs/`. `src/release.ts` reads it and derives the tag.
Renew the number by hand when a release is published.
