# Research tools

The tools a writer, a proofreader and a planner may use against the documented tree, one per kind of question. Each is optional: a machine without it does its class by hand and the writer's report says so. None of them is a source: every line number is re-read on disk at the documented commit before it reaches a page, and the engine (`tools/qa/`) reads none of them.

The campaign block's `tooling` key names which of them a campaign has (guidelines/campaign/spec.md [campaign]), and the writer prompt carries that key.

## The four kinds of question

| kind | question | tool | fallback |
|---|---|---|---|
| A, one file's syntax | what a line is: a definition, a member, an assignment to a field, a call, the function around it, the `#if` around it | a syntax parser for that source file | reading the file |
| B, meaning under a build | a symbol's type, which construct a same-named identifier denotes, what a macro expands to, which field a chained access ends in, a struct's layout, what an initializer assigns, which functions the tree compiles | the compile database through `clang-query`, `clang-check` and `clang -E` | A plus the declarations in scope, stated as a reading |
| C, the whole tree | where a name is defined, who calls it, what it calls, a file's outline | the symbol index, codebase-memory-mcp | the tree's `tags` file with `readtags`; `git grep` |
| D, text | strings and messages, comments citing a specification, `Documentation/`, Kconfig, Makefiles, commits and trailers; the mailing-list email a commit came from, for OTHER SOURCES (`sections.other-sources`) | `git grep`, `git log` | none needed for the text; for the email, the commit's `Link:` and `Closes:` trailers alone |

A question that spans two kinds is answered in order: C or A narrows the candidates, B settles identity. A count written on a page carries two bases of different shape (`facts.two-bases`); a symbol-index basis, a compile-database basis and a tree-wide grep count as different shapes.

### Which tool answers first

The tools complement one another and serve as one another's fallbacks.

**Per question, measured at v7.3 over the mm, VMA and mapping areas:** which answers first, which supplies the second basis, and what to do when the first is down, stalled or shows one of its known holes (the sections below).

| question | first answer | second basis | fallback, and the check that decides |
|---|---|---|---|
| where a name is defined (C) | the symbol index (`search_graph`), one row per architecture | `git grep -n -w` of definition-shaped lines in the roots | the disk decides a stub-versus-definition or forward-declaration row; the tags file with `readtags` when the index is down |
| who calls a function, tree-wide (C) | `git grep -n -p -E '\bname\('` as the floor and the enclosing-function basis | the symbol index (`trace_path` inbound) for speed and Rust callers | `clang-query` `callExpr(callee(functionDecl(hasName(...))), hasAncestor(functionDecl().bind("f")))` over the grep-named units the database compiles; every disagreement read on disk |
| what a function calls (C) | the symbol index (`trace_path` outbound), source-level names | `clang-query` `callExpr(hasAncestor(functionDecl(hasName(...))))`, post-preprocessing names, which also shows the compiled branch | reading the function |
| writers of a field (B) | `clang-query` assignment and `++`/`--` matchers over the grep-named units, in the forms below | `git grep -n -E '>field\s*(=[^=]|\+=|-=|\+\+|--)'` tree-wide | reading the file for writes through `WRITE_ONCE`, `memset`, `memcpy`, a designated initializer or an out-parameter, which no matcher sees |
| what a build compiles, a macro's expansion, a branch's value (B) | `clang-query` `set output print` on the definition, or `clang -E` from the unit's command | the `#if` and the resolved documented config | none: a gate's value in the documented build always comes from the resolved config, never from the database; `nm` on the database build's object says what that build compiled |
| a struct's size and offsets (B) | the plain `clang-check -fdump-record-layouts` of a unit that lays the record out, or a `_Static_assert`/`offsetof` probe compiled with the unit's command | hand arithmetic from the source against the documented config | an overlay of the documented config's `autoconf.h` with `-extra-arg-before=-I` on one unit, with its unrelated parse errors read |
| which function holds a text (C) | the symbol index `search_code` with `pattern` | `git grep -n -p` | none needed |
| a file's outline (A, C) | the symbol index `get_file_outline` | `grep -n` of definition lines | the disk for every `#if` twin and forward declaration the outline conflates |
| what a call through a struct member can reach, where a function is installed (C) | semcode `find_implementors` and `find_registrations` | `git grep -n -E '\.member\s*='` under the roots | `clang-query` `designatedInitExpr` over the grep-named units; a declaration split over two lines or carrying an attribute escapes a one-line grep |
| a graph question, callers of X within a directory (C) | the symbol index `query_graph` anchored on a named Function | `git grep` restricted to the directory | none; the CALLS edge's `line` attribute is not trusted |
| the email behind a commit (D) | the commit's `Link:` and `Closes:` trailers, taken verbatim | none | a commit with neither is cited without a URL |
| coverage of a file in the index | `check_index_coverage` before any graph answer about the file | `search_graph` on the name, which confirms or denies the node | `git grep` of definitions in the listed ranges |

## Gates are not a tool question

Whether the documented build compiles a file or a branch is read from three texts: the subsystem Makefile's `obj-$(CONFIG_...)` lines, the `#if`, `#ifdef` and `#ifndef` conditions around the code, and the documented config's resolved values, the `.config` of the documented config resolved once per campaign into a scratch directory.

