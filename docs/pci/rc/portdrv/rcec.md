# Root Complex Event Collector association

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

An endpoint integrated into the Root Complex has no Root Port above it, so a Root Complex Event Collector collects the error and PME messages it sends. The kernel needs to know which endpoints report to which collector, since the services handling such a message search for its sender behind the port that received it. A collector describes its endpoints in a capability, which the PCI core caches in a [`struct rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L875) when its scan finds the collector. When the PCIe port driver binds the collector, it points the [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) of each associated endpoint back at it. This page follows the association on x86 with ACPI, from the capability read through the link and the walks of the error and PME services to its release.

```text
    One RCEC, the association it caches and the RCiEPs linked to it
    ───────────────────────────────────────────────────────────────

    ┌──────────────────────────────┐   rcec_ea    ┌────────────────────────────────────┐
    │ struct pci_dev: the RCEC     ├─────────────▶│ struct rcec_ea                     │
    │ type PCI_EXP_TYPE_RC_EC      │              │ bitmap    one bit per device       │
    │ on bus N, bound by pcieport  │              │           number on bus N          │
    └──────────────────────────────┘              │ nextbusn  first and last bus of    │
           ▲                ▲                     │ lastbusn  the associated range     │
           │                │                     └────────────────────────────────────┘
           │ rcec           │ rcec
           │                │
    ┌──────┴───────┐ ┌──────┴───────┐ ┌──────────────┐ ┌──────────────┐
    │ RCiEP        │ │ RCiEP        │ │ RCiEP        │ │ RCiEP        │
    │ bus N, its   │ │ bus inside   │ │ bus N, its   │ │ bus outside  │
    │ device's bit │ │ nextbusn to  │ │ device's bit │ │ the range    │
    │ set          │ │ lastbusn     │ │ clear        │ │              │
    └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
      rcec: RCEC       rcec: RCEC       rcec NULL        rcec NULL

    each RCiEP is a struct pci_dev of type PCI_EXP_TYPE_RC_END
```

## SUMMARY

The model is two kinds of [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), told apart by their Device/Port Type, and one [`struct rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L875) per collector that caches which endpoints the collector answers for. The table settles which kernel object stands for each term of the specification, and the rest of the page uses the names it settles, RCEC and RCiEP among them.

| Term in the specification | Kernel representation | Where this page writes or reads it |
|---|---|---|
| Root Complex Event Collector, the RCEC | a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) for which [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) returns [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494), bound by the PCIe port driver | the port driver's probe and the PME and AER services |
| Root Complex Integrated Endpoint, the RCiEP | a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) for which [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) returns [`PCI_EXP_TYPE_RC_END`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L493) | [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41), [`walk_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L56) and [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) |
| RCEC Endpoint Association Extended Capability | the capability with ID [`PCI_EXT_CAP_ID_RCEC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L732), at the offset [`pci_find_ext_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540) returns | read by [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) |
| Association Bitmap for RCiEPs | [`bitmap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L878), read at [`PCI_RCEC_RCIEP_BITMAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L884) | written by [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149), read by [`rcec_assoc_rciep()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L24) |
| Associated Bus Numbers, Next Bus and Last Bus | [`nextbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L876) and [`lastbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L877), read at [`PCI_RCEC_BUSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L885) | written by [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149), read by [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) |
| the association of an RCiEP with its RCEC | the RCiEP's [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375), and on the RCEC's side its [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) | written by [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41) and [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) |

The scan fills the cache through [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149), the port driver's probe of the RCEC turns it into one [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) per associated RCiEP through [`pcie_link_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L110), and the AER and PME services enumerate the same RCiEPs through [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134). Both walks stay within the RCEC's own bus and its cached bus range, and the bitmap decides on the RCEC's own bus alone.

## SPECIFICATIONS

- PCI Express Base Specification, revision 5.0, section 7.9.10, cited by commit [90655631988f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=90655631988f8f501529e6de5f13614389717ead) ("PCI/ERR: Cache RCEC EA Capability offset in pci_init_capabilities()") for the RCEC Endpoint Association Extended Capability it decodes
- PCI Express Base Specification, revision 5.0, section 7.9.10.2: Association Bitmap for RCiEPs, cited by commit [d9b7eae8e342](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=d9b7eae8e3424c3480fe9f40ebafbb0c96426e4c) ("PCI/RCEC: Fix RCiEP device to RCEC association")
- PCI Express Base Specification, revision 5.0-1, section 7.9.10.3, cited by the comment at [`rcec.c:91`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L91) for a bus number that indicates no association

The specification defines the capability, its registers and the two Device/Port Types. The cached copy, the link and the walks over it are the kernel's own construction, which this page describes from [`rcec.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c), [`portdrv.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c), [`pme.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c) and [`aer.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c) at v7.2.

## COVERAGE

### Device/Port Type values and their accessors (include/uapi/linux/pci_regs.h, include/linux/pci.h, include/uapi/linux/pci.h)

