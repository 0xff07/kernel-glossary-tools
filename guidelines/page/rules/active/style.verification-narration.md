---
qa: off
---

# Verification narration

The page states the result with its scope condition; how it was established is not on the page.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| `\bgrep(s\|ped\|ping)?\b\|\bsemcode\b\|\bcaller index\b\|\b(search\|second) basis\b\|\bre-derived\b\|\bverified (negative\|absent)\b\|\btree-?wide (search\|scan\|sweep)\b` | violation | the view with code spans retained | | a verbatim quotation; a page about search tooling; a scope condition is never a match |

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. A verification narrated. **Before:**

```
Those three are the complete caller set at this tree, by a tree-wide grep
and the symbol index alike.
```

**After:**

```
Three paths call the helper. Hot-unplug, system resume, and runtime resume
all use it before removing router state.
```
