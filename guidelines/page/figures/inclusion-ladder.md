# Pattern: inclusion ladder

1. Use when several counts or sets nest, each a part of the one above it, and the page's point is what each level leaves out: a zone's spanned, present, managed and CMA pages; a request's total, mapped and completed bytes; a device's advertised, enabled and active lanes.
2. Draw one span bar `├───┤` per level, the widest on top and each lower bar inside the one above, broken where the level excludes a part, with the level's name at the left, a phrase and a mark at the right naming what the level counts, and `└ name ┘` callouts under the gaps naming what dropped out.
3. The shape asserts containment and the reason for every difference: a reader sees at a glance that one level is never larger than the one above it and which exclusion separates them; a bar that is not inside its parent is a drawing error, not a design choice.
4. Distinct from lengths against one ruler, which tests whether parts fit a budget; from nested spans, whose spans are intervals of one address space rather than counts; and from the ordered level ladder, whose levels are states a value moves through.

```
    The four page counts of one zone, each a part of the one above it
    ──────────────────────────────────────────────────────────────────

    spanned_pages     ├───────────────────────────────────────────────────────┤   the range, holes included  ➊
    present_pages     ├─────────────────────┤     ├───────────────────────────┤   the frames that exist  ➌
    managed_pages         ├─────────────────┤     ├─────────────────────┤         handed to the buddy allocator  ➋
    cma_pages             ├────────┤                                              managed frames reserved for CMA  ➍

                      └ reserved ┘         └ a hole ┘                  └ memblock ┘

    ➊ zone_end_pfn mmzone.h:1222  adds the span to the start frame
    ➋ zone_managed_pages mmzone.h:1208  reads the managed count without a lock
    ➌ populated_zone mmzone.h:1711  tests the present count alone
    ➍ zone_cma_pages mmzone.h:1214  reads the CMA count of the zone
```
