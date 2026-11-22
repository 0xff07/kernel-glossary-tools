---
qa: off
---

# Figure pattern selection

Match a justified figure to a row by its "reach for it when" column, and reach for a new shape only when no row fits. Then read the matched row's file under `guidelines/page/figures/`, and no other, before drawing: each carries the pattern's notes and one or two reference figures. The referenced files show the shape of the families used most; copying the shape and substituting names is usually enough.

| pattern | reach for it when | file |
|---|---|---|
| parent + N children fan-out | one parent spawns multiple typed children; identity comes from a parent field | `guidelines/page/figures/parent-n-children-fan-out.md` |
| sparse slot map with conditional backing | a uniform index space where each slot may or may not have a backing object | `guidelines/page/figures/sparse-slot-map-with-conditional-backing.md` |
| boxed flowchart with decision nodes | 3+ sequential decision points with side effects and back-edges | `guidelines/page/figures/boxed-flowchart-with-decision-nodes.md` |
| side-by-side struct comparison | two related types meet at a third operation (match, encode/decode) | `guidelines/page/figures/side-by-side-struct-comparison.md` |
| linked structs via field-level pointers | the field-level pointer topology between existing structs is the point | `guidelines/page/figures/linked-structs-via-field-level-pointers.md` |
| N-to-M source/destination mapping | disjoint inputs feed rows of one tabular destination | `guidelines/page/figures/n-to-m-source-destination-mapping.md` |
| queue / ring between two stages | producer and consumer communicate through a bounded buffer | `guidelines/page/figures/queue-ring-between-two-stages.md` |
| data dependency (inputs feed a transform) | source structs are read by a function that populates a destination struct | `guidelines/page/figures/data-dependency-inputs-feed-a-transform.md` |
| before / after transformation | an operation reshapes one data structure; show it on each side of the change | `guidelines/page/figures/before-after-transformation.md` |
| signal-timing / waveform | where a bit or sample lands in time relative to a clock or frame edge | `guidelines/page/figures/signal-timing-waveform.md` |
| swimlane sequence (actors × time) | several actors hand work to each other and cross-actor ordering is the point | `guidelines/page/figures/swimlane-sequence-actors-time.md` |
| state-transition graph | an object moves through named states with back-edges and self-loops | `guidelines/page/figures/state-transition-graph.md` |
| directed graph / DAG | a signal or dependency graph with fan-in/fan-out plus side-attached nodes | `guidelines/page/figures/directed-graph-dag.md` |
| register / address-offset map | registers at fixed offsets, or a block repeating at base + stride · index | `guidelines/page/figures/register-address-offset-map.md` |
| layered stack / membrane | layers stack and call through named API boundaries | `guidelines/page/figures/layered-stack-membrane.md` |
| ordered level ladder | a value moves through strictly-ordered levels and travel direction matters | `guidelines/page/figures/ordered-level-ladder.md` |
| refcount with threshold actions | a refcount gates hardware action only at the 0↔1 edge transitions | `guidelines/page/figures/refcount-with-threshold-actions.md` |
| cyclic ring buffer with position pointers | two pointers chase each other around one wrapping buffer | `guidelines/page/figures/cyclic-ring-buffer-with-position-pointers.md` |
| frame / bandwidth partition grid | one frame of a shared medium divides into slots claimed by entities | `guidelines/page/figures/frame-bandwidth-partition-grid.md` |
| values on one scale | several values are positions on one axis with a floor or a ceiling, and where each lands relative to the others matters | `guidelines/page/figures/values-on-one-scale.md` |
| topology with a boundary | a guard or a policy is a place in the device tree (a depth limit, a per-port bit), and which rule can reach a device depends on where it sits | `guidelines/page/figures/topology-with-a-boundary.md` |
| nested spans | what holds true inside a bracket (a lock held, a feature off) around an operation, with brackets nested | `guidelines/page/figures/nested-spans.md` |
| race window | one path acts on what it read earlier while another path changes it in between | `guidelines/page/figures/race-window.md` |
| lifetime Gantt | who may touch an object changes at named handovers, and the count is the sum of the holders | `guidelines/page/figures/lifetime-gantt.md` |
| drain | a transition waits for in-flight work to leave before it proceeds | `guidelines/page/figures/drain.md` |
| two-view memory strip | one buffer seen from two address spaces, with something on each side pointing into it | `guidelines/page/figures/two-view-memory-strip.md` |
| lengths against one ruler | a fixed budget must contain a sum of parts, and the failing case matters as much as the fitting one | `guidelines/page/figures/lengths-against-one-ruler.md` |
| scan bar chart | a loop keeps a running maximum or minimum over a set and one member can abort it | `guidelines/page/figures/scan-bar-chart.md` |
| metro map (routes over shared stations) | several ordered paths pass through one set of common stops, and which stop each path visits, skips or reverses is the point | `guidelines/page/figures/metro-map-shared-stations.md` |
| router stack with tunnel tracks | routers in a chain, and which adapter each tunnel leaves and enters, with the hub's own switch or hub between one tunnel and the next | `guidelines/page/figures/router-stack-tunnel-tracks.md` |
| protocol columns through a router stack | the passage of one protocol's traffic through a router: protocol adapter, lane adapters, link, lane adapters, protocol adapter | `guidelines/page/figures/protocol-columns-router-stack.md` |
| object lifecycle strip | one object's fields are written by different functions at named events, and the order and the inconsistent intervals are the point | `guidelines/page/figures/object-lifecycle-strip.md` |
| two-field state pair | an object's state is the relation between two of its fields, and numbered actions move it between the settled and the divergent state | `guidelines/page/figures/two-field-state-pair.md` |
| ranges on one address axis | the code places, validates, clips, splits or merges ranges that share one address axis, or crosses two sets of ranges on it, and where each lies against a bound and its neighbours decides its fate | `guidelines/page/figures/ranges-on-one-address-axis.md` |
| radix walk (a key indexes tables level by level) | a key, an address, an ID or a handle, is split into index fields, each selecting an entry of one table, and the entry holds the next level's table or the leaf: a page table, an IOMMU translation, device or PASID table, a radix tree or XArray | `guidelines/page/figures/radix-walk.md` |
| lockstep rulers | one object has two or more coordinates that convert into each other by fixed arithmetic, and the conversions are the page's subject: a frame number, its descriptor address and its physical address under a memory model, a byte offset and its sector and block numbers, a tick count and the time it stands for | `guidelines/page/figures/lockstep-rulers.md` |
| shadow arrays | two arrays are indexed by the same number and differ only in their cell size, so an index into one is an index into the other: a memmap beside the memory it describes, a bitmap beside the slots it tracks | `guidelines/page/figures/shadow-arrays.md` |
| inclusion ladder | several counts or sets are each a part of the one before them, and the point is what each level drops: a zone's spanned, present, managed and CMA pages, a request's total, mapped and completed bytes | `guidelines/page/figures/inclusion-ladder.md` |
| derivation columns | a chain of constants is derived step by step from one starting value and the build evaluates it under two or more configurations: section constants under 4-level and 5-level paging, timing constants under two clock rates | `guidelines/page/figures/derivation-columns.md` |
| sweep with artifacts | a loop visits a sparse set, skips the absent members and leaves an artifact at each present one: section memmaps populated for the present sections, device slots initialised for the populated ports | `guidelines/page/figures/sweep-with-artifacts.md` |
| unsigned-wrap number line | a membership or range test subtracts in unsigned arithmetic and compares the difference with a length, so one comparison rejects both sides: folio_contains, a ring index check, a bounds check written as `x - base < size` | `guidelines/page/figures/unsigned-wrap-number-line.md` |
| subdivision tree | an operation halves one object toward a target until a size is reached and leaves pieces of descending sizes, and a walk later steps over the pieces by their own sizes: the non-uniform folio split, a buddy block split toward an order | `guidelines/page/figures/subdivision-tree.md` |
| state strips on one axis | every position of one index space ends in a state the ranges covering it decide, and one or more passes write that state: the frames of a node after memmap initialization and after the hand-over to the buddy allocator, the slots of a bitmap after each reservation | `guidelines/page/figures/state-strips-on-one-axis.md` |

- A sparse slot map is neither a fan-out nor an N-to-M mapping;
- swimlane cells carry the state each actor reaches, never the next callee;
- data-dependency endpoints are structs and its arrows mean feeds or populates;
- a before-and-after keeps the identical cell style on both sides so the change reads as a diff;
- flowchart boxes name conditions and effects, never callees;
- an annotation that would hang off the right edge moves beneath the drawing inside the fence.

Input-decode material gets no figure, neither a grid of inputs against an outcome nor a decode tree of labels joined by arrows: a flat input-to-outcome product is a Markdown table, a nested one is prose, and a value tested against a limit is drawn to scale only when the magnitudes are the page's own facts. Threshold-refcount material is a rung ladder, never a grid.
