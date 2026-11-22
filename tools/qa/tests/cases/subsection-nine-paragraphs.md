# Nine paragraphs

## DETAILS

### The allocator carries a resource through validation

The firmware assigns an address range to the device. The kernel reads that assignment during discovery.

The device records the range as a resource. The record retains its start and end addresses.

The bus supplies the parent window. That window defines where the resource can fit.

The allocator compares the resource with the window. Both ends must lie inside it.

The allocator also checks the occupied ranges. A resource cannot overlap an existing allocation.

An accepted resource remains attached to the device. The allocator records its position in the parent.

A rejected assignment needs another allocation pass. The device keeps the request for that pass.

The next pass searches the remaining free space. It chooses a range that satisfies the request.

The allocator attaches the replacement range to the device. The resource now describes the accepted assignment.

<!-- kg:expect
only:
- arrangement.subsection-size
findings: []
-->
