# AER errors reported by firmware

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

When platform firmware keeps control of Advanced Error Reporting for a PCIe hierarchy, the kernel's AER service stays off for that hierarchy, yet its errors still have to be reported and recovered from. Firmware then hands each error to the kernel as a record of the ACPI Platform Error Interface, and the handler of Generic Hardware Error Sources passes the PCIe part of that record to the PCI core. That handler runs with interrupts disabled while recovery calls drivers and resets links, so a bounded queue and a work item carry each report from one context to the other. This page follows one report on x86-64 with ACPI, from the firmware's record through that queue to the printer, the counters, the tracepoint and the hand-off to error recovery.

```text
    A PCIe error that firmware reports, from its record to recovery
    ───────────────────────────────────────────────────────────────

    firmware              ┌─────────────────────────────────────────────┐
    keeps AER control     │ GHES error status block: a CPER record      │
                          │ PCIe error section: device_id, severity,    │
                          │ flags and aer_info, the AER registers       │
                          └──────────────────────┬──────────────────────┘
    ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌│╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
                                                 ▼ GHES notification
                          ┌─────────────────────────────────────────────┐  copy    ┌─────────────────────────┐
    GHES handler          │ severity mapped to an AER class             ├─────────▶│ pool region holding     │
    interrupts off        │ report: domain, bus, devfn, severity        │          │ struct                  │
                          │ and regs, a pointer to the copy             │          │ aer_capability_regs     │
                          └──────────────────────┬──────────────────────┘          └────────────┬────────────┘
                                                 │ copied in under the writers' lock            ▲
                                                 │                                              │ read, then
                                                 ▼                                              │ freed
                          ┌─────────────────────────────────────────────┐                       │
                          │ aer_recover_ring, sixteen report slots      │                       │
                          └──────────────────────┬──────────────────────┘                       │
                                                 │ work item queued, then one                   │
                                                 │ entry at a time                              │
    ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌│╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌│╌╌╌╌╌╌╌╌╌╌╌╌╌
                                                 ▼                                              │
                          ┌─────────────────────────────────────────────┐                       │
    kworker               │ struct pci_dev found by domain, bus, devfn  │                       │
    process context       │ printed, counted and traced                 ├───────────────────────┘
                          │ recovery for NONFATAL and FATAL             │
                          └─────────────────────────────────────────────┘
```

## SUMMARY

The page's objects pair the firmware's terms with kernel structures, and the table settles the names the rest of the page uses.

| Term | Kernel object | Where it is set or read |
|---|---|---|
| firmware keeps AER control | [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) of the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) left clear | [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) after `_OSC` |
| PCIe error section | a [`struct cper_sec_pcie`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L536) in a GHES error status block | [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912) dispatches it |
| AER register dump | [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568), read as [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41) | [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) copies it to a pool region |
| severity | a CPER severity, then [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14), [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) or [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16) | [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912) |
| queued report | a [`struct aer_recover_entry`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1207) in [`aer_recover_ring`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1215) | [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) |
| reporting function | the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) named by domain, bus and devfn | [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) looks it up |

A report crosses from interrupt context to process context through a ring of sixteen entries, and the copy of the registers that each entry points at belongs to the APEI pool until the work function frees it. The work function prints and counts every report it can match to a function, and it calls error recovery for the two uncorrectable classes, which then leaves every AER register to firmware.

## SPECIFICATIONS

The record format and the notification come from UEFI and ACPI, and the register layout from the PCI Express specification; the tree names each document at the site below, and the kernel structures that hold them are a synthesis read from include/linux/cper.h, include/linux/aer.h, drivers/acpi/apei/ghes.c and drivers/pci/pcie/aer.c.

- UEFI specification v2.7, section N.2.7, "PCI Express Error Section", named by [`cper.h:535`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L535) above [`struct cper_sec_pcie`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L536).
- ACPI Specification version 4.0, section 17.3.2.6, for the Generic Hardware Error Source, named without a title by [`ghes.c:13-14`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L13).
- PCIe r6.2, sections 7.8.4 and 7.9.14, for the sizes of the TLP logging registers, named without titles by [`aer.h:19-21`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L19).
- PCIe r7.0, section 6.2.7, for the errors that always log a TLP header, named without a title by [`aer.c:817`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L817).
- PCI Firmware Specification, for the `_OSC` method that grants AER control, named without a section by [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst).

## COVERAGE

### The ring between the two contexts

