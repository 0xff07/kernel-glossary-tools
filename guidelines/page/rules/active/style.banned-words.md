---
qa: off
---

# Banned words

The rule, count or helper a word stands in for is named: a rule for "contract", a count for "tally", the defining site for "canonical", "branch", "case" or "side" for the noun arm, and "step", "sequence" or "direction" for the noun leg.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| `\b(contracts?\|contractual\|tally\|tallies\|tallied\|tallying\|canonical(ly)?)\b` | violation | | | a verbatim quote |
| `\barms?\b\|\blegs?\b` | candidate | | `\b(Arm\|ARM\|ARM64\|arm64)\b` matched case-sensitively; `\barms? (a\|an\|the\|its\|each\|every\|no\|any\|one\|both\|all)\b`, the verb | a verbatim quote |
