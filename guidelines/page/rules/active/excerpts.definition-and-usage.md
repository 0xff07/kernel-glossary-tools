---
qa: auto
---

# Definition and usage

Every catalog symbol gets its definition excerpt and at least one usage excerpt: a unit reproduces the entry's anchored definition line, and another unit reproduces a line that spells the symbol (a tagged key as `struct X`, a member key by its member, any other by its name).

An entry with no such definition unit or no such usage unit is a violation; the symbol is then shown or de-cataloged, the prose that names it saying why no usage is shown. A symbol whose every caller lies in content the request excludes is shown whole and stays uncataloged: its usage is stated in prose in a sentence or two naming the excluding constraint, and no usage excerpt is taken from that content.

- A call-chain walk shows the invocation site and the callee body as separate blocks;
- a switch, loop or condition whose structure is the point is reproduced, never paraphrased;
- a macro or static array the prose depends on is reproduced where first depended on;
- a commit message with a table or figure is reproduced in a plain fence.
