// The code a page shows of the repository, as it stands at the tag of the
// release the documentation applies to (release.json): the excerpts, each
// with its file and its lines, and the number of lines of the files a page
// states the size of. Nothing here is read from Git at build time, so the
// build needs no clone; scripts/check-excerpts.mjs holds every excerpt and
// every number of the built pages against `git show v<release>:<file>`.
//
// An excerpt is copied, never typed:
//   git show v<release>:<file> | sed -n '<first>,<last>p'
import type { Lang } from './site';

export interface Excerpt {
  /** The file, by its path in the repository. */
  file: string;
  /** The first and the last line shown, counted from 1. */
  first: number;
  last: number;
  /** The lines as they stand in the file, character for character. */
  code: string;
}

/** The code between the first and the last line break of a template. */
const lines = (text: TemplateStringsArray): string => String.raw(text).replace(/^\n/, '').replace(/\n$/, '');

export const excerpts: Record<string, Excerpt> = {
  // How the session of the reference model answers the first two questions.
  'session-questions': {
    file: 'degelmann/deltarecon/engines/reference_model.py',
    first: 871,
    last: 876,
    code: lines`
    def model_point_ids(self) -> list[str]:
        with _readable_formula_errors():
            return [str(value) for value in self._points()[MODEL_POINT_ID_COLUMN]]

    def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
        return self._project_index(self._index(model_point_id))
`,
  },
};

/** The files a page states the size of. */
export const files = {
  /** The connection of the reference model. */
  connection: 'degelmann/deltarecon/engines/reference_model.py',
  /** The protocol between DeltaRecon and an engine. */
  protocol: 'degelmann/deltarecon/protocol.py',
} as const;

/** The number of lines of each such file at the tag. */
const lineCounts: Record<string, number> = {
  [files.connection]: 1170,
  [files.protocol]: 281,
};

/** What is wrong with an excerpt of the register, one sentence per fault. */
export function excerptFaults(excerpt: Excerpt): string[] {
  const faults: string[] = [];
  if (!Number.isInteger(excerpt.first) || !Number.isInteger(excerpt.last) || excerpt.first < 1 || excerpt.last < excerpt.first) {
    faults.push(`its lines ${excerpt.first} to ${excerpt.last} are no range`);
    return faults;
  }
  const held = excerpt.code.split('\n').length;
  const named = excerpt.last - excerpt.first + 1;
  if (held !== named) faults.push(`it holds ${held} lines and names ${named} (${excerpt.first} to ${excerpt.last})`);
  return faults;
}

/** The number of lines of a file at the tag; throws for a file without one. */
export function lineCount(file: string): number {
  const count = lineCounts[file];
  if (count === undefined) throw new Error(`no number of lines for "${file}" (src/excerpts.ts)`);
  return count;
}

/** A number as the language writes it: 1,170 in English, 1.170 in German. */
export function inWords(count: number, lang: Lang): string {
  return String(count).replace(/\B(?=(\d{3})+$)/g, lang === 'de' ? '.' : ',');
}
