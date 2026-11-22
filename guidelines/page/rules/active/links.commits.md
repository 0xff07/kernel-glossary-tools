---
qa: off
---

# Commits

A commit named in the lead, SUMMARY, DETAILS or section six is cited as `commit [<sha>](<commit URL>)`, its subject in double quotes after it where the sentence gives one, `commit [5e8f80d3de8d](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=5e8f80d3de8d60e1e5756cb9a43cce879e7267b8) ("thunderbolt: add the fixture router")`: the text is the abbreviated hash, twelve digits, plain, and the URL is `commit_permalink` filled with the full hash `git rev-parse` resolves for it at the documented tree.

The URL is built from the hash and never fetched: no one opens an address at kernel.org to write or check the page. Several commits read `commits [<sha>](…) and [<sha>](…)`. A hash the tree does not resolve is not cited. The catalog sections keep their own forms: an OTHER SOURCES entry `- [<subject> (commit <sha>)](<upstream thread URL>)`, a SPECIFICATIONS entry by hash and subject.

Use exactly twelve hexadecimal digits for prose commit-link text and the resolved full 40-digit hash in `https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id={commit}`. Do not fetch the URL. The documented tree must resolve the hash.