`make O=<scratch> x86_64_defconfig` does that on a clean tree; a tree that holds an in-tree `.config` (one built in place) refuses with "source tree is not clean", and then `scripts/kconfig/conf --defconfig=arch/x86/configs/x86_64_defconfig Kconfig`, run from the tree root with `KCONFIG_CONFIG`, `KCONFIG_AUTOCONFIG`, `KCONFIG_AUTOHEADER` and `KCONFIG_RUSTCCFG` pointing into the scratch directory and `srctree=. ARCH=x86 SRCARCH=x86`, resolves it without touching the tree.

The compile database is built from the config of its own build, a wider one such as allmodconfig, and says what that build compiles, never what the documented build has.

The build the campaign documents is the one its Campaign block lists (the CONFIG assumptions of CAMPAIGN FACTS), and a defconfig is read only to learn what it leaves set or unset. Resolve a defconfig into scratch without touching the tree, with the configuration tool the tree already built and the clang toolchain variables its compiler probes need (the probes fail silently without them, and the resolved file then lacks the options they guard):

```sh
K=<scratch>/kconfig; mkdir -p $K/include/config $K/include/generated
cd <tree> && CC=clang LD=ld.lld LLVM=1 HOSTCC=clang CLANG_FLAGS=-fintegrated-as \
  KCONFIG_CONFIG=$K/.config KCONFIG_AUTOCONFIG=$K/include/config/auto.conf \
  KCONFIG_AUTOHEADER=$K/include/generated/autoconf.h KCONFIG_RUSTCCFG=$K/include/generated/rustc_cfg \
  srctree=. ARCH=x86 SRCARCH=x86 scripts/kconfig/conf --defconfig=arch/x86/configs/x86_64_defconfig Kconfig
grep -E '^(# )?CONFIG_(PCI_IOV|PCI_DEBUG|ARCH_DMA_ADDR_T_64BIT)[ =]' $K/.config
```

