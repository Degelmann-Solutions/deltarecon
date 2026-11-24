// The copy button. The delivered page holds none; this script puts one
// beside every command: at the right end of the tab row of a platform
// switch, in the bar of a terminal block, above a code block that stands
// alone. A click copies the command (`data-copy`), without prompt and
// output. The button then shows "Copied" in its place for a while, and the
// text is announced; focus stays on the button. When the browser refuses,
// it shows and announces that copying failed and that the reader can select
// the command by hand. The texts stand on <body> (layouts/Page.astro).

/** How long "Copied" shows, and how long the longer failure text. */
const COPIED_FOR = 2500;
const FAILED_FOR = 6000;

const words = {
  copy: document.body.dataset.copyWord ?? '',
  copied: document.body.dataset.copiedWord ?? '',
  failed: document.body.dataset.copyFailed ?? '',
};

/** A copy button named `name`; `command` gives what a click copies. */
function copyButton(name: string, command: () => string | undefined): HTMLElement {
  const holder = document.createElement('span');
  holder.className = 'copy';
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'copy-button';
  button.dataset.copyButton = '';
  const status = document.createElement('span');
  status.className = 'sr-only';
  status.setAttribute('role', 'status');
  holder.append(button, status);

  let timer: number | undefined;
  const rest = (): void => {
    button.textContent = words.copy;
    button.setAttribute('aria-label', name);
    delete button.dataset.state;
    status.textContent = '';
  };
  const say = (state: 'copied' | 'failed'): void => {
    const text = state === 'copied' ? words.copied : words.failed;
    window.clearTimeout(timer);
    button.dataset.state = state;
    // The visible text is the name while it shows.
    button.removeAttribute('aria-label');
    button.textContent = text;
    status.textContent = text;
    timer = window.setTimeout(rest, state === 'copied' ? COPIED_FOR : FAILED_FOR);
  };

  button.addEventListener('click', async () => {
    try {
      const text = command();
      if (text === undefined) throw new Error('no command');
      await navigator.clipboard.writeText(text);
      say('copied');
    } catch {
      say('failed');
    }
  });
  rest();
  return holder;
}

if (words.copy) {
  // A platform switch with tabs: one button at the end of the tab row, for
  // the command of the platform that is shown.
  document.querySelectorAll<HTMLElement>('[data-platform-switch]').forEach((element) => {
    const row = element.querySelector<HTMLElement>(':scope > .platform-tabs');
    // A switch without commands has nothing to copy.
    if (!row || !element.querySelector('[data-copy]')) return;
    row.append(
      copyButton(element.dataset.copyLabel ?? words.copy, () => {
        const platform = document.documentElement.dataset.platform;
        return element.querySelector<HTMLElement>(
          `:scope > [data-platform-part="${platform}"] [data-copy]`,
        )?.dataset.copy;
      }),
    );
    element.dataset.copyButton = '';
  });

  // Every other command: a terminal block, a code block that stands alone.
  document.querySelectorAll<HTMLElement>('[data-copy]').forEach((block) => {
    if (block.closest('[data-platform-switch][data-copy-button]')) return;
    const button = copyButton(block.dataset.copyLabel ?? words.copy, () => block.dataset.copy);
    const bar = block.querySelector<HTMLElement>(':scope > .terminal-bar');
    if (bar) {
      bar.append(button);
      return;
    }
    const head = document.createElement('div');
    head.className = 'code-head';
    head.append(button);
    block.prepend(head);
    block.dataset.copyButton = '';
  });
}

// This file is a module of its own; its names are not global.
export {};
