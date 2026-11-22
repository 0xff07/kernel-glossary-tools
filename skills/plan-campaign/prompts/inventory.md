# The inventory prompt

One agent per area, dispatched in parallel by the plan workflow (`plan.js`, stage `inventory`). The agent reads this file and carries it out with the parameters its prompt gives: the area, the subsystem, the tree with its tag and commit, the kernel paths of the area, the documented build's resolved config when one exists, and the digest file it writes.

```
Inventory the <area name> area of the <subsystem> subsystem for a
documentation campaign. Read-only research on the tree; the only file
you write is the digest, <digest file>.

Tree: <path>, version <tag>, commit <commit>. Search with the tools
skills/research-tools.md describes (the tags file and readtags,
git grep, the compile database with clang-query, the symbol index where
one is registered), over: <kernel_paths subset for this area>. Index
line numbers are hints; confirm on disk before reporting a location.
Every location is tree-relative file:line.

Write a COMPACT digest (a report of anchored facts, not prose chapters):
1. Core structs of the area: each with its field groups, one-line roles,
   and the definition's file:line.
2. API families: entry points, helpers, accessor macros, grouped by
   family, each with file:line and a one-line role.
3. Lifecycle and locking: alloc/init/free paths, the serializing locks,
   refcounting, state fields and their transitions, with file:line anchors.
4. Hard-coded limits: every constant bounding the mechanism, with its
   value and file:line.
5. Version-specific facts: symbols renamed, removed, or newly added at
   this version relative to widely-documented older kernels.
6. Suggested page topics the request does not list, each justified by the
   anchor symbols it would be built around.
7. Tracing integration: tracepoint definitions and their instantiation
   sites, every trace_*() call site, probes on other subsystems'
   tracepoints, private ftrace instances, tracers and exporters, and the
   seams where this area fires an adjacent subsystem's events, cited at
   both ends. Per class: enumerate with file:line, or a verified negative.
8. Debug and diagnostic printing: the mechanisms in play, per-file counts
   for the heavy hitters, every control knob (Kconfig, module params, boot
   params) with file:line, and the load-bearing sites; assertion families
   are a mechanism entry with counts, never a site enumeration.
9. Asynchronous, deferred, or lazy processing: every workqueue, work item,
   timer, irq_work, tasklet, kthread, RCU deferral, completion handoff,
   task_work and notifier chain, each with queuing site, execution context
   and handler at file:line, plus lazy or deferred init designs; absent
   classes get verified negatives.
10. Subsystem-specific debugging infrastructure: dedicated debugfs, sysfs
    and procfs surfaces, debug chardevs and ioctls, fault injection, dump
    or replay facilities, each with file:line and its Kconfig gate; only
    what this subsystem itself declares. The tree's scripts and
    user-space tools are item 21.
11. Build gates per anchor: every struct, field group, function and macro
    of items 1-2 that sits behind a Kconfig option or an #if, with the
    gate, the documented build's value (from the resolved config the
    prompt names), and the stub or alternative definition compiled when
    the gate is off, at file:line; a symbol absent from the documented
    build is marked so.
12. The other value of each gate: for every gate of item 11 that changes
    behavior rather than removing code, one line on what the other build
    does (the alternative path, helper or data layout), so the catalog
    decides what a page documents and what it names as the other build.
13. Field protection: one row per field of the area's core structs: the
    lock, atomic, seqcount, RCU or unpublished-object rule that protects
    it, the comment line that states the rule, and one representative
    writer under it.
14. Annotated races: every data_race(), READ_ONCE/WRITE_ONCE pair, smp_*
    barrier with its pairing comment, __rcu pointer with its readers, and
    lockless-reader comment in the area, each with file:line and what it
    protects against.
15. Stated contracts and their enforcement: the invariants the comments
    state (counts, orderings, who may write a field, when a pointer is
    valid), each with its line, and the assertions that enforce them
    (static_assert, BUILD_BUG_ON, BUG_ON, WARN_ON, VM_BUG_ON,
    lockdep_assert, might_sleep), each with file:line and its gate's value
    in the documented build.
16. Failure paths: for every fallible operation of the area, what can
    fail, the unwind order (the labels and the cleanup each runs), what is
    left partially built and who releases it, and the return codes, with
    file:line.
17. User-visible surface and documentation: the sysctls, prctl operations,
    syscalls, boot parameters, procfs and sysfs files and uapi definitions
    that expose or control the mechanism, each with file:line and its
    gate; and every file under Documentation/ that describes the area,
    with the section that applies.
18. Object footprint: for each core struct, its size and alignment under
    the compile database (naming that build's config and randomization
    where they differ from the documented build's), the slab cache or
    allocator that holds it with its flags and GFP, the per-CPU and
    flexible-array parts, the usercopy window, and the cacheline-placement
    comments.
19. Tooling notes, at most 15 lines: one line per error or divergence
    observed between a tool's answer and the disk, naming the question,
    the tool, what it answered and what the disk says; and one line per
    question a tool answered faster or more completely than git grep
    could.
20. In-tree tests: every KUnit suite, every kselftest under
    tools/testing/selftests/, and every other test the tree carries (a
    test module, a driver's own selftests, a user-space harness under
    tools/testing/) that exercises a struct, a function or a user-visible
    surface of items 1-2 and 17: the suite or program with file:line, its
    cases each with the function it calls and the property it pins down,
    the seams the code under test carries for it (a symbol made visible
    or exported for the test, a stub or redirect, a mock device or
    fixture), the Kconfig option that builds it with its value in the
    documented build, the fragment the tree ships for running it and the
    command its documentation states, and the size in lines of the suite
    and of the helpers it rests on. Per class: enumerate, or a verified
    negative.
21. In-tree scripts and tools: every file under scripts/ and under
    tools/, the tests of item 20 and the headers copied for user-space
    builds aside, that reads, decodes, drives, checks or generates
    something of the area (a debugger helper that knows its structs, a
    decoder of its dumps or traces, a user-space program on its ioctls or
    files, a semantic patch or checker of its API, a generator of its
    code or tables): the file with the line that names the area, what it
    does with which interface, struct or symbol of items 1-2 and 17, and
    how the tree's documentation says it is invoked. Enumerate, or a
    verified negative.
Items 7-10, 20 and 21 are inventory devices: enumerate or verify negative at plan
time, and name gates at write time. Items 11-18 are read against the
documented build's resolved config where a gate is involved. Keep every
entry to one or two lines. Write the digest to the digest file and return
the structured output the prompt names: the area, the file, its line
count, the suggested topics (item 6) and the open questions you could not
settle on the tree.
```