`make O=<dir> x86_64_defconfig` refuses to run while the tree carries an in-tree build (the compile database's), which is why `conf` is called directly.

**Measured at v7.2:** x86_64_defconfig leaves CONFIG_PCI_IOV, CONFIG_PCI_DEBUG, CONFIG_DYNAMIC_DEBUG and CONFIG_HOTPLUG_PCI_PCIE unset and sets CONFIG_ARCH_DMA_ADDR_T_64BIT, while the tree's own `.config` behind the compile database sets PCI_IOV, PCI_DEBUG and OF; a page states the campaign's assumption where a gate depends on one of these.

## Tests, scripts and tools

### Finding the tests

The tests the tree carries for a function are found by its name in the test files, one batched `git grep -n -w -e <name> -e <name> -- '*test*'`, since every kind of test lives under a path that holds that word: a KUnit suite in a `tests/` directory or a `*_test.c` file beside the code (317 `.c` files of the tree register one with `kunit_test_suite` or `kunit_test_suites` at v7.3), a test module under `lib/` (32 `lib/test_*.c` files), a driver's own selftests (`drivers/gpu/drm/i915/selftests/`), a kselftest under `tools/testing/selftests/` and the user-space harnesses beside it (`tools/testing/vma/`, `tools/testing/radix-tree/`, `tools/testing/memblock/`).

A user-space test calls no kernel function, so the function's name does not find it: search for the syscall, the ioctl, the sysfs or the debugfs name of the surface the function serves.

The seams the code under test carries for a test are found by their macros: `VISIBLE_IF_KUNIT` and `EXPORT_SYMBOL_IF_KUNIT` (`include/kunit/visibility.h`), `KUNIT_STATIC_STUB_REDIRECT` (`include/kunit/static_stub.h`), and a driver's own pair, as amdgpu's `STATIC_IFN_KUNIT` and `EXPORT_IF_KUNIT` (`drivers/gpu/drm/amd/display/dc/dm_helpers.h`).

### The configuration a test is documented under

A production configuration leaves the tests unset: the Ubuntu generic amd64 configuration for 7.3 has `CONFIG_KUNIT` unset, so no suite's option has a line in it. The compile database's allmodconfig is no configuration to document a test against either, since 6,227 of the 16,399 options the two files carry differ between them.

A page on a test is written against the campaign's configuration with the test's options set, resolved once per campaign into the workspace: append the options to a copy of the campaign's `.config` and run `scripts/kconfig/conf --olddefconfig Kconfig` with the variables of the command above, which leaves the tree untouched.

**Measured at v7.3:** with `CONFIG_KUNIT`, `CONFIG_DRM_KUNIT_TEST`, `CONFIG_DRM_AMD_DC_KUNIT_TEST`, `CONFIG_DRM_I915_KUNIT_TEST` and `CONFIG_DRM_XE_KUNIT_TEST` set to `m`, 19 options differ from the Ubuntu configuration, those five and the 14 Kconfig sets with them.

The options to set come from the fragment the tree ships beside the test, a `.kunitconfig` (46 in the tree at v7.3) or a selftest directory's `config` file (97 under `tools/testing/selftests/`); the fragment is read for the test's options and never merged whole, because it is written for the small kernel `kunit.py` builds and sets what that kernel needs (the amdgpu display manager's sets `CONFIG_DRM_AMDGPU=y`, `CONFIG_GCOV=y` and `CONFIG_WERROR=y`).

### Scripts and tools

The scripts and tools the tree carries for a subject are found by the subject's own names under the two directories, with the tests and the headers copied for user-space builds left out: `git grep -l -w -e <struct> -e <file, ioctl or tracepoint name> -- scripts tools ':!tools/testing' ':!tools/include' ':!tools/arch'`.

What turns up, at v7.3: the gdb helpers of `scripts/gdb/linux/` (30 files, one per area, `mm.py`, `slab.py`, `page_owner.py` and `vmalloc.py` among them), the 76 semantic patches under `scripts/coccinelle/`, and the user-space programs of a `tools/<area>/` directory (`tools/mm/` holds `page_owner_sort.c`, `page-types.c` and `slabinfo.c`).

A subject may have none: a search for `drm_dp`, `dpcd`, `dp_aux` and `displayport` finds one file, a sound header copied for perf, and a word search for `drm` finds 17, perf's `drm_pmu.c` and its `drm_ioctl.sh` table generator among them.

## The symbol index: codebase-memory-mcp

### How to call it

Registered as an MCP server of the agent host; its index of the documented tree is a project named after the tree root's path (`list_projects` names it), kept in the tool's cache directory. Through the MCP tools, or the CLI `codebase-memory-mcp cli <tool> --project <project> ...` (about four seconds of start-up per call unless a daemon runs):

- `search_graph --name-pattern '^name$'`: definitions with file and line range.
- `trace_path --function-name <name> --direction inbound|outbound --depth 1`: callers or callees; a name defined in several files comes back ambiguous with qualified names, one per file, to query again.
- `get_file_outline --file-path <path>`: a file's declarations in order with line ranges.
- `query_graph --query "MATCH (a:Function {name: '<name>'})-[c:CALLS]->(b) RETURN b.name, properties(c)"`: call edges with `line`, `confidence` and the argument texts. Anchor every Cypher pattern on a named Function; a filter on a Field or Variable name alone runs past the time limit.

### Known holes

**Where it errs, measured at v7.2:**

- a function a macro defines (`SYSCALL_DEFINE2(arch_prctl, ...)`) is absent;
- a call inside a macro loop is attributed to the file, not the enclosing function;
- a function after an ACPICA `ACPI_EXPORT_SYMBOL(...)` line starts at that line;
- struct fields have no write edges;
- it sees every `#if` branch.

The binary needs `CBM_RUNTIME_DIR` set to a directory whose parent the user owns (the registration carries it).

**Measured again at v7.2:**

- `trace_path` returns no caller for a name that a header also defines as a `!CONFIG` stub, records no edge for a function that only writes a global, resolves a macro call to an unrelated node of the same name (`dev_err` to a struct member of hisi_acc_qm.h, `list_for_each_entry` and `INIT_LIST_HEAD` to the copies under scripts/gdb and drivers/gpu/drm/radeon) and misses callers outside the subsystem's own directory, elsewhere under drivers/ and in block/, mm/ and net/ (`trace_path` inbound on one exported function returned 5 of its 8 callers, missing blk-mq-dma.c, hmm.c and tso.c, and the header stub's node returned none);
- a `query_graph` anchored on the callee's Function node timed out three times over that census;
- a caller census takes `git grep -nw` and a `clang-query` caller match over the compile database before it believes a zero.

`search_graph` and `get_file_outline` report a `#define` as two lines, leave a file-scope array out of an outline (`amdv1_kunit_fmt_cfgs`) and know no function an `NS()` macro names (`NS(map_range)`, `NS(get_info)`), which a `clang-check -ast-dump-filter=amdv1_get_info` of the unit finds under its compiled name; a `query_graph` filter over a dozen names times out.

**Measured again at v7.3 over the mm, VMA and mapping areas** (in the inventories and the plan reviews of the campaigns that planned them):

- `check_index_coverage` is the first call on a page's files. Its `parse_partial` ranges are of two kinds: a range that hides nodes (mm/userfaultfd.c 3718 to its end, where `userfaultfd_register`'s calls hang on `validate_range`; fs/proc/task_mmu.c from `show_smaps_rollup` to its end; kernel/exit.c 1674-2015; the `__must_check` declaration lines of mm/vma.h and include/linux/mmap_lock.h; include/trace/events/maple_tree.h whole) and a one-line range that hides nothing (the `__rcu` and `__must_hold` lines of lib/maple_tree.c, the `for_each_vma` loop-macro lines, mm/madvise.c 2168-2245, a `scoped_guard` line).
  - A flagged range is a prompt to confirm with `search_graph` on the name, not a verdict.
- A function a macro defines (`SYSCALL_DEFINE2(process_mrelease)`, every SYSCALL_DEFINE of the mapping syscalls) has no node; its body's calls hang on a file-level phantom node (`mm.oom_kill`, `mm.mmap` for the brk body, `ipc.shm` for shmat), and `__file__` phantoms can dominate an inbound list (`vma_set_pgoff` 80 callers of which 73 are phantoms, 4 direct sites on disk). A syscall's call list comes from `git grep -p`.
- Where a header or a file defines a name twice under `#if`, the index answers with the stub or a forward declaration first: the `!CONFIG_PER_VMA_LOCK`, `!CONFIG_ANON_VMA_NAME`, `!CONFIG_DEBUG_MAPLE_TREE`, `!CONFIG_SHMEM`, `!CONFIG_NUMA` and `!MMU` branches (`vma_start_write`, `lock_vma_under_rcu`, `anon_vma_name_alloc`, `MT_BUG_ON`, `shmem_get_unmapped_area` carrying the real callees, `vma_dup_policy`, `may_expand_vm`, `mlock_future_ok`, `mmap_action_prepare`, the `#else` stubs of `move_normal_pmd`), a name defined twice in one file under `CONFIG_MMU` with a node for the `!MMU` twin only (`io_uring_mmap`), the first mm/util.c `arch_pick_mmap_layout` with no node at all, and `get_file_outline` returning the stub in place of the definition (four functions of mm/madvise.c) or placing a struct at its forward declaration or initializer.
  - Read the file of every hit, and anchor a documented definition by file and line from `git grep`, never from a `search_graph` range.
