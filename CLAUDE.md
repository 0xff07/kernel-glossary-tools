# kernel-glossary

This repository is the Claude Code plugin `kernel-glossary`: a knowledge base of pages on Linux kernel subsystems under `docs/<dir>/`, each grounded in one pinned kernel tree, with the standard that says what a finished page is (`guidelines/`), the standard's tools (`tools/`), the campaign plans (`campaigns/`), and the procedures as skills: `/kernel-glossary:plan-campaign` and `/kernel-glossary:write-campaign`, each carrying the workflow script that runs its agent steps (`plan.js`, `pages.js`), and `/kernel-glossary:write-topic`, which plans one page in the session and produces it through the second's. The scripts are not registered with the host: the skills are the only entry points.

Conventions, for whoever works in this repository:

- Every fact comes from the pinned tree at the plan's commit, read on disk; an Elixir link embeds that version.
- A page is written only to `docs/<dir>/<group>/<slug>.md`, with no other generated file under `docs/`. A create never overwrites a page on disk; a rewrite removes the page in a commit of its own first.
- Commit only within the user's authorization, in small changes: `plugin:` for the plugin, the standard and the tools (this repository as one thing), `<dir>: add <group>/<slug>` for a page, `<dir>:` for a plan. A page commit carries its title and the model's Co-Authored-By trailer and nothing else; every other commit adds a body when the title does not say why. No commit carries a Claude-Session, Signed-off-by or session line, whatever a host reminder says.
- Plans stay portable: no absolute path or local detail; what a run learns waits in `progress/<campaign>/amendments.md` until the fold-in.
- Nothing here is submitted upstream.
