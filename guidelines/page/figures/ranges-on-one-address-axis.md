# Pattern: ranges on one address axis

1. Use when the code places, validates, clips, splits or merges ranges that share one address axis (host bridge windows against the end of `iomem_resource`, the VMAs of an mm, the children of a resource, a region checked against its parent), or crosses two sets of ranges on it (memblock's memory ranges against the zones of a node), and the point is where each range lies against a bound and against its neighbours, since that position decides whether the range is kept, clipped, dropped or merged.
2. Draw one address axis with the bound as a labelled `┬` tick and an L-connector callout naming it; draw each range as a span bar `├───┤` with its name at its left end, in the order the code visits them, a range that overlaps another on its own row so that each keeps its extent. Where the operation rewrites the set, draw a before row and an after row and give every changed range a mark on the after row, the legend naming the function and the site that decided it.
   - Where the operation crosses two sets of ranges, as in the second figure, draw each set on a row of its own with the names inside the bars, then one row for the pieces the crossing yields, each named by the set expression that makes it (`A ∩ DMA32`), and one row for what no range covers. A cursor the loop carries has its own row, a `▲` under each position it takes and the position named beneath, and the visits stand in their order under the drawing.
3. The shape asserts position and extent on one axis: the reader reads each outcome off where the range lies relative to the bound and to its neighbours. A piece named by its set expression states its derivation, so the reader checks each of its ends against the two operands drawn above it. Keep the order and the crossings exact; the lengths are schematic unless the magnitudes are the page's own facts.
4. Distinct from the before-and-after transformation, whose two sides are one structure in cells; from lengths against one ruler, which tests whether parts fit a budget; from values on one scale, whose marks are points, not extents; and from state strips on one axis, which shade the state a pass leaves at every position under the ranges.

```
    Memory windows W1 to W5, in list order, against the end of iomem_resource
    ─────────────────────────────────────────────────────────────────────────

    before   W1 ├──────────────┤          W2 ├────────┤    W3 ├──────────────────┤   W4 ├───────┤
                     W5 ├─────────────┤
    address  ─────────────────────────────────────────────────────────────┬──────────────────────────▶
                                                                          └─ iomem_resource.end

    after    W1 ├─────────────────────┤   W2 ├────────┤    W3 ├───────────┤
                «C» W5 merged                                 «B» clipped               «A» W4 dropped

    «A» acpi_pci_root_validate_resources pci_root.c:821  drops a window starting at or past the end
    «B» acpi_pci_root_validate_resources :830  clips a window that crosses the end
    «C» acpi_pci_root_validate_resources :843  merges an overlap into the earlier window
```

```
    memmap_init's pass over two memory ranges and two zones, with the hole cursor
    ─────────────────────────────────────────────────────────────────────────────

    pfn ───────────────────────────────────────────────────────────────────────────────────────────────────────▶

    zones              ├─────────────────── ZONE_DMA32 ────────────────────────┼───────── ZONE_NORMAL ─────────┤

    memory ranges              ├────── range A ──────┤         ├─────────────── range B ───────────────┤

    clamped, inited            ├───── A ∩ DMA32 ─────┤         ├─ B ∩ DMA32 ──┤├───── B ∩ NORMAL ──────┤

    holes, reserved    ├──────┤                       ├───────┤                                         ├──────┤
                       DMA32                          DMA32                                             NORMAL

    hole_pfn           0                             ▲                        ▲                        ▲
                                                 end of A             end of B ∩ DMA32             end of B

    visits in order: (A, DMA32) inits A ∩ DMA32 and the hole before it; (A, NORMAL) clamps to nothing;
    (B, DMA32) inits B ∩ DMA32 and the hole before it; (B, NORMAL) inits B ∩ NORMAL with no hole;
    after the loop the tail from the end of B to the section boundary takes ZONE_NORMAL
```