- [`'PCI_EXP_TYPE_RC_END'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L493): the Device/Port Type of a Root Complex Integrated Endpoint
- [`'PCI_EXP_TYPE_RC_EC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494): the Device/Port Type of a Root Complex Event Collector
- [`'\<pcie_caps_reg\>':'include/linux/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2669): returns the cached PCI Express Capabilities register of a function
- [`'\<pci_pcie_type\>':'include/linux/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678): decodes the Device/Port Type from the cached register
- [`'PCI_SLOT'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L32): extracts the device number from a devfn

### RCEC Endpoint Association registers, include/uapi/linux/pci_regs.h

- [`'PCI_EXT_CAP_VER'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L723): extracts the Capability Version from an extended capability header
- [`'PCI_EXT_CAP_ID_RCEC'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L732): the ID of the RCEC Endpoint Association Extended Capability
- [`'PCI_RCEC_RCIEP_BITMAP'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L884): the offset of the Association Bitmap for RCiEPs in the capability
- [`'PCI_RCEC_BUSN'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L885): the offset of the Associated Bus Numbers register in the capability
- [`'PCI_RCEC_BUSN_REG_VER'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L886): the least Capability Version with the Associated Bus Numbers register
- [`'PCI_RCEC_BUSN_NEXT'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L887): extracts Next Bus from the Associated Bus Numbers register
- [`'PCI_RCEC_BUSN_LAST'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L888): extracts Last Bus from the Associated Bus Numbers register

### Capability lookup and configuration reads (drivers/pci/pci.c, drivers/pci/access.c)

- [`'\<pci_find_ext_capability\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540): returns the offset of an extended capability by its ID
- [`'\<pci_read_config_dword\>':'drivers/pci/access.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L580): reads a dword of the configuration space of a function

### The cached association (drivers/pci/pci.h, drivers/pci/pcie/rcec.c)

- [`'\<struct rcec_ea\>':'drivers/pci/pci.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L875): the cached Association Bitmap and bus range of an RCEC
- [`'\<pci_rcec_init\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149): reads the association capability of an RCEC into a new cache during the scan
- [`'\<pci_rcec_exit\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L186): frees the cache of a function when the function is released

### Linking and walking the associated RCiEPs (drivers/pci/pcie/rcec.c)

- [`'\<struct walk_rcec_data\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L18): the RCEC and the callback one walk over its association carries
- [`'\<pcie_link_rcec\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L110): points every associated RCiEP at its RCEC
- [`'\<walk_rcec\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68): walks the RCEC's own bus and the buses of its cached range
- [`'\<rcec_assoc_rciep\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L24): tests whether an RCiEP the walk found is associated with the RCEC
- [`'\<link_rcec_helper\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41): stores the RCEC in an associated RCiEP during the link
- [`'\<pcie_walk_rcec\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134): calls a service's callback on every RCiEP associated with an RCEC
- [`'\<walk_rcec_helper\>':'drivers/pci/pcie/rcec.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L56): calls the service's callback on an associated RCiEP the walk found

### Bus walks and lookups (drivers/pci/bus.c, drivers/pci/search.c)

- [`'\<pci_walk_bus\>':'drivers/pci/bus.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461): calls a callback on every function on a bus and below it under the bus-list semaphore
- [`'\<__pci_walk_bus\>':'drivers/pci/bus.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408): the recursion of the bus walk over a bus and the subordinate buses of its bridges
- [`'\<pci_find_bus\>':'drivers/pci/search.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L143): returns the bus with a given number in a given domain
## DOCUMENTATION

- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the AER driver's guide, which states that the driver attaches to Root Ports and RCECs with the AER capability
- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver and the services it registers on a port
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the `pcie_ports=` parameter, whose compat value disables the native port services
- [`Documentation/admin-guide/dynamic-debug-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/dynamic-debug-howto.rst): the control file and boot parameter that enable a debug callsite such as the one the link prints

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/ERR: Cache RCEC EA Capability offset in pci_init_capabilities() (commit 90655631988f)](https://lore.kernel.org/r/20201121001036.8560-4-sean.v.kelley@intel.com)
- [PCI/ERR: Add pcie_link_rcec() to associate RCiEPs (commit 507b460f8144)](https://lore.kernel.org/r/20201121001036.8560-12-sean.v.kelley@intel.com)
- [PCI/ERR: Recover from RCiEP AER errors (commit 579086225502)](https://lore.kernel.org/r/20201121001036.8560-13-sean.v.kelley@intel.com)
- [PCI/AER: Add pcie_walk_rcec() to RCEC AER handling (commit af113553d961)](https://lore.kernel.org/r/20201121001036.8560-14-sean.v.kelley@intel.com)
- [PCI/PME: Add pcie_walk_rcec() to RCEC PME handling (commit 9a2f604f4497)](https://lore.kernel.org/r/20201121001036.8560-15-sean.v.kelley@intel.com)
- [PCI/RCEC: Fix RCiEP device to RCEC association (commit d9b7eae8e342)](https://lore.kernel.org/r/20210222011717.43266-1-qiuxu.zhuo@intel.com)
- [PCI/AER: Clear stale errors on reporting agents upon probe (commit e242d09b58e8)](https://patch.msgid.link/3011c2ed30c11f858e35e29939add754adea7478.1769332702.git.lukas@wunner.de)

## REGISTERS

The paths on this page read one capability of the RCEC and one field of the PCI Express Capabilities register of every function they test. Each drawing names the macro and the cached member behind a field, and the paragraph above it says what the field decides here.

The RCEC Endpoint Association capability starts at the offset [`pci_find_ext_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540) returns for [`PCI_EXT_CAP_ID_RCEC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L732). [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) reads its header for the Capability Version, which decides whether the dword at [`PCI_RCEC_BUSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L885) exists, and copies the Association Bitmap at [`PCI_RCEC_RCIEP_BITMAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L884) into [`bitmap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L878) and the two bus numbers into [`nextbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L876) and [`lastbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L877). The bitmap decides which device numbers on the RCEC's own bus are associated, and the two bus numbers bound the other buses the walks visit.

```text
    RCEC Endpoint Association capability, three dwords from the capability offset
    ─────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x0  │          next         │  ver  │               ID              │
          │        (31:20)        │(19:16)│             (15:0)            │
          ├───────────────────────┴───────┴───────────────────────────────┤
    +0x4  │                             bitmap                            │
          │                             (31:0)                            │
          ├───────────────┬───────────────┬───────────────┬───────────────┤
    +0x8  │       ·       │    last bus   │    next bus   │       ·       │
          │    (31:24)    │    (23:16)    │     (15:8)    │     (7:0)     │
          └───────────────┴───────────────┴───────────────┴───────────────┘

    ID       = PCI_EXT_CAP_ID(header) (capability ID, PCI_EXT_CAP_ID_RCEC = 0x07 for this capability)
    ver      = PCI_EXT_CAP_VER(header) (Capability Version; the +0x8 dword exists from PCI_RCEC_BUSN_REG_VER = 0x02)
    next     = PCI_EXT_CAP_NEXT(header) (offset of the next extended capability, bits 21:20 masked)
    bitmap   = PCI_RCEC_RCIEP_BITMAP (+0x4, Association Bitmap for RCiEPs, cached in rcec_ea.bitmap)
    next bus = PCI_RCEC_BUSN_NEXT(busn) (bits 15:8 of PCI_RCEC_BUSN at +0x8, cached in rcec_ea.nextbusn)
    last bus = PCI_RCEC_BUSN_LAST(busn) (bits 23:16 of PCI_RCEC_BUSN, cached in rcec_ea.lastbusn)
    ·        = bits 31:24 and 7:0 of the +0x8 dword, which pci_regs.h does not name
```

The Device/Port Type field of the PCI Express Capabilities register, [`PCI_EXP_FLAGS_TYPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L485), decides whether a function is an RCEC or an RCiEP. [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) decodes it from the copy in [`pcie_flags_reg`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L385). The walks keep a function when the result is [`PCI_EXP_TYPE_RC_END`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L493), and the port driver and its services recognise an RCEC by [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494).

```text
    PCI Express Capabilities register, the word at PCI_EXP_FLAGS (0x02) of the PCIe capability
    ──────────────────────────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x02  │F│·│   IRQ   │S│  type │  vers │
          │ │ │  (13:9) │ │ (7:4) │ (3:0) │
          └─┴─┴─────────┴─┴───────┴───────┘

    type = PCI_EXP_FLAGS_TYPE (0x00f0, Device/Port Type, decoded by pci_pcie_type()):
           PCI_EXP_TYPE_RC_END (0x9) for an RCiEP, PCI_EXP_TYPE_RC_EC (0xa) for an RCEC
    vers = PCI_EXP_FLAGS_VERS (0x000f, Capability Version)
    S    = PCI_EXP_FLAGS_SLOT (0x0100, Slot Implemented)
    IRQ  = PCI_EXP_FLAGS_IRQ (0x3e00, Interrupt Message Number)
    F    = PCI_EXP_FLAGS_FLIT (0x8000, Flit Mode Supported)
    ·    = bit 14, which pci_regs.h does not name
    the word is cached whole in pci_dev.pcie_flags_reg, which pcie_caps_reg() returns
```

The other fields of the register play no part on these paths.

## DETAILS

DETAILS first settles the two Device/Port Types and why the port driver serves an RCEC like a Root Port. It then reads the association capability and follows [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) as it caches the capability during the scan. The link comes next, from the port driver's probe through the order the scan and the driver keep, the buses [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) visits and the tests that decide each RCiEP. The services' walk follows, with the PME and AER uses at probe, the search for an error's sender and the reset of an RCiEP. The last subsections free the cache at release and list the messages, hand-offs and files that expose the association.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at the v7.2 tag, on x86-64 with ACPI firmware, with the PCIe port, AER and dynamic-debug options of this documentation set on top of it. The table lists the options the prose names.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds [`rcec.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c) into the port driver and gives [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) the members [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) and [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375); unset, the four entry points are empty stubs |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | lets the port driver give an RCEC the AER service, whose probe, source search and reset use the association |
| [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) | y, following [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) and [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | builds the PME service, which marks the associated RCiEPs as able to wake the system |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | one of the two options [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) follows |
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | the ACPI host bridge driver scans a hierarchy before the drivers on it start |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | n | would build the error injector, the second reader of an RCiEP's [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the debug line of the link a callsite that can be enabled at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would compile drivers/pci with -DDEBUG and print that line unconditionally |

The table indexes the prose. Each subsection below names the option at the point where its effect applies.

### Two Device/Port Types name the collector and its endpoints

The decisions on this page start from a function's Device/Port Type, since the kernel tells an RCEC and an RCiEP from the other functions by that field. [`PCI_EXP_FLAGS_TYPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L485) masks the field in the PCI Express Capabilities register, and the values under it, [`PCI_EXP_TYPE_RC_END`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L493) and [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494) among them, are the constants the tests below compare with:

```c
/* include/uapi/linux/pci_regs.h:485 */
#define  PCI_EXP_FLAGS_TYPE	0x00f0	/* Device/Port type */
#define   PCI_EXP_TYPE_ENDPOINT	   0x0	/* Express Endpoint */
#define   PCI_EXP_TYPE_LEG_END	   0x1	/* Legacy Endpoint */
#define   PCI_EXP_TYPE_ROOT_PORT   0x4	/* Root Port */
#define   PCI_EXP_TYPE_UPSTREAM	   0x5	/* Upstream Port */
#define   PCI_EXP_TYPE_DOWNSTREAM  0x6	/* Downstream Port */
#define   PCI_EXP_TYPE_PCI_BRIDGE  0x7	/* PCIe to PCI/PCI-X Bridge */
#define   PCI_EXP_TYPE_PCIE_BRIDGE 0x8	/* PCI/PCI-X to PCIe Bridge */
#define   PCI_EXP_TYPE_RC_END	   0x9	/* Root Complex Integrated Endpoint */
#define   PCI_EXP_TYPE_RC_EC	   0xa	/* Root Complex Event Collector */
```

An RCiEP reports 0x9 and an RCEC 0xa. The code on this page also compares the type with [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488), 0x4, where a service treats an RCEC the way it treats a Root Port.

The tests read the type through two accessors that work on a copy of the register. [`pcie_caps_reg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2669) returns that copy, the [`pcie_flags_reg`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L385) member of the function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352):

```c
/* include/linux/pci.h:2665 */
/**
 * pcie_caps_reg - get the PCIe Capabilities Register
 * @dev: PCI device
 */
static inline u16 pcie_caps_reg(const struct pci_dev *dev)
{
	return dev->pcie_flags_reg;
}
```

The accessor returns a member of the object, so it costs no configuration read. [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) decodes the type from that member:

```c
/* include/linux/pci.h:2674 */
/**
 * pci_pcie_type - get the PCIe device/port type
 * @dev: PCI device
 */
static inline int pci_pcie_type(const struct pci_dev *dev)
{
	return (pcie_caps_reg(dev) & PCI_EXP_FLAGS_TYPE) >> 4;
}
```

The type is the cached word masked with [`PCI_EXP_FLAGS_TYPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L485) and shifted right by four. A test of an RCEC or an RCiEP therefore reads memory, and the walks below apply it to the functions they visit without reading configuration space.

### The port driver serves an RCEC like a Root Port

An RCEC receives error and PME messages the way a Root Port does, so the kernel hands both to the same consumers, the AER and PME services of the PCIe port driver. Each service is a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), the port driver's service instance on a port, which stands for a service and for no PCIe function. The driver's ID table, [`port_pci_ids`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L775), brings an RCEC to the port driver in the first place:

```c
/* drivers/pci/pcie/portdrv.c:775 */
static const struct pci_device_id port_pci_ids[] = {
	/* handle any PCI-Express port */
	{ PCI_DEVICE_CLASS(PCI_CLASS_BRIDGE_PCI_NORMAL, ~0) },
	/* subtractive decode PCI-to-PCI bridge, class type is 060401h */
	{ PCI_DEVICE_CLASS(PCI_CLASS_BRIDGE_PCI_SUBTRACTIVE, ~0) },
	/* handle any Root Complex Event Collector */
	{ PCI_DEVICE_CLASS(((PCI_CLASS_SYSTEM_RCEC << 8) | 0x00), ~0) },
	{ },
};
```

The first two entries match the PCI-to-PCI bridge classes that the comments attribute to ports, and the third matches the event-collector class with programming interface 0x00. The port driver therefore probes an RCEC beside the ports, and the services it gets are chosen by [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218), the port driver's survey of a port. The lines shown grant the AER and the PME service to a Root Port and an RCEC under the same conditions:

```c
/* drivers/pci/pcie/portdrv.c:218 */
static int get_port_device_capability(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	int services = 0;
... /* 17 lines, to :239 */
#ifdef CONFIG_PCIEAER
	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT ||
             pci_pcie_type(dev) == PCI_EXP_TYPE_RC_EC) &&
	    dev->aer_cap && pci_aer_available() &&
	    (pcie_ports_native || host->native_aer))
		services |= PCIE_PORT_SERVICE_AER;
#endif

	/* Root Ports and Root Complex Event Collectors may generate PMEs */
	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT ||
	     pci_pcie_type(dev) == PCI_EXP_TYPE_RC_EC) &&
	    (pcie_ports_native || host->native_pme)) {
		services |= PCIE_PORT_SERVICE_PME;

		/*
		 * Disable PME interrupt on this port in case it's been enabled
		 * by the BIOS (the PME service driver will enable it when
		 * necessary).
		 */
		pcie_pme_interrupt_enable(dev, false);
	}
```

The AER service needs [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), an AER capability at [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), AER support in the running kernel and native control of AER, which the host bridge's [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) or the flag [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) grants. The PME service needs native PME control the same way, through [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) or the same flag. A kernel built without [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) compiles the AER test out and gives an RCEC the PME service alone.

The two kinds of port that receive these services reach the functions they answer for in different ways, as the drawing sets side by side.

```text
    What the error and PME services reach from a Root Port and from an RCEC
    ───────────────────────────────────────────────────────────────────────

               ┌─────────────┐            ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    bus N      │ Root Port   │            │ RCEC        │   │ RCiEP       │   │ RCiEP       │
    (root)     │ ROOT_PORT   │            │ RC_EC       │   │ RC_END      │   │ RC_END      │
               └──────┬──────┘            └─────────────┘   └─────────────┘   └─────────────┘
                      │ subordinate
                      │
               ┌──────┴──────┐            no subordinate bus:
    bus N+1    │ Endpoint    │            nothing in the tree
               │ ENDPOINT    │            leads from the RCEC
               └─────────────┘            to an RCiEP

               ├─────────────┤
               reached through
               the tree below
               the Root Port                                                  ┌─────────────┐
    bus M                                                                     │ RCiEP       │
                                                                              │ RC_END      │
                                                                              └─────────────┘
                                          ├──────────────────────────────────────────────────┤
                                          reached through the association the RCEC caches
```

A Root Port answers for the tree below its [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus, so a service finds the reporting functions by walking down from the port. For an RCEC the services walk the association its capability describes, which the next subsections read, cache and walk.

### The association capability holds a bitmap and a bus range

An RCEC describes its RCiEPs itself, in an extended capability of its configuration space, so the kernel needs the capability's ID, the layout of its header and the offsets of its two registers. The header macros [`PCI_EXT_CAP_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L722), [`PCI_EXT_CAP_VER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L723) and [`PCI_EXT_CAP_NEXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L724) split a header dword into ID, version and next offset, and the IDs that follow run from AER, 0x01, to the RCEC's own [`PCI_EXT_CAP_ID_RCEC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L732), 0x07:

```c
/* include/uapi/linux/pci_regs.h:722 */
#define PCI_EXT_CAP_ID(header)		(header & 0x0000ffff)
#define PCI_EXT_CAP_VER(header)		((header >> 16) & 0xf)
#define PCI_EXT_CAP_NEXT(header)	((header >> 20) & 0xffc)

#define PCI_EXT_CAP_ID_ERR	0x01	/* Advanced Error Reporting */
#define PCI_EXT_CAP_ID_VC	0x02	/* Virtual Channel Capability */
#define PCI_EXT_CAP_ID_DSN	0x03	/* Device Serial Number */
#define PCI_EXT_CAP_ID_PWR	0x04	/* Power Budgeting */
#define PCI_EXT_CAP_ID_RCLD	0x05	/* Root Complex Link Declaration */
#define PCI_EXT_CAP_ID_RCILC	0x06	/* Root Complex Internal Link Control */
#define PCI_EXT_CAP_ID_RCEC	0x07	/* Root Complex Event Collector */
```

[`PCI_EXT_CAP_ID_RCEC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L732) is the ID the lookup matches, and [`PCI_EXT_CAP_VER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L723) extracts bits 19:16 of the header, the version that decides whether the capability has its bus-number register.

The two registers behind the header are named by the macros under the comment for the Endpoint Association, [`PCI_RCEC_RCIEP_BITMAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L884) and [`PCI_RCEC_BUSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L885), together with the version that brings the second register and its two field extractors:

```c
/* include/uapi/linux/pci_regs.h:883 */
/* Root Complex Event Collector Endpoint Association  */
#define PCI_RCEC_RCIEP_BITMAP	4	/* Associated Bitmap for RCiEPs */
#define PCI_RCEC_BUSN		8	/* RCEC Associated Bus Numbers */
#define  PCI_RCEC_BUSN_REG_VER	0x02	/* Least version with BUSN present */
#define  PCI_RCEC_BUSN_NEXT(x)	(((x) >> 8) & 0xff)
#define  PCI_RCEC_BUSN_LAST(x)	(((x) >> 16) & 0xff)
```

[`PCI_RCEC_RCIEP_BITMAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L884) is the Association Bitmap at offset 4 from the capability, a dword with one bit per device number on the RCEC's own bus. [`PCI_RCEC_BUSN`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L885) at offset 8 holds Next Bus in bits 15:8 and Last Bus in bits 23:16, which [`PCI_RCEC_BUSN_NEXT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L887) and [`PCI_RCEC_BUSN_LAST`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L888) extract. [`PCI_RCEC_BUSN_REG_VER`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L886) says that a capability has that dword from version 2 on.

The offset of the capability comes from [`pci_find_ext_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L540), the PCI core's lookup of an extended capability by its ID:

```c
/* drivers/pci/pci.c:526 */
/**
 * pci_find_ext_capability - Find an extended capability
 * @dev: PCI device to query
 * @cap: capability code
 *
 * Returns the address of the requested extended capability structure
 * within the device's PCI configuration space or 0 if the device does
 * not support it.  Possible values for @cap include:
 *
 *  %PCI_EXT_CAP_ID_ERR		Advanced Error Reporting
 *  %PCI_EXT_CAP_ID_VC		Virtual Channel
 *  %PCI_EXT_CAP_ID_DSN		Device Serial Number
 *  %PCI_EXT_CAP_ID_PWR		Power Budgeting
 */
u16 pci_find_ext_capability(struct pci_dev *dev, int cap)
{
	return pci_find_next_ext_capability(dev, 0, cap);
}
EXPORT_SYMBOL_GPL(pci_find_ext_capability);
```

According to its comment, the lookup returns the offset of the capability in the function's configuration space, or 0 when the function has none. The body passes 0 as the starting point to the variant of the lookup that takes one.

The kernel keeps what the two registers say in [`struct rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L875), a cache the RCEC's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) points at, so that the walks read memory and leave the RCEC's configuration space alone. The definition stands under [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), like the code that uses it:

```c
/* drivers/pci/pci.h:873 */
#ifdef CONFIG_PCIEPORTBUS
/* Cached RCEC Endpoint Association */
struct rcec_ea {
	u8		nextbusn;
	u8		lastbusn;
	u32		bitmap;
};
#endif
```

[`bitmap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L878) holds the Association Bitmap dword as read. [`nextbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L876) and [`lastbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L877) are the first and the last bus number of the associated range, a byte each like any bus number. [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) is their writer at v7.2, and the walks read them.

The file that holds the code of this page is linked into the port driver's object, which [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) builds, as the start of [`Makefile`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Makefile) shows:

```c
/* drivers/pci/pcie/Makefile:5 */
pcieportdrv-y			:= portdrv.o rcec.o

obj-$(CONFIG_PCIEPORTBUS)	+= pcieportdrv.o bwctrl.o
```

A kernel without [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) has no rcec.c and no RCEC members in [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). Its callers then compile against the empty inline stubs at [`drivers/pci/pci.h:904-911`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L904), in the block of the header that declares the four entry points:

```c
/* drivers/pci/pci.h:897 */
#ifdef CONFIG_PCIEPORTBUS
void pci_rcec_init(struct pci_dev *dev);
void pci_rcec_exit(struct pci_dev *dev);
void pcie_link_rcec(struct pci_dev *rcec);
void pcie_walk_rcec(struct pci_dev *rcec,
		    int (*cb)(struct pci_dev *, void *),
		    void *userdata);
#else
static inline void pci_rcec_init(struct pci_dev *dev) { }
static inline void pci_rcec_exit(struct pci_dev *dev) { }
static inline void pcie_link_rcec(struct pci_dev *rcec) { }
static inline void pcie_walk_rcec(struct pci_dev *rcec,
				  int (*cb)(struct pci_dev *, void *),
				  void *userdata) { }
#endif
```

The stubs keep the callers in the scan, the release and the services free of conditional compilation. The drawing maps the capability's three dwords onto the members of the cache they fill.

```text
    Three dwords of the association capability feed struct rcec_ea
    ──────────────────────────────────────────────────────────────

    capability + 0x0              capability + 0x4              capability + 0x8
    ┌────────────────────────┐    ┌────────────────────────┐    ┌────────────────────────┐
    │ header                 │    │ Association Bitmap     │    │ Associated Bus Numbers │
    │ version (19:16)        │    │ bit n: device n, bus N │    │ Next 15:8, Last 23:16  │
    └────────────┬───────────┘    └────────────┬───────────┘    └────────────┬───────────┘
                 │ version 2 or more:          │ copied whole                │ read only when
                 │ read + 0x8                  │                             │ the version allows
                 └─────────────────────────────┼─────────────────────────────┘
                                               │ filled at the scan of the RCEC
                                               ▼
                              ┌──────────────────────────────────┐
                              │ struct rcec_ea                   │
                              │ bitmap    the + 0x4 dword        │
                              │ nextbusn  Next Bus, or 0xff      │
                              │ lastbusn  Last Bus, or 0x00      │
                              └──────────────────────────────────┘
                              version 1: 0xff and 0x00 stand for no bus range

    capability: the offset of the extended capability with ID 0x07 in the RCEC
    each box above is one dword read from the configuration space of the RCEC
```

The header feeds a decision and no member, the bitmap dword is copied as read, and the bus-number dword is split into two bytes. A version 1 capability has no bus-number dword, and the cache then holds 0xff in [`nextbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L876) and 0x00 in [`lastbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L877), a pair the walk tests for before it visits a range.

### pci_rcec_init caches the association when the scan meets an RCEC

The cache is filled once per RCEC, while the scan sets up a function it has just found. [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726) is that setup. It installs the release callback that later frees the cache, and it initializes the function's capabilities before it puts the function on its bus's [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list:

```c
/* drivers/pci/probe.c:2726 */
void pci_device_add(struct pci_dev *dev, struct pci_bus *bus)
{
	int ret;

	pci_configure_device(dev);

	device_initialize(&dev->dev);
	dev->dev.release = pci_release_dev;
	... /* 16 lines, to :2750 */
	pci_init_capabilities(dev);

	/*
	 * Add the device to our list of discovered devices
	 * and the bus list for fixup functions, etc.
	 */
	down_write(&pci_bus_sem);
	list_add_tail(&dev->bus_list, &bus->devices);
	up_write(&pci_bus_sem);
```

Capability setup runs at [`probe.c:2750`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2750), before the function joins the list under the write side of [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) at [`probe.c:2756-2758`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2756), so the cache of an RCEC exists before a walk of its bus can find the RCEC. The release callback installed at [`probe.c:2733`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2733) is the path that ends the cache. [`pci_init_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2650) calls the initializer of each capability the core handles, the association's among them:

```c
/* drivers/pci/probe.c:2650 */
static void pci_init_capabilities(struct pci_dev *dev)
{
	pci_ea_init(dev);		/* Enhanced Allocation */
	pci_msi_init(dev);		/* Disable MSI */
	pci_msix_init(dev);		/* Disable MSI-X */

	/* Buffers for saving PCIe and PCI-X capabilities */
	pci_allocate_cap_save_buffers(dev);

	pci_imm_ready_init(dev);	/* Immediate Readiness */
	pci_pm_init(dev);		/* Power Management */
	pci_vpd_init(dev);		/* Vital Product Data */
	pci_configure_ari(dev);		/* Alternative Routing-ID Forwarding */
	pci_iov_init(dev);		/* Single Root I/O Virtualization */
	pci_ats_init(dev);		/* Address Translation Services */
	pci_pri_init(dev);		/* Page Request Interface */
	pci_pasid_init(dev);		/* Process Address Space ID */
	pci_acs_init(dev);		/* Access Control Services */
	pci_ptm_init(dev);		/* Precision Time Measurement */
	pci_aer_init(dev);		/* Advanced Error Reporting */
	pci_dpc_init(dev);		/* Downstream Port Containment */
	pci_rcec_init(dev);		/* Root Complex Event Collector */
```

The call at [`probe.c:2671`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2671) comes after the AER and DPC initializers and runs for each function set up, so [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) has to recognise an RCEC itself. It reads the RCEC's configuration space with [`pci_read_config_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L580), the PCI core's dword read for a function, whose body shows when a read does not reach the hardware:

```c
/* drivers/pci/access.c:580 */
int pci_read_config_dword(const struct pci_dev *dev, int where,
					u32 *val)
{
	if (pci_dev_is_disconnected(dev)) {
		PCI_SET_ERROR_RESPONSE(val);
		return PCIBIOS_DEVICE_NOT_FOUND;
	}
	return pci_bus_read_config_dword(dev->bus, dev->devfn, where, val);
}
EXPORT_SYMBOL(pci_read_config_dword);
```

A function marked disconnected gets [`PCIBIOS_DEVICE_NOT_FOUND`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L841) back without a hardware access, and any other read goes through the accessor of the function's bus at its devfn. [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) tests the type, looks the capability up, allocates the cache and fills it, returning early when one of the first three steps finds nothing to do:

```c
/* drivers/pci/pcie/rcec.c:149 */
void pci_rcec_init(struct pci_dev *dev)
{
	struct rcec_ea *rcec_ea;
	u32 rcec, hdr, busn;
	u8 ver;

	/* Only for Root Complex Event Collectors */
	if (pci_pcie_type(dev) != PCI_EXP_TYPE_RC_EC)
		return;

	rcec = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_RCEC);
	if (!rcec)
		return;

	rcec_ea = kzalloc_obj(*rcec_ea);
	if (!rcec_ea)
		return;

	pci_read_config_dword(dev, rcec + PCI_RCEC_RCIEP_BITMAP,
			      &rcec_ea->bitmap);

	/* Check whether RCEC BUSN register is present */
	pci_read_config_dword(dev, rcec, &hdr);
	ver = PCI_EXT_CAP_VER(hdr);
	if (ver >= PCI_RCEC_BUSN_REG_VER) {
		pci_read_config_dword(dev, rcec + PCI_RCEC_BUSN, &busn);
		rcec_ea->nextbusn = PCI_RCEC_BUSN_NEXT(busn);
		rcec_ea->lastbusn = PCI_RCEC_BUSN_LAST(busn);
	} else {
		/* Avoid later ver check by setting nextbusn */
		rcec_ea->nextbusn = 0xff;
		rcec_ea->lastbusn = 0x00;
	}

	dev->rcec_ea = rcec_ea;
}
```

A function of a type other than [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494), or an RCEC without the capability, leaves [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) NULL, and the entry points below return at once for such a function. The local `rcec` of [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) is the capability's offset, a u32 that shares its name with the [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) member and with the parameters below that hold an RCEC's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). The version taken from the header at [`rcec.c:171-173`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L171) picks the branch, and an allocation failure leaves the RCEC without a cache like a missing capability. The return values of the three configuration reads go unchecked.

The members written here, the pointer that publishes them and the pointer the link later writes into each RCiEP change at a few named events, from this scan to the RCEC's release, which the strip lays out.

```text
    The association's fields and pointers from the RCEC's scan to its release
    ─────────────────────────────────────────────────────────────────────────

    time ─────────────────────────────────────────────────────────────────────────────────────────────────▶

                     pci_rcec_init, at the scan of the RCEC           RCEC bound      RCEC released
    event            alloc    bitmap   bus range        publish       link            free     clear
                     ▼        ▼        ▼                ▼             ▼               ▼        ▼
                     ┌────────┬───────────────────────────────────────────────────────┬────────────────────
    bitmap           │ 0      │ association bitmap                                    │ freed
                     └────────┴───────────────────────────────────────────────────────┴────────────────────
                     ┌─────────────────┬──────────────────────────────────────────────┬────────────────────
    nextbusn         │ 0               │ Next Bus, or 0xff                            │ freed
                     └─────────────────┴──────────────────────────────────────────────┴────────────────────
                     ┌─────────────────┬──────────────────────────────────────────────┬────────────────────
    lastbusn         │ 0               │ Last Bus, or 0x00                            │ freed
                     └─────────────────┴──────────────────────────────────────────────┴────────────────────
                     ┌──────────────────────────────────┬──────────────────────────────────────┬───────────
    RCEC rcec_ea     │ NULL                             │ the rcec_ea object                   │ NULL
                     └──────────────────────────────────┴──────────────────────────────────────┴───────────
                     ┌────────────────────────────────────────────────┬────────────────────────────────────
    RCiEP rcec       │ NULL                                           │ the RCEC's struct pci_dev
                     └────────────────────────────────────────────────┴────────────────────────────────────
                     ①        ②        ③ ④ ⑤ ⑥          ⑦             ⑧               ⑨        ⑩

    rows 1 to 3 are the fields of struct rcec_ea; the RCiEP row is the rcec of each RCiEP the link reaches

    ① pci_rcec_init rcec.c:163  allocates a zeroed struct rcec_ea with kzalloc_obj
    ② pci_rcec_init :167  reads the bitmap dword into bitmap with pci_read_config_dword
    ③ pci_rcec_init :175  copies Next Bus into nextbusn when the version is 2 or more
    ④ pci_rcec_init :176  copies Last Bus into lastbusn on the same branch
    ⑤ pci_rcec_init :179  sets nextbusn to 0xff for a capability of version 1
    ⑥ pci_rcec_init :180  sets lastbusn to 0x00 on the same branch
    ⑦ pci_rcec_init :183  publishes the object in the RCEC's rcec_ea
    ⑧ link_rcec_helper :48  points an associated RCiEP's rcec at the RCEC
    ⑨ pci_rcec_exit :188  frees the object with kfree
    ⑩ pci_rcec_exit :189  clears the RCEC's rcec_ea
```

① is the allocation in [`pci_rcec_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L149) at [`rcec.c:163`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L163), which returns a zeroed object through `kzalloc_obj()`. ② fills [`bitmap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L878) through the configuration read at :167. ③ copies Next Bus into [`nextbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L876) at :175 for a capability of version 2 or more. ④ copies Last Bus into [`lastbusn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L877) on the next line. ⑤ stores 0xff in nextbusn at :179 for a version 1 capability. ⑥ stores 0x00 in lastbusn on the next line. ⑦ publishes the object in the RCEC's [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) at :183, from which point the walks can use it. ⑧ is [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41) storing the RCEC in an associated RCiEP's [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) during the port driver's probe. ⑨ is [`pci_rcec_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L186) freeing the object, which leaves the RCEC's pointer holding a freed address for one line. ⑩ clears that pointer, while the RCiEP's rcec keeps pointing at the RCEC. Two writers stay off the strip because they serve every function and this page shows no line of them that writes these members. [`pci_alloc_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2500) in probe.c zeroes each function's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) when the scan allocates it, which is why both pointers start as NULL, and [`pci_release_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2482) in probe.c frees the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) at the end of its release, which ends both pointers with their object.

After the scan, an RCEC with the capability holds a filled cache, and its RCiEPs still have a NULL [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375).

### The port driver's probe links the RCiEPs of an RCEC

The cache answers which RCiEPs belong to an RCEC, but the recovery path starts from an RCiEP and needs the opposite answer, its RCEC. The port driver computes that answer when it binds an RCEC, by storing the RCEC in the [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) of each associated RCiEP. Its probe, [`pcie_portdrv_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685), accepts the port types and an RCEC, and links before it registers a service:

```c
/* drivers/pci/pcie/portdrv.c:685 */
static int pcie_portdrv_probe(struct pci_dev *dev,
					const struct pci_device_id *id)
{
	int type = pci_pcie_type(dev);
	int status;

	if (!pci_is_pcie(dev) ||
	    ((type != PCI_EXP_TYPE_ROOT_PORT) &&
	     (type != PCI_EXP_TYPE_UPSTREAM) &&
	     (type != PCI_EXP_TYPE_DOWNSTREAM) &&
	     (type != PCI_EXP_TYPE_RC_EC)))
		return -ENODEV;

	if (type == PCI_EXP_TYPE_RC_EC)
		pcie_link_rcec(dev);

	status = pcie_port_device_register(dev);
	if (status)
		return status;
```

The link at [`portdrv.c:698-699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L698) runs before the services are registered at [`portdrv.c:701`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L701), and an error return from that registration leaves the link in place. Every walk over the association carries its state in a [`struct walk_rcec_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L18), which holds the RCEC and, for a service's walk, the service's callback with its argument:

```c
/* drivers/pci/pcie/rcec.c:18 */
struct walk_rcec_data {
	struct pci_dev *rcec;
	int (*user_callback)(struct pci_dev *dev, void *data);
	void *user_data;
};
```

[`rcec`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L19) is the RCEC whose association is walked. [`user_callback`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L20) and [`user_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L21) hold a service's callback and the argument it receives, and the link leaves both NULL. [`pcie_link_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L110) is the entry point the probe calls; it fills the state and hands it to [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) with the helper that stores the link:

```c
/* drivers/pci/pcie/rcec.c:104 */
/**
 * pcie_link_rcec - Link RCiEP devices associated with RCEC.
 * @rcec: RCEC whose RCiEP devices should be linked.
 *
 * Link the given RCEC to each RCiEP device found.
 */
void pcie_link_rcec(struct pci_dev *rcec)
{
	struct walk_rcec_data rcec_data;

	if (!rcec->rcec_ea)
		return;

	rcec_data.rcec = rcec;
	rcec_data.user_callback = NULL;
	rcec_data.user_data = NULL;

	walk_rcec(link_rcec_helper, &rcec_data);
}
```

An RCEC without a cache returns at the test of [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374), so the probe of such an RCEC links nothing. For any other RCEC, [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41) receives each function the walk finds, with the state as its argument.

When the probe runs decides which RCiEPs the walk can find, which the next subsection takes up.

### The link follows the scan and needs the port driver

The link stores the RCEC in the RCiEPs that are on a bus list when the RCEC's probe runs, and it runs at that probe alone. On x86 with [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9), the ACPI host bridge driver scans the hierarchy below a host bridge before it starts the drivers on it, as [`acpi_pci_root_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L637) shows at its two stages:

```c
/* drivers/acpi/pci_root.c:637 */
static int acpi_pci_root_add(struct acpi_device *device,
			     const struct acpi_device_id *not_used)
	... /* 77 lines, to :716 */
	/*
	 * Scan the Root Bridge
	 * --------------------
	 * Must do this prior to any attempt to bind the root device, as the
	 * PCI namespace does not get created until this call is made (and
	 * thus the root bridge's pci_dev does not exist).
	 */
	root->bus = pci_acpi_scan_root(root);
	if (!root->bus) {
		dev_err(&device->dev,
			"Bus %04x:%02x not present in PCI namespace\n",
			root->segment, (unsigned int)root->secondary.start);
		device->driver_data = NULL;
		result = -ENODEV;
		goto remove_dmar;
	}
	... /* 23 lines, to :755 */
	pci_lock_rescan_remove();
	pci_bus_add_devices(root->bus);
	pci_unlock_rescan_remove();
```

The scan at [`pci_root.c:723`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L723) returns the root bus once the hierarchy is scanned, and the drivers of the hierarchy start at [`pci_root.c:756`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L756), in the order the comment above the scan requires. Each function the scan finds is listed on its bus while [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726) sets it up:

```c
/* drivers/pci/probe.c:2726 */
void pci_device_add(struct pci_dev *dev, struct pci_bus *bus)
{
	int ret;
	... /* 27 lines, to :2756 */
	down_write(&pci_bus_sem);
	list_add_tail(&dev->bus_list, &bus->devices);
	up_write(&pci_bus_sem);
```

The list insertion happens during the scan, before the drivers start, so the RCEC's probe can find the RCiEPs of the hierarchy on their buses.

The link also needs the port driver itself, which a boot parameter can keep from registering. [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) parses `pcie_ports=`, and the value compat sets [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607):

```c
/* drivers/pci/pcie/portdrv.c:606 */
/* If this switch is set, PCIe port native services should not be enabled. */
bool pcie_ports_disabled;

/*
 * If the user specified "pcie_ports=native", use the PCIe services regardless
 * of whether the platform has given us permission.  On ACPI systems, this
 * means we ignore _OSC.
 */
bool pcie_ports_native;

/*
 * If the user specified "pcie_ports=dpc-native", use the Linux DPC PCIe
 * service even if the platform hasn't given us permission.
 */
bool pcie_ports_dpc_native;

static int __init pcie_port_setup(char *str)
{
	if (!strncmp(str, "compat", 6))
		pcie_ports_disabled = true;
	else if (!strncmp(str, "native", 6))
		pcie_ports_native = true;
	else if (!strncmp(str, "dpc-native", 10))
		pcie_ports_dpc_native = true;

	return 1;
}
__setup("pcie_ports=", pcie_port_setup);
```

The value native sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), which the service conditions shown earlier accept in place of the platform's permission, and dpc-native concerns DPC alone. [`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) reads the disabling flag before it registers the driver:

```c
/* drivers/pci/pcie/portdrv.c:839 */
static int __init pcie_portdrv_init(void)
{
	if (pcie_ports_disabled)
		return -EACCES;

	pcie_init_services();
	dmi_check_system(pcie_portdrv_dmi_table);

	return pci_register_driver(&pcie_portdriver);
}
device_initcall(pcie_portdrv_init);
```

With `pcie_ports=compat` the initcall returns `-EACCES` before [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) is registered, so the port driver probes no RCEC and links no RCiEP. The drawing puts the scan, the driver core, the port driver and one RCiEP side by side in time.

```text
    The link follows the scan of the hierarchy and needs the port driver
    ────────────────────────────────────────────────────────────────────

    time ↓
    root bus scan              driver core                port driver                an RCiEP's struct pci_dev
    ─────────────────────────┼──────────────────────────┼──────────────────────────┼─────────────────────────────
    RCEC found: capability   ╎                          ╎                          ╎
    init caches rcec_ea      ╎                          ╎                          ╎
                             ╎                          ╎                          ╎
    RCiEP found, listed      ╎                          ╎                          ╎
    on its bus ──────────────────────────────────────────────────────────────────▶ ╎ listed, rcec NULL
                             ╎                          ╎                          ╎
    hierarchy scanned ─────▶ ╎ functions added,         ╎                          ╎
                             ╎ binding allowed ───────▶ ╎ RCEC probed, its         ╎
                             ╎                          ╎ associated RCiEPs        ╎
                             ╎                          ╎ linked ────────────────▶ ╎ rcec = the RCEC
                             ╎                          ╎                          ╎
                             ╎                          ╎ with pcie_ports=compat   ╎
                             ╎                          ╎ never registered         ╎ rcec stays NULL
                             ╎                          ╎                          ╎
```

An RCiEP that a later rescan adds is listed after the RCEC's probe has run. [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41) is the sole writer of [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) at v7.2, so such an RCiEP keeps a NULL rcec until the RCEC is probed again.

So far, the scan has cached the association in [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374), and the RCEC's probe has started the link, which reaches the RCiEPs already listed and needs the port driver; the strip stands between ⑦ and ⑧.

### walk_rcec visits the RCEC's bus and then its bus range

The link and the services' walks share [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68), which decides which buses to visit. It visits the RCEC's own bus, the bus the bitmap describes, and then each existing bus of the cached range, handing the helper it receives to the PCI core's bus walk:

```c
/* drivers/pci/pcie/rcec.c:68 */
static void walk_rcec(int (*cb)(struct pci_dev *dev, void *data),
		      void *userdata)
{
	struct walk_rcec_data *rcec_data = userdata;
	struct pci_dev *rcec = rcec_data->rcec;
	u8 nextbusn, lastbusn;
	struct pci_bus *bus;
	unsigned int bnr;

	if (!rcec->rcec_ea)
		return;

	/* Walk own bus for bitmap based association */
	pci_walk_bus(rcec->bus, cb, rcec_data);

	nextbusn = rcec->rcec_ea->nextbusn;
	lastbusn = rcec->rcec_ea->lastbusn;

	/* All RCiEP devices are on the same bus as the RCEC */
	if (nextbusn == 0xff && lastbusn == 0x00)
		return;

	for (bnr = nextbusn; bnr <= lastbusn; bnr++) {
		/* No association indicated (PCIe 5.0-1, 7.9.10.3) */
		if (bnr == rcec->bus->number)
			continue;

		bus = pci_find_bus(pci_domain_nr(rcec->bus), bnr);
		if (!bus)
			continue;

		/* Find RCiEP devices on the given bus ranges */
		pci_walk_bus(bus, cb, rcec_data);
	}
}
```

[`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) returns at once for an RCEC without a cache. Its locals `nextbusn` and `lastbusn` copy the cached bounds, and the pair 0xff and 0x00 that marks a version 1 capability ends the function at [`rcec.c:86-88`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L86), after the first walk. Otherwise the loop runs its local `bnr`, an unsigned int, from the first bound to the last, skipping the RCEC's own bus, which the comment at [`rcec.c:91`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L91) ties to the specification, and skipping a number with no bus. Each visit goes through [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461), the PCI core's walk over a bus and the buses below it, which holds [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading while [`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408) does the work:

```c
/* drivers/pci/bus.c:448 */
/**
 *  pci_walk_bus - walk devices on/under bus, calling callback.
 *  @top: bus whose devices should be walked
 *  @cb: callback to be called for each device found
 *  @userdata: arbitrary pointer to be passed to callback
 *
 *  Walk the given bus, including any bridged devices
 *  on buses under this bus.  Call the provided callback
 *  on each device found.
 *
 *  We check the return of @cb each time. If it returns anything
 *  other than 0, we break out.
 */
void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *), void *userdata)
{
	down_read(&pci_bus_sem);
	__pci_walk_bus(top, cb, userdata);
	up_read(&pci_bus_sem);
}
EXPORT_SYMBOL_GPL(pci_walk_bus);
```

The read side of the semaphore holds off the writers of the bus lists, which take its write side, for the length of the walk. [`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408) is the recursion, and it decides both the order of the visits and where a walk stops:

```c
/* drivers/pci/bus.c:408 */
static int __pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *),
			  void *userdata)
{
	struct pci_dev *dev;
	int ret = 0;

	list_for_each_entry(dev, &top->devices, bus_list) {
		ret = cb(dev, userdata);
		if (ret)
			break;
		if (dev->subordinate) {
			ret = __pci_walk_bus(dev->subordinate, cb, userdata);
			if (ret)
				break;
		}
	}
	return ret;
}
```

The callback runs on the functions of the bus in list order, and the walk descends into the [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus of each bridge it meets. The first walk of [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68) therefore also reaches the functions behind any Root Port on the RCEC's bus. A nonzero return from the callback ends the walk at every level, and [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) drops the value. The loop turns a bus number into a bus with [`pci_find_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L143), given the domain of the RCEC's bus:

```c
/* drivers/pci/search.c:134 */
/**
 * pci_find_bus - locate PCI bus from a given domain and bus number
 * @domain: number of PCI domain to search
 * @busnr: number of desired PCI bus
 *
 * Given a PCI bus number and domain number, the desired PCI bus is located
 * in the global list of PCI buses.  If the bus is found, a pointer to its
 * data structure is returned.  If no bus is found, %NULL is returned.
 */
struct pci_bus *pci_find_bus(int domain, int busnr)
{
	struct pci_bus *bus = NULL;
	struct pci_bus *tmp_bus;

	while ((bus = pci_find_next_bus(bus)) != NULL)  {
		if (pci_domain_nr(bus) != domain)
			continue;
		tmp_bus = pci_do_find_bus(bus, busnr);
		if (tmp_bus)
			return tmp_bus;
	}
	return NULL;
}
EXPORT_SYMBOL(pci_find_bus);
```

Following its comment, the lookup searches the global list of PCI buses within the domain and returns NULL when no bus has the number, a number the loop then skips. The drawing places the visits of one walk on the bus-number axis of the domain.

```text
    The buses one walk of the association visits, on the bus-number axis of the RCEC's domain
    ─────────────────────────────────────────────────────────────────────────────────────────

    bus number    N           P           Q            nextbusn                        lastbusn
    buses     ────●───────────●───●───●───●───────────────●───────○───────●───────○───────●──────────────────▶ 0xff

    first walk   ├─┤         ├───────────┤
                 bus N:      buses behind bridges on bus N,
                 bitmap test reached from bus N, no RC_END

    range loop                                           ├───────────────────────────────┤
                                                          ▼       ·       ▼       ·       ▼
                                                         walk    skip    walk    skip    walk
                                                         ○ : no bus with that number in the domain

    ● a bus that exists   ○ a number with no bus
    bus N inside nextbusn..lastbusn is skipped by the loop, the first walk covered it
    nextbusn 0xff with lastbusn 0x00 ends the walk after bus N, with no loop
```

Bus N and the buses behind its bridges go through the first walk, where the helper keeps the RCiEPs and passes over the other functions. The loop then visits each bus of the range that exists, and a number without a bus costs one lookup.

### rcec_assoc_rciep keeps the RCiEPs the RCEC names

The walk offers each function it finds to the helper, and the helper keeps the RCiEPs the association names. Two tests decide, the function's type and, on the RCEC's own bus, the bitmap bit of its device number. [`rcec_assoc_rciep()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L24) applies the second:

```c
/* drivers/pci/pcie/rcec.c:24 */
static bool rcec_assoc_rciep(struct pci_dev *rcec, struct pci_dev *rciep)
{
	unsigned long bitmap = rcec->rcec_ea->bitmap;
	unsigned int devn;

	/* An RCiEP found on a different bus in range */
	if (rcec->bus->number != rciep->bus->number)
		return true;

	/* Same bus, so check bitmap */
	for_each_set_bit(devn, &bitmap, 32)
		if (devn == PCI_SLOT(rciep->devfn))
			return true;

	return false;
}
```

An RCiEP on a bus other than the RCEC's is associated without a bitmap test, since the walk reaches other buses through the cached range or below the RCEC's bus. A function of type [`PCI_EXP_TYPE_RC_END`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L493) that the first walk finds behind a bridge on the RCEC's bus is on another bus as well, and the test associates it the same way. On the RCEC's own bus the loop at [`rcec.c:34-36`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L34) compares the number of each set bit of a copy of [`bitmap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L878) with the function's device number, over the 32 bit numbers the literal at :34 sets, the width of the bitmap register. The parameter `rcec` is the RCEC's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and `rciep` the function under test. The device number comes from [`PCI_SLOT()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L32), one of the macros that split a devfn, whose comment gives the layout:

```c
/* include/uapi/linux/pci.h:23 */
/*
 * The PCI interface treats multi-function devices as independent
 * devices.  The slot/function address of each device is encoded
 * in a single byte as follows:
 *
 *	7:3 = slot
 *	2:0 = function
 */
#define PCI_DEVFN(slot, func)	((((slot) & 0x1f) << 3) | ((func) & 0x07))
#define PCI_SLOT(devfn)		(((devfn) >> 3) & 0x1f)
#define PCI_FUNC(devfn)		((devfn) & 0x07)
```

Bits 7:3 of [`devfn`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L361) are the device number, so the functions of one device test the same bit. The conversion came in with commit [d9b7eae8e342](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=d9b7eae8e3424c3480fe9f40ebafbb0c96426e4c) ("PCI/RCEC: Fix RCiEP device to RCEC association"), after the first version had compared devfn itself with the bit numbers. [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41), the helper the link passes, applies the type test first and the association test second, and writes the link when both pass:

```c
/* drivers/pci/pcie/rcec.c:41 */
static int link_rcec_helper(struct pci_dev *dev, void *data)
{
	struct walk_rcec_data *rcec_data = data;
	struct pci_dev *rcec = rcec_data->rcec;

	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_RC_END) &&
	    rcec_assoc_rciep(rcec, dev)) {
		dev->rcec = rcec;
		pci_dbg(dev, "PME & error events signaled via %s\n",
			pci_name(rcec));
	}

	return 0;
}
```

A function that passes both gets its [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) pointed at the RCEC, the strip's ⑧, and a debug line on the RCiEP names the RCEC. The write happens inside the walk, while [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) is held for reading. That line is a dynamic-debug callsite with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set. The helper takes no reference on the RCEC's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and returns 0 for any function, so the walk goes on to the next one. The drawing runs both tests over one RCEC's bus and one bus of its range.

```text
    Device numbers on the RCEC's bus against its bitmap, and the rcec each match receives
    ─────────────────────────────────────────────────────────────────────────────────────

    devfn bit       7 6 5 4 3 2 1 0
                   ┌─┬─┬─┬─┬─┬─┬─┬─┐   the device number is bits 7:3 of devfn, so every function
                   │ device  │ fn  │   of a device tests the same bit of the bitmap
                   └─────────┴─────┘

    device number      0        1        2        3        4        5      6 .. 31
                   ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┐
    bitmap bit     │ 0      │ 0      │ 1      │ 1      │ 0      │ 1      │ 0      │
                   ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤
    function on    │ RCEC   │ none   │ RCiEP  │ Root   │ RCiEP  │ none   │ none   │
    bus N          │ RC_EC  │        │ RC_END │ Port   │ RC_END │        │        │
                   └────────┴────────┴────────┴────────┴────────┴────────┴────────┘

    outcome          type                ▼      type     bit 0
                     not 0x9          ┌──────┐  not 0x9  no link
    left behind                       │ rcec │
                                      └──────┘  the RCiEP at device 2 points at the RCEC

    other bus      ┌────────┐
    in range       │ RCiEP  │ ──▶ rcec points at the RCEC: any device number, no bitmap test
                   └────────┘
```

Device 3 has its bit set and holds a Root Port, which the type test rejects, and device 4 holds an RCiEP whose bit is clear, so its [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) stays NULL. The RCiEP on the bus of the range gets its rcec whatever its device number.

### pcie_walk_rcec hands the associated RCiEPs to a service

A service that needs the RCiEPs of an RCEC uses the same walk with a callback of its own. [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) fills the callback members of [`struct walk_rcec_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L18) and passes [`walk_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L56) to [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68):

```c
/* drivers/pci/pcie/rcec.c:124 */
/**
 * pcie_walk_rcec - Walk RCiEP devices associating with RCEC and call callback.
 * @rcec:	RCEC whose RCiEP devices should be walked
 * @cb:		Callback to be called for each RCiEP device found
 * @userdata:	Arbitrary pointer to be passed to callback
 *
 * Walk the given RCEC. Call the callback on each RCiEP found.
 *
 * If @cb returns anything other than 0, break out.
 */
void pcie_walk_rcec(struct pci_dev *rcec, int (*cb)(struct pci_dev *, void *),
		    void *userdata)
{
	struct walk_rcec_data rcec_data;

	if (!rcec->rcec_ea)
		return;

	rcec_data.rcec = rcec;
	rcec_data.user_callback = cb;
	rcec_data.user_data = userdata;

	walk_rcec(walk_rcec_helper, &rcec_data);
}
```

An RCEC without a cache returns at once, as in the link. The kernel-doc above the function says that a return other than 0 from the callback breaks out of the walk. Whether it does depends on [`walk_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L56), which applies the link's two tests and then calls the service's callback:

```c
/* drivers/pci/pcie/rcec.c:56 */
static int walk_rcec_helper(struct pci_dev *dev, void *data)
{
	struct walk_rcec_data *rcec_data = data;
	struct pci_dev *rcec = rcec_data->rcec;

	if ((pci_pcie_type(dev) == PCI_EXP_TYPE_RC_END) &&
	    rcec_assoc_rciep(rcec, dev))
		rcec_data->user_callback(dev, rcec_data->user_data);

	return 0;
}
```

The helper drops the callback's return value and returns 0, so the walk reaches each associated RCiEP whatever the callback returns, which the kernel-doc of [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) does not describe. The two entry points differ in what they put into [`struct walk_rcec_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L18) and in the helper they pass, as the drawing sets side by side.

```text
    Two fillings of walk_rcec_data meet in one walk of the association
    ──────────────────────────────────────────────────────────────────

    the link, at the RCEC's probe               a service's walk
    ┌────────────────────────────────┐          ┌────────────────────────────────┐
    │ struct walk_rcec_data          │          │ struct walk_rcec_data          │
    │ rcec           the RCEC        │          │ rcec           the RCEC        │
    │ user_callback  NULL            │          │ user_callback  cb              │
    │ user_data      NULL            │          │ user_data      userdata        │
    └───────────────┬────────────────┘          └───────────────┬────────────────┘
                    │ with the link helper                      │ with the walk helper
                    └─────────────────────┬─────────────────────┘
                                          │
                                          ▼
                     ┌─────────────────────────────────────────┐
                     │ one walk of bus N and the bus range,    │
                     │ the helper called on every function     │
                     └────────────────────┬────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
        each associated RCiEP:                  each associated RCiEP: cb(dev, userdata),
        rcec points at the RCEC                 its return value dropped, the walk goes on
```

Each [`struct walk_rcec_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L18) is a local of its entry point, filled in three lines and gone when the entry point returns, so it carries no state from one walk to the next. Five functions call [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) at v7.2. Two of them belong to the CXL error code, which this page leaves out, and the other three are the PME and AER uses the next subsections show.

### The PME and AER services walk the association when they probe

The PME and AER services are probed on an RCEC as on a Root Port, after the link, and both act on the RCiEPs at that point. The AER service's error handling uses the association twice more, to find an error's sender and to reset an RCiEP. The drawing places these uses on one time axis.

```text
    The port services use the association at probe and when an RCiEP reports an error
    ─────────────────────────────────────────────────────────────────────────────────

    time ↓
    port driver                PME service                AER service                AER error handling
    ─────────────────────────┼──────────────────────────┼──────────────────────────┼─────────────────────────────
    RCEC bound ➊             ╎                          ╎                          ╎
    RCiEPs linked,           ╎                          ╎                          ╎
    services registered      ╎                          ╎                          ╎
      ─────────────────────▶ ╎ probe ➋                  ╎                          ╎
                             ╎ RCEC and RCiEPs          ╎                          ╎
                             ╎ wakeup capable           ╎                          ╎
                             ╎                          ╎                          ╎
      ────────────────────────────────────────────────▶ ╎ probe ➌                  ╎
                             ╎                          ╎ stale status of          ╎
                             ╎                          ╎ RCiEPs cleared           ╎
                             ╎                          ╎                          ╎
                             ╎                          ╎ error message            ╎
                             ╎                          ╎ from an RCiEP            ╎
                             ╎                          ╎   ─────────────────────▶ ╎ source found among
                             ╎                          ╎                          ╎ the RCiEPs ➍
                             ╎                          ╎                          ╎
                             ╎                          ╎                          ╎ RCiEP reset, Root
                             ╎                          ╎                          ╎ Error Status of its
                             ╎                          ╎                          ╎ rcec cleared ➎
                             ╎                          ╎                          ╎
    the two service probes follow the registration of their services, in either order

    ➊ pcie_portdrv_probe portdrv.c:699  links the RCiEPs before the services are registered
    ➋ pcie_pme_mark_devices pme.c:317  hands each associated RCiEP to the wakeup marking
    ➌ aer_enable_rootport aer.c:1555  clears stale error status at each associated RCiEP
    ➍ find_source_device aer.c:1114  searches the associated RCiEPs for the error source
    ➎ aer_root_reset aer.c:1682  takes an RCiEP's rcec as the holder of its Root Error registers
```

➊ is the link in [`pcie_portdrv_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685) at [`portdrv.c:699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L699), which runs before the services are registered. ➋ is [`pcie_pme_mark_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L312) handing each associated RCiEP to the PME service's wakeup marking. ➌ is [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) clearing the stale error status of each associated RCiEP during the AER service's probe. ➍ is [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099) searching the associated RCiEPs for the sender of an error message. ➎ is [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) taking an RCiEP's [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) as the function that holds its Root Error registers.

The PME service exists with [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117), which Kconfig derives from the port driver and power management:

```c
/* drivers/pci/pcie/Kconfig:117 */
config PCIE_PME
	def_bool y
	depends on PCIEPORTBUS && PM
```

The option is a `def_bool` that follows [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) and [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217), both set in the configuration this page assumes. [`pcie_pme_mark_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L312) marks the functions whose PME the service handles as able to wake the system, through the callback [`pcie_pme_can_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L298) that stands right above it:

```c
/* drivers/pci/pcie/pme.c:293 */
/**
 * pcie_pme_can_wakeup - Set the wakeup capability flag.
 * @dev: PCI device to handle.
 * @ign: Ignored.
 */
static int pcie_pme_can_wakeup(struct pci_dev *dev, void *ign)
{
	device_set_wakeup_capable(&dev->dev, true);
	return 0;
}

/**
 * pcie_pme_mark_devices - Set the wakeup flag for devices below a port.
 * @port: PCIe root port or event collector to handle.
 *
 * For each device below given root port, including the port itself (or for each
 * root complex integrated endpoint if @port is a root complex event collector)
 * set the flag indicating that it can signal run-time wake-up events.
 */
static void pcie_pme_mark_devices(struct pci_dev *port)
{
	pcie_pme_can_wakeup(port, NULL);

	if (pci_pcie_type(port) == PCI_EXP_TYPE_RC_EC)
		pcie_walk_rcec(port, pcie_pme_can_wakeup, NULL);
	else if (port->subordinate)
		pci_walk_bus(port->subordinate, pcie_pme_can_wakeup, NULL);
}
```

The RCEC itself is marked first, then each associated RCiEP through [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134), where a Root Port has its [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus walked. The callback returns 0 in any case. [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) calls the marking at the end of the service's probe, once its interrupt is requested:

```c
/* drivers/pci/pcie/pme.c:326 */
static int pcie_pme_probe(struct pcie_device *srv)
{
	struct pci_dev *port = srv->port;
	struct pcie_pme_service_data *data;
	int type = pci_pcie_type(port);
	int ret;
	... /* 24 lines, to :356 */
	pci_info(port, "Signaling with IRQ %d\n", srv->irq);

	pcie_pme_mark_devices(port);
```

The marking follows the line that announces the service's IRQ, so the RCiEPs are marked from the end of the probe on. [`aer_enable_rootport()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1533) ends the AER service's probe by clearing error status left from before the probe, on the RCEC and on the agents that report to it:

```c
/* drivers/pci/pcie/aer.c:1533 */
static void aer_enable_rootport(struct aer_rpc *rpc)
{
	struct pci_dev *pdev = rpc->rpd;
	int aer = pdev->aer_cap;
	u16 reg16;
	u32 reg32;

	/* Clear PCIe Capability's Device Status */
	pcie_capability_read_word(pdev, PCI_EXP_DEVSTA, &reg16);
	pcie_capability_write_word(pdev, PCI_EXP_DEVSTA, reg16);

	/* Disable system error generation in response to error messages */
	pcie_capability_clear_word(pdev, PCI_EXP_RTCTL,
				   SYSTEM_ERROR_INTR_ON_MESG_MASK);

	/* Clear error status of this Root Port or RCEC */
	pci_read_config_dword(pdev, aer + PCI_ERR_ROOT_STATUS, &reg32);
	pci_write_config_dword(pdev, aer + PCI_ERR_ROOT_STATUS, reg32);

	/* Clear error status of agents reporting to this Root Port or RCEC */
	if (reg32 & AER_ERR_STATUS_MASK) {
		if (pci_pcie_type(pdev) == PCI_EXP_TYPE_RC_EC)
			pcie_walk_rcec(pdev, clear_status_iter, NULL);
		else if (pdev->subordinate)
			pci_walk_bus(pdev->subordinate, clear_status_iter,
				     NULL);
	}
```

The RCiEPs' status is cleared through [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) when the RCEC's Root Error Status, read at [`aer.c:1549`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1549), has one of the bits the test at [`aer.c:1553`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1553) masks, and a Root Port has its subordinate bus walked in that place. This step came in with commit [e242d09b58e8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e242d09b58e869f86071b7889acace4cff215935) ("PCI/AER: Clear stale errors on reporting agents upon probe"). The callback is [`clear_status_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1513), which skips an agent whose error reporting is not enabled yet:

```c
/* drivers/pci/pcie/aer.c:1513 */
static int clear_status_iter(struct pci_dev *dev, void *data)
{
	u16 devctl;

	/* Skip if pci_enable_pcie_error_reporting() hasn't been called yet */
	pcie_capability_read_word(dev, PCI_EXP_DEVCTL, &devctl);
	if (!(devctl & PCI_EXP_AER_FLAGS))
		return 0;

	pci_aer_clear_status(dev);
	pcie_clear_device_status(dev);
	return 0;
}
```

An RCiEP whose Device Control register lacks the error reporting bits keeps its status, since, according to the comment, its error reporting has not been enabled yet. Any other RCiEP has its AER status and its Device Status cleared. Both probes reach the RCiEPs through the cache, whether or not the link stored their [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375).

### find_source_device searches the RCiEPs for an error's sender

When an RCEC's AER service receives an error message, it has to find the function whose status records the error. Below a Root Port it searches the subordinate bus, and for an RCEC the association, as [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099) shows:

```c
/* drivers/pci/pcie/aer.c:1087 */
/**
 * find_source_device - search through device hierarchy for source device
 * @parent: pointer to Root Port pci_dev data structure
 * @e_info: including detailed error information such as ID
 *
 * Return: true if found.
 *
 * Invoked by DPC when error is detected at the Root Port.
 * Caller of this function must set id, severity, and multi_error_valid of
 * struct aer_err_info pointed by @e_info properly.  This function must fill
 * e_info->error_dev_num and e_info->dev[], based on the given information.
 */
static bool find_source_device(struct pci_dev *parent,
			       struct aer_err_info *e_info)
{
	struct pci_dev *dev = parent;
	int result;

	/* Must reset in this function */
	e_info->error_dev_num = 0;

	/* Is Root Port an agent that sends error message? */
	result = find_device_iter(dev, e_info);
	if (result)
		return true;

	if (pci_pcie_type(parent) == PCI_EXP_TYPE_RC_EC)
		pcie_walk_rcec(parent, find_device_iter, e_info);
	else
		pci_walk_bus(parent->subordinate, find_device_iter, e_info);

	if (!e_info->error_dev_num)
		return false;
	return true;
}
```

The RCEC itself is tested first, and an RCEC that is the sender ends the search. Otherwise each associated RCiEP goes to [`find_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067), and the search succeeds when it has listed a source. [`find_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1067) is the callback, and its return value asks the walk to stop:

```c
/* drivers/pci/pcie/aer.c:1067 */
static int find_device_iter(struct pci_dev *dev, void *data)
{
	struct aer_err_info *e_info = (struct aer_err_info *)data;

	if (is_error_source(dev, e_info)) {
		/* List this device */
		if (add_error_device(e_info, dev)) {
			/* We cannot handle more... Stop iteration */
			pci_err(dev, "Exceeded max supported (%d) devices with errors logged\n",
				AER_MAX_MULTI_ERR_DEVICES);
			return 1;
		}

		/* If there is only a single error, stop iteration */
		if (!e_info->multi_error_valid)
			return 1;
	}
	return 0;
}
```

The callback returns 1 after the first source when the message reported a single error, and when the list of sources cannot take a further one. Below a Root Port that 1 ends the walk. Through [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) it is dropped by [`walk_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L56), so the search over an RCEC goes on to the last associated RCiEP, and each further source the list cannot take prints the "Exceeded max supported" line again.

### aer_root_reset reaches an RCiEP's Root Error registers through rcec

The AER path passes [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) to the error recovery as its reset callback, from [`pci_aer_handle_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1170) at [`aer.c:1191-1193`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1191) and from [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) at [`aer.c:1247-1250`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1247). Around the reset of the function it receives, the callback masks the AER interrupt of the function that holds the Root Error registers and clears their status afterwards, and for an RCiEP it finds that function through [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375):

```c
/* drivers/pci/pcie/aer.c:1661 */
/**
 * aer_root_reset - reset Root Port hierarchy, RCEC, or RCiEP
 * @dev: pointer to Root Port, RCEC, or RCiEP
 *
 * Invoked by Port Bus driver when performing reset.
 */
static pci_ers_result_t aer_root_reset(struct pci_dev *dev)
{
	int type = pci_pcie_type(dev);
	struct pci_dev *root;
	int aer;
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	u32 reg32;
	int rc;

	/*
	 * Only Root Ports and RCECs have AER Root Command and Root Status
	 * registers.  If "dev" is an RCiEP, the relevant registers are in
	 * the RCEC.
	 */
	if (type == PCI_EXP_TYPE_RC_END)
		root = dev->rcec;
	else
		root = pcie_find_root_port(dev);

	/*
	 * If the platform retained control of AER, an RCiEP may not have
	 * an RCEC visible to us, so dev->rcec ("root") may be NULL.  In
	 * that case, firmware is responsible for these registers.
	 */
	aer = root ? root->aer_cap : 0;

	if ((host->native_aer || pcie_ports_native) && aer)
		aer_disable_irq(root);

	if (type == PCI_EXP_TYPE_RC_EC || type == PCI_EXP_TYPE_RC_END) {
		rc = pcie_reset_flr(dev, PCI_RESET_DO_RESET);
		if (!rc)
			pci_info(dev, "has been reset\n");
		else
			pci_info(dev, "not reset (no FLR support: %d)\n", rc);
	} else {
		rc = pci_bus_error_reset(dev);
		pci_info(dev, "%s Port link has been reset (%d)\n",
			pci_is_root_bus(dev->bus) ? "Root" : "Downstream", rc);
	}

	if ((host->native_aer || pcie_ports_native) && aer) {
		/* Clear Root Error Status */
		pci_read_config_dword(root, aer + PCI_ERR_ROOT_STATUS, &reg32);
		pci_write_config_dword(root, aer + PCI_ERR_ROOT_STATUS, reg32);

		aer_enable_irq(root);
	}

	return rc ? PCI_ERS_RESULT_DISCONNECT : PCI_ERS_RESULT_RECOVERED;
}
```

For an RCiEP the function holding the registers is its [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375), and for the other types the Root Port above the function. The reset itself, at [`aer.c:1696-1706`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1696), differs by type and belongs to the recovery. When rcec is NULL the local `aer` is 0, and the reset runs without masking or clearing anything in an RCEC. The comment ties that case to a platform that retains control of AER, and the earlier subsections give three more, an RCEC without the capability, a kernel booted with `pcie_ports=compat` and an RCiEP added after its RCEC's probe.

The error injector, built with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37), is the second reader of an RCiEP's [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) at v7.2. [`aer_inject()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L319) falls back to it when no Root Port is above the target:

```c
/* drivers/pci/pcie/aer_inject.c:319 */
static int aer_inject(struct aer_error_inj *einj)
{
	... /* 11 lines, to :332 */
	dev = pci_get_domain_bus_and_slot(einj->domain, einj->bus, devfn);
	if (!dev)
		return -ENODEV;
	rpdev = pcie_find_root_port(dev);
	/* If Root Port not found, try to find an RCEC */
	if (!rpdev)
		rpdev = dev->rcec;
	if (!rpdev) {
		pci_err(dev, "Neither Root Port nor RCEC found\n");
		ret = -ENODEV;
		goto out_put;
	}
```

An RCiEP with a NULL rcec cannot be injected into, and the injector prints "Neither Root Port nor RCEC found" for it. The option is unset in the configuration this page assumes.

So far, the association has been cached, linked and walked by the PME and AER probes and by the search for an error's sender, and an RCiEP's rcec has led the reset to its RCEC. What remains is the end of the cache.

### pci_rcec_exit frees the cache when the RCEC is released

The cache lasts as long as the RCEC's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). The release callback that [`pci_device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2726) installs, [`pci_release_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2482), runs when the last reference to a function drops and releases the function's capabilities first:

```c
/* drivers/pci/probe.c:2474 */
/**
 * pci_release_dev - Free a PCI device structure when all users of it are
 *		     finished
 * @dev: device that's been disconnected
 *
 * Will be called only by the device core when all users of this PCI device are
 * done.
 */
static void pci_release_dev(struct device *dev)
{
	struct pci_dev *pci_dev;

	pci_dev = to_pci_dev(dev);
	pci_release_capabilities(pci_dev);
```

The comment says that the device core calls it once the users of the function are done, and the call at [`probe.c:2487`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2487) releases the capabilities before the rest of the teardown. [`pci_release_capabilities()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2466) undoes the capability setup, the association's part included:

```c
/* drivers/pci/probe.c:2466 */
static void pci_release_capabilities(struct pci_dev *dev)
{
	pci_aer_exit(dev);
	pci_rcec_exit(dev);
	pci_iov_release(dev);
	pci_free_cap_save_buffers(dev);
}
```

[`pci_rcec_exit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L186) runs for each released function, beside the AER teardown, so it has to accept a function without a cache. It frees the cache and clears the pointer, the strip's ⑨ and ⑩:

```c
/* drivers/pci/pcie/rcec.c:186 */
void pci_rcec_exit(struct pci_dev *dev)
{
	kfree(dev->rcec_ea);
	dev->rcec_ea = NULL;
}
```

For a function without a cache, `kfree()` receives NULL and the pointer is cleared again. The RCiEPs keep their [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375), since no path at v7.2 clears it and [`link_rcec_helper()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L41) took no reference, so an RCiEP that outlives its RCEC holds the address of the released [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352).

### Messages, hand-offs and files expose the association

A reader watching the association needs to know which traces it leaves. The cache, the link and the walks define and fire no tracepoint, and the RAS tracepoint `ras:aer_event` fires in the AER printers at [`aer.c:879`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L879) and [`aer.c:955`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L955) once the AER path reports a source, outside the association's own code. The messages of these paths print at the sites in the table.

| Site | Message | When it prints |
|---|---|---|
| [`rcec.c:49`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L49) | "PME & error events signaled via %s", at debug level on the RCiEP | the link stores an RCEC in an RCiEP |
| [`pme.c:356`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L356) | "Signaling with IRQ %d" | the PME service's probe on an RCEC or a Root Port |
| [`aer.c:1075`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1075) | "Exceeded max supported (%d) devices with errors logged" | a source the list cannot take, repeated per further source over an RCEC |
| [`aer.c:1699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1699) | "has been reset" | the reset of an RCEC or an RCiEP succeeds |
| [`aer.c:1701`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1701) | "not reset (no FLR support: %d)" | the reset of an RCEC or an RCiEP fails |
| [`aer_inject.c:340`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L340) | "Neither Root Port nor RCEC found" | an injection into an RCiEP whose rcec is NULL, with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) |

The line at rcec.c:49 is the one debug line of the association, a dynamic-debug callsite with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set. Enabled through `/sys/kernel/debug/dynamic_debug/control` or the `dyndbg=` boot parameter, it shows for each RCiEP which RCEC the link stored, and it prints during the RCEC's probe, so a boot-time setting or a new probe is needed to see it. With [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) set, which this page does not assume, the line prints unconditionally, because [`Makefile`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Makefile) compiles the directory with -DDEBUG:

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

The flag reaches drivers/pci/pcie through the subdirectory flags. The paths cross few hand-offs. The link, the PME marking and the AER clearing run inside the probe of the port driver or of a service, with no work item, timer or thread of their own, and the walks hold [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading. The search for an error's sender belongs to the AER service's error handling, whose interrupt [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) requests as a threaded interrupt:

```c
/* drivers/pci/pcie/aer.c:1607 */
static int aer_probe(struct pcie_device *dev)
{
	int status;
	struct aer_rpc *rpc;
	struct device *device = &dev->device;
	struct pci_dev *port = dev->port;
	... /* 19 lines, to :1632 */
	status = devm_request_threaded_irq(device, dev->irq, aer_irq, aer_isr,
					   IRQF_SHARED, "aerdrv", dev);
	if (status) {
		pci_err(port, "request AER IRQ %d failed\n", dev->irq);
		return status;
	}
```

The interrupt gets a hard handler and a thread function, and the AER service's error handling, which reaches [`find_source_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1099) and the recovery, runs from that thread. The firmware-first path reaches [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) from [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218), a work function of the AER service. No file in sysfs, procfs or debugfs shows [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375) or the cache at v7.2. The surfaces that bear on the association are the ones in the table.

| Surface | Path or parameter | What it shows or changes |
|---|---|---|
| dynamic debug | `/sys/kernel/debug/dynamic_debug/control`, or `dyndbg=` at boot | enables the line of the link at [`rcec.c:49`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L49) |
| boot parameter | `pcie_ports=compat` | keeps [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) unregistered, so no RCiEP is linked |
| boot parameter | `pcie_ports=native` | sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), which grants the AER and PME services to an RCEC without the platform's permission |
| error injection | the injector of [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | reaches an RCiEP's RCEC through its [`rcec`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L375), unset in this page's configuration |
| sysfs, procfs, debugfs | none | no file shows the association or its cache |

The association's state is otherwise held in the RCEC's capability, which the REGISTERS drawings lay out, and in the members this page has followed from the scan to the release.
