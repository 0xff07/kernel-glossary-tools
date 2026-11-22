# Pattern: unsigned-wrap number line

1. Use when a test subtracts a base from a value in unsigned arithmetic and compares the difference with a length, so that one comparison rejects a value on either side of the range: an index tested against a folio, an offset tested against a buffer, a sequence number tested against a window.
2. Draw the original axis on top with the range as a double-line segment `═══` between two `┬` ticks whose callouts name its bounds and the three cases labelled above, then the sentence that performs the subtraction between the axes carrying the test's mark, and the distance axis beneath, where the range starts at zero, the length is the single `┬` tick and a value from the left of the range reappears at the far right, near the top of the unsigned range; leave blank lines around the middle sentence so the two axes read apart.
3. The shape asserts that subtraction maps the three cases onto one axis where a single less-than comparison decides, and that the wrapped case lands above the length rather than below zero; the reader follows one query from the top axis to the bottom one and sees why no second comparison is needed.
4. Distinct from ranges on one address axis, which places ranges against a bound without transforming them; from values on one scale, whose positions are magnitudes rather than cases; and from the cyclic ring buffer, whose wrap is a position inside the ring rather than an arithmetic effect.

```
    folio_contains: one unsigned comparison rejects an index on either side of the folio
    ──────────────────────────────────────────────────────────────────────────────────

                      left ▼                        inside ▼                right ▼
    file index    ──────────────────────────┬═══════════════════════┬─────────────────────────────────────────────▶
                                            └ folio->index          └ folio->index + nr_pages


    @1 index − folio->index, in unsigned arithmetic, moves each query onto the distance line


                          inside ▼              right ▼                                                   left ▼
    distance    0 ─═══════════════════════┬───────────────────────────────────────────────────────────────────────▶
                                          └ nr_pages
                    below nr_pages: inside      at or above: outside                  wrapped near ULONG_MAX: outside

    @1 folio_contains pagemap.h:985  compares the wrapped distance with the page count
```
