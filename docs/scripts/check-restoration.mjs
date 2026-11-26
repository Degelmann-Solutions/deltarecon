// Observable focus at layout changes and restoration of kept pages.
// A dispatched persisted pageshow exercises handlers; only an observed
// persisted event during history navigation counts as a real cache hit.
import { chromium } from 'playwright';
import {
  BETWEEN, DESKTOP, PHONE, expectations, loadOtherPages, loadPages,
  openPage, searchTexts, startPreview,
} from './harness.mjs';

const { failures, expect, report } = expectations('check-restoration');
const pages = await loadPages();
const { notFound } = await loadOtherPages();
const entries = [...pages.filter((entry) => entry.isRoot), ...notFound];
const KEY = 'deltarecon-docs-platform';

async function visibleFocus(page, selector, name) {
  const active = await page.evaluate((selector) => {
    const element = document.activeElement;
    return {
      matches: element?.matches(selector),
      visible: element instanceof HTMLElement && element !== document.body &&
        element.getClientRects().length > 0 && !element.closest('[inert]') &&
        getComputedStyle(element).visibility !== 'hidden',
      name: element?.outerHTML.slice(0, 180),
    };
  }, selector);
  expect(active.matches && active.visible, `${name}: expected visible focus on ${selector}, got ${active.name}`);
}

async function resize(page, viewport, selector) {
  await page.setViewportSize(viewport);
  await page.waitForFunction((selector) => document.querySelector(selector), selector);
  // Media-query listeners and layout settle before inspecting focus.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function searchTransitions(browser, origin, entry) {
  const { context, page } = await openPage(browser, `${origin}${entry.address}`, { viewport: BETWEEN });
  try {
    page.setDefaultTimeout(4000);
    await page.locator('[data-menu-button]').click();
    await resize(page, DESKTOP, '#chapters');
    await visibleFocus(page, entry.id === 'page-not-found' ? '#chapters a[href]' : '#chapters a[aria-current="page"]', `${entry.address}: menu becomes column`);
    await resize(page, BETWEEN, 'header input[type="search"]');
    console.log(`check-restoration: ${entry.address}: focus transitions`);
    const field = page.locator('input[type="search"]');
    const term = searchTexts[entry.lang].ownWord;
    for (const hit of [false, true]) {
      await resize(page, BETWEEN, 'header input[type="search"]');
      await field.fill(term);
      await page.waitForSelector(`[data-search-results="${term}"] a`);
      const selector = hit ? '[data-search-results] a' : 'input[type="search"]';
      await page.locator(selector).first().focus();
      await resize(page, PHONE, '#chapters input[type="search"]');
      await visibleFocus(page, '[data-menu-button]', `${entry.address}: narrow closed menu, hit ${hit}`);
      expect(await field.inputValue() === term, `${entry.address}: narrowing lost the term`);
      await page.locator('[data-menu-button]').click();
      await field.focus(); // Reopens the results when top-bar focusout closed them.
      await page.locator(selector).first().focus();
      await resize(page, { width: 600, height: 800 }, 'header input[type="search"]');
      // The open-menu top bar hides search at tablet width; Close remains visible.
      await visibleFocus(page, '[data-menu-close]', `${entry.address}: widen open menu, hit ${hit}`);
      expect(await field.inputValue() === term, `${entry.address}: widening lost the term`);
      await page.keyboard.press('Tab');
      await visibleFocus(page, 'a[href], button, input', `${entry.address}: tab after move`);
      await page.locator('[data-menu-close]').click();
      await field.focus();
      await page.locator(selector).first().focus();
      await page.keyboard.press('Tab');
      await visibleFocus(page, 'a[href], button, input', `${entry.address}: search usable after close`);
    }
    // Leaving search intentionally must not leave stale focus to restore.
    await page.locator('header [data-counterpart]').focus();
    await resize(page, PHONE, '#chapters input[type="search"]');
    await visibleFocus(page, 'header [data-counterpart]', `${entry.address}: unrelated focus survives resize`);
    await page.locator('[data-menu-button]').click();
    await resize(page, { width: 600, height: 800 }, 'header input[type="search"]');
    await visibleFocus(page, '[data-menu-close]', `${entry.address}: visible close focus survives resize`);
    await page.locator('[data-menu-close]').click();
    await resize(page, BETWEEN, 'header input[type="search"]');
    await page.locator('[data-menu-button]').click();
    await resize(page, DESKTOP, '#chapters');
    await visibleFocus(page, entry.id === 'page-not-found' ? '#chapters a[href]' : '#chapters a[aria-current="page"]', `${entry.address}: menu becomes column`);
    expect(await page.getAttribute('html', 'data-menu') === 'closed', `${entry.address}: widened menu stays open`);
  } finally {
    await context.close();
  }
}

