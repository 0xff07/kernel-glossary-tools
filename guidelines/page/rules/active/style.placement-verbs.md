---
qa: off
---

# Placement verbs

A location is stated as its mechanism: defined in a file, held in a struct, attached behind a pointer, occupying a slot; a field transitions through its values.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| `\b(lives?\|lived\|living\|sits?\|sat\|sitting\|hangs?\|hung\|hanging\|wants?\|wanted\|wanting)\b` | candidate | + figure | `\b(a\|an\|the\|this\|that\|its\|their\|each\|every\|any\|no\|one)\s+(live\|hang)\b` | the adjective ("the live ring"); a real actor; a verbatim quote; hardware earns no exemption |
