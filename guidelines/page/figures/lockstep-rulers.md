# Pattern: lockstep rulers

1. Use when one object carries several coordinates that convert into each other by fixed arithmetic and the conversions are the subject: a frame number, its descriptor address and its physical address under a memory model; a byte offset against its sector and block numbers; a tick count and the time it represents.
2. Draw one ruler per coordinate system as a span bar `├───┤` on its own row, the rulers aligned so that one column is one object on every row, the origin and the far end labelled on each; mark the worked object on each ruler with a `┬` or `┴` tick and connect the ticks by vertical arrows carrying the conversion's mark, a downward arrow for one direction and an upward one, on a second object, for the inverse; a hole, an unmapped range or an absent region is the same gap on every ruler, named on each row.
3. The shape asserts that the coordinates stay in lockstep, so a conversion is a vertical move and never a search, and that a gap in one coordinate is a gap in all of them; the reader checks the arithmetic on the labels and reads the inverse from the upward arrow. Keep the scale sentence under the title so the ticks are read as one object.
4. Distinct from the two-view memory strip, which draws one buffer's cells under two rulers that point into it; from values on one scale, whose positions are magnitudes on a single axis; and from shadow arrays, which draw the two coordinate systems as arrays sharing one index.

```
    One frame, number n, under the three coordinates of the vmemmap model
    ──────────────────────────────────────────────────────────────────────
    the three rulers share one scale: a cell is one frame on each of them

                           0         n                  m                           max_pfn
    frame number           ├─────────┬─────────────────────────┤ hole      ├──────────────┤
                                     │ ➊ vmemmap + n    ▲
                                     │                  │ ➋ page − vmemmap
                                     ▼                  │
    descriptor address     ├─────────┬──────────────────┴──────┤ unmapped  ├──────────────┤
                           vmemmap   &vmemmap[n]        &vmemmap[m]            vmemmap + max_pfn
                                     │ ➌ n << PAGE_SHIFT
                                     ▼
    physical address       ├───────────────────────────────────┤ no memory ├──────────────┤
                           0         n × PAGE_SIZE

    ➊ __pfn_to_page memory_model.h:46  adds the frame number to vmemmap
    ➋ __page_to_pfn :47  subtracts vmemmap from the descriptor's address
    ➌ page_to_phys :85  shifts the frame number into a physical address
```
