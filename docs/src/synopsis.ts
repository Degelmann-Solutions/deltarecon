// The usage line of every command of the released `deltarecon`, as its help
// (`deltarecon <command> --help`) prints it, without `[-h]` and wrapped for
// the page. The page "Single commands" shows it under the heading of each
// command (components/Synopsis.astro); scripts/check-release.mjs holds it
// against the help of the released package, word for word.
export const usage: Record<string, readonly string[]> = {
  request: [
    'deltarecon request --revision REVISION [--stage STAGE] --label LABEL',
    '                   --run-id RUN_ID --output OUTPUT',
    '                   [--subset MODEL_POINT_ID [MODEL_POINT_ID ...]]',
    '                   [--enable CHANGE_ID [CHANGE_ID ...]]',
    '                   [--manifest MANIFEST] [--engine MODULE:CLASS]',
    '                   [--engine-path DIR] [--engine-option KEY=VALUE]',
    '                   [--repositories DIR]',
  ],
  run: [
    'deltarecon run [--workers N] [--engine MODULE:CLASS] [--engine-path DIR]',
    '               [--repositories DIR]',
    '               request',
  ],
  replay: [
    'deltarecon replay [--tolerance FILE] [--workers N] [--engine MODULE:CLASS]',
    '                  [--engine-path DIR] [--repositories DIR]',
    '                  run_record',
  ],
  compare: ['deltarecon compare request'],
  regression: [
    'deltarecon regression --revision REVISION --output OUTPUT [--label LABEL]',
    '                      [--tolerance FILE] [--workers N]',
    '                      [--engine MODULE:CLASS] [--engine-path DIR]',
    '                      [--engine-option KEY=VALUE] [--repositories DIR]',
    '                      run_record',
  ],
  derive: [
    'deltarecon derive --output OUTPUT [--engine MODULE:CLASS]',
    '                  [--engine-path DIR] [--repositories DIR]',
    '                  older_record newer_record',
  ],
  walk: [
    'deltarecon walk --output OUTPUT [--tolerance FILE] [--workers N]',
    '                [--engine MODULE:CLASS] [--engine-path DIR]',
    '                [--repositories DIR]',
    '                older_record newer_record',
  ],
  search: [
    'deltarecon search --output OUTPUT [--quantity NAME] [--periods FIRST-LAST]',
    '                  [--walk FOLDER] [--reuse-walk] [--target-only]',
    '                  [--tolerance FILE] [--workers N] [--engine MODULE:CLASS]',
    '                  [--engine-path DIR] [--repositories DIR]',
    '                  older_record newer_record',
  ],
  quickstart: ['deltarecon quickstart [--no-pause] [--lang {de,en}] [--repositories DIR]'],
};