- A name defined once per architecture is one node per architecture, located correctly, but the x86 nodes of `init_new_context`, `destroy_context`, `arch_dup_mmap` and `arch_exit_mmap` show no callers and their callee edges resolve to the `!CONFIG` stubs; a `__weak` default with an x86 override binds the caller to the default (`load_elf_binary`'s `arch_randomize_brk` to the mm/util.c form the x86 build does not compile), and the x86 node shows no caller.
- In-degrees are no census, and the hole is widest for header static inlines and cross-tree APIs:
  - `lock_vma_under_rcu` 4 against 16 C sites and a Rust wrapper (every arch/ fault handler, bpf, tcp and binder missing), `vma_lookup` 2 against 78 lines, `vm_flags_set` 0 against 94, `mmap_read_lock` 6 against 156, `mmget_not_zero` 1 against 71, `vfs_mmap` 2 against 5;
  - a `__must_check` function is a Method node `__must_check.<name>` with no callers;
  - a `DEFINE_SPINLOCK` or `DEFINE_MUTEX` object has no node;
  - degree counts disagree between the index's own tools (`mmput` 125 by `search_code`, 119 by `trace_path`);
  - a CALLS edge's `line` is wrong in places;
  - a callee list omits `__must_check` functions and functions with a `!CONFIG` header stub (`do_mremap`'s omits `mmap_write_lock_killable` and `vma_lookup`, `copy_vma_and_data`'s omits `mremap_userfaultfd_prep`);
  - a dispatch through a callback table is invisible (`perf_mmap_close`'s inbound list holds only `perf_mmap`);
  - a `#ifndef` caller is reported without being marked uncompiled.
- A bare name is ambiguous against a tools/testing stand-in (`vfs_mmap`, `move_page_tables`, `split_vma`, `get_sysctl_max_map_count`, `update_hiwater_rss` against dup.h and stubs.h) or a nommu twin (`do_mremap`, `do_mmap`); the qualified name separates them and surfaces the harness's own hooks (`fail_prealloc`, the test caller `attach_vma` flagged as a test).
- Where it is right it is fast: definition ranges matched the disk for every lifecycle, locking and VMA symbol checked (21 of 21, 24 of 24, 23 anchors in one call); `trace_path` matched grep for `mmgrab` (70), `vma_iter_prealloc` (10), `lock_next_vma`, `vma_merge_new_range`, `commit_merge`, `__split_vma`, `copy_vma`, `hugetlb_reserve_pages` and `__mmap_region`, gave `expand_stack`'s six and `vm_unmapped_area`'s 22 cross-architecture callers in one call, found the Rust `VmaRef`, `VmaNew`, `VmaMixedMap` and `MmapReadGuard::vma_lookup` methods with exact spans where a brief had the wrong file, and `search_code` for `.may_split` matched grep's nine files in 6.5 s.
  - `git grep -n -p` stays the floor of every census and the compile database its second basis.

## The compile database

### Building and running it

`compile_commands.json` at the tree root, generated by clang (`make LLVM=1 compile_commands.json`, or `scripts/clang-tools/gen_compile_commands.py` over an `LLVM=1` build), lists every unit that build compiles with its exact command, and the clang tools read it with `-p <tree>/compile_commands.json`, so each unit is parsed as it was built.

A database written by a GCC build does not serve: every clang tool fails on the GCC-only warning options in its commands. The tools are `clang-query` (AST matchers over one or more units), `clang-check` (an AST dump or a record layout of one unit) and `clang -E` (what a unit's own command preprocesses), the first two from clang-tools-extra; no index is built and no Python binding is needed.

About half a second per unit at v7.2 (arch/x86/pci/acpi.c), and several units with several `-c` matchers go in one `clang-query` run, so the questions of one page are batched.

The units a matcher reads come from the database (`python3 -c 'import json; print(" ".join(e["file"] for e in json.load(open("compile_commands.json")) if "/drivers/pci/" in e["file"]))'`), the directories a campaign leaves at the seam (drivers/pci/controller and drivers/pci/endpoint for an x86 page) left out; a file absent from the database is one that build does not compile, which answers the last question of kind B for that build and says nothing about the documented one (the gates above).

A matcher holds the AST of every unit it is given until it exits, about 400 MB a unit: give `clang-query` the grep-named units of one subsystem, a few dozen at most, never a tree-wide list. A `match designatedInitExpr()` over the whole tree at v7.3 reached 24 GB of memory in four minutes, the machine's limit, and was killed; the tree-wide question (kind C) belongs to `git grep` and the symbol index, the matcher to the units they name.

| question | command |
|---|---|
| a definition, its AST, a designated initializer | `clang-check -p <db> -ast-dump -ast-dump-filter=<name> <file>` (an initializer's `InitListExpr` prints its designators) |
| a struct's size and field offsets | `clang-check -p <db> -extra-arg=-Xclang -extra-arg=-fdump-record-layouts <file>` (`-fdump-record-layouts-complete` prints every record the unit sees) |
| the callers of a function | `clang-query -p <db> <files> -c 'set output diag' -c 'match callExpr(callee(functionDecl(hasName("<name>"))))'` |
| the calls a function makes | `... -c 'match callExpr(hasAncestor(functionDecl(hasName("<name>"))))'`, with `set output print` for each call's text |
| the writers of a struct's field, through a pointer or a value | `... -c 'match binaryOperator(isAssignmentOperator(), hasLHS(memberExpr(member(hasName("<field>")), hasObjectExpression(hasType(pointsTo(recordDecl(hasName("<struct>"))))))))'`, and the same with `hasType(recordDecl(...))` for an embedded object |
| the writers of a file-scope variable | `... -c 'match binaryOperator(isAssignmentOperator(), hasLHS(declRefExpr(to(varDecl(hasName("<name>"))))))'` |
| the address of a field taken | `... -c 'match unaryOperator(hasOperatorName("&"), hasUnaryOperand(memberExpr(member(hasName("<field>")))))'` |
| the uses of a macro | `... -c 'match stmt(isExpandedFromMacro("<MACRO>"))'` |
| what a unit compiles under that build | the unit's command from the database with `-c` and `-o <object>` removed and `-E -P` added, run from its `directory`; a name that survives preprocessing is compiled, one that does not is behind a condition that build left out |

`set output diag` prints one `file:line:col` per match, `set output print` the matched text, `set output dump` the subtree. A `hasName` matcher matches every definition of that name, so a static function two files define is told apart by the file of each match.

### Known holes

**Where it errs, measured at v7.2 over the PCI pages:**

- a matcher sees only the units it is given, so a tree-wide count needs the symbol index or `git grep -nw` as its second base (`facts.two-bases`);
- a whole-object `memcpy` or `memset`, a field filled through an out-parameter and a write through a pointer parameter are no `binaryOperator`, so a writer match that finds nothing is read against the file;
- a call through a function pointer or a `__setup` table is no `callExpr` to its target;
- a call spelled through a macro matches the function the macro expands to, and the macro's own use is matched by `isExpandedFromMacro`;
- a static inline of a header matches once per unit that includes it, so matches are de-duplicated by file and line;
- a tristate option is `m` in an allmodconfig database, so `IS_BUILTIN` differs from the documented build.

**Measured again at v7.3 over the mm, VMA and mapping areas** (the database there is the tree's own x86-64 build with COMPILE_TEST, RANDSTRUCT_FULL, LOCKDEP, LOCK_STAT, DEBUG_SPINLOCK, KASAN, DEBUG_VM, DEBUG_VM_MAPLE_TREE, X86_VSMP and BASE_SMALL, without X86_X32_ABI; the documented build is an Ubuntu config):

- What the database compiles beyond the documented build (`validate_mm`, the `VM_BUG_ON` family, the maple-tree debug checks, `CONFIG_ADDRESS_MASKING`) is named as the database's build; a file absent from it (mm/nommu.c) or a definition absent from the x86 unit (`expand_upwards`) confirms what the documented build omits; `nm` on the database's objects settles "compiled or not" for a gate that does not depend on the config (the generic `get_unmapped_area` searchers are `T` in mm/mmap.o while the `arch_get_unmapped_area` fallback pair and the `__weak` `arch_randomize_brk` are absent).
- Layouts:
  - `-fdump-record-layouts-complete` lays records out before a trailing `____cacheline_aligned` applies and understates them (struct mm_struct 2776 against 2944, `struct mm_cid_pcpu` 4 against 64);
  - the plain dump of a unit that lays the record out, or a `_Static_assert`/`offsetof` probe compiled with the unit's command (`-DRANDSTRUCT` removed for declaration order), is the layout basis;
  - a struct a unit only points at gets no layout (`struct vm_operations_struct`, 144 bytes by probe after a guess of 160 failed), and `ma_wr_state` and `ma_topiary` got none even when instantiated, so a size comes from a probe or a type-mismatch diagnostic;
  - `-fdump-record-layouts-simple` reports sizes in bits;
  - `-fsyntax-only` with the sanitized command (no `-MMD`, no `-o`) gives every struct size at once;
  - `-fstack-usage` on the unit's command gives frame sizes, which no other tool does;
  - a command runs from the tree root because the randstruct seed path is relative.
  - The database's sizes carry its lockdep and KASAN fields (struct maple_tree 88 against 16, struct vm_area_struct 256 against 192, struct percpu_counter against 40); a documented layout is computed from the declaration order, or approximated by re-pointing the unit's command at the resolved config's `autoconf.h` with `-extra-arg-before=-I` and reading the unrelated errors.
- Matchers:
  - a field in an anonymous struct or union needs one `ignoringImplicit(memberExpr(...))` level per nesting (`hasObjectExpression(ignoringImplicit(memberExpr(hasObjectExpression(hasType(pointsTo(recordDecl(hasName("mm_struct"))))))))`, with `vm_start` and `vm_end` two levels deep and `mm_count` two deep), and the plain writer recipe matches nothing on such a struct, so a zero taken with it is wrong;
  - for a member neither nested form matched (`flags`), a member-name-only `memberExpr(member(hasName("flags")))` found the sites, and a plain `memberExpr(member(hasName("map_count")))` matched `mm->map_count` directly with exactly eight writers;
  - a parenthesized LHS from a macro needs `ignoringParenImpCasts`;
  - a write through `WRITE_ONCE`, `memset`, `memcpy`, a designated initializer or an out-parameter is no `binaryOperator`, so a field-writer census unions the matcher with a grep for those forms;
  - `whileStmt(isExpandedFromMacro("for_each_vma"))` matches nothing where `callExpr(isExpandedFromMacro(...))` matches the sites, and `isExpandedFromMacro` returns one row per sub-statement, so a count dedups by line;
  - a `hasAnyName` list of about 47 names fails to parse ("Expected end of code") and batches of about ten work;
  - `DEFINE_GUARD` noise from include/linux/mmap_lock.h is filtered from a `callExpr` census;
  - `varDecl(isDefinition)` also matches tentative forward declarations where `designatedInitExpr` lists every hook installation cleanly.
  - About 0.6 s per unit (52 units in 31 s; 19 units in about 10 s for 76 field-access sites with columns; a field-writer census of one struct in under a second), and it finds union-member assignments (`vma->flags = ...`) that grep patterns miss.

## The tags file

`<tree>/tags` from `make tags` (universal-ctags with the kernel's ignore list). `readtags -t <tree>/tags -e <name>` locates a definition anywhere in the tree in milliseconds; `-Q '(eq? $kind "f")'` filters by kind.

Its entries carry a search pattern and no line number (`-n` prints none; the pattern is cut at 96 bytes), and a line that holds a tab breaks a tab-split of the output, so a reader that waits for `line:` finds nothing: `tools/tagsfile.py` settles each pattern to its line on disk (the k-th entry of one pattern to the k-th such line, the twins two `#if` branches define) and moves a function to the first line of a split signature; `anchors.py resolve` and the research pack read through it, in milliseconds per name, and fall back to `git grep` only for a name the file lacks.

A member name defined in several structs of one file is settled by its `struct:` scope; `tools/testing/` stand-ins (`tools/testing/vma/include/dup.h` repeats `struct vm_area_struct`) are listed after the kernel's own definitions and dropped by `NAME@path`. It is the fallback for kind C and has no call graph.

A constant that two `#if` branches of one enum define (`PT_MAX_VA_ADDRESS_LG2` in amdv1.h) is indexed at the first branch, the selftest's, so the documented build's value is read on disk. A campaign may generate none (the v7.3 campaigns do not); the research pack's definition search then falls back to `git grep` in the Campaign block's roots.

## The research pack

The RESEARCH PACK of a brief (`tools/campaign/run.py content --hints`, `guidelines/campaign/spec.md` [prompt]) is the tags file and `git grep` run once for every name the scope and the page's `symbols` give: the definition lines with a function's range, a `-w` census counted tree-wide and printed for the roots and the rest of the code up to a cap, and the callers by function, the call sites only. Every line is a hint to re-read on disk before it is cited, never a citation.

**Measured at v7.3 over 102 pages, the briefs against the templates the writers built:**

- the writers excerpted 75% of the definitions the pack listed, 31% of its caller ranges and 28% of its census lines;
- half of all excerpts begin at a line the pack had named, a third elsewhere in a file it had named, 13% in files it never named;
- 37 pages corrected the pack in a hint, 46 corrections in all.

**What it gets wrong, and what to do:**

- The tags file from `make tags` indexes the built architecture only (`scripts/tags.sh`: ALLSOURCE_ARCHS defaults to SRCARCH; at v7.3 the file holds 70,727 entries under `arch/x86/` and none under `arch/arm64/` or `arch/powerpc/`), and the git-grep fallback sets the other architectures aside, so a hook every architecture defines (`set_pte_at`, `flush_tlb_range`) shows one or two definitions, not one per architecture; a tags file built with `ALLSOURCE_ARCHS=all` would list them all, and the pack would then need the documented architecture's picked by hand.
  - A config-dependent definition inside the documented architecture (`ptep_get_lockless`: the GUP_GET_PXX_LOW_HIGH form that X86_PAE selects, the fallback that x86-64 compiles) is listed in both forms; the `#if` around each says which the documented build compiles.
- A common name (`flags`, `lock`, `next`) gets its definitions under the roots and a count past PACK_DEFS_CAP (40), no census and no callers past PACK_COMMON_CAP (200) mentions: its census is taken by hand with a pathspec.
  - The cap sits where the names change character: of the 5.29 million names the tags file holds at v7.3, 1,963 have more than 40 entries, and the band from 41 to 200 is struct members and macro names shared across drivers (`vport`, `tx_queue`, `spinlock`, `parent_name`, `dev_name`, `kref`, `mm`), nothing a page is about.
- The census is `git grep -n -w`: it counts comments, strings, Kconfig text and other architectures (set aside and counted, not printed), so a count read off it is a ceiling until the lines are read.
  - The callers by function are the call sites, the lines where the name stands before `(`: a function pointer installed in an operations table, a SYSCALL_DEFINE argument and an EXPORT_SYMBOL are in the census and not among the callers, so a consumer census that needs the installs reads the census lines or clang-query.
- **Fixed on 2026-11-08 after writers reported them:**
  - a static function declared ahead of its definition was reported as a one-line stub at the prototype (the tags file's twin patterns);
  - an object a macro defines (`DEFINE_STATIC_KEY_MAYBE(CONFIG_DEBUG_VM, name)`, `DEFINE_PER_CPU(type, name)`) was "no definition found";
  - `SYSCALL_DEFINE4(migrate_pages, ...)` stood among the callers of `migrate_pages()`;
  - a column-0 macro invocation without a `;` (`PAGEFLAG(Locked, locked, PF_NO_TAIL)`) was taken for a function whose body was the next brace to close, so `folio_test_swapcache` and every function below such a line in include/linux/page-flags.h was "no definition found";
  - a function the tags file knew only as a stub or a prototype (`css_put`, whose definition stands behind `CGROUP_REF_FN_ATTRS` on its own line) was never searched for by grep, so its real definition was missing.
  - A pack line that still looks wrong goes into the unreproduced hints of the writer's report, which is how these were found.

## The checker's parser

`tools/qa/tree.py` gives one set of facts about a source file: its functions, types, file-scope variables, macros and members, each with the line that names it, the first line of its signature and its last line.

- Who reads the facts:
  - the checker, in every rule that asks which construct holds a line: `excerpts.enclosing`, `excerpts.walkthrough`, `excerpts.outline`, `excerpts.contiguity`, `drawing.legend`;
  - `excerpt.py --whole`;
  - the `members` view.
- Where the facts come from:
  - tree-sitter's C grammar, which reads the file as written: every `#if` branch, and no macro expanded;
  - the layout kernel style gives a definition (a function's braces in column 0, a macro's `#define` line and its continuation), to which the parser holds the reading where a macro tree-sitter cannot read costs it a function's end or the definitions after it.
- What a misread fact shows as:
  - a finding the source does not bear out;
  - a function those rules pass over without a word.

**What to do with a misreading:**

- A page that meets one says so in its writer's report, in the `tooling` text, with the file, the lines and what the checker read there.
- The count of such reports decides whether the parser is changed.
- A misreading no page has met is recorded here and left as it is.

### Known misreadings

**Misreadings the writers report, by a text search of the 208 writers' reports under `progress/`:** nine pages, at six places in the tree, all six fixed by 2026-11-15.

- A union whose body is a macro with no `;`: dmub_cmd.h:2735, three pages.
- A struct of such macros: clk_mgr_internal.h:439, one page.
- A conditional group that opens one block per branch: amdgpu_dm_cursor.c:90, two pages.
- A function a `#if` splits: `resource_build_scaling_params`, dc_resource.c:1565, one page.
- A block a macro closes: `} for_each_vma(vmi, vma);`, fs/proc/task_mmu.c:1588, one page.
- A macro invocation above a function: mm/interval_tree.c:16, one page.

**Misreadings no writer has reported, found by an audit at v7.3 of the 2,748 source files the pages of `docs/` cite:**

- A function a macro writes above a body takes its name from the macro:
  - the macro's one argument: `SYSCALL_DEFINE0(fork)`, kernel/fork.c:2862, is `fork`; `DEFINE_IDTENTRY(exc_divide_error)`, arch/x86/kernel/traps.c:380, is `exc_divide_error`;
  - the macro's own name when it takes more: `SYSCALL_DEFINE1(brk, unsigned long, brk)`, mm/mmap.c:117, is a function named `SYSCALL_DEFINE1`, so the five syscalls of mm/mmap.c are told apart by their lines.
- What a macro invocation defines with no body below it is no fact, no construct holds its line, and `excerpt.py --whole` answers "lies in no construct" there:
  - a variable: `static DEFINE_PER_CPU(struct bh_accounting, bh_accounting) = {0, 0};`, fs/buffer.c:2855;
  - a function: `DRM_ENUM_NAME_FN(drm_get_tv_mode_name, drm_tv_mode_enum_list)`, drivers/gpu/drm/drm_connector.c:1286;
  - a cleanup helper: `DEFINE_FREE(state_release, ...)`, amdgpu_dm.c:1463.
- A macro is one construct from its `#define` line to the end of its continuation:
  - a function its body writes is a construct of its own in some macros and not in others, by where tree-sitter stops reading the body, which is at a comment inside it: the five functions of `INTERVAL_TREE_DEFINE` (include/linux/interval_tree_generic.h:28-183) are constructs, the one of `DEFINE_SHOW_ATTRIBUTE` (include/linux/seq_file.h:206-218) is not;
  - `excerpt.py --whole path:LINE` shows which construct holds a line;
  - a body line outside such a function belongs to the macro, and `excerpts.enclosing` refuses an excerpt of a macro without its `#define` line whatever the prose above the fence links (the comment at interval_tree_generic.h:71-78).
- A conditional group that writes the signature once per branch above one body (`handle_invalid_op`, arch/x86/kernel/traps.c:391-396):
  - the first branch's signature is a prototype in no construct;
  - the function begins at the second, line 394.
- A variable is no fact where:
  - it is declared on the closing brace of an unnamed struct or enum: `acpi_skip_ac_and_battery_pmic_ids`, drivers/acpi/x86/utils.c:597-600; `drm_compat_ioctls`, drivers/gpu/drm/drm_ioc32.c:330-333; `vsyscall_mode`, arch/x86/entry/vsyscall/vsyscall_64.c:44;
  - its initializer is an `#include`: `sysctl_sched_features`, kernel/sched/core.c:171.

## Text

`git -C <tree> grep -n` for strings, comments, Kconfig and Makefiles; `git -C <tree> log --format=%B -1 <sha>` for commit messages and their `Link:` and `Closes:` trailers (`sections.other-sources`).

**Measured at v7.3,** git is also the floor of every census and the fastest history tool:

- `git grep -n -p` prints the enclosing function of every match and was the fastest basis for consumer lists of a lock or mapping API, including the index's unparsed ranges;
  - `git grep -n -w` is the floor of a caller census, and a `-w` pattern with a trailing `\(` silently undercounts calls, so a lookbehind regex is used;
  - `-p` misattributes an initializer inside a macro body or an array (`DRM_GEM_FOPS`, `snd_pcm_f_ops[2]`), so a census by holder struct needs a brace-walking classifier over the hits;
  - the definition-shape grep `^[A-Za-z_].*\bname\(` misses a function whose name opens the line.
  - A bare word match counts string literals, which is how a boot parameter, a sysctl procname or a meminfo line (`align_va_addr`, `legacy_va_layout`, `CommitLimit`, `perf_event_paranoid`) passes an existence check with no C symbol behind it; a page anchors the handler or the variable. A macro-generated name (`VMA_*_BIT` from `DECLARE_VMA_BIT`) never appears on its declaration line, so `git grep -w` finds only its uses.
- `git log v7.0..v7.3 -L ':<func>:<file>'` gives a function's history in one pass where the file-level log holds a hundred commits and proves "no change in the range" for a whole function; `-L` was empty on `__shmem_file_setup` where `-S` found the change, so a negative from `-L` is confirmed with `-S` on the path.
  - `git log -S` over the whole history exceeds 120 s per query and is scoped to a path or a revision range; on a path it names the first use, not the definition; it misses a rename that keeps the old name as a substring (`set_vma_from_desc` to `compat_set_vma_from_desc`), where the full signature string finds it.
  - `git describe --contains` and `git merge-base --is-ancestor` settle which release a commit landed in and corrected two dates a brief carried.
- A reuse audit of archived pages: `git show <tag>:<path>` slices and a scripted sweep over the saved pages (compare every anchor line between two tags, search the new tag for the same line text, map units across elisions) give full counts where repeated `sed -n` calls do not; a first-match "name in file" fallback lands on comments, and the "moved same text" class takes the nearest identical line and can mis-place a generic member line, so `git grep -n` on the definition shape corrects both.

## semcode

[semcode](https://github.com/facebookexperimental/semcode) is used for one kind of question only, a dispatch through a function pointer, which the symbol index cannot see: `find_implementors` lists the functions installed in a member of a struct type, and `find_registrations` the members a function is installed in.

Its other tools (`dig`, `lore_search`, `find_function`, `find_type`, `find_callers`, `find_calls`, `grep_functions`, `file_survey`) are not used by this repository: the thread behind a commit comes from the commit's `Link:` and `Closes:` trailers alone, kinds A to D have the tools above, and a count or a caller set taken from them is not a basis of `facts.two-bases`.

A page never names the tool (`style.verification-narration`).

**Measured at v7.3, when one campaign allowed the code-reading tools as an experiment:** the lore index on the measuring machine covered linux-mm, so `dig` found the thread of a `mm/vma` commit and nothing for a futex, sched or x86 commit that came through the tip tree, whose URLs come from `Link:` trailers.

`find_function` locates definitions with ranges and return types; `find_callers` treats a SYSCALL_DEFINE body as a macro function and knows the Rust helpers, but missed x86's `cpu_init` among `mmgrab`'s callers and lists one definition's callers for a same-named function; `find_calls` resolves per-architecture callees to another architecture unless given `scope {"arch": "x86"}`; `find_type` ignores an anchored regex; `vgrep_functions` needs a model the machine lacked.

The server is one process shared by every agent and calls queue on it: a scoped `find_calls` or `find_callers`, `lore_search` by regex, `grep_functions` by body regex and `file_survey` each ran longer than the host's 1800 s idle timeout on a 4.5 GB index and were aborted, under load and again idle, and once such a call hangs every later call, `dig` included, waits behind it (the process computing at about 19% CPU, not deadlocked).

The cheap kinds (`find_function`, an unscoped `find_callers`, `dig` by commit) answer in seconds on an idle server. So no agent on the critical path called semcode; the campaigns planned after that one excluded it from every prompt for that reason.

**Measured again on 2026-11-13, on semcode built from its newest source with its index and ten lore lists rebuilt:** `dig` matched nine of ten commits by their subject, but its default answer, the most recent match, was the patch itself for four of the nine and a reply, a stable backport or a revert for the rest, and it prints a Message-ID and no URL, from which `sections.other-sources` lets no page build one.

`find_callers` answered five caller questions with no caller four times and with 10 callers once, where the tree has 1, 1, 1, 218 and 103 call lines. `find_implementors` on two members and `find_registrations` on three functions agreed with the tree's initializers: every install a text extraction found, and seven more it had missed, one declared with `__maybe_unused` and six with a line break after `struct`.

The server refuses every question for 17 to 31 seconds after it starts and rewrites index files on each start.
