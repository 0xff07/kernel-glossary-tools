---
qa: auto
---

# Recorded judgement

Seven judgements are recorded line by line in the evidence sheet's ACCEPTANCE section, each `done, <evidence>` with the evidence a verifier can spot-check, or `n/a, <reason>`; a line missing, empty or `done` alone is a candidate until it is filled. The lines are:

- `scope-covered` (every anchor symbol and behavior the scope names has a location on the page, or a REDUCTIONS row with its reason),
- `claims-nearby` (every behavioral sentence has the source that supports it beside it on the page),
- `guards` (every restated guard or threshold keeps the code's operators and constants, derived by exact negation and shown beside the sentence),
- `invariants` (every lifecycle invariant has had its counterexample search over every assignment site, lock-less caller and free path, recorded with its basis),
- `activation-delta` (every mechanism that can be switched on answers, from cited code, what runs while it is active, what stops, which existing call sites gain a precondition, and what returns it to inactive; or `n/a` naming the gate when switching belongs to another page),
- `modes` (where a mechanism has several active modes, each difference is explained, or the construct that makes the modes identical is named) and
- `constructs` (every state-holding construct, lifecycle stage, helper and hard-coded limit the subject reaches has its excerpt or citation on the page, or its absence is stated with the reason).

The lines are written once, when the page is complete; a verifier reads them and spot-checks one.

The sheet's ACCEPTANCE section is a list, one line per key, `- <key>: done, <evidence>` or `- <key>: n/a, <reason>`; the key is what stands before the first colon, the text what follows it, and a colon after `done` reads the same as the comma. A line whose text is empty, or is `done` alone with or without a period or comma, is the candidate.
