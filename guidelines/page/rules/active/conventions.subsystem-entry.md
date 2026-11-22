---
qa: off
---

# Subsystem entry

`guidelines/subsystems.md` carries, per subsystem, the tag, the `docs/` directory, the kernel paths, the specification, the section-six heading (REGISTERS, METHODS, PRIMITIVES or INTERFACES) and, for a subsystem whose callers are other core subsystems rather than drivers, `consumers: core` (a driver-facing subsystem says `consumers: drivers` or nothing); the prep pass resolves the page's entry and the page follows it; its kernel paths decide which files lie in the subsystem.
