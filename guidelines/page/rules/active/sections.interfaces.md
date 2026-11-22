---
qa: off
---

# Interfaces

On a page whose section six is INTERFACES, the section is the subject's contract with the code and the people outside it: the surfaces through which other code reaches the subject and the knobs through which a reader observes or steers it, so that a caller, a driver author or a debugger finds what they must know in one place without reading DETAILS.

Section six carries no table and no excerpt, whichever heading it has. Its form is lists by use, under a short paragraph naming what the subject exposes: each class below that applies has a list of its own under a label, a line of its own that names the class and ends in a colon, as `Entry points:` does, and each item is one surface, the symbol linked to its definition line and the contract stated in one or two sentences.

A section whose items all belong to one class is one list with no label.

The section holds, in this order, the classes that apply and an explicit negative for a class the subject lacks, the negative an item under that class's label or a sentence of the paragraph above the lists:

1. Entry points, under `Entry points:`: every function the subject offers its callers, exported symbols and inline helpers alike, and every operation a driver implements or hook the core calls through an ops table or a notifier; for each, who may call it (an export, its namespace or `GPL` status, or a static reached only through the subject), the context it runs in and the locks it takes or expects held, and what it returns.
2. Inputs read from callers, under `Inputs read from callers:`: the attribute words, flags, parameters and CONFIG options that change what the entry points do, each linked, with the effect named; a bit layout among them is a figure, drawn where the trigger table asks for one, never a table.
3. User-visible surfaces the subject itself creates or reads, under `User-visible surfaces:`: sysfs and debugfs files with their modes and what they print, ioctls, boot parameters, each linked to the code that creates or parses it.
4. The observability lists the page owes for its flows, the tracepoints that can fire, where messages print, the asynchronous or deferred hand-offs and the debugging surfaces, when the page keeps them here rather than in a DETAILS subsection, each under a label of its own, `Tracepoints:`, `Debug and diagnostic messages:`, `Asynchronous and deferred hand-offs:` and `Debugging surfaces:`; a class the flow lacks is named as absent.
5. The scripts and tools the tree carries for the subject, under `Scripts and tools:`, when the page keeps its observability lists here: each file linked, with what it does with the subject in one sentence.

A subject that exposes nothing beyond what DETAILS walks states that in one sentence and names the one function or file through which it is reached. REGISTERS, METHODS and PRIMITIVES keep their own rules.
