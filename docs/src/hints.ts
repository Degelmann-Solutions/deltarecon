// The register of the hint groups of the page "When something goes wrong".
// A group holds the hints of one step of a step page or of one section of a
// page of prose. Each entry names the anchor of the group on the help page
// (the same in both languages), the page it belongs to and the step or the
// section of that page, by its anchor.
//
// Both directions read it: the help page builds a group from its entry
// (components/HintGroup.astro), and a step or a section takes the link to
// its group from it (components/HintLink.astro). The order of the entries is
// the order of the groups on the help page: the pages in path order, the
// steps and sections of a page in their order.
//
// scripts/check-hints.mjs holds the built pages of both languages against
// it. This file imports nothing but types, so that the check scripts can
// load it (see scripts/harness.mjs). The words of a group and of a hint link
// stand in `texts` of src/site.ts.

/** The page that holds the groups, by its key in the page register. */
export const helpPage = 'when-something-goes-wrong';

/** The anchor of the last section of the help page, the contact block. */
export const contactAnchor = 'contact';

export interface HintGroup {
  /** Anchor of the group on the help page: small letters, digits, hyphens. */
  anchor: string;
  /** The page the group belongs to, by its key in the page register. */
  page: string;
  /** A step of a step page, or a section of a page of prose. */
  kind: 'step' | 'section';
  /** Anchor of that step or section on its page. */
  target: string;
}

const group = (page: string, kind: HintGroup['kind'], target: string): HintGroup => ({
  anchor: `${page}-${target}`,
  page,
  kind,
  target,
});

export const hintGroups: readonly HintGroup[] = [
  group('quick-start', 'step', 'download'),
  group('quick-start', 'step', 'check'),
  group('quick-start', 'step', 'unpack'),
  group('quick-start', 'step', 'start'),
  group('quick-start', 'step', 'demo'),
  group('quick-start', 'step', 'result'),
  group('own-calculations', 'step', 'folder'),
  group('own-calculations', 'step', 'other-quantity'),
  group('own-calculations', 'step', 'newer-revision'),
  group('own-calculations', 'step', 'search'),
  group('single-commands', 'section', 'start'),
  group('single-commands', 'section', 'run'),
  group('single-commands', 'section', 'quickstart'),
  group('build-an-adapter', 'step', 'select'),
  group('build-an-adapter', 'step', 'first-run'),
];

/** The group with an anchor; throws for an anchor the register does not hold. */
export function findGroup(anchor: string): HintGroup {
  const found = hintGroups.find((entry) => entry.anchor === anchor);
  if (!found) {
    throw new Error(`No hint group "${anchor}" in the register of the hint groups (src/hints.ts).`);
  }
  return found;
}

/** The group of a step or a section of a page, if it has one. */
export function groupOf(page: string, kind: HintGroup['kind'], target: string): HintGroup | undefined {
  return hintGroups.find(
    (entry) => entry.page === page && entry.kind === kind && entry.target === target,
  );
}

/**
 * What is wrong with the register, one sentence per fault: an anchor that is
 * not small letters, digits and hyphens, an anchor twice, the anchor of the
 * contact block, a page the page register does not hold, the help page
 * itself, two groups of one step or section, and groups that leave the order
 * of the path. `pageIds` are the keys of the page register in path order.
 * Empty when the register holds.
 */
export function groupFaults(groups: readonly HintGroup[], pageIds: readonly string[]): string[] {
  const faults: string[] = [];
  const anchors = new Set<string>();
  const targets = new Set<string>();
  let last = -1;
  for (const entry of groups) {
    const name = `the hint group "${entry.anchor}"`;
    if (!/^[a-z][a-z0-9-]*$/.test(entry.anchor)) {
      faults.push(`${name} has no anchor of small letters, digits and hyphens`);
    }
    if (anchors.has(entry.anchor) || entry.anchor === contactAnchor) {
      faults.push(`${name} repeats an anchor of the help page`);
    }
    anchors.add(entry.anchor);
    const target = `${entry.page} ${entry.kind} ${entry.target}`;
    if (targets.has(target)) {
      faults.push(`${name} is a second group of the ${entry.kind} "${entry.target}" of the page "${entry.page}"`);
    }
    targets.add(target);
    const at = pageIds.indexOf(entry.page);
    if (at === -1) {
      faults.push(`${name} names the page "${entry.page}", which the page register (src/site.ts) does not hold`);
    } else if (entry.page === helpPage) {
      faults.push(`${name} names the help page itself`);
    } else if (at < last) {
      faults.push(`${name} stands after a group of a later page: the groups follow the order of the path`);
    } else {
      last = at;
    }
  }
  return faults;
}
