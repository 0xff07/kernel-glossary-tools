# Comma-joined sentence

## DETAILS

### The allocator preserves each resource through its passes

The controller records the resources that the firmware already assigned, The kernel checks those resources against the available parent windows, The allocator keeps each accepted range attached to its device, The rejected range remains available for a later allocation pass, The next pass selects a window that contains the request, The device can then use the address that this pass assigned.

<!-- kg:expect
only:
- arrangement.paragraphs
findings:
- - arrangement.paragraphs
  - review
  - 7
  - The controller records the resources that the firmware already assigned, The kernel checks those resources against the available parent windows, The allocator keeps each accepted range attached to its device, The rejected range remains available for a later allocation pass, The next pass selects a window that contains the request, The device can then use the address that this pass assigned.
-->
