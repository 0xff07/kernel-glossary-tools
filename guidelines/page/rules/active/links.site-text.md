---
qa: off
---

# Site text

A location link's text names its file by base name, `tb.c:130` or `tb.c:130-135`, not by its path from the tree root: the URL carries the path, the provenance of the excerpt beside the prose spells it out, and a table of sites stays narrow. Two exceptions keep the path:

- a page that cites two files sharing a base name, `drivers/thunderbolt/acpi.c` beside `arch/x86/pci/acpi.c`, writes both from the tree root, and
- `Kconfig` and `Makefile` keep their path because their base name recurs across the tree.

Any other file without an extension is named by its base name like the rest, `sysfs-bus-thunderbolt:24`. A symbol link's file is a cited file too: linking a symbol defined in a file that shares its base name with a file the page cites by location makes every such location text carry its path, so a location link into a file the page already cites, or the operation named in words, comes before a link to a stray symbol.

An outline table's location cell is no location link: it keeps the base name even when another cited file shares it, the provenance lines of the pieces spelling the path.
