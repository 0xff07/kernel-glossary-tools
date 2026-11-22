# The standard

Two directories, two contracts.

`page/` says what a finished page is: the page model, the template and every rule, with the figure patterns the rules point to and the register examples the `registers.*` rules carry. Every sentence here can be checked against one page and the kernel tree it documents. Nothing here says who writes a page, in what order, or with what notes; a page produced by any process is judged by this directory alone.

`campaign/` says what a campaign plan is: the format of `campaigns/<campaign>.md`, how a plan is validated and indexed, what a plan must settle before pages are written, and how what a run learns is folded back into it. Every sentence here can be checked against one plan file. It may refer to `page/`; `page/` never refers to it.

`subsystems.md` is the one file both read: the output directory, the kernel paths, the specification names and the section-six heading of each subsystem.
