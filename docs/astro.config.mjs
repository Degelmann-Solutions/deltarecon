// @ts-check
import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import tailwindcss from '@tailwindcss/vite';

// Static output. The site is deployed as plain files under /deltarecon/docs
// of the company website; every page address ends with a slash.
export default defineConfig({
  site: 'https://degelmann-solutions.de',
  base: '/deltarecon/docs',
  trailingSlash: 'always',
  output: 'static',
  integrations: [mdx()],
  vite: {
    plugins: [tailwindcss()],
    // Keep page scripts as files of their own. Astro inlines small scripts
    // into the page, and an inlined script with a dynamic import (the load of
    // the search index) keeps Vite's unreplaced `__VITE_PRELOAD__` marker and
    // fails in the browser.
    build: { assetsInlineLimit: 0 },
  },
});