- [`'\<aer_recover_queue\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263): copies one report into the ring under the writers' lock and queues the work item.
- [`'\<aer_recover_work_func\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218): drains the ring in process context, prints each report, frees its region and starts recovery.
- [`'\<struct aer_recover_entry\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1207): one queued report, the function's address, its AER class and a pointer to the register copy.
- [`'\<aer_recover_ring\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1215): the kfifo of reports between the GHES handler and the work function.
- [`'\<aer_recover_ring_lock\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1260): serializes the writers of the ring.
- [`'AER_RECOVER_RING_SIZE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1205): the number of slots in the ring.

### Severity classes

- [`'AER_NONFATAL'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14): the class of an uncorrectable error recovered with the channel left normal.
- [`'AER_FATAL'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15): the class of an uncorrectable error recovered with the channel frozen.
- [`'AER_CORRECTABLE'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16): the class of a corrected error, printed and counted only.
- [`'\<cper_severity_to_aer\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912): maps a CPER section severity to one of the three classes.

### The register copy and its printer

- [`'\<struct aer_capability_regs\>':'include/linux/aer.h'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41): the view through which the kernel reads the AER registers a firmware record carries.
- [`'\<pci_print_aer\>':'drivers/pci/pcie/aer.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926): counts, traces and prints one register copy for a function.

## DOCUMENTATION

- [`Documentation/PCI/pcieaer-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pcieaer-howto.rst): the kernel handles AER only when firmware grants control through `_OSC`, and the AER ratelimits and statistics are sysfs attributes.
- [`Documentation/ABI/testing/sysfs-bus-pci-devices-aer`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci-devices-aer): the per-device AER counters and ratelimit attributes that the printer updates and consults.
- [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst): the driver callbacks the recovery stage calls for the two uncorrectable classes.
- [`Documentation/firmware-guide/acpi/apei/output_format.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/firmware-guide/acpi/apei/output_format.rst): the format in which APEI prints a record, including the PCIe error section and its AER fields.
- [`Documentation/firmware-guide/acpi/apei/einj.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/firmware-guide/acpi/apei/einj.rst): the APEI error injection interface, which asks firmware to raise an error, a PCIe one named by its segment, bus, device and function among them.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/AER: Simplify AER_RECOVER_RING_SIZE definition (commit 95881c86c987)](https://lore.kernel.org/r/20230824193712.542167-7-helgaas@kernel.org)
- [PCI/AER: Refactor cper_print_aer() for use by CXL driver module (commit 6777877eb7a3)](https://lore.kernel.org/r/20231018171713.1883517-13-rrichter@amd.com)
- [PCI: Add TLP Prefix reading to pcie_read_tlp_log() (commit ad41ddeeac21)](https://lore.kernel.org/r/20250114170840.1633-8-ilpo.jarvinen@linux.intel.com)
- [PCI/ERR: Handle TLP Log in Flit mode (commit 7e077e6707b3)](https://lore.kernel.org/r/20250207161836.2755-3-ilpo.jarvinen@linux.intel.com)
- [PCI/AER: Update statistics before ratelimiting (commit 88a7765e62b9)](https://patch.msgid.link/20250522232339.1525671-11-helgaas@kernel.org)
- [PCI/AER: Trace error event before ratelimiting (commit 6bb4befbd65f)](https://patch.msgid.link/20250522232339.1525671-12-helgaas@kernel.org)
- [PCI/AER: Reduce pci_print_aer() correctable error level to KERN_WARNING (commit 36c5932074aa)](https://patch.msgid.link/20250522232339.1525671-15-helgaas@kernel.org)
- [PCI/AER: Ratelimit correctable and non-fatal error logging (commit a57f2bfb4a58)](https://patch.msgid.link/20250522232339.1525671-19-helgaas@kernel.org)
- [PCI/AER: Print TLP Log for errors introduced since PCIe r1.1 (commit c8ab5e888bb6)](https://patch.msgid.link/5f707caf1260bd8f15012bb032f7da9a9b898aba.1756712066.git.lukas@wunner.de)
- [PCI/ERR: Remove service dependency in pcie_do_recovery() (commit b6cf1a42f916)](https://lore.kernel.org/r/60e02b87b526cdf2930400059d98704bf0a147d1.1585000084.git.sathyanarayanan.kuppuswamy@linux.intel.com)
- [ACPI: extlog: Trace CPER PCI Express Error Section (commit e778ffefa34d)](https://patch.msgid.link/20260114101543.85926-3-fabio.m.de.francesco@linux.intel.com)

## REGISTERS

The firmware's record carries a copy of a function's AER capability, and the kernel reads that copy, which stands in for the registers, so the registers drawn here are the ones whose values reach [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) through [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41). The capability starts with the extended capability header and places each register at the offset [`PCI_ERR_UNCOR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L772) and its neighbours in include/uapi/linux/pci_regs.h give.

```text
    The AER capability, by the offsets pci_regs.h gives its registers
    ─────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x00  │      next (31:20)     │  ver  │      capability ID (15:0)     │
          ├───────────────────────┴───────┴───────────────────────────────┤
    0x04  │                   Uncorrectable Error Status                  │
          ├───────────────────────────────────────────────────────────────┤
    0x08  │                    Uncorrectable Error Mask                   │
          ├───────────────────────────────────────────────────────────────┤
    0x0c  │                  Uncorrectable Error Severity                 │
          ├───────────────────────────────────────────────────────────────┤
    0x10  │                    Correctable Error Status                   │
          ├───────────────────────────────────────────────────────────────┤
    0x14  │                     Correctable Error Mask                    │
          ├───────────────────────────────────────────────────────────────┤
    0x18  │            Advanced Error Capabilities and Control            │
          ├───────────────────────────────────────────────────────────────┤
    0x1c  │                      Header Log, dword 0                      │
          ├───────────────────────────────────────────────────────────────┤
    0x20  │                      Header Log, dword 1                      │
          ├───────────────────────────────────────────────────────────────┤
    0x24  │                      Header Log, dword 2                      │
          ├───────────────────────────────────────────────────────────────┤
    0x28  │                      Header Log, dword 3                      │
          ├───────────────────────────────────────────────────────────────┤
    0x2c  │                       Root Error Command                      │
          ├───────────────────────────────────────────────────────────────┤
    0x30  │                       Root Error Status                       │
          ├───────────────────────────────┬───────────────────────────────┤
    0x34  │    uncorrectable source ID    │     correctable source ID     │
          ├───────────────────────────────┴───────────────────────────────┤
    0x38  │                    TLP Prefix Log, dword 0                    │
          ├───────────────────────────────────────────────────────────────┤
    0x3c  │                    TLP Prefix Log, dword 1                    │
          ├───────────────────────────────────────────────────────────────┤
    0x40  │                    TLP Prefix Log, dword 2                    │
          ├───────────────────────────────────────────────────────────────┤
    0x44  │                    TLP Prefix Log, dword 3                    │
          └───────────────────────────────────────────────────────────────┘

    ID, ver, next = PCI_EXT_CAP_ID(), PCI_EXT_CAP_VER(), PCI_EXT_CAP_NEXT(); ID is PCI_EXT_CAP_ID_ERR (0x01)
    Uncorrectable Error Status, Mask, Severity = PCI_ERR_UNCOR_STATUS, PCI_ERR_UNCOR_MASK, PCI_ERR_UNCOR_SEVER
    Correctable Error Status, Mask = PCI_ERR_COR_STATUS, PCI_ERR_COR_MASK
    Advanced Error Capabilities and Control = PCI_ERR_CAP; Header Log = PCI_ERR_HEADER_LOG (16 bytes)
    Root Error Command, Root Error Status = PCI_ERR_ROOT_COMMAND, PCI_ERR_ROOT_STATUS
    source IDs = PCI_ERR_ROOT_ERR_SRC, split by ERR_COR_ID() and ERR_UNCOR_ID() of aer.c
    TLP Prefix Log = PCI_ERR_PREFIX_LOG (up to 16 bytes)
    members header to header_log.dw[3] of struct aer_capability_regs sit at the offsets 0x00 to 0x28
```

The members of [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41) from [`header`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L42) through the first four dwords of [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49) lie at the same offsets as the registers above, so the printer's reads of status, mask, severity, control and the four header dwords land on the registers they name. The Root Port registers at [`PCI_ERR_ROOT_COMMAND`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L822) and after, and the TLP Prefix Log at [`PCI_ERR_PREFIX_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L836), fall under other members of the structure, which DETAILS draws beside the copy that creates the mismatch.

The status registers decide what the printer says. A set bit of Uncorrectable Error Status that the mask at [`PCI_ERR_UNCOR_MASK`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L796) leaves unmasked is counted, traced and printed by name, and the bit decides whether a logged TLP header is printed and which agent and layer the message names.

```text
    Uncorrectable Error Status at cap + 0x04, the bits pci_print_aer names
    ──────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │N│Y│Z│C│W│K│L│G│B│I│V│R│E│M│O│X│A│T│F│P│·│·│·│·│·│·│S│D│·│·│·│U│
          └┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴─┴─┴─┴─┴─┴─┴┬┴┬┴─┴─┴─┴┬┘
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             │ │       │
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             │ │       └─── U = PCI_ERR_UNC_UND (0)
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             │ └─────────── D = PCI_ERR_UNC_DLP (4), Data Link Layer
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │             └───────────── S = PCI_ERR_UNC_SURPDN (5)
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────── P = PCI_ERR_UNC_POISON_TLP (12), header
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────── F = PCI_ERR_UNC_FCP (13)
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────── T = PCI_ERR_UNC_COMP_TIME (14)
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────────── A = PCI_ERR_UNC_COMP_ABORT (15), header
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────────── X = PCI_ERR_UNC_UNX_COMP (16), header
           │ │ │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────────────── O = PCI_ERR_UNC_RX_OVER (17)
           │ │ │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────────────── M = PCI_ERR_UNC_MALF_TLP (18), header
           │ │ │ │ │ │ │ │ │ │ │ │ └───────────────────────────────────────── E = PCI_ERR_UNC_ECRC (19), header
           │ │ │ │ │ │ │ │ │ │ │ └─────────────────────────────────────────── R = PCI_ERR_UNC_UNSUP (20), header
           │ │ │ │ │ │ │ │ │ │ └───────────────────────────────────────────── V = PCI_ERR_UNC_ACSV (21), header
           │ │ │ │ │ │ │ │ │ └─────────────────────────────────────────────── I = PCI_ERR_UNC_INTN (22)
           │ │ │ │ │ │ │ │ └───────────────────────────────────────────────── B = PCI_ERR_UNC_MCBTLP (23), header
           │ │ │ │ │ │ │ └─────────────────────────────────────────────────── G = PCI_ERR_UNC_ATOMEG (24), header
           │ │ │ │ │ │ └───────────────────────────────────────────────────── L = PCI_ERR_UNC_TLPPRE (25), header
           │ │ │ │ │ └─────────────────────────────────────────────────────── K = PCI_ERR_UNC_POISON_BLK (26), header
           │ │ │ │ └───────────────────────────────────────────────────────── W = PCI_ERR_UNC_DMWR_BLK (27), header
           │ │ │ └─────────────────────────────────────────────────────────── C = PCI_ERR_UNC_IDE_CHECK (28), header
           │ │ └───────────────────────────────────────────────────────────── Z = PCI_ERR_UNC_MISR_IDE (29), header
           │ └─────────────────────────────────────────────────────────────── Y = PCI_ERR_UNC_PCRC_CHECK (30), header
           └───────────────────────────────────────────────────────────────── N = PCI_ERR_UNC_XLAT_BLK (31), header

    the same bits form the Uncorrectable Error Mask (cap + 0x08) and Severity (cap + 0x0c) registers
    pci_print_aer reads uncor_status, masked by uncor_mask, and prints uncor_severity whole
    header = a bit of AER_LOG_TLP_MASKS, for which tlp_header_logged() reports a logged TLP header;
             T reports one only with PCI_ERR_CAP_COMP_TIME_LOG set in the control register
    agent: T and R report the requester, A the completer, every other bit the receiver (AER_GET_AGENT)
    layer: D reports the Data Link Layer, every other bit the Transaction Layer (AER_GET_LAYER_ERROR)
    bits 1 to 3 and 6 to 11 have no macro in pci_regs.h
```

Correctable errors use the Correctable Error Status register at [`PCI_ERR_COR_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L800) and its mask, with fewer bits and no header log.

```text
    Correctable Error Status at cap + 0x10, the bits pci_print_aer names
    ────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │O│I│A│M│·│·│·│N│D│T│·│·│·│·│·│R│
          └┬┴┬┴┬┴┬┴─┴─┴─┴┬┴┬┴┬┴─┴─┴─┴─┴─┴┬┘
           │ │ │ │       │ │ │           │
           │ │ │ │       │ │ │           └─── R = PCI_ERR_COR_RCVR (0), Physical Layer
           │ │ │ │       │ │ └─────────────── T = PCI_ERR_COR_BAD_TLP (6), Data Link Layer
           │ │ │ │       │ └───────────────── D = PCI_ERR_COR_BAD_DLLP (7), Data Link Layer
           │ │ │ │       └─────────────────── N = PCI_ERR_COR_REP_ROLL (8), Data Link Layer
           │ │ │ └─────────────────────────── M = PCI_ERR_COR_REP_TIMER (12), Data Link Layer
           │ │ └───────────────────────────── A = PCI_ERR_COR_ADV_NFAT (13)
           │ └─────────────────────────────── I = PCI_ERR_COR_INTERNAL (14)
           └───────────────────────────────── O = PCI_ERR_COR_LOG_OVER (15)

    the same bits form the Correctable Error Mask register at cap + 0x14
    pci_print_aer reads cor_status, masked by cor_mask
    layer: as noted beside each bit, every other bit the Transaction Layer (AER_GET_LAYER_ERROR)
    agent: N and M report the transmitter, every other bit the receiver (AER_GET_AGENT)
    bits 31:16 have no macro in pci_regs.h and are not drawn; bits 1 to 5 and 9 to 11 have none either
```

The Advanced Error Capabilities and Control register at [`PCI_ERR_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L811) supplies two values on this path, the First Error Pointer that marks one status bit "(First)" in the printout, and the Completion Timeout logging bit that lets a Completion Timeout count as an error with a logged header.

```text
    Advanced Error Capabilities and Control at cap + 0x18, the fields this path reads
    ─────────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │    no macro   │   SIZE  │F│ no macro│C│P│ · │  ECRC │   FEP   │
          │    (31:24)    │ (23:19) │ │ (17:13) │ │ │   │ (8:5) │  (4:0)  │
          └───────────────┴─────────┴─┴─────────┴─┴─┴───┴───────┴─────────┘

    FEP = PCI_ERR_CAP_FEP() (First Error Pointer), copied into the first_error of struct aer_err_info
    C = PCI_ERR_CAP_COMP_TIME_LOG (0x00001000), read by tlp_header_logged() for a Completion Timeout
    P = PCI_ERR_CAP_PREFIX_LOG_PRESENT (0x00000800); F = PCI_ERR_CAP_TLP_LOG_FLIT (0x00040000)
    SIZE = PCI_ERR_CAP_TLP_LOG_SIZE (0x00f80000); ECRC = PCI_ERR_CAP_ECRC_GENC, _GENE, _CHKC, _CHKE (bits 5 to 8)
    P, F and SIZE are read on the native path only; the firmware path reads cap_control for FEP and C
    the register is held in cap_control of struct aer_capability_regs; bits 9, 10 and 13 to 17 have no macro
```

[`PCI_ERR_CAP_FEP()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L812) masks the low five bits of the control word into a bit number, which [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) stores in [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846). The other fields size the TLP log that the kernel reads from the registers when it owns AER, and the firmware path, which receives the log already copied, reads none of them.

## DETAILS

DETAILS first shows how the kernel gives up the AER registers of a host bridge to firmware, and how the GHES handler then receives a PCIe error section with interrupts disabled. It reads the section's layout, the register dump it carries and the mapping of its severity onto the three AER classes, and then follows the GHES handler as it copies the dump and queues a report. The ring of reports, the queueing under its lock and the work function that drains it come next, followed by the printer, its ratelimit and the hand-off to error recovery. The last subsections cover the two branches that drop a report, the configuration option that removes the path, and the messages, tracepoints, hand-offs and files that make the path visible.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at the pinned v7.2 commit with the options of this campaign added, on x86-64 with ACPI, and it assumes the three APEI options that the defconfig leaves unset and without which the path does not exist. The table indexes the options the prose names, with the value the page assumes.

| Option | Assumed value | What it decides on these paths |
|---|---|---|
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | builds the ACPI host-bridge code that clears [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) when `_OSC` withholds AER control |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds the port driver, whose AER service a clear [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) leaves out |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | builds aer.c with [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) and [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667); a dependency of [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) |
| [`CONFIG_ACPI_APEI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L8) | y, set by hand | the APEI core, the other dependency of [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) |
| [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20) | y, set by hand | builds ghes.c with [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) and the pool its regions come from |
| [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) | y, set by hand | builds the ring, [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263), [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218), [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912) and the body of [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) |
| [`CONFIG_HAVE_ACPI_APEI_NMI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L5) | y, selected by x86 with ACPI | lets a GHES source notify through an NMI, whose records reach the PCI core from irq_work |
| [`CONFIG_VMCORE_INFO`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.kexec#L8) | y | makes the non-fatal branch of the counters also record the error for crash-dump tooling |
| [`CONFIG_PCI_DOMAINS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L32) | y, selected by x86 with PCI | compiles the x86 [`pci_domain_nr()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/include/asm/pci.h#L43) that the lookup compares the record's segment with |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the `pci_dbg()` sites of the recovery stage switchable at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | unset | would turn those sites on unconditionally |
| [`CONFIG_ACPI_EXTLOG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L494) | unset | the extended error log driver, whose PCIe printer compiles to an empty body whatever its value |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | unset | the AER error injector, which needs the AER service that this path lacks |
| [`CONFIG_ACPI_APEI_EINJ`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L56) | unset | the APEI error injector, which asks firmware to raise an error |

The table only indexes the prose, and each option's effect is stated again, with the option named, in the subsection where it applies.

### Firmware keeps the AER registers when `_OSC` withholds control

Reporting an AER error means reading a function's status registers and clearing them, so the kernel and the platform firmware cannot both do it. The PCI core assumes the kernel owns the registers, and an ACPI platform that keeps them for itself refuses AER control when the kernel asks for it through the `_OSC` method of the host bridge. The bit [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) of the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) records the outcome, and the AER paths of this page test it.

[`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659) sets up a host bridge right after the PCI core allocates it, and its stage below sets the AER bit before any platform code has looked at the bridge. Read its comment for the reason the bit can be taken away later.

```c
/* drivers/pci/probe.c:659 */
static void pci_init_host_bridge(struct pci_host_bridge *bridge)
{
	INIT_LIST_HEAD(&bridge->windows);
	INIT_LIST_HEAD(&bridge->dma_ranges);
	INIT_LIST_HEAD(&bridge->ports);

	/*
	 * We assume we can manage these PCIe features.  Some systems may
	 * reserve these for use by the platform itself, e.g., an ACPI BIOS
	 * may implement its own AER handling and use _OSC to prevent the
	 * OS from interfering.
	 */
	bridge->native_aer = 1;
```

The bridge starts out claiming AER for the kernel, together with the other PCIe services set beside it. According to the comment, "an ACPI BIOS may implement its own AER handling and use _OSC to prevent the OS from interfering". On x86 that refusal reaches the bit in [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995), the function of the [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) host-bridge code that builds the root bus of an ACPI host bridge, and its stage below clears [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) when [`OSC_PCI_EXPRESS_AER_CONTROL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/acpi.h#L643) is missing from the controls the firmware granted.

```c
/* drivers/acpi/pci_root.c:995 */
struct pci_bus *acpi_pci_root_create(struct acpi_pci_root *root,
				     struct acpi_pci_root_ops *ops,
				     struct acpi_pci_root_info *info,
				     void *sysdata)
{
	... /* 29 lines, to :1029 */
	host_bridge = to_pci_host_bridge(bus->bridge);
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_NATIVE_HP_CONTROL))
		host_bridge->native_pcie_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_SHPC_NATIVE_HP_CONTROL))
		host_bridge->native_shpc_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_AER_CONTROL))
		host_bridge->native_aer = 0;
```

The test reads the granted controls one bit at a time, so firmware can keep AER while it grants native hotplug or PME, which the neighbouring lines handle the same way. Every device below the bridge inherits the outcome, because the AER code finds the bridge from each device's bus. [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) decides which services the port driver of [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) creates for a port, and its stage below shows the bit deciding the AER service.

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
```

A Root Port, a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose type is [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488), or a Root Complex Event Collector of type [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494), gets the AER service only when the kernel owns AER, through the bridge bit or through [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), which the last subsection traces to its boot parameter. With the bit clear and no override, no AER interrupt handler exists for the port, and the two outcomes then differ in who reads the registers and in how an error reaches the PCI core.

```text
    Two owners of a Root Port's AER registers, chosen per host bridge
    ─────────────────────────────────────────────────────────────────

    _OSC granted AER control:                           _OSC left AER control with firmware:
    native_aer set, or pcie_ports=native                native_aer clear, no pcie_ports=native

    ┌───────────────────────────────────────┐           ┌───────────────────────────────────────────┐
    │ portdrv adds the AER port service     │           │ no AER port service on the Root Port      │
    │ the AER interrupt reaches the kernel  │           │ the error is signaled to firmware         │
    └───────────────────┬───────────────────┘           └─────────────────────┬─────────────────────┘
                        │ reads and clears                                    │ firmware reads and clears
                        │                                                     │
                        ▼                                                     ▼
    ┌───────────────────────────────────────┐           ┌───────────────────────────────────────────┐
    │ AER capability registers              │           │ AER capability registers                  │
    └───────────────────────────────────────┘           └─────────────────────┬─────────────────────┘
                                                                              │ CPER record, GHES notification
                                                                              │
                                                                              ▼
                                                        ┌───────────────────────────────────────────┐
                                                        │ the PCIe error section, handed to         │
                                                        │ the PCI core by the GHES handler          │
                                                        └───────────────────────────────────────────┘
```

On the right-hand side the kernel takes no AER interrupt on the port, and it learns about an error only from the record that firmware builds, which the next subsection follows into the kernel.

### GHES hands the PCIe section over with interrupts disabled

Firmware that keeps AER reads the registers when an error is signaled and writes a hardware error record into the error status block of a Generic Hardware Error Source, then notifies the kernel. The help text of [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20) names this arrangement the firmware-first mode, and its kernel side is drivers/acpi/apei/ghes.c, which this page follows only as far as the hand-over of a PCIe section.

```c
/* drivers/acpi/apei/Kconfig:20 */
config ACPI_APEI_GHES
	bool "APEI Generic Hardware Error Source"
	depends on ACPI_APEI
	select ACPI_HED
	select IRQ_WORK
	select GENERIC_ALLOCATOR
	select ARM_SDE_INTERFACE if ARM64
	help
	  Generic Hardware Error Source provides a way to report
	  platform hardware errors (such as that from chipset). It
	  works in so called "Firmware First" mode, that is, hardware
	  errors are reported to firmware firstly, then reported to
	  Linux by firmware. This way, some non-standard hardware
	  error registers or non-standard hardware link can be checked
	  by firmware to produce more valuable hardware error
	  information for Linux.
```

A record is a Common Platform Error Record made of sections, each typed by a GUID, and a PCIe error travels as a section of type [`CPER_SEC_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L201). [`ghes_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1663) attaches each error source to the notification its firmware table declares, and its stage below is the switch that chooses how the kernel hears about a new record.

```c
/* drivers/acpi/apei/ghes.c:1663 */
static int ghes_probe(struct platform_device *ghes_dev)
{
	struct acpi_hest_generic *generic;
	... /* 63 lines, to :1729 */
	switch (generic->notify.type) {
	case ACPI_HEST_NOTIFY_POLLED:
		timer_setup(&ghes->timer, ghes_poll_func, 0);
		ghes_add_timer(ghes);
		break;
	case ACPI_HEST_NOTIFY_EXTERNAL:
		/* External interrupt vector is GSI */
		rc = acpi_gsi_to_irq(generic->notify.vector, &ghes->irq);
		if (rc) {
			pr_err(GHES_PFX "Failed to map GSI to IRQ for generic hardware error source: %d\n",
			       generic->header.source_id);
			goto err;
		}
		rc = request_irq(ghes->irq, ghes_irq_func, IRQF_SHARED,
				 "GHES IRQ", ghes);
		if (rc) {
			pr_err(GHES_PFX "Failed to register IRQ for generic hardware error source: %d\n",
			       generic->header.source_id);
			goto err;
		}
		break;

	case ACPI_HEST_NOTIFY_SCI:
	case ACPI_HEST_NOTIFY_GSIV:
	case ACPI_HEST_NOTIFY_GPIO:
		mutex_lock(&ghes_list_mutex);
		if (list_empty(&ghes_hed))
			register_acpi_hed_notifier(&ghes_notifier_hed);
		list_add_rcu(&ghes->list, &ghes_hed);
		mutex_unlock(&ghes_list_mutex);
		break;

	case ACPI_HEST_NOTIFY_SEA:
		rc = ghes_sea_add(ghes);
		if (rc)
			goto err;
		break;
	case ACPI_HEST_NOTIFY_NMI:
		rc = ghes_nmi_add(ghes);
		if (rc)
			goto err;
		break;
```

An x86 platform uses the polled, external-interrupt, SCI, GSIV, GPIO and NMI types. The NMI type is compiled because the x86 Kconfig selects [`CONFIG_HAVE_ACPI_APEI_NMI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L5) whenever ACPI is set, on the second line of the unit below.

```c
/* arch/x86/Kconfig:188 */
	select HAVE_ACPI_APEI			if ACPI
	select HAVE_ACPI_APEI_NMI		if ACPI
```

The first line lets [`CONFIG_ACPI_APEI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L8) be chosen on x86 at all, since that option depends on it. The SEA and software-delegated types of the switch serve arm64 platforms and are left out here. Each x86 type other than NMI ends in [`ghes_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1176), which reads the record out of the status block, prints it and passes it to [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912).

```c
/* drivers/acpi/apei/ghes.c:1176 */
static int ghes_proc(struct ghes *ghes)
{
	struct acpi_hest_generic_status *estatus = ghes->estatus;
	u64 buf_paddr;
	int rc;

	rc = ghes_read_estatus(ghes, estatus, &buf_paddr, FIX_APEI_GHES_IRQ);
	if (rc)
		goto out;

	if (ghes_severity(estatus->error_severity) >= GHES_SEV_PANIC)
		__ghes_panic(ghes, estatus, buf_paddr, FIX_APEI_GHES_IRQ);

	if (!ghes_estatus_cached(estatus)) {
		if (ghes_print_estatus(NULL, ghes->generic, estatus))
			ghes_estatus_cache_add(ghes->generic, estatus);
	}
	ghes_do_proc(ghes, estatus);

out:
	ghes_clear_estatus(ghes, estatus, buf_paddr, FIX_APEI_GHES_IRQ);

	return rc;
}
```

The record is printed through [`ghes_print_estatus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1005) before the PCI core sees any of it, a printout the observability subsection returns to, and the status block is released at `out` whatever the processing did. A record whose overall severity is fatal stops earlier, in the panic call right after the read, as the severity subsection shows. [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912) visits the sections of the record and dispatches on each section's type, and its stage below shows the loop and the branch for a PCIe section.

```c
/* drivers/acpi/apei/ghes.c:912 */
static void ghes_do_proc(struct ghes *ghes,
			 const struct acpi_hest_generic_status *estatus)
{
	int sev, sec_sev;
	struct acpi_hest_generic_data *gdata;
	guid_t *sec_type;
	const guid_t *fru_id = &guid_null;
	char *fru_text = "";
	bool queued = false;
	bool sync = is_hest_sync_notify(ghes);

	sev = ghes_severity(estatus->error_severity);
	apei_estatus_for_each_section(estatus, gdata) {
		sec_type = (guid_t *)gdata->section_type;
		sec_sev = ghes_severity(gdata->error_severity);
		... /* 6 lines, to :933 */
		ghes_log_hwerr(sev, sec_type);
		if (guid_equal(sec_type, &CPER_SEC_PLATFORM_MEM)) {
			struct cper_sec_mem_err *mem_err = acpi_hest_get_payload(gdata);

			atomic_notifier_call_chain(&ghes_report_chain, sev, mem_err);

			arch_apei_report_mem_error(sev, mem_err);
			queued = ghes_handle_memory_failure(gdata, sev, sync);
		} else if (guid_equal(sec_type, &CPER_SEC_PCIE)) {
			ghes_handle_aer(gdata);
```

A PCIe section goes to [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) together with `gdata`, the loop's pointer to the section's [`struct acpi_hest_generic_data`](https://elixir.bootlin.com/linux/v7.2/source/include/acpi/actbl1.h#L1936) header, which carries the section's severity and flags in front of its payload. The same loop then continues with the next section, so one record can hand several PCIe sections to the PCI core in a row.

The context of that call constrains everything the PCI core does with a section. At v7.2 [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912) has two callers, [`ghes_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1176) and [`ghes_proc_in_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1278), and the table lists the five ways a record reaches it on x86 with the line that sets the context.

| Caller | How it runs | Context of the call |
|---|---|---|
| [`ghes_irq_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1228) | the interrupt handler of an external-interrupt source | [`ghes.c:1234-1236`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1234), `ghes_notify_lock_irq` held, interrupts disabled |
| [`ghes_poll_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1216) | the timer callback of a polled source | [`ghes.c:1221-1223`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1221), the same lock and interrupt state |
| [`ghes_notify_hed()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1243) | the notifier the Hardware Error Device calls for SCI, GSIV and GPIO sources | [`ghes.c:1250-1255`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1250), the same lock and interrupt state |
| [`ghes_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1663) | the probe of an error source, for a record already pending | [`ghes.c:1789-1791`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1789), the same lock and interrupt state |
| [`ghes_proc_in_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1278) | the irq_work callback for records an NMI handler queued | [`ghes.c:1300`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1300), IRQ context |

The NMI type defers its records once more, because, in the words of the comment above [`ghes_proc_in_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1278), the handlers for records "may not be NMI safe". The stage below shows that comment and the loop that hands each queued record to [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912).

```c
/* drivers/acpi/apei/ghes.c:1264 */
/*
 * Handlers for CPER records may not be NMI safe. For example,
 * memory_failure_queue() takes spinlocks and calls schedule_work_on().
 * In any NMI-like handler, memory from ghes_estatus_pool is used to save
 * estatus, and added to the ghes_estatus_llist. irq_work_queue() causes
 * ghes_proc_in_irq() to run in IRQ context where each estatus in
 * ghes_estatus_llist is processed.
 *
 * Memory from the ghes_estatus_pool is also used with the ghes_estatus_cache
 * to suppress frequent messages.
 */
static struct llist_head ghes_estatus_llist;
static struct irq_work ghes_proc_irq_work;

static void ghes_proc_in_irq(struct irq_work *irq_work)
{
	struct llist_node *llnode, *next;
	struct ghes_estatus_node *estatus_node;
	struct acpi_hest_generic *generic;
	struct acpi_hest_generic_status *estatus;
	u32 len, node_len;

	llnode = llist_del_all(&ghes_estatus_llist);
	/*
	 * Because the time order of estatus in list is reversed,
	 * revert it back to proper order.
	 */
	llnode = llist_reverse_order(llnode);
	while (llnode) {
		next = llnode->next;
		estatus_node = llist_entry(llnode, struct ghes_estatus_node,
					   llnode);
		estatus = GHES_ESTATUS_FROM_NODE(estatus_node);
		len = cper_estatus_len(estatus);
		node_len = GHES_ESTATUS_NODE_LEN(len);

		ghes_do_proc(estatus_node->ghes, estatus);
```

According to the comment, an NMI handler saves the record in memory from [`ghes_estatus_pool`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L174) and queues `ghes_proc_irq_work`, and the callback above takes the queued records back in their original order and processes each in IRQ context. The figure gathers the five ways in, with the context each one leaves the dispatch in.

```text
    How a record reaches the section dispatch on x86, and the context it runs in
    ────────────────────────────────────────────────────────────────────────────

    notification type         kernel entry                  common step                 context

    polled ─────────────────▶ timer callback ──────┐       ┌────────────────────────┐   spinlock held,
    external interrupt ─────▶ interrupt handler ───┼──────▶│ record read, printed   │   interrupts off
    SCI, GSIV, GPIO ────────▶ HED notifier ────────┤       └───────────┬────────────┘
    pending at probe ───────▶ device probe ────────┘                   │
                                                                       │
                                                                       ▼
                                                           ┌────────────────────────┐
                                                           │ sections dispatched    │
                                                           └────────────────────────┘
                                                                       ▲
                                                           ┌───────────┴────────────┐
    NMI ────────────────────▶ NMI handler: record ────────▶│ irq_work callback      │   IRQ context
                              saved, irq_work queued       └────────────────────────┘

    a fatal record panics in the common step or in the NMI handler, before any section is dispatched
```

Whichever way it arrived, the PCI core receives a PCIe section with interrupts disabled on the CPU that took the notification, and it can neither sleep nor call a driver there.

### The section names the function and carries its AER registers

The PCI core needs the address of the function that reported the error and the values its AER registers held, and a PCIe error section carries both. [`struct cper_sec_pcie`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L536) is the layout of the section's payload, and each part of it counts only when its bit in [`validation_bits`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L537) is set. Read the definition for where the address and the register dump are placed.

```c
/* include/linux/cper.h:535 */
/* PCI Express Error Section, UEFI v2.7 sec N.2.7 */
struct cper_sec_pcie {
	u64		validation_bits;
	u32		port_type;
	struct {
		u8	minor;
		u8	major;
		u8	reserved[2];
	}		version;
	u16		command;
	u16		status;
	u32		reserved;
	struct {
		u16	vendor_id;
		u16	device_id;
		u8	class_code[3];
		u8	function;
		u8	device;
		u16	segment;
		u8	bus;
		u8	secondary_bus;
		u16	slot;
		u8	reserved;
	}		device_id;
	struct {
		u32	lower;
		u32	upper;
	}		serial_number;
	struct {
		u16	secondary_status;
		u16	control;
	}		bridge;
	u8	capability[60];
	u8	aer_info[96];
};
```

[`device_id`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L558) is the address and identity of the function, its PCI segment in [`segment`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L553), its bus number in [`bus`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L554), and its device and function numbers in [`device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L552) and [`function`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L551), beside the vendor, device and class identifiers. [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568) is a 96-byte dump of the function's AER capability, and it is the last member of the 208-byte structure. The members between them, the port type, the version, the Command and Status values, the serial number, the bridge registers and the 60-byte capability array, stay unread on this path. The two validation bits this path requires are defined beside the others for the section.

```c
/* include/linux/cper.h:273 */
#define CPER_PCIE_VALID_PORT_TYPE		0x0001
#define CPER_PCIE_VALID_VERSION			0x0002
#define CPER_PCIE_VALID_COMMAND_STATUS		0x0004
#define CPER_PCIE_VALID_DEVICE_ID		0x0008
#define CPER_PCIE_VALID_SERIAL_NUMBER		0x0010
#define CPER_PCIE_VALID_BRIDGE_CONTROL_STATUS	0x0020
#define CPER_PCIE_VALID_CAPABILITY		0x0040
#define CPER_PCIE_VALID_AER_INFO		0x0080
```

[`CPER_PCIE_VALID_DEVICE_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L276), bit 3, says that [`device_id`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L558) is filled in, and [`CPER_PCIE_VALID_AER_INFO`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L280), bit 7, says the same of [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568). A section without both carries nothing the PCI core can attribute or print, and the GHES handler drops it, as the producer subsection shows.

The readers of [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568) on this path cast it to [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41), declared in include/linux/aer.h after the TLP log structure it embeds. Read the unit below for the members and their sizes, since the length of the copy and the position of each member follow from them.

```c
/* include/linux/aer.h:19 */
/*
 * AER and DPC capabilities TLP Logging register sizes (PCIe r6.2, sec 7.8.4
 * & 7.9.14).
 */
#define PCIE_STD_NUM_TLP_HEADERLOG     4
#define PCIE_STD_MAX_TLP_PREFIXLOG     4
#define PCIE_STD_MAX_TLP_HEADERLOG	(PCIE_STD_NUM_TLP_HEADERLOG + 10)

struct pci_dev;

struct pcie_tlp_log {
	union {
		u32 dw[PCIE_STD_MAX_TLP_HEADERLOG];
		struct {
			u32 _do_not_use[PCIE_STD_NUM_TLP_HEADERLOG];
			u32 prefix[PCIE_STD_MAX_TLP_PREFIXLOG];
		};
	};
	u8 header_len;		/* Length of the Logged TLP Header in DWORDs */
	bool flit;		/* TLP was logged when in Flit mode */
};

struct aer_capability_regs {
	u32 header;
	u32 uncor_status;
	u32 uncor_mask;
	u32 uncor_severity;
	u32 cor_status;
	u32 cor_mask;
	u32 cap_control;
	struct pcie_tlp_log header_log;
	u32 root_command;
	u32 root_status;
	u16 cor_err_source;
	u16 uncor_err_source;
};
```

The first seven members are dwords named after the registers at the head of the AER capability, from the extended capability [`header`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L42) through [`uncor_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L43), [`uncor_mask`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L44), [`uncor_severity`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L45), [`cor_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L46) and [`cor_mask`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L47) to [`cap_control`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L48). [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49) is a [`struct pcie_tlp_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L29), whose [`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31) array holds [`PCIE_STD_MAX_TLP_HEADERLOG`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L25), fourteen, dwords and overlays [`prefix`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L34) on its fifth to eighth, followed by [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) and [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38). [`root_command`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L50), [`root_status`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L51), [`cor_err_source`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L52) and [`uncor_err_source`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L53) close the structure with the Root Port registers.

The sizes add up to 100 bytes on x86-64: 28 for the seven dwords, 60 for the TLP log with its two trailing bytes padded to a dword, 8 for the two root registers and 4 for the two 16-bit source identifiers. The structure grew past the 96 bytes of [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568) with commit [7e077e6707b3](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=7e077e6707b3428562ba30d883ff8f54e98dc18b) ("PCI/ERR: Handle TLP Log in Flit mode"), which turned [`dw`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L31) into fourteen dwords. When the kernel owns AER it fills the TLP log from two register ranges, and [`pcie_read_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L63) shows where the dwords after the fourth come from.

```c
/* drivers/pci/pcie/tlp.c:63 */
int pcie_read_tlp_log(struct pci_dev *dev, int where, int where2,
		      unsigned int tlp_len, bool flit, struct pcie_tlp_log *log)
{
	unsigned int i;
	int off, ret;

	if (tlp_len > ARRAY_SIZE(log->dw))
		tlp_len = ARRAY_SIZE(log->dw);

	memset(log, 0, sizeof(*log));

	for (i = 0; i < tlp_len; i++) {
		if (i < PCIE_STD_NUM_TLP_HEADERLOG)
			off = where + i * 4;
		else
			off = where2 + (i - PCIE_STD_NUM_TLP_HEADERLOG) * 4;

		ret = pci_read_config_dword(dev, off, &log->dw[i]);
		if (ret)
			return pcibios_err_to_errno(ret);
	}
```

The first four dwords come from the Header Log at `where`, a parameter that the native caller sets to the Header Log offset, and every later dword comes from `where2`, the parameter that carries the TLP Prefix Log offset. The structure is therefore a set of values the kernel assembles, and its members after the Header Log follow the order of that assembly. Laid over a byte dump of the capability, those members fall on other registers, as the two views of the copied bytes show.

```text
    The bytes the GHES handler copies, by register offset and by struct member
    ──────────────────────────────────────────────────────────────────────────

           aer_info[96], by pci_regs.h          struct aer_capability_regs, 100 bytes
    offset ┌──────────────────────────────┐     ┌─────────────────────────────────────┐
    0x00   │ capability header            │  =  │ header                              │
    0x04   │ Uncorrectable Error Status   │  =  │ uncor_status                        │
    0x08   │ Uncorrectable Error Mask     │  =  │ uncor_mask                          │
    0x0c   │ Uncorrectable Error Severity │  =  │ uncor_severity                      │
    0x10   │ Correctable Error Status     │  =  │ cor_status                          │
    0x14   │ Correctable Error Mask       │  =  │ cor_mask                            │
    0x18   │ Capabilities and Control     │  =  │ cap_control                         │
    0x1c   │ Header Log, dword 0          │  =  │ header_log.dw[0]                    │
    0x20   │ Header Log, dword 1          │  =  │ header_log.dw[1]                    │
    0x24   │ Header Log, dword 2          │  =  │ header_log.dw[2]                    │
    0x28   │ Header Log, dword 3          │  =  │ header_log.dw[3]                    │
           ├──────────────────────────────┤     ├─────────────────────────────────────┤
    0x2c   │ Root Error Command           │  ≠  │ header_log.prefix[0], dw[4]         │
    0x30   │ Root Error Status            │  ≠  │ header_log.prefix[1], dw[5]         │
    0x34   │ Error Source Identification  │  ≠  │ header_log.prefix[2], dw[6]         │
    0x38   │ TLP Prefix Log, dword 0      │  ≠  │ header_log.prefix[3], dw[7]         │
    0x3c   │ TLP Prefix Log, dword 1      │  ≠  │ header_log.dw[8]                    │
    0x40   │ TLP Prefix Log, dword 2      │  ≠  │ header_log.dw[9]                    │
    0x44   │ TLP Prefix Log, dword 3      │  ≠  │ header_log.dw[10]                   │
           ├──────────────────────────────┤     │                                     │
    0x48   │ no register macro            │     │ header_log.dw[11]                   │
    0x4c   │                              │     │ header_log.dw[12]                   │
    0x50   │                              │     │ header_log.dw[13]                   │
    0x54   │                              │     │ header_len, flit, two padding bytes │
    0x58   │                              │     │ root_command                        │
    0x5c   │                              │     │ root_status                         │
           └──────────────────────────────┘     ├─────────────────────────────────────┤ ◀─ aer_info ends at 0x60
    0x60                                        │ cor_err_source, uncor_err_source    │ ◀─ copied from past the array
                                                └─────────────────────────────────────┘

    = the member sits at the register's offset; ≠ it does not; one row is one dword
    pci_print_aer reads members of rows 0x04 to 0x28 itself; trace_aer_event copies dw[0] to dw[13]
    when a header is logged; pcie_print_tlp_log reads flit at 0x55, then prefix[0] to prefix[3],
    or, with flit set, dw[4] up to the header_len at 0x54
```

Every member [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) reads directly lies in the rows where both views agree, so the status, mask, severity, control and the four Header Log dwords it prints are the registers they name. The members past that row read whatever the firmware placed at their offsets, and the last four bytes of the 100 lie past the end of [`struct cper_sec_pcie`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L536), which ends with [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568).

### The section severity becomes one of three AER classes

Firmware grades the section on the CPER scale of severities, while the printer, the counters and recovery act on the three AER classes. The CPER scale is an enumeration in include/linux/cper.h, used for the severity of a whole record and of each section in it.

```c
/* include/linux/cper.h:34 */
/*
 * Severity definition for error_severity in struct cper_record_header
 * and section_severity in struct cper_section_descriptor
 */
enum {
	CPER_SEV_RECOVERABLE,
	CPER_SEV_FATAL,
	CPER_SEV_CORRECTED,
	CPER_SEV_INFORMATIONAL,
};
```

Recoverable is 0, fatal 1, corrected 2 and informational 3, and the GHES code reads the same scale from the [`error_severity`](https://elixir.bootlin.com/linux/v7.2/source/include/acpi/actbl1.h#L1938) of a section's header. The AER classes are plain macros of include/linux/aer.h with their own numbering, in which non-fatal is 0, fatal 1 and correctable 2.

```c
/* include/linux/aer.h:14 */
#define AER_NONFATAL			0
#define AER_FATAL			1
#define AER_CORRECTABLE			2
#define DPC_FATAL			3
```

[`DPC_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L17) is a value the DPC service uses, and the mapping below never produces it. [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912) translates one scale into the other, and it is compiled only with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37), as the preprocessor lines around it show.

```c
/* drivers/pci/pcie/aer.c:911 */
#ifdef CONFIG_ACPI_APEI_PCIEAER
int cper_severity_to_aer(int cper_severity)
{
	switch (cper_severity) {
	case CPER_SEV_RECOVERABLE:
		return AER_NONFATAL;
	case CPER_SEV_FATAL:
		return AER_FATAL;
	default:
		return AER_CORRECTABLE;
	}
}
EXPORT_SYMBOL_GPL(cper_severity_to_aer);
#endif
```

Recoverable becomes [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) and fatal becomes [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15), and the `default` branch makes every other value, corrected, informational or one outside the enumeration, [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16).

A section can also report that the hardware component was reset to contain the error. That is a flag of the section's header, [`CPER_SEC_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L158), defined among the section flags with the meaning its comment gives.

```c
/* include/linux/cper.h:157 */
/* If set, the component must be re-initialized or re-enabled prior to use */
#define CPER_SEC_RESET				0x0004
```

The GHES handler, shown in the next subsection, raises the class to [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) when this flag is set, whatever the severity gave, because a component that firmware reset needs reinitializing before use. The ladder puts the mapping and that override side by side.

```text
    Section severities land on three AER classes, and a reset flag lifts any of them
    ────────────────────────────────────────────────────────────────────────────────

    error_severity of the section                 AER class, ordered
                                                ┌─────────────────────────┐
    CPER_SEV_FATAL         1  ─────────────────▶│ AER_FATAL        1      │◀────┐
                                                ├─────────────────────────┤     │ CPER_SEC_RESET set in the
    CPER_SEV_RECOVERABLE   0  ─────────────────▶│ AER_NONFATAL     0      ├─────┤ section's flags: the class
                                                ├─────────────────────────┤     │ becomes AER_FATAL whatever
    CPER_SEV_CORRECTED     2  ────────────┬────▶│ AER_CORRECTABLE  2      ├─────┘ the severity gave
                                          │     └─────────────────────────┘
    CPER_SEV_INFORMATIONAL 3  ────────────┤
    any other value   ────────────────────┘

    FATAL: recovery with the channel frozen; NONFATAL: recovery with the channel normal;
    CORRECTABLE: the report is printed, counted and traced, and no recovery runs
    the digits are the values of the CPER enum and the AER macros
```

The fatal rung is reached by a section, and the whole record never carries a fatal severity this far. [`ghes_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1176) tests the record's severity right after reading it, and the lines shown again below end in a panic for a record [`ghes_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L324) rates at panic level.

```c
/* drivers/acpi/apei/ghes.c:1176 */
static int ghes_proc(struct ghes *ghes)
{
	struct acpi_hest_generic_status *estatus = ghes->estatus;
	... /* 6 lines, to :1185 */

	if (ghes_severity(estatus->error_severity) >= GHES_SEV_PANIC)
		__ghes_panic(ghes, estatus, buf_paddr, FIX_APEI_GHES_IRQ);
```

The NMI path makes the same test in [`ghes_in_nmi_queue_one_entry()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1337) before it queues a record, so a fatal record does not reach the irq_work callback either.

```c
/* drivers/acpi/apei/ghes.c:1337 */
static int ghes_in_nmi_queue_one_entry(struct ghes *ghes,
				       enum fixed_addresses fixmap_idx)
{
	struct acpi_hest_generic_status *estatus, tmp_header;
	... /* 36 lines, to :1377 */
	sev = ghes_severity(estatus->error_severity);
	if (sev >= GHES_SEV_PANIC) {
		ghes_print_queued_estatus();
		__ghes_panic(ghes, estatus, buf_paddr, fixmap_idx);
	}
```

[`ghes_severity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L324) is the translation that decides it, from the CPER scale to the GHES scale.

```c
/* drivers/acpi/apei/ghes.c:324 */
static inline int ghes_severity(int severity)
{
	switch (severity) {
	case CPER_SEV_INFORMATIONAL:
		return GHES_SEV_NO;
	case CPER_SEV_CORRECTED:
		return GHES_SEV_CORRECTED;
	case CPER_SEV_RECOVERABLE:
		return GHES_SEV_RECOVERABLE;
	case CPER_SEV_FATAL:
		return GHES_SEV_PANIC;
	default:
		/* Unknown, go panic */
		return GHES_SEV_PANIC;
	}
}
```

A record graded fatal, or with a value outside the enumeration, maps to `GHES_SEV_PANIC` and stops the kernel before [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912) runs. A fatal section inside a record graded lower, or any section with [`CPER_SEC_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L158) set, is how [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) reaches the PCI core through this path.

### ghes_handle_aer copies the dump into the pool and queues it

The section's bytes are held in the GHES status block, which [`ghes_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1176) releases as soon as the record is processed, and the work that prints and recovers runs much later. The report must therefore carry its own copy of the registers. commit [e2abc47a5a1a](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e2abc47a5a1a9f641e7cacdca643fdd40729bf6e) ("ACPI: APEI: Fix AER info corruption when error status data has multiple sections") introduced the copy, because the pointer queued before it pointed into a buffer that, in the words of its message, "could be reused before aer_recover_work_func() reads the data". The copy comes from [`ghes_estatus_pool`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L174), the allocator GHES already uses in these contexts, through [`gen_pool_alloc()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/genalloc.h#L152), whose kerneldoc states where it may run.

```c
/* include/linux/genalloc.h:142 */
/**
 * gen_pool_alloc - allocate special memory from the pool
 * @pool: pool to allocate from
 * @size: number of bytes to allocate from the pool
 *
 * Allocate the requested number of bytes from the specified pool.
 * Uses the pool allocation function (with first-fit algorithm by default).
 * Can not be used in NMI handler on architectures without
 * NMI-safe cmpxchg implementation.
 */
static inline unsigned long gen_pool_alloc(struct gen_pool *pool, size_t size)
{
	return gen_pool_alloc_algo(pool, size, pool->algo, pool->data);
}
```

The call returns an address as an `unsigned long`, 0 when the pool has no room, and the GHES handler casts it to a pointer. [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) is the producer of the PCI core's queue, and its comment maps GHES severities onto AER classes before the body checks the section, computes the address and the class, copies the registers and queues the report.

```c
/* drivers/acpi/apei/ghes.c:626 */
/*
 * PCIe AER errors need to be sent to the AER driver for reporting and
 * recovery. The GHES severities map to the following AER severities and
 * require the following handling:
 *
 * GHES_SEV_CORRECTABLE -> AER_CORRECTABLE
 *     These need to be reported by the AER driver but no recovery is
 *     necessary.
 * GHES_SEV_RECOVERABLE -> AER_NONFATAL
 * GHES_SEV_RECOVERABLE && CPER_SEC_RESET -> AER_FATAL
 *     These both need to be reported and recovered from by the AER driver.
 * GHES_SEV_PANIC does not make it to this handling since the kernel must
 *     panic.
 */
static void ghes_handle_aer(struct acpi_hest_generic_data *gdata)
{
#ifdef CONFIG_ACPI_APEI_PCIEAER
	struct cper_sec_pcie *pcie_err = acpi_hest_get_payload(gdata);

	if (pcie_err->validation_bits & CPER_PCIE_VALID_DEVICE_ID &&
	    pcie_err->validation_bits & CPER_PCIE_VALID_AER_INFO) {
		unsigned int devfn;
		int aer_severity;
		u8 *aer_info;

		devfn = PCI_DEVFN(pcie_err->device_id.device,
				  pcie_err->device_id.function);
		aer_severity = cper_severity_to_aer(gdata->error_severity);

		/*
		 * If firmware reset the component to contain
		 * the error, we must reinitialize it before
		 * use, so treat it as a fatal AER error.
		 */
		if (gdata->flags & CPER_SEC_RESET)
			aer_severity = AER_FATAL;

		aer_info = (void *)gen_pool_alloc(ghes_estatus_pool,
						  sizeof(struct aer_capability_regs));
		if (!aer_info)
			return;
		memcpy(aer_info, pcie_err->aer_info, sizeof(struct aer_capability_regs));

		aer_recover_queue(pcie_err->device_id.segment,
				  pcie_err->device_id.bus,
				  devfn, aer_severity,
				  (struct aer_capability_regs *)
				  aer_info);
	}
#endif
}
```

The whole body is enclosed in `#ifdef` [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37), so without the option the function compiles to an empty one and a PCIe section is printed by GHES and otherwise ignored. The comment speaks of GHES severities while the code passes the section's CPER severity to [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912), and the two describe the same mapping. The figure follows each field the handler reads to the argument it produces.

```text
    What the GHES handler reads from the section and what it hands to the queue
    ───────────────────────────────────────────────────────────────────────────

     struct acpi_hest_generic_data                                                    ⑦ the queue's arguments
    ┌──────────────────────────────┐                                                    ┌──────────────────────┐
    │ error_severity               ├──────── ③ AER class ───────────────────┬──────────▶│ severity             │
    │ flags                        ├──────── ④ CPER_SEC_RESET: AER_FATAL ───┘           │                      │
    └──────────────────────────────┘                                            ┌──────▶│ domain               │
                                                                                │ ┌────▶│ bus                  │
     struct cper_sec_pcie                                                       │ │ ┌──▶│ devfn                │
    ┌──────────────────────────────┐                                            │ │ │   │                      │
    │ validation_bits              ├──────── ① both bits set, or return         │ │ │   │ aer_regs             │
    │ device_id.segment            ├────────────────────────────────────────────┘ │ │   └─────┬────────────────┘
    │ device_id.bus                ├──────────────────────────────────────────────┘ │         │
    │ device_id.device, .function  ├──────── ② PCI_DEVFN ───────────────────────────┘         │
    │ aer_info[96]                 ├──────── ⑥ memcpy of 100 bytes ───┐                       │ points at the region
    └──────────────────────────────┘                                  │                       │
                                                                      │                       │
                                                                      │                       │
                                                                      │                       │
                                                                      ▼                       │
                                                      ┌───────────────────────────────┐       │
                                                      │ ⑤ pool region from            │◀──────┘
                                                      │ ghes_estatus_pool, 100 bytes  │
                                                      └───────────────────────────────┘

    ① ghes_handle_aer  ghes.c:645  returns unless both validation bits are set
    ② ghes_handle_aer  :651  packs device and function into devfn with PCI_DEVFN
    ③ ghes_handle_aer  :653  maps the section severity to an AER class through cper_severity_to_aer
    ④ ghes_handle_aer  :660  makes the class AER_FATAL when CPER_SEC_RESET is set in flags
    ⑤ ghes_handle_aer  :663  allocates the region from ghes_estatus_pool through gen_pool_alloc
    ⑥ ghes_handle_aer  :667  copies the AER registers into the region with memcpy
    ⑦ ghes_handle_aer  :669  hands the five values to aer_recover_queue
```

① [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) returns at once unless both [`CPER_PCIE_VALID_DEVICE_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L276) and [`CPER_PCIE_VALID_AER_INFO`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L280) are set in [`validation_bits`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L537). ② `ghes_handle_aer()` packs [`device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L552) and [`function`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L551) into one devfn byte with [`PCI_DEVFN()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L31). ③ `ghes_handle_aer()` maps [`error_severity`](https://elixir.bootlin.com/linux/v7.2/source/include/acpi/actbl1.h#L1938) to an AER class through [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912). ④ `ghes_handle_aer()` replaces that class with [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) when [`CPER_SEC_RESET`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L158) is set in [`flags`](https://elixir.bootlin.com/linux/v7.2/source/include/acpi/actbl1.h#L1941). ⑤ `ghes_handle_aer()` takes a region the size of [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41) from [`ghes_estatus_pool`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L174) through [`gen_pool_alloc()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/genalloc.h#L152). ⑥ `ghes_handle_aer()` copies that many bytes from [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/cper.h#L568) into the region with `memcpy()`. ⑦ `ghes_handle_aer()` hands the segment, the bus, the devfn, the class and the region to [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263).

The devfn of ② is the byte the PCI core uses for a function's device and function numbers, and [`PCI_DEVFN()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L31) builds it the way [`PCI_SLOT()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L32) and [`PCI_FUNC()`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci.h#L33) later take it apart for the messages of the queue.

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

The device number takes bits 7 to 3 and the function number bits 2 to 0, each masked to its width, so out-of-range values in the section cannot spill into the other field. The segment becomes the domain argument unchanged, and the work function later compares it with the domain of each function it knows. When the pool has no room at ⑤ the handler returns without queuing anything and without a message of its own, and the error then leaves no trace in the PCI core. From ⑦ on the region belongs to the queue, which keeps a pointer to it and no copy.

So far, a PCIe section has left the firmware's status block as five values and a 100-byte region taken from the GHES pool, the first two columns of the strip in the next subsection, and nothing in the PCI core has seen it yet.

### The ring holds sixteen reports between two contexts

The producer runs with interrupts disabled on any CPU, and the consumer must be able to sleep, so the two meet in a buffer that the producer can fill without blocking. [`aer_recover_ring`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1215) is that buffer, a kfifo of [`struct aer_recover_entry`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1207) reports defined statically in aer.c under [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37). Read the unit for the size of the ring and the contents of one report.

```c
/* drivers/pci/pcie/aer.c:1203 */
#ifdef CONFIG_ACPI_APEI_PCIEAER

#define AER_RECOVER_RING_SIZE		16

struct aer_recover_entry {
	u8	bus;
	u8	devfn;
	u16	domain;
	int	severity;
	struct aer_capability_regs *regs;
};

static DEFINE_KFIFO(aer_recover_ring, struct aer_recover_entry,
		    AER_RECOVER_RING_SIZE);
```

[`AER_RECOVER_RING_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1205) is 16, and [`DEFINE_KFIFO()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L148) needs a power of two, so the ring holds sixteen reports. A report is the address of the reporting function, in [`bus`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1208), [`devfn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1209) and the 16-bit [`domain`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1210), its AER class in [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1211), and [`regs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1212), the pointer to the region the producer filled. The kfifo itself is the structure that [`__STRUCT_KFIFO()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L67) declares, an array of the element type beside the generic header, which the ring's definition expands to.

```c
/* include/linux/kfifo.h:67 */
#define __STRUCT_KFIFO(type, size, recsize, ptrtype) \
{ \
	__STRUCT_KFIFO_COMMON(type, recsize, ptrtype); \
	type		buf[((size < 2) || (size & (size - 1))) ? -1 : size]; \
}

#define STRUCT_KFIFO(type, size) \
	struct __STRUCT_KFIFO(type, size, 0, type)
```

The array size expression turns a size that is not a power of two into -1, so such a ring does not compile. The header the union starts with is a [`struct __kfifo`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L49), whose counters decide which slots are full.

```c
/* include/linux/kfifo.h:49 */
struct __kfifo {
	unsigned int	in;
	unsigned int	out;
	unsigned int	mask;
	unsigned int	esize;
	void		*data;
};
```

[`in`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L50) counts the elements ever put and [`out`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L51) the elements ever taken, and [`mask`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L52) is the slot count less one, so a counter selects its slot with a bitwise and. [`esize`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L53) is the size of one element and [`data`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L54) points at the array, which the copy helpers use. [`DEFINE_KFIFO()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L148) fills these members at compile time, both counters at 0 and the mask at fifteen for this ring.

```c
/* include/linux/kfifo.h:140 */
/**
 * DEFINE_KFIFO - macro to define and initialize a fifo
 * @fifo: name of the declared fifo datatype
 * @type: type of the fifo elements
 * @size: the number of elements in the fifo, this must be a power of 2
 *
 * Note: the macro can be used for global and local fifo data type variables.
 */
#define DEFINE_KFIFO(fifo, type, size) \
	DECLARE_KFIFO(fifo, type, size) = \
	(typeof(fifo)) { \
		{ \
			{ \
			.in	= 0, \
			.out	= 0, \
			.mask	= __is_kfifo_ptr(&(fifo)) ? \
				  0 : \
				  ARRAY_SIZE((fifo).buf) - 1, \
			.esize	= sizeof(*(fifo).buf), \
			.data	= __is_kfifo_ptr(&(fifo)) ? \
				NULL : \
				(fifo).buf, \
			} \
		} \
	}
```

The ring therefore needs no initialization call, and it exists from boot whether or not a report ever arrives. [`kfifo_unused()`](https://elixir.bootlin.com/linux/v7.2/source/lib/kfifo.c#L20) derives the free space from the two counters, in unsigned arithmetic that stays correct when the counters wrap.

```c
/* lib/kfifo.c:20 */
static inline unsigned int kfifo_unused(struct __kfifo *fifo)
{
	return (fifo->mask + 1) - (fifo->in - fifo->out);
}
```

The ring of the figure holds five reports, between [`out`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L51) at 19 and [`in`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L50) at 24, and has eleven slots free.

```text
    aer_recover_ring: sixteen slots between two free-running counters
    ─────────────────────────────────────────────────────────────────

    slot     0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15
           ┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐
           │    │    │    │ ▓▓ │ ▓▓ │ ▓▓ │ ▓▓ │ ▓▓ │    │    │    │    │    │    │    │    │
           └────┴────┴────┴──┬─┴────┴────┴────┴────┴──┬─┴────┴────┴────┴────┴────┴────┴────┘
                             ▲                        ▲
                           out = 19                 in = 24
                           19 & 15 = 3              24 & 15 = 8
                           read next                written next

    mask = 15, the slot count less one; both counters start at 0, only grow, and select slot (counter & mask)
    held = in - out = 5; unused = (mask + 1) - (in - out) = 11, both in unsigned arithmetic
    a put when unused is 0 copies nothing and returns 0; a get when in equals out copies nothing and returns 0
```

Writers and the reader touch different counters, and the comment above [`aer_recover_ring_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1260) relies on that. The lock and the work item are defined right after the work function.

```c
/* drivers/pci/pcie/aer.c:1255 */
/*
 * Mutual exclusion for writers of aer_recover_ring, reader side don't
 * need lock, because there is only one reader and lock is not needed
 * between reader and writer.
 */
static DEFINE_SPINLOCK(aer_recover_ring_lock);
static DECLARE_WORK(aer_recover_work, aer_recover_work_func);
```

According to the comment, only the writers need mutual exclusion, "because there is only one reader". The one reader is [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218), which the static definition of the work item [`aer_recover_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) binds to it. A report then passes through three copies of [`struct aer_recover_entry`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1207), the producer's local, a slot of the ring and the work function's local, while the region it points at stays in place, and the strip follows one report through them.

```text
    One report, from the GHES handler to the free of its region
    ───────────────────────────────────────────────────────────
    fields: the pool region, struct aer_recover_entry in its three copies, and the ring slot

    time ─────────────────────────────────────────────────────────────────────────────────────────▶
    event               alloc       copy        build       put         get         free
                        ▼           ▼           ▼           ▼           ▼           ▼
                        ┌───────────┬───────────────────────────────────────────────┬───────────┐
    region              │➊ taken    │➋ AER registers, read by the worker            │➏ freed    │
                        └───────────┴───────────────────────────────────────────────┴───────────┘
                                                ┌───────────┐
    entry, producer                             │➌ set      │
                                                └───────────┘
                                                            ┌───────────┬───────────────────────┐
    ring slot                                               │➍ copy     │➎ copied out, free     │
                                                            └───────────┴───────────────────────┘
                                                                        ┌───────────────────────┐
    entry, worker                                                       │➎ copy of the slot     │
                                                                        └───────────────────────┘

    ring full: the region stays taken from ➋ on, no slot is written, and nothing frees it
    no struct pci_dev: the worker skips ➏ after ➎, and nothing frees the region

    ➊ ghes_handle_aer       ghes.c:663  takes the region from the pool through gen_pool_alloc
    ➋ ghes_handle_aer       :667        copies the AER registers into the region with memcpy
    ➌ aer_recover_queue     aer.c:1266  sets the five members of its local entry
    ➍ aer_recover_queue     :1274       copies the entry into the slot at in through kfifo_in_spinlocked
    ➎ aer_recover_work_func :1223       copies the slot at out into its local entry through kfifo_get
    ➏ aer_recover_work_func :1242       returns the region through ghes_estatus_pool_region_free
```

➊ [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) takes the region from the pool through [`gen_pool_alloc()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/genalloc.h#L152). ➋ `ghes_handle_aer()` copies the AER registers into the region with `memcpy()`. ➌ [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) sets the five members of its local entry. ➍ `aer_recover_queue()` copies the entry into the slot at [`in`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L50) through [`kfifo_in_spinlocked()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L576). ➎ [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) copies the slot at [`out`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L51) into its own local entry through [`kfifo_get()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L477). ➏ `aer_recover_work_func()` returns the region to the pool through [`ghes_estatus_pool_region_free()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L238).

No other function writes these members or this region at v7.2, since [`struct aer_recover_entry`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1207) is local to aer.c and, after ⑦, the region's address is held by the entry alone, and the ring's counters are written only through the two kfifo calls of ➍ and ➎. Between ➋ and ➏ the region is owned by whichever copy of the entry holds its address, and the two rows under the bars are the branches where nobody frees it, which a later subsection reads.

### aer_recover_queue copies a report in under the writers' lock

Several CPUs can take GHES notifications at the same time, and each runs its own producer, so the ring has many writers and a single reader. [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) is the writer's side, exported to the APEI code and declared for it in include/linux/aer.h. Read it for its three steps, building the report, copying it in under the lock and queuing the work.

```c
/* drivers/pci/pcie/aer.c:1263 */
void aer_recover_queue(int domain, unsigned int bus, unsigned int devfn,
		       int severity, struct aer_capability_regs *aer_regs)
{
	struct aer_recover_entry entry = {
		.bus		= bus,
		.devfn		= devfn,
		.domain		= domain,
		.severity	= severity,
		.regs		= aer_regs,
	};

	if (kfifo_in_spinlocked(&aer_recover_ring, &entry, 1,
				 &aer_recover_ring_lock))
		schedule_work(&aer_recover_work);
	else
		pr_err("buffer overflow in recovery for %04x:%02x:%02x.%x\n",
		       domain, bus, PCI_SLOT(devfn), PCI_FUNC(devfn));
}
EXPORT_SYMBOL_GPL(aer_recover_queue);
```

The designated initializer builds the report as a local of whichever context called, and [`kfifo_in_spinlocked()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L576) copies it into the ring under [`aer_recover_ring_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1260). The macro returns the number of elements it copied, so a 1 queues [`aer_recover_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) with [`schedule_work()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/workqueue.h#L758) and a 0 prints "buffer overflow in recovery for" with the address. Neither branch frees the region, which on the overflow branch nobody else holds. The kfifo unit below holds [`kfifo_in()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L554) and its locked form [`kfifo_in_spinlocked()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L576) with their kerneldoc, and it answers what the count means and how the lock is taken.

```c
/* include/linux/kfifo.h:542 */
/**
 * kfifo_in - put data into the fifo
 * @fifo: address of the fifo to be used
 * @buf: the data to be added
 * @n: number of elements to be added
 *
 * This macro copies the given buffer into the fifo and returns the
 * number of copied elements.
 *
 * Note that with only one concurrent reader and one concurrent
 * writer, you don't need extra locking to use these macro.
 */
#define	kfifo_in(fifo, buf, n) \
({ \
	typeof((fifo) + 1) __tmp = (fifo); \
	typeof(__tmp->ptr_const) __buf = (buf); \
	unsigned long __n = (n); \
	const size_t __recsize = sizeof(*__tmp->rectype); \
	struct __kfifo *__kfifo = &__tmp->kfifo; \
	(__recsize) ?\
	__kfifo_in_r(__kfifo, __buf, __n, __recsize) : \
	__kfifo_in(__kfifo, __buf, __n); \
})

/**
 * kfifo_in_spinlocked - put data into the fifo using a spinlock for locking
 * @fifo: address of the fifo to be used
 * @buf: the data to be added
 * @n: number of elements to be added
 * @lock: pointer to the spinlock to use for locking
 *
 * This macro copies the given values buffer into the fifo and returns the
 * number of copied elements.
 */
#define	kfifo_in_spinlocked(fifo, buf, n, lock) \
({ \
	unsigned long __flags; \
	unsigned int __ret; \
	spin_lock_irqsave(lock, __flags); \
	__ret = kfifo_in(fifo, buf, n); \
	spin_unlock_irqrestore(lock, __flags); \
	__ret; \
})
```

[`kfifo_in_spinlocked()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L576) takes the lock with `spin_lock_irqsave()` around [`kfifo_in()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L554), and on this path the interrupts it would disable are already off. For a ring of fixed-size elements such as this one, `__recsize` is 0 and [`kfifo_in()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L554) calls [`__kfifo_in()`](https://elixir.bootlin.com/linux/v7.2/source/lib/kfifo.c#L114), which decides how much of the request fits.

```c
/* lib/kfifo.c:114 */
unsigned int __kfifo_in(struct __kfifo *fifo,
		const void *buf, unsigned int len)
{
	unsigned int l;

	l = kfifo_unused(fifo);
	if (len > l)
		len = l;

	kfifo_copy_in(fifo, buf, len, fifo->in);
	fifo->in += len;
	return len;
}
EXPORT_SYMBOL(__kfifo_in);
```

[`__kfifo_in()`](https://elixir.bootlin.com/linux/v7.2/source/lib/kfifo.c#L114) clamps the request to the free slots [`kfifo_unused()`](https://elixir.bootlin.com/linux/v7.2/source/lib/kfifo.c#L20) reports, copies that many elements and advances [`in`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L50) by the same number. A request for one element into a full ring therefore copies nothing and returns 0, the branch [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) reports as an overflow. A successful put then asks for the work item to run, and [`schedule_work()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/workqueue.h#L758) says in its kerneldoc what a second request does while the first is pending.

```c
/* include/linux/workqueue.h:744 */
/**
 * schedule_work - put work task in per-CPU workqueue
 * @work: job to be done
 *
 * Returns %false if @work was already on the system per-CPU workqueue and
 * %true otherwise.
 *
 * This puts a job in the system per-CPU workqueue if it was not already
 * queued and leaves it in the same position on the system per-CPU
 * workqueue otherwise.
 *
 * Shares the same memory-ordering properties of queue_work(), cf. the
 * DocBook header of queue_work().
 */
static inline bool schedule_work(struct work_struct *work)
{
	return queue_work(system_percpu_wq, work);
}
```

A put that finds [`aer_recover_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) still pending queues nothing new, and the run already queued takes every report in the ring, which is why the work function loops. The swimlane shows two producers on two CPUs feeding one run of the work item.

```text
    Two reports from two CPUs, one run of the work item
    ───────────────────────────────────────────────────
    time ↓
    GHES handler, CPU 0      ╎ GHES handler, CPU 1      ╎ ring                 ╎ work item
    ─────────────────────────┼──────────────────────────┼──────────────────────┼────────────────────────────────
    lock held, put ─────────────────────────────────────▶ in 0 to 1            ╎
    queue the work ────────────────────────────────────────────────────────────▶ pending
                             ╎ lock held, put ──────────▶ in 1 to 2            ╎
                             ╎ already pending, ───────────────────────────────▶ unchanged
                             ╎ nothing queued           ╎                      ╎
                             ╎                          ╎                      ╎ runs on a kworker
                             ╎                          ╎ out 0 to 1 ◀─────────╎ first report
                             ╎                          ╎ out 1 to 2 ◀─────────╎ second report
                             ╎                          ╎ in equals out        ╎ the loop ends

    put = copy one entry in under aer_recover_ring_lock, interrupts off; the reader takes no lock
    the second put finds the work item still pending, so the one run takes both entries
```

The lock orders the two puts, and the reader never takes it, as the comment above [`aer_recover_ring_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1260) allows for a single reader. The work item runs on the system per-CPU workqueue, so its run starts on a kworker after the producers have returned, and the next subsection reads what it does there.

### aer_recover_work_func drains the ring in process context

On a kworker the PCI core may sleep, take its locks and call drivers, which interrupt context forbids. [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) turns each report back into a function, prints it, returns its region to the pool and starts recovery for the two uncorrectable classes. Read it as one loop that does this report after report until the ring is empty.

```c
/* drivers/pci/pcie/aer.c:1218 */
static void aer_recover_work_func(struct work_struct *work)
{
	struct aer_recover_entry entry;
	struct pci_dev *pdev;

	while (kfifo_get(&aer_recover_ring, &entry)) {
		pdev = pci_get_domain_bus_and_slot(entry.domain, entry.bus,
						   entry.devfn);
		if (!pdev) {
			pr_err_ratelimited("%04x:%02x:%02x.%x: no pci_dev found\n",
					   entry.domain, entry.bus,
					   PCI_SLOT(entry.devfn),
					   PCI_FUNC(entry.devfn));
			continue;
		}
		pci_print_aer(pdev, entry.severity, entry.regs);

		/*
		 * Memory for aer_capability_regs(entry.regs) is being
		 * allocated from the ghes_estatus_pool to protect it from
		 * overwriting when multiple sections are present in the
		 * error status. Thus free the same after processing the
		 * data.
		 */
		ghes_estatus_pool_region_free((unsigned long)entry.regs,
					    sizeof(struct aer_capability_regs));

		if (entry.severity == AER_NONFATAL)
			pcie_do_recovery(pdev, pci_channel_io_normal,
					 aer_root_reset);
		else if (entry.severity == AER_FATAL)
			pcie_do_recovery(pdev, pci_channel_io_frozen,
					 aer_root_reset);
		pci_dev_put(pdev);
	}
}
```

Each pass takes one report into the local `entry` and looks the function up by its address. A report whose function the kernel does not know is logged with "no pci_dev found" under a ratelimit and skipped. A found function is printed with [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926), its region goes back to the pool, and [`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) and [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) start [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) with the channel normal or frozen, while [`AER_CORRECTABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L16) starts nothing. The reference the lookup took is dropped at the end of the pass. [`kfifo_get()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L477) is the reader's side of the ring, and its kerneldoc states when the reader needs no lock.

```c
/* include/linux/kfifo.h:465 */
/**
 * kfifo_get - get data from the fifo
 * @fifo: address of the fifo to be used
 * @val: address where to store the data
 *
 * This macro reads the data from the fifo.
 * It returns 0 if the fifo was empty. Otherwise it returns the number
 * processed elements.
 *
 * Note that with only one concurrent reader and one concurrent
 * writer, you don't need extra locking to use these macro.
 */
#define	kfifo_get(fifo, val) \
__kfifo_uint_must_check_helper( \
({ \
	typeof((fifo) + 1) __tmp = (fifo); \
	typeof(__tmp->ptr) __val = (val); \
	unsigned int __ret; \
	const size_t __recsize = sizeof(*__tmp->rectype); \
	struct __kfifo *__kfifo = &__tmp->kfifo; \
	if (__recsize) \
		__ret = __kfifo_out_r(__kfifo, __val, sizeof(*__val), \
			__recsize); \
	else { \
		__ret = !kfifo_is_empty(__tmp); \
		if (__ret) { \
			*(typeof(__tmp->type))__val = \
				(__is_kfifo_ptr(__tmp) ? \
				((typeof(__tmp->type))__kfifo->data) : \
				(__tmp->buf) \
				)[__kfifo->out & __tmp->kfifo.mask]; \
			smp_wmb(); \
			__kfifo->out++; \
		} \
	} \
	__ret; \
}) \
)
```

For this ring `__recsize` is 0, so the macro copies the element at [`out`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L51) masked by [`mask`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L52) into the caller's variable, orders that copy with `smp_wmb()` and then advances [`out`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/kfifo.h#L51). It returns 0 when the ring is empty, which ends the loop of the work function. The lookup is [`pci_get_domain_bus_and_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L230), and its kerneldoc says what the caller owes for the result.

```c
/* drivers/pci/search.c:215 */
/**
 * pci_get_domain_bus_and_slot - locate PCI device for a given PCI domain (segment), bus, and slot
 * @domain: PCI domain/segment on which the PCI device resides.
 * @bus: PCI bus on which desired PCI device resides
 * @devfn: encodes number of PCI slot in which the desired PCI device
 * resides and the logical device number within that slot in case of
 * multi-function devices.
 *
 * Given a PCI domain, bus, and slot/function number, the desired PCI
 * device is located in the list of PCI devices. If the device is
 * found, its reference count is increased and this function returns a
 * pointer to its data structure.  The caller must decrement the
 * reference count by calling pci_dev_put().  If no device is found,
 * %NULL is returned.
 */
struct pci_dev *pci_get_domain_bus_and_slot(int domain, unsigned int bus,
					    unsigned int devfn)
{
	struct pci_dev *dev = NULL;

	for_each_pci_dev(dev) {
		if (pci_domain_nr(dev->bus) == domain &&
		    (dev->bus->number == bus && dev->devfn == devfn))
			return dev;
	}
	return NULL;
}
EXPORT_SYMBOL(pci_get_domain_bus_and_slot);
```

The search compares the domain, the bus number and the devfn of every PCI device the system knows with the report's three values, and returns the match with its reference count raised. On x86 the domain of a bus comes from [`pci_domain_nr()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/include/asm/pci.h#L43), which reads the [`domain`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/include/asm/pci.h#L15) of the [`struct pci_sysdata`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/include/asm/pci.h#L14) that the bus carries, under [`CONFIG_PCI_DOMAINS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L32), which the x86 Kconfig selects whenever PCI is set.

```c
/* arch/x86/Kconfig:316 */
	select PCI_DOMAINS			if PCI
```

With the option selected, the x86 body below is the one compiled.

```c
/* arch/x86/include/asm/pci.h:35 */
static inline struct pci_sysdata *to_pci_sysdata(const struct pci_bus *bus)
{
	return bus->sysdata;
}

#ifdef CONFIG_PCI

#ifdef CONFIG_PCI_DOMAINS
static inline int pci_domain_nr(struct pci_bus *bus)
{
	return to_pci_sysdata(bus)->domain;
}
```

The firmware's segment is thus compared with the domain recorded for each function's root bus, and a mismatch or a function removed since the error leaves the lookup empty. [`pci_dev_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1580) drops the reference at the end of the pass.

```c
/* drivers/pci/pci-driver.c:1573 */
/**
 * pci_dev_put - release a use of the pci device structure
 * @dev: device that's been disconnected
 *
 * Must be called when a user of a device is finished with it.  When the last
 * user of the device calls this function, the memory of the device is freed.
 */
void pci_dev_put(struct pci_dev *dev)
{
	if (dev)
		put_device(&dev->dev);
}
EXPORT_SYMBOL(pci_dev_put);
```

The put tolerates NULL, though the loop reaches it only with a found function. The region goes back through [`ghes_estatus_pool_region_free()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L238), the APEI helper the work function calls with the region's address and the size of [`struct aer_capability_regs`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L41).

```c
/* drivers/acpi/apei/ghes.c:230 */
/**
 * ghes_estatus_pool_region_free - free previously allocated memory
 *				   from the ghes_estatus_pool.
 * @addr: address of memory to free.
 * @size: size of memory to free.
 *
 * Returns none.
 */
void ghes_estatus_pool_region_free(unsigned long addr, u32 size)
{
	gen_pool_free(ghes_estatus_pool, addr, size);
}
EXPORT_SYMBOL_GPL(ghes_estatus_pool_region_free);
```

The helper hands both values to [`gen_pool_free()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/genalloc.h#L170) on [`ghes_estatus_pool`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L174), the generic allocator's release for an address it gave out.

```c
/* include/linux/genalloc.h:170 */
static inline void gen_pool_free(struct gen_pool *pool, unsigned long addr,
                size_t size)
{
	gen_pool_free_owner(pool, addr, size, NULL);
}
```

The size passed matches the size [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) allocated, so the pool takes back exactly the region of the report. After the free the entry's [`regs`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1212) in the ring slot is stale, and only the local copy's values are used for the recovery that follows.

### pci_print_aer counts and traces every report

The work function hands each register copy to [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926), which turns it into the counters, the trace event and the console lines that the AER code keeps for a reported error. It fills the [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) that the AER printing helpers take, updates the function's counters and fires the tracepoint, and only then asks the ratelimit whether to print. The figure shows that order, with the ratelimit as the line between what happens to every report and what can be skipped.

```text
    pci_print_aer: every report is counted and traced, then the ratelimit decides what prints
    ─────────────────────────────────────────────────────────────────────────────────────────

    ┌───────────────────────────────────────┐
    │ the copy: struct aer_capability_regs  │
    └───────────┬───────────────────────────┘
                │ «1» severity, first_error
                │ «2» status, mask, level
                │ «3» tlp_header_valid
                ▼
    ┌───────────────────────────────────────┐
    │ struct aer_err_info, a local          │
    └───────────┬───────────────────────────┘
                │
                ├──── «4» ────▶ aer_info counters of the device, read through sysfs
                │
                ├──── «5» ────▶ the aer_event tracepoint
                │
                │  «6» per-device ratelimit: a refused report returns here
    ════════════╪═══════════════════════════════════════════════════════════════════════════════════════
                │
                ├──── «7» ────▶ console: status, mask, bit names, layer, agent; uncor_severity if uncorrectable
                │
                └──── «8» ────▶ console: the TLP Header line, when tlp_header_valid is set

    the console lines take KERN_WARNING for AER_CORRECTABLE and KERN_ERR otherwise

    «1» pci_print_aer  aer.c:932  fills severity and first_error of the local info
    «2» pci_print_aer  :937       picks the correctable or uncorrectable status, mask and level
    «3» pci_print_aer  :945       asks tlp_header_logged whether the header log holds a TLP
    «4» pci_print_aer  :954       counts the unmasked bits through pci_dev_aer_stats_incr
    «5» pci_print_aer  :955       emits the aer_event tracepoint through trace_aer_event
    «6» pci_print_aer  :958       returns when aer_ratelimit refuses another message
    «7» pci_print_aer  :964       prints the status and mask, then the set bits, layer and agent
    «8» pci_print_aer  :974       prints the logged TLP through pcie_print_tlp_log
```

«1» [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) fills [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841) and [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) of its local error information when it declares it. «2» `pci_print_aer()` picks the correctable or the uncorrectable status and mask, and the printk level, by the class. «3» `pci_print_aer()` asks [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) whether the Header Log holds a TLP for an uncorrectable status. «4» `pci_print_aer()` counts the unmasked status bits through [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747). «5» `pci_print_aer()` emits the `aer_event` tracepoint through `trace_aer_event()`. «6» `pci_print_aer()` returns when [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800) refuses another message for the function and class. «7» `pci_print_aer()` prints the status and mask, then the names of the set bits, the layer and the agent. «8» `pci_print_aer()` prints the logged TLP through [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106).

The function is exported for code outside aer.c, and at v7.2 it has three callers in the tree: [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218), [`extlog_print_pcie()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/acpi_extlog.c#L136), whose body the configuration subsection shows to be compiled out, and a CXL error handler that this page leaves out. Its 52 lines are read in two pieces, cut at the ratelimit.

| Piece | Lines | Stage |
|---|---|---|
| ❶ | aer.c:926-959 | fills the error information, counts, traces and applies the ratelimit |
| ❷ | aer.c:960-977 | prints the status, the set bits, the layer and agent, the severity register and the TLP |

❶ The first piece of [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) reads the copy into the error information and does the work that every report gets.

```c
/* drivers/pci/pcie/aer.c:926 */
void pci_print_aer(struct pci_dev *dev, int aer_severity,
		   struct aer_capability_regs *aer)
{
	const char *bus_type;
	int layer, agent, tlp_header_valid = 0;
	u32 status, mask;
	struct aer_err_info info = {
		.severity = aer_severity,
		.first_error = PCI_ERR_CAP_FEP(aer->cap_control),
	};

	if (aer_severity == AER_CORRECTABLE) {
		status = aer->cor_status;
		mask = aer->cor_mask;
		info.level = KERN_WARNING;
	} else {
		status = aer->uncor_status;
		mask = aer->uncor_mask;
		info.level = KERN_ERR;
		tlp_header_valid = tlp_header_logged(status, aer->cap_control);
	}

	info.status = status;
	info.mask = mask;
	info.is_cxl = pcie_is_cxl(dev);

	bus_type = aer_err_bus(&info);

	pci_dev_aer_stats_incr(dev, &info);
	trace_aer_event(pci_name(dev), (status & ~mask), aer_severity,
			tlp_header_valid, &aer->header_log, bus_type);

	if (!aer_ratelimit(dev, info.severity))
		return;
```

The class picks the register pair, and the level drops to `KERN_WARNING` for a correctable report, which commit [36c5932074aa](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=36c5932074aaedebf905374dba2399a529215aa1) ("PCI/AER: Reduce pci_print_aer() correctable error level to KERN_WARNING") lowered from `KERN_ERR`. `is_cxl` records whether the function is on a CXL link, so that the bus type in the trace reads CXL there and PCIe elsewhere. The error information is a [`struct aer_err_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L833) of drivers/pci/pci.h, whose kerneldoc describes each member.

```c
/* drivers/pci/pci.h:814 */
/**
 * struct aer_err_info - AER Error Information
 * @dev: Devices reporting error
 * @ratelimit_print: Flag to log or not log the devices' error. 0=NotLog/1=Log
 * @__pad1: Padding for alignment
 * @error_dev_num: Number of devices reporting an error
 * @level: printk level to use in logging
 * @id: Value from register PCI_ERR_ROOT_ERR_SRC
 * @severity: AER severity, 0-UNCOR Non-fatal, 1-UNCOR fatal, 2-COR
 * @root_ratelimit_print: Flag to log or not log the root's error. 0=NotLog/1=Log
 * @multi_error_valid: If multiple errors are reported
 * @first_error: First reported error
 * @__pad2: Padding for alignment
 * @is_cxl: Bus type error: 0-PCI Bus error, 1-CXL Bus error
 * @tlp_header_valid: Indicates if TLP field contains error information
 * @status: COR/UNCOR error status
 * @mask: COR/UNCOR mask
 * @tlp: Transaction packet information
 */
struct aer_err_info {
	struct pci_dev *dev[AER_MAX_MULTI_ERR_DEVICES];
	int ratelimit_print[AER_MAX_MULTI_ERR_DEVICES];
	int error_dev_num;
	const char *level;

	unsigned int id:16;

	unsigned int severity:2;
	unsigned int root_ratelimit_print:1;
	unsigned int __pad1:4;
	unsigned int multi_error_valid:1;

	unsigned int first_error:5;
	unsigned int __pad2:1;
	unsigned int is_cxl:1;
	unsigned int tlp_header_valid:1;

	unsigned int status;
	unsigned int mask;
	struct pcie_tlp_log tlp;
};
```

The printer sets [`severity`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L841), [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846), [`level`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L837), [`status`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L851), [`mask`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L852) and [`is_cxl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L848), and the initializer leaves every other member zero. Those members, the array of devices, the source identifier, the multiple-error flag and the TLP log among them, serve the native Root Port path, where one interrupt can report several functions. Whether a TLP header was logged is kept in a local here, and [`tlp_header_logged()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L815) decides it from the status and the control register, with the list of errors in [`AER_LOG_TLP_MASKS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L99).

```c
/* drivers/pci/pcie/aer.c:99 */
#define AER_LOG_TLP_MASKS		(PCI_ERR_UNC_POISON_TLP|	\
					PCI_ERR_UNC_POISON_BLK |	\
					PCI_ERR_UNC_ECRC|		\
					PCI_ERR_UNC_UNSUP|		\
					PCI_ERR_UNC_COMP_ABORT|		\
					PCI_ERR_UNC_UNX_COMP|		\
					PCI_ERR_UNC_ACSV |		\
					PCI_ERR_UNC_MCBTLP |		\
					PCI_ERR_UNC_ATOMEG |		\
					PCI_ERR_UNC_DMWR_BLK |		\
					PCI_ERR_UNC_XLAT_BLK |		\
					PCI_ERR_UNC_TLPPRE |		\
					PCI_ERR_UNC_MALF_TLP |		\
					PCI_ERR_UNC_IDE_CHECK |		\
					PCI_ERR_UNC_MISR_IDE |		\
					PCI_ERR_UNC_PCRC_CHECK)
```

The mask is the set of uncorrectable errors for which, by the comment in the function below, a header is always logged.

```c
/* drivers/pci/pcie/aer.c:815 */
static bool tlp_header_logged(u32 status, u32 capctl)
{
	/* Errors for which a header is always logged (PCIe r7.0 sec 6.2.7) */
	if (status & AER_LOG_TLP_MASKS)
		return true;

	/* Completion Timeout header is only logged on capable devices */
	if (status & PCI_ERR_UNC_COMP_TIME &&
	    capctl & PCI_ERR_CAP_COMP_TIME_LOG)
		return true;

	return false;
}
```

A Completion Timeout counts as logged only when the control register has [`PCI_ERR_CAP_COMP_TIME_LOG`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L818) set, so a function that cannot log that header does not print a stale one. The counters come next, in [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747), and they are members of the [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60) that the function's [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371) points to.

```c
/* drivers/pci/pcie/aer.c:60 */
struct aer_info {

	/*
	 * Fields for all AER capable devices. They indicate the errors
	 * "as seen by this device". Note that this may mean that if an
	 * Endpoint is causing problems, the AER counters may increment
	 * at its link partner (e.g. Root Port) because the errors will be
	 * "seen" by the link partner and not the problematic Endpoint
	 * itself (which may report all counters as 0 as it never saw any
	 * problems).
	 */
	/* Counters for different type of correctable errors */
	u64 dev_cor_errs[AER_MAX_TYPEOF_COR_ERRS];
	/* Counters for different type of fatal uncorrectable errors */
	u64 dev_fatal_errs[AER_MAX_TYPEOF_UNCOR_ERRS];
	/* Counters for different type of nonfatal uncorrectable errors */
	u64 dev_nonfatal_errs[AER_MAX_TYPEOF_UNCOR_ERRS];
	/* Total number of ERR_COR sent by this device */
	u64 dev_total_cor_errs;
	/* Total number of ERR_FATAL sent by this device */
	u64 dev_total_fatal_errs;
	/* Total number of ERR_NONFATAL sent by this device */
	u64 dev_total_nonfatal_errs;

	/*
	 * Fields for Root Ports & Root Complex Event Collectors only; these
	 * indicate the total number of ERR_COR, ERR_FATAL, and ERR_NONFATAL
	 * messages received by the Root Port / Event Collector, INCLUDING the
	 * ones that are generated internally (by the Root Port itself)
	 */
	u64 rootport_total_cor_errs;
	u64 rootport_total_fatal_errs;
	u64 rootport_total_nonfatal_errs;

	/* Ratelimits for errors */
	struct ratelimit_state correctable_ratelimit;
	struct ratelimit_state nonfatal_ratelimit;
};
```

The device counters count by error bit and in total for each class, and the Root Port counters and the two ratelimit states complete the structure. [`pci_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L385) allocates it when a function is set up, and its stage below shows the condition and the ratelimit defaults.

```c
/* drivers/pci/pcie/aer.c:385 */
void pci_aer_init(struct pci_dev *dev)
{
	int n;

	dev->aer_cap = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_ERR);
	if (!dev->aer_cap)
		return;

	dev->aer_info = kzalloc_obj(*dev->aer_info);
	if (!dev->aer_info) {
		dev->aer_cap = 0;
		return;
	}

	ratelimit_state_init(&dev->aer_info->correctable_ratelimit,
			     DEFAULT_RATELIMIT_INTERVAL, DEFAULT_RATELIMIT_BURST);
	ratelimit_state_init(&dev->aer_info->nonfatal_ratelimit,
			     DEFAULT_RATELIMIT_INTERVAL, DEFAULT_RATELIMIT_BURST);
```

The condition is an AER capability, whoever owns AER, so a firmware-reported error is counted like a native one, and both ratelimit states start at the default interval and burst. The increment below adds to the total of the class and then to the counter of every unmasked bit.

```c
/* drivers/pci/pcie/aer.c:747 */
static void pci_dev_aer_stats_incr(struct pci_dev *pdev,
				   struct aer_err_info *info)
{
	unsigned long status = info->status & ~info->mask;
	int i, max = -1;
	u64 *counter = NULL;
	struct aer_info *aer_info = pdev->aer_info;

	if (!aer_info)
		return;

	switch (info->severity) {
	case AER_CORRECTABLE:
		aer_info->dev_total_cor_errs++;
		counter = &aer_info->dev_cor_errs[0];
		max = AER_MAX_TYPEOF_COR_ERRS;
		break;
	case AER_NONFATAL:
		aer_info->dev_total_nonfatal_errs++;
		hwerr_log_error_type(HWERR_RECOV_PCI);
		counter = &aer_info->dev_nonfatal_errs[0];
		max = AER_MAX_TYPEOF_UNCOR_ERRS;
		break;
	case AER_FATAL:
		aer_info->dev_total_fatal_errs++;
		counter = &aer_info->dev_fatal_errs[0];
		max = AER_MAX_TYPEOF_UNCOR_ERRS;
		break;
	}

	for_each_set_bit(i, &status, max)
		counter[i]++;
}
```

A function without the structure counts nothing. The non-fatal branch also calls [`hwerr_log_error_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/vmcore_info.h#L85), which with [`CONFIG_VMCORE_INFO`](https://elixir.bootlin.com/linux/v7.2/source/kernel/Kconfig.kexec#L8) set counts the recoverable PCI error where crash-dump tooling reads it and otherwise compiles to the empty inline below.

```c
/* include/linux/vmcore_info.h:82 */
#ifdef CONFIG_VMCORE_INFO
void hwerr_log_error_type(enum hwerr_error_type src);
#else
static inline void hwerr_log_error_type(enum hwerr_error_type src) {};
#endif
```

The tracepoint is [`aer_event`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) of the `ras` trace system, defined in include/ras/ras_event.h under [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), and its fields are the values «5» passes.

```c
/* include/ras/ras_event.h:337 */
TRACE_EVENT(aer_event,
	TP_PROTO(const char *dev_name,
		 const u32 status,
		 const u8 severity,
		 const u8 tlp_header_valid,
		 struct pcie_tlp_log *tlp,
		 const char *bus_type),


	TP_ARGS(dev_name, status, severity, tlp_header_valid, tlp, bus_type),

	TP_STRUCT__entry(
		__string(	dev_name,	dev_name	)
		__field(	u32,		status		)
		__field(	u8,		severity	)
		__field(	u8, 		tlp_header_valid)
		__array(	u32, 		tlp_header, PCIE_STD_MAX_TLP_HEADERLOG)
		__string(	bus_type,	bus_type	)
	),

	TP_fast_assign(
		__assign_str(dev_name);
		__assign_str(bus_type);
		__entry->status		= status;
		__entry->severity	= severity;
		__entry->tlp_header_valid = tlp_header_valid;
		if (tlp_header_valid) {
			int i;

			for (i = 0; i < PCIE_STD_MAX_TLP_HEADERLOG; i++)
				__entry->tlp_header[i] = tlp->dw[i];
		}
	),

	TP_printk("%s %s Bus Error: severity=%s, %s, TLP Header=%s\n",
		__get_str(dev_name), __get_str(bus_type),
		__entry->severity == AER_CORRECTABLE ? "Corrected" :
			__entry->severity == AER_FATAL ?
			"Fatal" : "Uncorrected, non-fatal",
		__entry->severity == AER_CORRECTABLE ?
		__print_flags(__entry->status, "|", aer_correctable_errors) :
		__print_flags(__entry->status, "|", aer_uncorrectable_errors),
		__entry->tlp_header_valid ?
			__print_array(__entry->tlp_header, PCIE_STD_MAX_TLP_HEADERLOG, 4) :
			"Not available")
);
```

The event records the function's name, the unmasked status bits, the class, the flag of a logged header, the fourteen TLP log dwords when that flag is set, and the bus type string. Its output names the class "Corrected", "Fatal" or "Uncorrected, non-fatal" and decodes the status bits by name. commit [6bb4befbd65f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6bb4befbd65fa7f99688fb707e376637e5acfe36) ("PCI/AER: Trace error event before ratelimiting") moved the event in front of the ratelimit, so a tracer sees every report the printer sees. The ratelimit itself is [`aer_ratelimit()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L800), which picks the state for the class from the function's [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60).

```c
/* drivers/pci/pcie/aer.c:800 */
static int aer_ratelimit(struct pci_dev *dev, unsigned int severity)
{
	if (!dev->aer_info)
		return 1;

	switch (severity) {
	case AER_NONFATAL:
		return __ratelimit(&dev->aer_info->nonfatal_ratelimit);
	case AER_CORRECTABLE:
		return __ratelimit(&dev->aer_info->correctable_ratelimit);
	default:
		return 1;	/* Don't ratelimit fatal errors */
	}
}
```

A function without the structure, and every [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) report, passes unlimited. Non-fatal and correctable reports go through `__ratelimit()` on their own state, set up by the allocation shown above, so a storm of firmware reports for one function still counts and traces each report while its console lines thin out.

### The ratelimit decides which reports reach the console

A report that passed the ratelimit is printed as a short block of lines named after the AER registers it came from, which a reader of the log can match against the register drawings. ❷ The second piece of [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) derives the layer and the agent from the status and prints.

```c
/* drivers/pci/pcie/aer.c:960 */

	layer = AER_GET_LAYER_ERROR(aer_severity, status);
	agent = AER_GET_AGENT(aer_severity, status);

	aer_printk(info.level, dev, "aer_status: 0x%08x, aer_mask: 0x%08x\n",
		   status, mask);
	__aer_print_error(dev, &info);
	aer_printk(info.level, dev, "aer_layer=%s, aer_agent=%s\n",
		   aer_error_layer[layer], aer_agent_string[agent]);

	if (aer_severity != AER_CORRECTABLE)
		aer_printk(info.level, dev, "aer_uncor_severity: 0x%08x\n",
			   aer->uncor_severity);

	if (tlp_header_valid)
		pcie_print_tlp_log(dev, &aer->header_log, info.level,
				   dev_fmt("  "));
}
```

The printer writes four kinds of line, all through [`aer_printk()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L41) at the level chosen earlier: the status and mask, one line per set bit from [`__aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L829), the layer and the agent, and, for an uncorrectable report, the whole Uncorrectable Error Severity register. The layer and the agent come from two macros of aer.c that test the status against masks of error bits.

```c
/* drivers/pci/pcie/aer.c:427 */
#define AER_AGENT_RECEIVER		0
#define AER_AGENT_REQUESTER		1
#define AER_AGENT_COMPLETER		2
#define AER_AGENT_TRANSMITTER		3

#define AER_AGENT_REQUESTER_MASK(t)	((t == AER_CORRECTABLE) ?	\
	0 : (PCI_ERR_UNC_COMP_TIME|PCI_ERR_UNC_UNSUP))
#define AER_AGENT_COMPLETER_MASK(t)	((t == AER_CORRECTABLE) ?	\
	0 : PCI_ERR_UNC_COMP_ABORT)
#define AER_AGENT_TRANSMITTER_MASK(t)	((t == AER_CORRECTABLE) ?	\
	(PCI_ERR_COR_REP_ROLL|PCI_ERR_COR_REP_TIMER) : 0)

#define AER_GET_AGENT(t, e)						\
	((e & AER_AGENT_COMPLETER_MASK(t)) ? AER_AGENT_COMPLETER :	\
	(e & AER_AGENT_REQUESTER_MASK(t)) ? AER_AGENT_REQUESTER :	\
	(e & AER_AGENT_TRANSMITTER_MASK(t)) ? AER_AGENT_TRANSMITTER :	\
	AER_AGENT_RECEIVER)

#define AER_PHYSICAL_LAYER_ERROR	0
#define AER_DATA_LINK_LAYER_ERROR	1
#define AER_TRANSACTION_LAYER_ERROR	2

#define AER_PHYSICAL_LAYER_ERROR_MASK(t) ((t == AER_CORRECTABLE) ?	\
	PCI_ERR_COR_RCVR : 0)
#define AER_DATA_LINK_LAYER_ERROR_MASK(t) ((t == AER_CORRECTABLE) ?	\
	(PCI_ERR_COR_BAD_TLP|						\
	PCI_ERR_COR_BAD_DLLP|						\
	PCI_ERR_COR_REP_ROLL|						\
	PCI_ERR_COR_REP_TIMER) : PCI_ERR_UNC_DLP)

#define AER_GET_LAYER_ERROR(t, e)					\
	((e & AER_PHYSICAL_LAYER_ERROR_MASK(t)) ? AER_PHYSICAL_LAYER_ERROR : \
	(e & AER_DATA_LINK_LAYER_ERROR_MASK(t)) ? AER_DATA_LINK_LAYER_ERROR : \
	AER_TRANSACTION_LAYER_ERROR)
```

[`AER_GET_AGENT()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L439) names the completer for a Completer Abort, the requester for a Completion Timeout or an Unsupported Request, the transmitter for the two replay errors, and the receiver otherwise. [`AER_GET_LAYER_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L457) names the Physical Layer for a correctable Receiver Error, the Data Link Layer for the correctable link errors and the uncorrectable Data Link Protocol error, and the Transaction Layer otherwise, and the two indices select strings from [`aer_error_layer`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L471) and [`aer_agent_string`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L547). The status is tested in priority order, so a status with several bits set names the agent and the layer of the first match. [`aer_printk()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L41) is a thin wrapper over the driver core's printk.

```c
/* drivers/pci/pcie/aer.c:41 */
#define aer_printk(level, pdev, fmt, arg...) \
	dev_printk(level, &(pdev)->dev, fmt, ##arg)
```

Every line therefore goes out through `dev_printk()` with the function's embedded device. [`__aer_print_error()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L829) prints one line per unmasked status bit, using the string tables of aer.c.

```c
/* drivers/pci/pcie/aer.c:829 */
static void __aer_print_error(struct pci_dev *dev, struct aer_err_info *info)
{
	const char **strings;
	unsigned long status = info->status & ~info->mask;
	const char *level = info->level;
	const char *errmsg;
	int i;

	if (info->severity == AER_CORRECTABLE)
		strings = aer_correctable_error_string;
	else
		strings = aer_uncorrectable_error_string;

	for_each_set_bit(i, &status, 32) {
		errmsg = strings[i];
		if (!errmsg)
			errmsg = "Unknown Error Bit";

		aer_printk(level, dev, "   [%2d] %-22s%s\n", i, errmsg,
				info->first_error == i ? " (First)" : "");
	}
}
```

A bit without a name in the table prints as "Unknown Error Bit", and the bit at [`first_error`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L846) carries " (First)". The last line is the TLP, which [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106) prints from the copy's [`header_log`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L49).

```c
/* drivers/pci/pcie/tlp.c:97 */
/**
 * pcie_print_tlp_log - Print TLP Header / Prefix Log contents
 * @dev: PCIe device
 * @log: TLP Log structure
 * @level: Printk log level
 * @pfx: String prefix
 *
 * Prints TLP Header and Prefix Log information held by @log.
 */
void pcie_print_tlp_log(const struct pci_dev *dev,
			const struct pcie_tlp_log *log, const char *level,
			const char *pfx)
{
	/* EE_PREFIX_STR fits the extended DW space needed for the Flit mode */
	char buf[11 * PCIE_STD_MAX_TLP_HEADERLOG + 1];
	unsigned int i;
	int len;

	len = scnprintf(buf, sizeof(buf), "%#010x %#010x %#010x %#010x",
			log->dw[0], log->dw[1], log->dw[2], log->dw[3]);

	if (log->flit) {
		for (i = PCIE_STD_NUM_TLP_HEADERLOG; i < log->header_len; i++) {
			len += scnprintf(buf + len, sizeof(buf) - len,
					 " %#010x", log->dw[i]);
		}
	} else {
		if (log->prefix[0])
			len += scnprintf(buf + len, sizeof(buf) - len,
					 EE_PREFIX_STR);
		for (i = 0; i < ARRAY_SIZE(log->prefix); i++) {
			if (!log->prefix[i])
				break;
			len += scnprintf(buf + len, sizeof(buf) - len,
					 " %#010x", log->prefix[i]);
		}
	}

	dev_printk(level, &dev->dev, "%sTLP Header%s: %s\n", pfx,
		log->flit ? " (Flit)" : "", buf);
}
```

The first four dwords always print. After them the function reads [`flit`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L38), and either the dwords up to [`header_len`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L37) or the [`prefix`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L34) dwords, all members that, in a firmware copy, lie past the Header Log at offsets of other registers, as the two views of the copied bytes showed. The report has now reached the console, the counters and the trace buffer, and what is left for it is recovery.

So far, a report has crossed the ring, been matched to its [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), and been counted, traced and possibly printed, the ➎ column of the strip, while its region is about to go back to the pool at ➏.

### The class chooses how recovery treats the function

The work function passes an uncorrectable report to [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), the PCI core's error recovery, which asks the drivers below the reporting point whether they can continue and resets the link when they cannot. The AER class becomes a channel state, the value recovery hands to every driver to say whether it can still reach its device, and the values are an enumeration of include/linux/pci.h.

```c
/* include/linux/pci.h:199 */
/**
 * typedef pci_channel_state_t
 *
 * The pci_channel state describes connectivity between the CPU and
 * the PCI device.  If some PCI bus between here and the PCI device
 * has crashed or locked up, this info is reflected here.
 */
typedef unsigned int __bitwise pci_channel_state_t;

enum {
	/* I/O channel is in normal state */
	pci_channel_io_normal = (__force pci_channel_state_t) 1,

	/* I/O to channel is blocked */
	pci_channel_io_frozen = (__force pci_channel_state_t) 2,

	/* PCI card is dead */
	pci_channel_io_perm_failure = (__force pci_channel_state_t) 3,
};
```

[`AER_NONFATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L14) becomes [`pci_channel_io_normal`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L210) and [`AER_FATAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/aer.h#L15) becomes [`pci_channel_io_frozen`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L213), and the third value is never passed from this path. The stage of [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) below shows the choice of the recovery point, the effect of the state, and the step that depends on who owns AER.

```c
/* drivers/pci/pcie/err.c:210 */
pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,
		pci_channel_state_t state,
		pci_ers_result_t (*reset_subordinates)(struct pci_dev *pdev))
{
	int type = pci_pcie_type(dev);
	struct pci_dev *bridge;
	pci_ers_result_t status = PCI_ERS_RESULT_CAN_RECOVER;
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	... /* 10 lines, to :228 */
	if (type == PCI_EXP_TYPE_ROOT_PORT ||
	    type == PCI_EXP_TYPE_DOWNSTREAM ||
	    type == PCI_EXP_TYPE_RC_EC ||
	    type == PCI_EXP_TYPE_RC_END)
		bridge = dev;
	else
		bridge = pci_upstream_bridge(dev);

	pci_walk_bridge(bridge, pci_pm_runtime_get_sync, NULL);

	pci_dbg(bridge, "broadcast error_detected message\n");
	if (state == pci_channel_io_frozen)
		pci_walk_bridge(bridge, report_frozen_detected, &status);
	else
		pci_walk_bridge(bridge, report_normal_detected, &status);
	... /* 7 lines, to :250 */
	if (status == PCI_ERS_RESULT_NEED_RESET ||
	    state == pci_channel_io_frozen) {
		if (reset_subordinates(bridge) != PCI_ERS_RESULT_RECOVERED) {
			pci_warn(bridge, "subordinate device reset failed\n");
			goto failed;
		}
	}
	... /* 18 lines, to :275 */
	/*
	 * If we have native control of AER, clear error status in the device
	 * that detected the error.  If the platform retained control of AER,
	 * it is responsible for clearing this status.  In that case, the
	 * signaling device may not even be visible to the OS.
	 */
	if (host->native_aer || pcie_ports_native) {
		pcie_clear_device_status(dev);
		pci_aer_clear_nonfatal_status(dev);
	}
```

An error reported for an Endpoint is recovered at the bridge above it, and one reported for a Root Port or a Downstream Port at the port itself, with everything below it. A frozen channel always resets, by calling the `reset_subordinates` parameter, which the work function sets to [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667); a normal channel resets only when a driver answered that it needs one. After the drivers resume, the device and AER status of the reporting function are cleared only when the kernel owns AER, and the comment hands the clearing to firmware otherwise. [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) is the reset callback, and it is written for both owners.

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

Under firmware control both blocks guarded by [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) are skipped, so the Root Port's AER interrupt is neither disabled nor re-enabled, and its Root Error Status is left alone. What remains is the reset itself, an FLR of the function for an RCEC or an RCiEP and a reset of the link below the bridge otherwise, with its "has been reset" or "link has been reset" message. The spans set the two sequences side by side.

```text
    Recovery around the reset, with and without native AER control
    ──────────────────────────────────────────────────────────────

    native_aer set, or pcie_ports=native
    time ────────────────────────────────────────────────────────────────────────────────────────────────▶
         ├─ the Root Port's AER interrupt is off ─────────────────────────┤
            ├─ link reset of the bridge ┤ ├─ Root Error Status cleared ┤
                                                                             ├─ function status cleared ─┤

    native_aer clear, no pcie_ports=native
    time ────────────────────────────────────────────────────────────────────────────────────────────────▶
            ├─ link reset of the bridge ┤

    function status = the device status and the AER status of the function that reported the error
    without native control, Root Error Status and the function status are left to firmware
    the link reset runs for a frozen channel or when a driver asks for one; an RCEC or RCiEP takes an FLR instead
```

On the firmware path, then, recovery touches the drivers and the link and no AER register. Its result is not checked by the work function, which drops its reference and takes the next report from the ring.

### Overflow and a failed lookup drop a report and strand its region

Every report owns a region of the GHES pool from ➊ on, and the same pool serves every record GHES handles, so a path that loses a report without freeing its region leaves that memory unusable for later records. Two branches of this path do that. The first is the overflow branch of [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263), shown again below.

```c
/* drivers/pci/pcie/aer.c:1263 */
void aer_recover_queue(int domain, unsigned int bus, unsigned int devfn,
		       int severity, struct aer_capability_regs *aer_regs)
	... /* 9 lines, to :1274 */
	if (kfifo_in_spinlocked(&aer_recover_ring, &entry, 1,
				 &aer_recover_ring_lock))
		schedule_work(&aer_recover_work);
	else
		pr_err("buffer overflow in recovery for %04x:%02x:%02x.%x\n",
		       domain, bus, PCI_SLOT(devfn), PCI_FUNC(devfn));
}
```

With the ring full, the report is never copied in, and the only pointer to the region was the `aer_regs` parameter, which goes out of scope when the function returns. [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) ignores the outcome, since the queue returns nothing, so the region stays allocated from ➋ on. The second branch is the lookup failure in [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218).

```c
/* drivers/pci/pcie/aer.c:1218 */
static void aer_recover_work_func(struct work_struct *work)
{
	... /* 3 lines, to :1223 */
	while (kfifo_get(&aer_recover_ring, &entry)) {
		pdev = pci_get_domain_bus_and_slot(entry.domain, entry.bus,
						   entry.devfn);
		if (!pdev) {
			pr_err_ratelimited("%04x:%02x:%02x.%x: no pci_dev found\n",
					   entry.domain, entry.bus,
					   PCI_SLOT(entry.devfn),
					   PCI_FUNC(entry.devfn));
			continue;
		}
```

The `continue` skips the call to [`ghes_estatus_pool_region_free()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L238) further down, and the slot the report came from is already free, so the region's address is gone with the local entry. At v7.2 [`ghes_estatus_pool_region_free()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L238) has one caller, the work function, and every other release into the pool in ghes.c frees an object of GHES itself.

| Site | What it releases |
|---|---|
| [`ghes.c:495`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L495) | the memory-failure callback a synchronous memory error queued |
| [`ghes.c:723`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L723) | the copy of a vendor record handed to its notifier |
| [`ghes.c:1096`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1096) | an entry of the cache that suppresses repeated printouts |
| [`ghes.c:1307`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1307) | a record an NMI handler queued, after [`ghes_proc_in_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1278) processed it |
| [`ghes.c:1394`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1394) | a record the NMI path could not queue |

Neither drop leaves a reference behind, and each keeps its region allocated in the pool for as long as the kernel runs. The overflow branch prints "buffer overflow in recovery for" with the address, and the lookup failure prints "no pci_dev found" under a ratelimit, so the log names each dropped report, the second kind up to the ratelimit.

### CONFIG_ACPI_APEI_PCIEAER gates the ring and the producer

The path exists only in a kernel built with [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37), the option that joins the APEI side to the AER side. Its Kconfig entry states both dependencies and gives no default.

```c
/* drivers/acpi/apei/Kconfig:37 */
config ACPI_APEI_PCIEAER
	bool "APEI PCIe AER logging/recovering support"
	depends on ACPI_APEI && PCIEAER
	help
	  PCIe AER errors may be reported via APEI firmware first mode.
	  Turn on this option to enable the corresponding support.
```

The option needs [`CONFIG_ACPI_APEI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L8) and [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), and a configuration that does not set it builds without the path. In aer.c the option encloses [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912), as its unit showed, and the ring with everything after it up to the export of [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263), whose opening and closing lines are shown again below.

```c
/* drivers/pci/pcie/aer.c:1203 */
#ifdef CONFIG_ACPI_APEI_PCIEAER

#define AER_RECOVER_RING_SIZE		16
```

```c
/* drivers/pci/pcie/aer.c:1263 */
void aer_recover_queue(int domain, unsigned int bus, unsigned int devfn,
		       int severity, struct aer_capability_regs *aer_regs)
... /* 15 lines, to :1280 */
}
EXPORT_SYMBOL_GPL(aer_recover_queue);
#endif
```

In ghes.c it encloses the body of [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640), shown again from its signature to its closing brace with the body folded.

```c
/* drivers/acpi/apei/ghes.c:640 */
static void ghes_handle_aer(struct acpi_hest_generic_data *gdata)
{
#ifdef CONFIG_ACPI_APEI_PCIEAER
	struct cper_sec_pcie *pcie_err = acpi_hest_get_payload(gdata);
	... /* 30 lines, to :674 */
	}
#endif
}
```

The table sets out which option builds each part of the path, with the build rule that compiles each file.

| Part of the path | File | Built when |
|---|---|---|
| the notification handlers, the pool, the record printout and an empty [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) | ghes.c, by [`drivers/acpi/apei/Makefile:3`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Makefile#L3) | [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20) is set |
| the body of [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640) | ghes.c | [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) is set as well |
| [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912), [`aer_recover_ring`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1215), [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) and [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) | aer.c | [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37) is set |
| [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926), the counters and [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) | aer.c, by [`drivers/pci/pcie/Makefile:10`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Makefile#L10) | [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) is set |
| [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) and [`pcie_print_tlp_log()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L106) | err.c and tlp.c, by the same line | [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) is set |

With the option set, a PCIe section with both validation bits produces a report, the ring and the work item carry it, and the printer and recovery run in the kworker. With it unset, the producer is an empty function, so GHES still prints the record in [`ghes_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1176) and the PCI core sees nothing of it, no counter, no tracepoint and no recovery, while [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) stays built with [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) for its other callers. The option is a build-time switch, so a running kernel has no way to turn the path off and on. The option also does not depend on [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20), and include/acpi/ghes.h covers that case with an empty inline in the `#else` branch of its `#ifdef` [`CONFIG_ACPI_APEI_GHES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L20) block.

```c
/* include/acpi/ghes.h:87 */
void ghes_estatus_pool_region_free(unsigned long addr, u32 size);
#else
static inline struct list_head *ghes_get_devices(void) { return NULL; }

static inline void ghes_estatus_pool_region_free(unsigned long addr, u32 size) { return; }
#endif
```

Without GHES, ghes.c is not built, so [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640), the only caller of [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) at v7.2, does not exist, and the ring is compiled but never filled. The extended error log driver of [`CONFIG_ACPI_EXTLOG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L494) carries a second PCIe printer for the records of I/O machine checks, and [`extlog_print_pcie()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/acpi_extlog.c#L136) tests the option under another name.

```c
/* drivers/acpi/acpi_extlog.c:136 */
static void extlog_print_pcie(struct cper_sec_pcie *pcie_err,
			      int severity)
{
#ifdef ACPI_APEI_PCIEAER
	struct aer_capability_regs *aer;
	struct pci_dev *pdev;
	unsigned int devfn;
	unsigned int bus;
	int aer_severity;
	int domain;

	if (!(pcie_err->validation_bits & CPER_PCIE_VALID_DEVICE_ID &&
	      pcie_err->validation_bits & CPER_PCIE_VALID_AER_INFO))
		return;

	aer_severity = cper_severity_to_aer(severity);
	aer = (struct aer_capability_regs *)pcie_err->aer_info;
	domain = pcie_err->device_id.segment;
	bus = pcie_err->device_id.bus;
	devfn = PCI_DEVFN(pcie_err->device_id.device,
			  pcie_err->device_id.function);
	pdev = pci_get_domain_bus_and_slot(domain, bus, devfn);
	if (!pdev)
		return;

	pci_print_aer(pdev, aer_severity, aer);
	pci_dev_put(pdev);
#endif
}
```

The guard tests `ACPI_APEI_PCIEAER`, a preprocessor name that nothing in the tree defines at v7.2, since Kconfig emits the option as [`CONFIG_ACPI_APEI_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L37). The body is therefore removed by the preprocessor under every configuration, and the function is empty even with both options set. The guard came with commit [e778ffefa34d](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=e778ffefa34ddcdc32a260452627e390941812eb) ("ACPI: extlog: Trace CPER PCI Express Error Section"), and its body would have called [`cper_severity_to_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L912) and [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) without the ring, as a printer only.

So far, the path has been followed from the `_OSC` decision through the record, the copy, the ring, the printer and recovery to the two branches that lose a region, and the option above decides whether any of it is built.

### Messages, tracepoints and hand-offs make the path visible

A reader who suspects that a firmware-reported error went missing can follow it through the printouts and events of each stage, and the tables below list them in the order the path reaches them. Of the functions this page shows, [`pci_print_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L926) is the one that fires a tracepoint, [`aer_event`](https://elixir.bootlin.com/linux/v7.2/source/include/ras/ras_event.h#L337) at «5» of the printer's figure, for every report that matches a function, before the ratelimit. Neither [`ghes_handle_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L640), [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) nor [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) fires a tracepoint of its own, and the dispatch of a PCIe section in [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912) fires none, as their units show. The disabled printer of the extended error log fires nothing either.

The first printout of a firmware-reported error is the record itself, which [`ghes_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1176) prints through [`ghes_print_estatus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1005) when [`ghes_estatus_cached()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1029) has not seen the same record recently. The printer applies a ratelimit of its own.

```c
/* drivers/acpi/apei/ghes.c:1005 */
static int ghes_print_estatus(const char *pfx,
			      const struct acpi_hest_generic *generic,
			      const struct acpi_hest_generic_status *estatus)
{
	/* Not more than 2 messages every 5 seconds */
	static DEFINE_RATELIMIT_STATE(ratelimit_corrected, 5*HZ, 2);
	static DEFINE_RATELIMIT_STATE(ratelimit_uncorrected, 5*HZ, 2);
	struct ratelimit_state *ratelimit;

	if (ghes_severity(estatus->error_severity) <= GHES_SEV_CORRECTED)
		ratelimit = &ratelimit_corrected;
	else
		ratelimit = &ratelimit_uncorrected;
	if (__ratelimit(ratelimit)) {
		__ghes_print_estatus(pfx, generic, estatus);
		return 1;
	}
	return 0;
}
```

At most two records of each kind print every five seconds, the corrected ones and the others, independent of the per-function ratelimits of the AER printer. The table lists every message of the path in the order a report meets them.

| Site | Message | Level | What it reports |
|---|---|---|---|
| [`ghes.c:1190`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1190) | the record printout of [`ghes_print_estatus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L1005) | by record severity | the whole record, the PCIe section's fields included, before the PCI core sees it |
| [`aer.c:1278-1279`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1278) | "buffer overflow in recovery for %04x:%02x:%02x.%x" | `pr_err` | a report dropped because the ring was full |
| [`aer.c:1227-1230`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1227) | "%04x:%02x:%02x.%x: no pci_dev found" | `pr_err_ratelimited` | a report whose function the kernel does not know |
| [`aer.c:964-972`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L964) | "aer_status:", the bit names, "aer_layer=", "aer_uncor_severity:" | warning or error | the copy of the registers, after the ratelimit |
| [`tlp.c:135-136`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/tlp.c#L135) | "TLP Header" | warning or error | the logged TLP, when a header was logged |
| [`aer.c:1699-1705`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1699) | "has been reset", "not reset", "link has been reset" | `pci_info` | the reset done by [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) |
| [`err.c:253`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L253) | "subordinate device reset failed" | `pci_warn` | a reset that did not recover |
| [`err.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L288) | "device recovery successful" | `pci_info` | the end of a recovery that worked |
| [`err.c:296`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L296) | "device recovery failed" | `pci_info` | the end of a recovery that did not |

The functions of this page contain no `pci_dbg()`, `dev_dbg()` or `pr_debug()` site. The recovery stage has four `pci_dbg()` sites, which with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set are switchable callsites in /sys/kernel/debug/dynamic_debug/control, and [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), left unset, would turn them on for every build.

| Site | Message | What enabling it shows |
|---|---|---|
| [`err.c:238`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L238) | "broadcast error_detected message" | that recovery reached the drivers below the bridge, for either class |
| [`err.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L246) | "broadcast mmio_enabled message" | that every driver could continue without a reset |
| [`err.c:265`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L265) | "broadcast slot_reset message" | that a reset happened and drivers are asked to reinitialize |
| [`err.c:272`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L272) | "broadcast resume message" | that recovery reached its last phase |

Enabling them for err.c shows which phases a firmware-reported error took recovery through, which the two `pci_info()` lines at the end summarize only as success or failure. The path crosses three asynchronous hand-offs and one synchronous one, from the GHES notification to the kworker, and the swimlane of the queue's subsection draws the second and third.

| Hand-off | From | To |
|---|---|---|
| the GHES notification, an interrupt, a timer, the HED notifier or an NMI deferred through irq_work | firmware | [`ghes_do_proc()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/ghes.c#L912) with interrupts disabled |
| [`aer_recover_ring`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1215) | [`aer_recover_queue()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1263) in that context | [`aer_recover_work_func()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1218) |
| the work item [`aer_recover_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1261) on the system per-CPU workqueue | [`schedule_work()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/workqueue.h#L758) | a kworker |
| [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210), synchronous | the kworker | the error handlers of the drivers below the bridge |

No timer, RCU callback or notifier chain of the PCI core lies on the path, and the drivers' error handlers run in the kworker that took the report.

### sysfs counters, a boot parameter and injectors expose the path

The counters [`pci_dev_aer_stats_incr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L747) updates are the path's lasting trace, and they appear in the sysfs directory of every function that has an AER capability. [`aer_stats_attr_group`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L637) lists the files and hides them for a function without [`aer_info`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L371).

```c
/* drivers/pci/pcie/aer.c:608 */
static struct attribute *aer_stats_attrs[] __ro_after_init = {
	&dev_attr_aer_dev_correctable.attr,
	&dev_attr_aer_dev_fatal.attr,
	&dev_attr_aer_dev_nonfatal.attr,
	&dev_attr_aer_rootport_total_err_cor.attr,
	&dev_attr_aer_rootport_total_err_fatal.attr,
	&dev_attr_aer_rootport_total_err_nonfatal.attr,
	NULL
};

static umode_t aer_stats_attrs_are_visible(struct kobject *kobj,
					   struct attribute *a, int n)
{
	struct device *dev = kobj_to_dev(kobj);
	struct pci_dev *pdev = to_pci_dev(dev);

	if (!pdev->aer_info)
		return 0;

	if ((a == &dev_attr_aer_rootport_total_err_cor.attr ||
	     a == &dev_attr_aer_rootport_total_err_fatal.attr ||
	     a == &dev_attr_aer_rootport_total_err_nonfatal.attr) &&
	    ((pci_pcie_type(pdev) != PCI_EXP_TYPE_ROOT_PORT) &&
	     (pci_pcie_type(pdev) != PCI_EXP_TYPE_RC_EC)))
		return 0;

	return a->mode;
}

const struct attribute_group aer_stats_attr_group = {
	.attrs  = aer_stats_attrs,
	.is_visible = aer_stats_attrs_are_visible,
};
```

The files `/sys/bus/pci/devices/<function>/aer_dev_correctable`, `aer_dev_fatal` and `aer_dev_nonfatal` show the counters this path increments, one count per bit and the totals of [`struct aer_info`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L60). The three Root Port totals stay at zero for firmware-reported errors, because the printer calls the device counter only, and they count the messages a native Root Port receives. The ratelimits of the printer are files of the `/sys/bus/pci/devices/<function>/aer/` directory, the group [`aer_attr_group`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L741), with the same visibility rule. [`aer_ratelimit_attrs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L712) generates the handlers of the interval and burst files of one class, and the unit below starts at that macro and its two uses.

```c
/* drivers/pci/pcie/aer.c:712 */
#define aer_ratelimit_attrs(name)					\
	aer_ratelimit_interval_attr(name##_ratelimit_interval_ms,	\
				    name##_ratelimit)			\
	aer_ratelimit_burst_attr(name##_ratelimit_burst,		\
				 name##_ratelimit)

aer_ratelimit_attrs(correctable)
aer_ratelimit_attrs(nonfatal)

static struct attribute *aer_attrs[] = {
	&dev_attr_correctable_ratelimit_interval_ms.attr,
	&dev_attr_correctable_ratelimit_burst.attr,
	&dev_attr_nonfatal_ratelimit_interval_ms.attr,
	&dev_attr_nonfatal_ratelimit_burst.attr,
	NULL
};

static umode_t aer_attrs_are_visible(struct kobject *kobj,
				     struct attribute *a, int n)
{
	struct device *dev = kobj_to_dev(kobj);
	struct pci_dev *pdev = to_pci_dev(dev);

	if (!pdev->aer_info)
		return 0;

	return a->mode;
}

const struct attribute_group aer_attr_group = {
	.name = "aer",
	.attrs = aer_attrs,
	.is_visible = aer_attrs_are_visible,
};
```

Writing the interval or the burst of a class changes how many firmware reports of that class reach the console, and leaves the counters and the tracepoint unaffected. The boot parameter that changes the path is `pcie_ports=native`, parsed by [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622).

```c
/* drivers/pci/pcie/portdrv.c:609 */
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

According to the comment, "native" means the kernel ignores `_OSC`, and [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) makes it claim AER even when firmware withheld it, so the port driver adds the AER service and [`aer_root_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1667) and [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) take their native branches for firmware-reported errors too. The `pci=noaer` option is not consulted anywhere on the path, since neither the work function nor the printer tests it.

Two injectors exist, and neither is this path's. The AER injector of [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) works by raising the interrupt of the Root Port's AER service, and its stage below shows the lookup that fails when firmware owns AER.

```c
/* drivers/pci/pcie/aer_inject.c:319 */
static int aer_inject(struct aer_error_inj *einj)
{
	struct aer_error *err, *rperr;
	... /* 142 lines, to :464 */
	device = pcie_port_find_device(rpdev, PCIE_PORT_SERVICE_AER);
	if (device) {
		edev = to_pcie_device(device);
		if (!get_service_data(edev)) {
			pci_warn(edev->port, "AER service is not initialized\n");
			ret = -EPROTONOSUPPORT;
			goto out_put;
		}
		pci_info(edev->port, "Injecting errors %08x/%08x into device %s\n",
			 einj->cor_status, einj->uncor_status, pci_name(dev));
		ret = irq_inject_interrupt(edev->irq);
	} else {
		pci_err(rpdev, "AER device not found\n");
		ret = -ENODEV;
	}
```

Under firmware control the port has no AER service, so [`aer_inject()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L319) prints "AER device not found" and returns `-ENODEV`. The APEI injector of [`CONFIG_ACPI_APEI_EINJ`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/apei/Kconfig#L56) asks firmware to raise an error, through an "einj" directory in the APEI debugfs directory, and this page does not follow it into firmware. No debugfs or procfs file shows the ring, its counters or the regions it holds.
