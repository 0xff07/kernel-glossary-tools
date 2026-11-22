---
qa: off
---

# Counts serve claims

A count sits beside the claim it serves: the paragraph states the invariant, boundary or ownership split, and the count proves it. Counts are what survive checking, so a writer drifts toward producing them; what the reader understands is the test, and an enumeration that is the finding says what it shows before its size.

A population of code locations counted for its own sake teaches nothing: the reader learns a number and no mechanism, and such a count without its claim is noise. A closed set whose members are themselves the content, the fields of a register, the values of an enumeration, the states of a machine, is enumerated because a reader must be able to look each member up, and needs no such warrant.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. A count standing in for a claim. **Before:**

```
At v7.0 the table holds 30 members, 24 function pointers plus 6 data and
policy members. Twenty-two of them are reached through a
snd_soc_dai_set_sysclk() style function ...
```

**After:**

```
The callbacks fall into four groups by when they run. The driver
callbacks (probe, remove, pcm_new, compress_new) run once as the DAI is
brought up, the clocking and format callbacks are driven by the machine
driver from its hw_params hook, and the PCM callbacks ...
```
