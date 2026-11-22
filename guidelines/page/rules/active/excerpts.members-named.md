---
qa: manual
---

# Members named

Beside a definition, every member shown is explained, what it holds and which path writes or reads it; a run the source's own comment groups, a run the page's subject never reaches, or the neighbours shown around the member a paragraph is about, may take one phrase naming them and what they hold, which is how a long definition is read along rather than explained line by line.

A table above the fence naming each shown member with its purpose serves as that explanation, and the paragraph after it then says only what the table leaves out. A definition read in pieces is explained piece by piece: the paragraph before a piece says what its run of members is for, and the paragraph after it explains the members shown.

How many members there are or where the struct sits is shape, and shape is not explanation.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. The paragraph beside a struct excerpt. **Before:**

```
One struct xhci_port exists per hardware port for the lifetime of the
host controller's memory setup. The first five fields are what the
construction pass writes, and everything after them belongs to paths
that run once the root hubs are live.
```

**After:**

```
port_reg is the port's register quad in MMIO, and every PORTSC read or
write on this page goes through it. hw_portnum is the port's index in
the flat hw_ports array, the numbering a Port Status Change Event
carries minus one, which is how handle_port_status finds the port.
hcd_portnum is its index inside the root hub that claimed it ...
```
