// The commands and the output the page "Your own calculations on the
// reference model" shows. They are read from the capture files under
// captures/v<release>/own-calculations/, one per step and platform
// (`<step>-windows.txt`, `<step>-linux.txt`): the commands of the page, run
// in their order in the released package after the guided demo. A file
// holds, per command, the line `command: <as typed>`, what the command
// printed (standard output and standard error), and the line
// `exit status: <n>`. No page types output.
//
// The build fails, with the file,
//   - when a file is missing or does not have that shape;
//   - when the commands a page types for a step differ from those of the
//     capture (`sessionOf`), with step and platform;
//   - when the Windows and the Linux capture of a step differ in more than
//     what varies by run: the path separators, the time stamp of the demo
//     folder, and the folder the package was unpacked into.
// The demo captures beside this folder are read by captures.ts, which does
// not see these files.
import { packageFolder, platforms, tag, type Platform } from './release';

const files = import.meta.glob<string>('./captures/*/own-calculations/*.txt', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** One command of a capture: as typed, what it printed, how it ended. */
export interface CapturedCommand {
  command: string;
  lines: string[];
  status: number;
}

/** A line of a terminal session: output, or the mark of a cut. */
export type TerminalLine = { text: string } | { cut: string; left: number };

/** One command of a terminal session with what the page shows of its output. */
export interface TerminalEntry {
  command: string;
  lines: TerminalLine[];
}

const COMMAND = 'command: ';
const STATUS = /^exit status: (-?\d+)$/;

function fileOf(step: string, platform: Platform): string {
  return `captures/${tag}/own-calculations/${step}-${platform}.txt`;
}

function read(step: string, platform: Platform): CapturedCommand[] {
  const file = fileOf(step, platform);
  const source = files[`./${file}`];
  if (source === undefined) throw new Error(`src/${file}: the capture file is missing.`);
  const commands: CapturedCommand[] = [];
  let open: { command: string; lines: string[] } | undefined;
  source
    .replace(/\n$/, '')
    .split('\n')
    .forEach((line, index) => {
      const at = `src/${file}:${index + 1}`;
      const status = STATUS.exec(line);
      if (line.startsWith(COMMAND)) {
        if (open) throw new Error(`${at}: a command begins before the exit status of "${open.command}".`);
        open = { command: line.slice(COMMAND.length), lines: [] };
      } else if (!open) {
        throw new Error(`${at}: the line stands before a line "${COMMAND}…".`);
      } else if (status) {
        commands.push({ ...open, status: Number(status[1]) });
        open = undefined;
      } else {
        open.lines.push(line);
      }
    });
  if (open) throw new Error(`src/${file}: no exit status after the command "${open.command}".`);
  if (commands.length === 0) throw new Error(`src/${file}: the capture holds no command.`);
  return commands;
}

/**
 * A line of output without what varies by run: the path separators, the
 * time stamp of the demo folder, the folder the package was unpacked into.
 */
export function neutral(line: string): string {
  let text = line.replaceAll('\\', '/').replace(/quickstart-\d{8}T\d{6}Z/g, 'quickstart-<time>');
  for (const platform of platforms) {
    const folder = packageFolder(platform);
    text = text.replace(
      new RegExp(`(?:[A-Za-z]:)?/\\S*/${folder.replaceAll('.', '\\.')}(?=/)`, 'g'),
      '<package folder>',
    );
  }
  return text;
}

const cache = new Map<string, CapturedCommand[]>();

/** The capture of a step on a platform, held against the other platform. */
function capture(step: string, platform: Platform): CapturedCommand[] {
  if (!cache.has(`${step}-${platform}`)) {
    const [first, ...others] = platforms.map((name) => ({ name, commands: read(step, name) }));
    for (const other of others) {
      const differ = (what: string): Error =>
        new Error(
          `src/${fileOf(step, first.name)} and src/${fileOf(step, other.name)} differ ${what}; only path separators, the time stamp of the demo folder and the folder of the package may differ.`,
        );
      if (first.commands.length !== other.commands.length) throw differ('in the number of commands');
      first.commands.forEach((command, index) => {
        const twin = other.commands[index];
        if (command.status !== twin.status) {
          throw differ(`in the exit status of command ${index + 1} (${command.status} and ${twin.status})`);
        }
        if (command.lines.length !== twin.lines.length) {
          throw differ(
            `in the number of lines command ${index + 1} printed (${command.lines.length} and ${twin.lines.length})`,
          );
        }
        command.lines.forEach((line, at) => {
          if (neutral(line) !== neutral(twin.lines[at])) {
            throw differ(`in line ${at + 1} of the output of command ${index + 1} ("${line}" and "${twin.lines[at]}")`);
          }
        });
      });
    }
    for (const { name, commands } of [first, ...others]) cache.set(`${step}-${name}`, commands);
  }
  return cache.get(`${step}-${platform}`)!;
}

/**
 * The session of a step on a platform: each command with its output. The
 * build fails when `commands`, the command lines the page types for that
 * step and platform, are not those of the capture.
 */
export function sessionOf(step: string, platform: Platform, commands: readonly string[]): TerminalEntry[] {
  const captured = capture(step, platform);
  const typed = commands.join('\n');
  const run = captured.map((entry) => entry.command).join('\n');
  if (typed !== run) {
    throw new Error(
      `Step "${step}", ${platform}: the page types the command\n${typed}\nand src/${fileOf(step, platform)} holds\n${run}\nA command of the page is the command of its capture.`,
    );
  }
  return captured.map((entry) => ({
    command: entry.command,
    lines: entry.lines.map((text) => ({ text })),
  }));
}

/**
 * A session with one cut: the run of lines that `left` matches, from the
 * first such line on, is replaced by a mark. `words` gives the text of the
 * mark from the number of lines left out; it is page text, not output.
 */
export function cut(
  session: TerminalEntry[],
  left: RegExp,
  words: (count: number) => string,
): TerminalEntry[] {
  return session.map((entry) => {
    const texts = entry.lines.map((line) => ('text' in line ? line.text : undefined));
    const first = texts.findIndex((text) => text !== undefined && left.test(text));
    if (first === -1) return entry;
    let end = first;
    while (end < texts.length && texts[end] !== undefined && left.test(texts[end]!)) end += 1;
    return {
      command: entry.command,
      lines: [
        ...entry.lines.slice(0, first),
        { cut: words(end - first), left: end - first },
        ...entry.lines.slice(end),
      ],
    };
  });
}

/** The exit status of the last command of a step, the same on both platforms. */
export function statusOf(step: string): number {
  return capture(step, platforms[0]).at(-1)!.status;
}

/** The lines the last command of a step printed, as the first platform (Windows) has them. */
export function outputOf(step: string): string[] {
  return capture(step, platforms[0]).at(-1)!.lines;
}

/**
 * The one line a refused command prints, with "…" in the place of the path
 * it names, which differs by platform and by where the package lies. The
 * build fails when the capture holds more than that line or names no path.
 */
export function refusal(step: string): string {
  const [first, ...others] = platforms.map((platform) => {
    const lines = capture(step, platform).at(-1)!.lines;
    const file = fileOf(step, platform);
    if (lines.length !== 1) throw new Error(`src/${file}: a refusal of one line is expected, the capture holds ${lines.length}.`);
    const message = lines[0].replace(/(?:[A-Za-z]:)?[\\/]\S+/, '…');
    if (!message.includes('…')) throw new Error(`src/${file}: the refusal names no path.`);
    return message;
  });
  if (others.some((message) => message !== first)) {
    throw new Error(`The captures of the step "${step}" differ in the refusal beyond the path it names.`);
  }
  return first;
}

/** A contribution a search prints: the state it leads to, the revision, the signed sum. */
export interface Contribution {
  /** The number of the state after the revision. */
  state: number;
  /** The revision in full, as the search prints it. */
  revision: string;
  /** Its first seven characters, as the tables of the demo show it. */
  short: string;
  sum: number;
}

/** The contributions the search of a step prints, in their order. */
export function contributionsOf(step: string): Contribution[] {
  const lines = outputOf(step);
  const found: Contribution[] = [];
  lines.forEach((line, index) => {
    const head = /^contribution from state \d+ to (\d+): ([0-9a-f]{40})$/.exec(line);
    if (!head) return;
    const sum = /: sum (-?\d+(?:\.\d+)?), absolute sum /.exec(lines[index + 1] ?? '');
    if (!sum) {
      throw new Error(`src/${fileOf(step, platforms[0])}: no sum after the line "${line}".`);
    }
    found.push({ state: Number(head[1]), revision: head[2], short: head[2].slice(0, 7), sum: Number(sum[1]) });
  });
  if (found.length === 0) {
    throw new Error(`src/${fileOf(step, platforms[0])}: the search prints no contribution.`);
  }
  return found;
}

/** How many states the search of a step ran, and how many a walk runs. */
export function runsOf(step: string): { run: number; walk: number; saved: number } {
  const counted = /^search: searched; (\d+) states run, (\d+) for a walk, (\d+) saved$/.exec(outputOf(step)[0] ?? '');
  if (!counted) {
    throw new Error(`src/${fileOf(step, platforms[0])}: the first line of the search does not count its states.`);
  }
  return { run: Number(counted[1]), walk: Number(counted[2]), saved: Number(counted[3]) };
}

/**
 * The contributions of a step that the table of the demo's search does not
 * hold. The build fails when a row of that table has no contribution here
 * with the same sum, rounded to two decimals as the demo prints it.
 */
export function beyondDemo(step: string, rows: readonly { revision: string; value: number }[]): Contribution[] {
  const found = contributionsOf(step);
  for (const row of rows) {
    const twin = found.find((entry) => entry.short === row.revision);
    if (!twin || twin.sum.toFixed(2) !== row.value.toFixed(2)) {
      throw new Error(
        `src/${fileOf(step, platforms[0])}: the search does not print the revision ${row.revision} of the demo's table with its sum ${row.value.toFixed(2)}${twin ? ` (it prints ${twin.sum})` : ''}.`,
      );
    }
  }
  return found.filter((entry) => !rows.some((row) => row.revision === entry.short));
}
