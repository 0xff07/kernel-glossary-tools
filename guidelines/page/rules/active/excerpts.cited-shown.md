---
qa: auto
---

# Cited shown

Prose explaining behavior at a site shows that source beside itself, including when the explanation reaches across files. A paragraph linking two or more files whose cited sites no excerpt reproduces is a file jump and fails unless it is a census. Use as many locally introduced and explained excerpts as the explanation needs; cut a reach the subject does not drive.

A census states the total, by number or the claim's quantifier, and lists members with no more than a label between them. Four or more members of one set use a table with each construct linked, except the steps of one operation or a member-by-member walk beside its supporting excerpt. A total followed by what each member does is an explanation and requires the code.

Table rows are lookups and are not counted as a file-jump paragraph.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. A producer and its consumer explained apart. **Before:**

```
The predicate that reads the pointer is where the two lanes part, and
tb_port_has_remote() is that predicate.

tb_port_has_remote() answers false for three cases before it answers
true, and the third is the lane rule, under which an adapter that has a
dual_link_port and a non-zero link_nr is the secondary lane and is
treated as having nothing behind it.
```

**After:**

```
The peer pointer and the traversal decision describe different properties
of a lane adapter. tb_port_has_remote() checks the adapter's direction
and peer presence before applying its secondary-lane condition.

    /* drivers/thunderbolt/tb.h:620 */
    static inline bool tb_port_has_remote(const struct tb_port *port)
    {
    	if (tb_is_upstream_port(port))
    		return false;
    	if (!port->remote)
    		return false;
    	if (port->dual_link_port && port->link_nr)
    		return false;

    	return true;
    }

tb_port_has_remote() rejects the secondary adapter when
port->dual_link_port is set and port->link_nr is nonzero. The peer
pointer remains populated on the adapter this condition excludes. The
upstream guard also applies to primary adapters.
```
