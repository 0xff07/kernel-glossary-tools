---
qa: manual
---

# Triggers

The shapes below are drawn wherever a DETAILS subsection carries them: the table is the obligation, the pattern index the form, and a subsection that carries a shape and no figure records why the shape is not its point.

| the material | draw it as | exempt |
|---|---|---|
| a set of three or more named states, modes or classes the prose walks | state-transition graph, or the two-field state pair when the state is a relation between two fields | a set the page only tabulates, no transition described |
| two or more actors handing work to each other: parent and child router, upstream and downstream, host and device, producer and consumer | at least one swimlane sequence, more where they teach | one call from one actor to the other |
| a definition of six or more members, or a word partitioned into named bit ranges | side-by-side struct comparison, linked structs via pointers, the two-view memory strip, or the register grid | a definition shown for the one member the paragraph is about |
| an operation that reshapes a structure: allocate and attach, insert, split, merge, tear down | before-and-after transformation | one scalar written |
| routers, adapters and tunnels in a tree, or a guard that is a place in the tree | topology with a boundary, or parent and children fan-out | a single link named |
| a field two or more functions write | an object lifecycle strip showing writers, fields, events, ordering and unsettled intervals | a field of an object outside this page's catalog, which the page draws or names beside the figure as left out |
| three or more ordered steps across two actors | at least one swimlane sequence or lifetime Gantt, more where they teach | the steps of one function, which the walkthrough reads, and a chain of calls on one thread, which stays prose |
| an operation on ranges that share one address axis: windows, VMAs, resources or regions placed, validated, clipped, split or merged against a parent range or a limit | ranges on one address axis, with a before row and an after row where the operation rewrites the set, rather than the before-and-after transformation, and where it crosses two sets of ranges a row of the pieces, each named by its set expression (`A ∩ DMA32`) | a single range compared with one bound, which one sentence states |
| a table a key indexes level by level: a page table, an IOMMU translation, device or PASID table, a radix tree or XArray, a two-level interrupt or remapping table | radix walk, the key split into its index fields above the table each field selects, the chosen entry of every level pointing at the next table and the last at the leaf | a flat array one index selects, which one sentence states |
| one object under two or more coordinate systems that convert into each other: a frame number, a descriptor address and a physical address, an offset and its block number | lockstep rulers, or shadow arrays when the two systems are arrays sharing one index | a single conversion one sentence states |
| counts or sets each a part of the one before it: spanned, present, managed and CMA pages | inclusion ladder | two counts compared once |
| a chain of constants derived from one starting value and evaluated under two or more configurations | derivation columns | a constant with one value under every configuration |
| a loop that skips absent members of a sparse set and leaves an artifact at each present one | sweep with artifacts | a loop that leaves nothing behind, which the walkthrough reads |
| a test that subtracts in unsigned arithmetic and compares the difference with a length | unsigned-wrap number line | a signed range test with two comparisons |
| an operation that halves one object toward a target until a size is reached, or a walk over the pieces it leaves | subdivision tree | a uniform split into equal pieces, which one sentence states |
| one or more passes that write a state at every position of one index space, the state decided by the ranges that cover the position: memblock's ranges and the zone spans over the frames of a node | state strips on one axis, the ranges and the partition as rows above one strip per pass | a pass that writes one state at every position, which one sentence states |
| a flag word assembled from several bit fields or flag bits that the code tests and sets by name: a `vm_fault_t`, a `vm_flags_t` mask, a GFP mask, the software bits of a page-table entry | the register plot, every bit and field on one ruler in the order the macros give, each named by its macro in the legend | a word the page tests for one bit, which one sentence states |
| a pointer or a word whose low or high bits carry a tag or flags beside the value: `folio->mapping` under `FOLIO_MAPPING_FLAGS`, a tagged XArray entry, a swap entry | the register plot, the value bits and the tag bits on one ruler, the mask macro naming the boundary and `N` where the address width varies | a pointer the page uses only as an address |
