---
qa: off
---

# Openers

The lead and the first paragraph of every H2 section establish what the mechanism is for and the conditions under which its result holds before introducing unfamiliar implementing symbols. A DETAILS subsection starts from the object, state or problem the reader has reached and establishes the relationship it will explain next. It may carry forward the previous result rather than repeat the purpose of the whole mechanism.

A familiar symbol may lead when its role is already clear; an unfamiliar identifier or a count alone gives no orientation.

Read the openers in sequence for what the reader knows at each point and why the next explanation is needed. The test of deleting a number from a first sentence helps locate a count-led opener: what remains should still establish a purpose, state or relationship. Do not fill the opening with implementation conditions that only the following source makes intelligible.

An illustration from the original guidance, in plain text so that nothing in it goes stale: it shows content, not page formatting, and on a page every symbol is linked. An opening that names the helper before the result. **Before:**

```
Turning the lane back on is the first step of bonding it, and the enable
has to be followed by a wait, because a lane whose Lane Disable bit was
just cleared has not trained yet. tb_xdomain_lane_bonding_enable() does
the two in order before it touches the bonding bit.
```

**After:**

```
The XDomain bonding path checks that the secondary lane has come up after
enabling it. tb_xdomain_lane_bonding_enable() calls tb_wait_for_port() on
the secondary adapter after tb_port_enable() succeeds.
```
