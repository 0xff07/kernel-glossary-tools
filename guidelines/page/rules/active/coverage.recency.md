---
qa: auto
---

# Recency

An example driver has substantive commits within three years before the documented version, ignoring renames and churn. Describe its vendor/bus/class, file and callback from its own source rather than by analogy to another driver or page. State when no active driver exercises the behavior. An example is a cited file under drivers/ outside the subsystem's own kernel_paths, excluding Kconfig and Makefile.

A subsystem whose entry in `guidelines/subsystems.md` says `consumers: core`, one whose callers are other core subsystems rather than drivers (memory management, the scheduler), owes no driver example: none of its cited files is an example, a file under drivers/ it links is a seam lookup, and this rule does not apply to its pages.

Compare committer dates with the documented commit, using 365.25 days per year. Read the actual change: a recent typo, tree-wide change or API conversion does not by itself prove substantive behavior; an API conversion containing substantive change may qualify.

The window is three years before the documented version's commit time. An example driver is a cited file under drivers/ but outside the subsystem's own kernel_paths, excluding Kconfig and Makefile. Inspect the commit for substantive change; a recent timestamp alone is insufficient. Rename-only, typo or tree-wide churn does not establish recency; inspect whether an API conversion includes substantive behavior.

The rule applies to a subsystem whose entry says `consumers: drivers` or says nothing about its consumers.