async function restored(page, platform, name) {
  const state = await page.evaluate(() => ({
    platform: document.documentElement.dataset.platform,
    menu: document.documentElement.dataset.menu,
    inert: [...document.querySelectorAll('[data-behind-menu]')].some((element) => element.inert),
    tabs: [...document.querySelectorAll('[data-platform-tab]')].map((tab) => ({
      platform: tab.dataset.platformTab, selected: tab.getAttribute('aria-selected'), index: tab.tabIndex,
      visible: document.getElementById(tab.getAttribute('aria-controls'))?.getClientRects().length > 0,
    })),
  }));
  expect(state.platform === platform && state.menu === 'closed' && !state.inert, `${name}: platform/menu/inert mismatch: ${JSON.stringify(state)}`);
  expect(state.tabs.length > 0 && state.tabs.every((tab) =>
    tab.selected === String(tab.platform === platform) && tab.index === (tab.platform === platform ? 0 : -1) &&
    tab.visible === (tab.platform === platform)), `${name}: tabs or panels disagree with storage`);
  await visibleFocus(page, 'a[href], button, input', name);
}

async function pageshow(browser, origin, entry) {
  const { context, page } = await openPage(browser, `${origin}${entry.address}`, { viewport: PHONE });
  try {
    page.setDefaultTimeout(4000);
    for (const platform of ['linux', 'windows']) {
      await page.locator('[data-menu-button]').click();
      await page.locator('#chapters a[href]').first().focus();
      await page.evaluate(({ key, platform }) => {
        localStorage.setItem(key, platform);
        window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
      }, { key: KEY, platform });
      await restored(page, platform, `${entry.address}: dispatched persisted pageshow (${platform})`);
    }
    // A normal pageshow must leave the current page state alone.
    await page.locator('[data-menu-button]').click();
    await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: false })));
    expect(await page.getAttribute('html', 'data-menu') === 'open', `${entry.address}: nonpersisted pageshow closed menu`);
    await page.locator('[data-menu-close]').click();
  } finally {
    await context.close();
  }
}

async function realCache(browser, origin, entry) {
  const { context, page } = await openPage(browser, `${origin}${entry.address}`, { viewport: PHONE });
  try {
    page.setDefaultTimeout(4000);
    await page.evaluate(() => {
      window.__restorationProbe = [];
      window.addEventListener('pageshow', (event) => window.__restorationProbe.push(event.persisted));
    });
    await page.locator('[data-menu-button]').click();
    const destination = pages.find((candidate) => candidate.lang === entry.lang && candidate.id === 'quick-start');
    await page.locator(`#chapters a[href="${destination.address}"]`).click();
    await page.waitForURL(`${origin}${destination.address}`);
    await page.evaluate((key) => localStorage.setItem(key, 'linux'), KEY);
    await page.goBack({ waitUntil: 'load' });
    const hit = await page.evaluate(() => window.__restorationProbe?.includes(true) ?? false);
    console.log(`check-restoration: ${entry.address}: real back navigation ${hit ? 'confirmed persisted cache hit' : 'no confirmed cache hit (fresh load)'}`);
    if (hit) await restored(page, 'linux', `${entry.address}: real cache restoration`);
  } finally {
    await context.close();
  }
}

const { origin: reported, stop } = startPreview();
let browser;
try {
  const origin = await reported;
  // Playwright otherwise disables the very browser cache this check probes.
  browser = await chromium.launch({ ignoreDefaultArgs: ['--disable-back-forward-cache'] });
  for (const entry of entries) {
    try { await searchTransitions(browser, origin, entry); }
    catch (error) { failures.push(`${entry.address}: ${error.stack ?? error.message}`); }
  }
  for (const entry of pages.filter((entry) => entry.id === 'own-calculations')) {
    try { await pageshow(browser, origin, entry); await realCache(browser, origin, entry); }
    catch (error) { failures.push(`${entry.address}: ${error.stack ?? error.message}`); }
  }
} catch (error) {
  failures.push(error.stack ?? error.message);
} finally {
  await browser?.close();
  stop();
}
report('search/menu breakpoint focus and persisted-pageshow handlers');
