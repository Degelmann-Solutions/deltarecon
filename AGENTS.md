# Agent Instructions

DeltaRecon is an open-source project. Contributors and agents read and write English.

## Language of generated artifacts

- Write every artifact in English: specs, briefs, PRDs, architecture documents, epics and stories, sprint status, build records, reviews, retrospectives, research summaries, documentation, code, comments, docstrings, and commit messages.
- This applies to all planning artifacts, to everything under `docs/`, and to the working tree.
- The conversation with the user may be in German. The language of the conversation never changes the language of the artifacts.
- Source material under `.input/` is partly German and is not part of the public repository. Summarize it in English and do not copy it verbatim.

## Pitfalls

- Steps that act outside the working tree (renaming or creating a repository, pushing, changing visibility, publishing a package) run only in the main session and only after the maintainer says go. A delegated agent never runs them.
- After any amend, rebase, or squash of a commit that will be pushed, run the full test suite again on the result before the push.
- A pinned expected value (a result hash, an example digest) is never overwritten to make a test pass. A test fails when the pin and the present value differ outside the commit that intends the change.
- The contract pack under `contracts/` is public. Every change to it bumps the contract version; version 1.0 is not amended in place.
- When contract text, README, or a comment describes behaviour, change it in the same commit as the code and check it against the code.
- Actuarial semantics (time basis and period origin, quantity names, cost categories, which benefits are fixed by contract) are confirmed with the maintainer before the build, not inferred.
- Before adding a helper, search the package for one that already does it. Copying recorded files, assembling run records, and building compare requests are common candidates.
