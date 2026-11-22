---
qa: off
---

# Other sources

OTHER SOURCES holds material no model generated, kept for grounding a model and for a person checking the page by hand: the commits behind the mechanism with their mailing-list threads, and whatever a reader adds later to read beside the page.

A model's contribution sits under a heading naming it, `### Added by <model>`, one block per writer pass: commit entries `[<commit subject> (commit <abbreviated sha>)](<URL>)`, the sha of 10 to 40 hex digits, with the URL taken byte for byte from a trailer `upstream_trailer` names in the commit's message, or from the mailing-list archive's thread of that commit where the message carries none, never constructed, guessed or normalized; where neither gives a URL, the block carries `None: no commit behind this mechanism carries an upstream link.`, and a commit without a URL is cited in prose by sha and subject and gets no entry.

In prose, a commit is cited by its abbreviated sha, linked as described here, and its subject in double quotes, `commit [5e8f80d3de8d](<commit URL>) ("thunderbolt: add the fixture router")`, so that the subject reads as a quotation: a subsystem prefix's colon is then no label, and an identifier inside it is no plain identifier.

Everything outside those blocks is the reader's, in any form, added by hand. The section is the reader's shelf:

- a model writes only inside its own block;
- it rewrites, reorders or removes nothing outside it,
- carries the section over verbatim when the page is rewritten, and
- never fetches a link from it.

A check compares the section with the committed page and refuses a lost reader's line.

Allowed trailers are Link and Closes. The exact empty-block sentence is `None: no commit behind this mechanism carries an upstream link.` Compare material outside the model's own block with the committed page; preserve every reader-added line. No link in this section is fetched.
