---
qa: off
---

# Hedges

A claim names the exact condition the code tests; a frequency or a degree comes with the counter or branch it was measured on.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| `\b(<hedge>)\b` | violation | | `\w-(<hedge>)\b` and `\b(<hedge>)-\w`, the word inside a hyphenated compound | a hedge inside a quote; a measured statistic that cites its counter |

`<hedge>`: usually, typically, generally, often, normally, commonly, mostly, in practice, tends to, on a hot CPU, simply, essentially, basically, arguably.
