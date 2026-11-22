---
qa: manual
---

# Observability

For the flows it documents, a page lists what makes them observable:

- the tracepoints that can fire,
- where debug and diagnostic messages print (the `pr_fmt` and `dev_dbg` families and the dynamic-debug sites),
- the asynchronous or deferred hand-offs the flow crosses (work items, timers, threads, RCU, notifier chains) and
- the debugging surfaces that expose its state (sysfs, debugfs, boot parameters),

each as an explicit list with its sites cited or as an explicit negative; a class absent from the flow is named as absent, never left out.
