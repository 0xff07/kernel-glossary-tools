# PCIe port service interrupts

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe port can run up to five services at once, and each one needs an interrupt for the events it handles. Those events range from power management and hotplug to link bandwidth changes, errors and containment. The port is one function with one interrupt setup, so the port driver, portdrv, allocates its MSI-X or MSI vectors once. It then hands every service the Linux IRQ of the vector its hardware signals. Registers in the port's configuration space name those vectors, and three of the services read the same register. This page traces how portdrv counts, allocates and distributes the vectors, when it falls back to the port's pin interrupt, and how each service receives and requests its IRQ.

```text
    Three message numbers select vectors, and the five service slots take their IRQs
    ────────────────────────────────────────────────────────────────────────────────

    register of the port        number  vector      Linux IRQ   irqs[], one slot per service bit
                                                               ┌────────────────────────────┐
    PCI Express Capabilities  ──▶ m ──▶ entry m ──▶ IRQ x ──┬─▶│ [0] PME     IRQ x          │
                                                            ├─▶│ [2] HP      IRQ x          │
                                                            └─▶│ [4] BWCTRL  IRQ x          │
                                                               ├────────────────────────────┤
    Root Error Status (AER)   ──▶ a ──▶ entry a ──▶ IRQ y ────▶│ [1] AER     IRQ y          │
                                                               ├────────────────────────────┤
    DPC Capability            ──▶ d ──▶ entry d ──▶ IRQ z ────▶│ [3] DPC     IRQ z          │
                                                               └──────────────┬─────────────┘
                                                                              │ slot i becomes the irq of the service
                                                                              ▼ instance whose service bit is 1 << i
                                                               ┌────────────────────────────┐
                                                               │ struct pcie_device, irq    │
                                                               │ one per service, whose     │
                                                               │ driver requests that IRQ   │
                                                               └────────────────────────────┘

    entry k is the MSI-X table entry k or the k-th MSI vector; x, y and z coincide where the numbers do
    with INTx in place of MSI-X and MSI, every slot holds the port's pin IRQ from pci_dev.irq
```

## SUMMARY

Each running service is a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance, whose [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) member points at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) and whose [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) member holds the Linux IRQ the service requests. The table pairs the specification's interrupt terms with the kernel objects that hold them.

| term in the specification | kernel representation | set by |
|---|---|---|
| Interrupt Message Number | the five-bit fields [`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496), [`PCI_ERR_ROOT_AER_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L834) and [`PCI_EXP_DPC_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1083), read into the locals `pme`, `aer` and `dpc` | [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) |
| MSI-X table entry or MSI vector | the index that [`pci_irq_vector()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L311) turns into a Linux IRQ | [`pci_alloc_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L232) |
| interrupt of a port service | a slot of the array `irqs`, indexed by service bit, then [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) | [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113), [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) |
| port service | a service bit such as [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20) and its [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) | [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) |
| INTx, the pin interrupt | [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454), the IRQ that ACPI routing assigns to the Interrupt Pin | [`acpi_pci_irq_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_irq.c#L384) |

The journey starts at the port's probe and settles one interrupt mode for the whole port. That mode is MSI-X or MSI with as many vectors as the largest message number needs, or else the pin interrupt for every service. In every mode PME, hotplug and bandwidth control receive the IRQ that the PCI Express Capabilities register names, while AER and DPC receive the IRQs their own registers name.

## SPECIFICATIONS

The interrupt fields this page reads are defined by the PCI Express Base Specification, and the vector limit by the MSI rules of the PCI Local Bus Specification; the tree cites both by revision and section without titles. The distribution of vectors to services is a kernel synthesis that no specification defines, read here from drivers/pci/pcie/portdrv.c.

- PCIe r3.1, sec 7.8.2, cited without a title by [`portdrv.c:25-29`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L25) for the Interrupt Message Number of the PCI Express Capability, which must fall in the first 32 MSI-X entries.
- PCI r3.0, sec 6.8.3.1, cited without a title by [`portdrv.c:25-29`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L25) for the limit of 32 MSI vectors per function.
- PCIe r3.1, sec 7.8.2, 7.10.10 and 7.31.2, cited without titles by [`portdrv.c:63-68`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L63) for the three Interrupt Message Number fields that [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads.
- PCIe Base Spec r5.0 sec 6.7.3.4, cited without a title by [`pciehp_hpc.c:689-693`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L689) for a port in MSI mode sending no new hotplug interrupt until every Slot Status event bit is zero.

## COVERAGE

### Vector allocation and distribution

- [`'\<pcie_init_service_irqs\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177): chooses the interrupt mode of the whole port and fills the service slots, falling back to the pin interrupt.
- [`'\<pcie_port_enable_irq_vec\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113): requests MSI-X or MSI vectors twice and gives each service slot the IRQ of its message number.
- [`'\<pcie_message_numbers\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57): reads the three Interrupt Message Numbers and returns the count of vectors the largest needs.
- [`'PCIE_PORT_MAX_MSI_ENTRIES'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L30): the ceiling of the first request, 32 vectors.
- [`'pcie_device.irq'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60): the Linux IRQ a service instance receives from its slot and its driver requests.

### The PME switch

- [`'\<pcie_pme_no_msi\>':'drivers/pci/pcie/portdrv.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113): tells the interrupt setup that PME signaling must avoid MSI.
- [`'\<pcie_pme_msi_disabled\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31): the global switch that a boot parameter or a DMI match sets.

### Interrupt Message Number fields, include/uapi/linux/pci_regs.h

- [`'PCI_EXP_FLAGS_IRQ'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496): the number in the PCI Express Capabilities register, shared by PME, hotplug and bandwidth control.
- [`'PCI_ERR_ROOT_AER_IRQ'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L834): the Advanced Error Interrupt Message Number in the Root Error Status register.
- [`'PCI_EXP_DPC_IRQ'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1083): the number in the DPC Capability register.

## DOCUMENTATION

- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the section on MSI and MSI-X vector resources says that service drivers request the irq of their instance and leave the port's interrupt mode to the port driver; the same paragraph names an `interrupt_mode` field that the struct no longer has at v7.2.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the `pcie_pme=nomsi`, `pci=nomsi` and `pcie_ports=` parameters that steer the port toward the pin interrupt or away from its services.
- [`Documentation/PCI/msi-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/msi-howto.rst): the [`pci_alloc_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L232) and [`pci_irq_vector()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L311) interface the port driver uses, and the `pci=nomsi` switch.
- [`Documentation/ABI/testing/sysfs-bus-pci`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci): the `irq` attribute and the `msi_irqs/` directory of a function, which show the port's pin IRQ or first MSI IRQ and its allocated vectors.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/portdrv: Use shared MSI/MSI-X vector for Bandwidth Management (commit 15d2aba7c602)](https://lore.kernel.org/lkml/155597243666.19387.1205950870601742062.stgit@gimli.home)
- [PCI/bwctrl: Re-add BW notification portdrv as PCIe BW controller (commit 665745f27487)](https://lore.kernel.org/r/20241018144755.7875-7-ilpo.jarvinen@linux.intel.com)
- [PCI/portdrv: Do not setup up IRQs if there are no users (commit 0e8ae5a6ff59)](https://lore.kernel.org/r/8f9a13ac-8ab1-15ac-06cb-c131b488a36f@siemens.com)
- [Revert "PCI/portdrv: Do not setup up IRQs if there are no users" (commit 075b7d363c67)](https://lore.kernel.org/r/20220210222717.GA658201@bhelgaas)
- [PCI/portdrv: Use FIELD_GET() (commit 8a0395578a9b)](https://lore.kernel.org/r/20231010204436.1000644-11-helgaas@kernel.org)
- [PCI/portdrv: Use PCI_IRQ_INTX instead of PCI_IRQ_LEGACY (commit a665b0a93f3b)](https://lore.kernel.org/r/20240325070944.3600338-3-dlemoal@kernel.org)

## REGISTERS

Three registers of the port's configuration space each carry an Interrupt Message Number, the vector that one group of the port's interrupts uses, and [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads all three. The drawings place each number among its register's other fields, which the paths of this page do not read.

```text
    PCI Express Capabilities register, 16 bits at PCI_EXP_FLAGS (0x02) of the PCI Express Capability
    ────────────────────────────────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    cap+2 │F│·│   IRQ   │S│  type │  vers │
          │ │ │  (13:9) │ │ (7:4) │ (3:0) │
          └─┴─┴─────────┴─┴───────┴───────┘

    IRQ = PCI_EXP_FLAGS_IRQ (0x3e00, the Interrupt Message Number of PME, hotplug and link bandwidth interrupts)
    F = PCI_EXP_FLAGS_FLIT (0x8000, Flit Mode Supported); S = PCI_EXP_FLAGS_SLOT (0x0100, Slot Implemented)
    type = PCI_EXP_FLAGS_TYPE (0x00f0, Device/Port Type); vers = PCI_EXP_FLAGS_VERS (0x000f, Capability Version)
    bit 14 has no macro in pci_regs.h; cap is the offset of the PCI Express Capability
```

[`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496) decides the vector of PME, hotplug and link bandwidth interrupts, and so the one IRQ that the three services share. The register is read at offset [`PCI_EXP_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L483) of the PCI Express Capability whenever the port runs any of the three services. The Device/Port Type and Slot Implemented fields beside the number are left to other paths.

```text
    Root Error Status register, 32 bits at PCI_ERR_ROOT_STATUS (0x30) of the AER Capability
    ───────────────────────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    aer+30│   IRQ   │            reserved (26:7)            │F│N│T│V│U│D│C│
          │ (31:27) │                                       │ │ │ │ │ │ │ │
          └─────────┴───────────────────────────────────────┴─┴─┴─┴─┴─┴─┴─┘

    IRQ = PCI_ERR_ROOT_AER_IRQ (0xf8000000, the Advanced Error Interrupt Message Number)
    C = PCI_ERR_ROOT_COR_RCV (ERR_COR Received); D = PCI_ERR_ROOT_MULTI_COR_RCV (Multiple ERR_COR)
    U = PCI_ERR_ROOT_UNCOR_RCV (ERR_FATAL/NONFATAL Received); V = PCI_ERR_ROOT_MULTI_UNCOR_RCV (Multiple FATAL/NONFATAL)
    T = PCI_ERR_ROOT_FIRST_FATAL (First UNC is Fatal); N = PCI_ERR_ROOT_NONFATAL_RCV; F = PCI_ERR_ROOT_FATAL_RCV
    bits 26:7 have no macro in pci_regs.h; aer is the offset of the AER Capability, held in aer_cap
```

[`PCI_ERR_ROOT_AER_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L834) decides the vector of the AER service. The register is read at the offset that [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) records, when that offset is nonzero and the port runs the AER service. The status bits below the number stay unread on these paths.

```text
    DPC Capability register, 16 bits at PCI_EXP_DPC_CAP (0x04) of the DPC Extended Capability
    ─────────────────────────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    dpc+4 │· ·│H│A│  log  │S│P│R│   IRQ   │
          │   │ │ │ (11:8)│ │ │ │  (4:0)  │
          └───┴─┴─┴───────┴─┴─┴─┴─────────┘

    IRQ = PCI_EXP_DPC_IRQ (0x001F, the Interrupt Message Number of DPC interrupts)
    R = PCI_EXP_DPC_CAP_RP_EXT (Root Port Extensions); P = PCI_EXP_DPC_CAP_POISONED_TLP (Poisoned TLP Egress Blocking)
    S = PCI_EXP_DPC_CAP_SW_TRIGGER (Software Triggering); log = PCI_EXP_DPC_RP_PIO_LOG_SIZE (RP PIO Log Size [3:0])
    A = PCI_EXP_DPC_CAP_DL_ACTIVE (ERR_COR on DL_Active); H = PCI_EXP_DPC_RP_PIO_LOG_SIZE4 (RP PIO Log Size [4])
    bits 15:14 have no macro in pci_regs.h; dpc is the offset of the DPC Extended Capability
```

[`PCI_EXP_DPC_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1083) decides the vector of the DPC service, read from the DPC Extended Capability whenever the port runs the DPC service. The DPC service prints the same field when it starts, so its value appears in the kernel log beside the IRQ it chose.

## DETAILS

DETAILS first sets out the model, an array of five IRQ slots that the port's probe fills before it creates its service instances. The function that chooses the interrupt mode for the whole port comes next, and the subsections after it follow that choice in order. They cover the switch that keeps PME off MSI, the registers whose message numbers name the vectors, the two vector requests and the distribution that gives three services one vector. The pin-interrupt fallback, the field of [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) that receives each slot and the service drivers that request it follow. The last subsections show the handlers that share one vector and the messages, tracepoints and files that make the distribution visible.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at the v7.2 tag, on x86-64 with ACPI firmware. The PCIe port, AER, DPC, hotplug, MSI and dynamic-debug options of the table are set on top of it. Power management comes from the defconfig itself, whose sleep options enable [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) and with it the PME service.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y, as in the defconfig | builds portdrv.c, the interrupt setup and the bandwidth service |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | builds the MSI-X and MSI allocator; unset, [`pci_alloc_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L232) grants only the pin interrupt |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | compiles the AER number read of [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) and builds the AER service |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y, through [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | lets [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) default to y |
| [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) | y | makes [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) return [`pcie_pme_msi_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31); unset, the test returns false |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds the DPC service that requests the DPC slot's IRQ |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds the hotplug service that requests the shared IRQ |
| [`CONFIG_DMI`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/Kconfig#L944) | y, the x86 default | lets the DMI match set the PME switch at boot |
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | routes the port's pin through `_PRT` to the IRQ of the fallback |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the debug lines of the bandwidth service and of the pin routing switchable at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would print the debug lines of drivers/pci unconditionally |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | n | would build the AER injector that raises the AER service's IRQ |

The table indexes the prose. Each subsection below names the option where its effect applies.

### Each service of a port reads one slot of an array

A PCIe port is one function, and one function owns one MSI-X table or one MSI capability, yet up to five services act on the port's behalf. Each service is a separate driver bound to its own [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance, so the port's probe decides every instance's interrupt before it creates the instances. The decisions land in an array of five Linux IRQ numbers, one slot per service, indexed by the bit numbers that portdrv.h gives the services.

[`PCIE_PORT_SERVICE_PME_SHIFT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L15) and the four shifts after it number the services, each mask such as [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) is one bit of a service mask, and [`PCIE_PORT_DEVICE_MAXSERVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L26) sizes the array. Read the definitions for the slot index each service owns.

```c
/* drivers/pci/pcie/portdrv.h:14 */
/* Service Type */
#define PCIE_PORT_SERVICE_PME_SHIFT	0	/* Power Management Event */
#define PCIE_PORT_SERVICE_PME		(1 << PCIE_PORT_SERVICE_PME_SHIFT)
#define PCIE_PORT_SERVICE_AER_SHIFT	1	/* Advanced Error Reporting */
#define PCIE_PORT_SERVICE_AER		(1 << PCIE_PORT_SERVICE_AER_SHIFT)
#define PCIE_PORT_SERVICE_HP_SHIFT	2	/* Native Hotplug */
#define PCIE_PORT_SERVICE_HP		(1 << PCIE_PORT_SERVICE_HP_SHIFT)
#define PCIE_PORT_SERVICE_DPC_SHIFT	3	/* Downstream Port Containment */
#define PCIE_PORT_SERVICE_DPC		(1 << PCIE_PORT_SERVICE_DPC_SHIFT)
#define PCIE_PORT_SERVICE_BWCTRL_SHIFT	4	/* Bandwidth Controller (notifications) */
#define PCIE_PORT_SERVICE_BWCTRL	(1 << PCIE_PORT_SERVICE_BWCTRL_SHIFT)

#define PCIE_PORT_DEVICE_MAXSERVICES   5
```

A service's slot index is its shift, from PME at 0 through AER, hotplug and DPC to bandwidth control at 4. Its bit in a service mask is 1 shifted left by that index. Five slots therefore cover every service portdrv defines at v7.2.

[`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) holds the array as its local `irqs` and fills it before it creates any instance. Its first stage enables the port and asks [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) for the mask of services the port runs. It passes the mask and the array to [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177); read the stage for what the probe does when that call fails.

```c
/* drivers/pci/pcie/portdrv.c:331 */
static int pcie_port_device_register(struct pci_dev *dev)
{
	int status, capabilities, i, nr_service;
	int irqs[PCIE_PORT_DEVICE_MAXSERVICES];

	/* Enable PCI Express port device */
	status = pci_enable_device(dev);
	if (status)
		return status;

	/* Get and check PCI Express port services */
	capabilities = get_port_device_capability(dev);
	if (!capabilities)
		return 0;

	pci_set_master(dev);
	/*
	 * Initialize service irqs. Don't use service devices that
	 * require interrupts if there is no way to generate them.
	 * However, some drivers may have a polling mode (e.g. pciehp_poll_mode)
	 * that can be used in the absence of irqs.  Allow them to determine
	 * if that is to be used.
	 */
	status = pcie_init_service_irqs(dev, irqs, capabilities);
	if (status) {
		capabilities &= PCIE_PORT_SERVICE_HP;
		if (!capabilities)
			goto error_disable;
	}
```

The local `capabilities` holds the service mask, and a port whose mask is empty returns before any interrupt work. When the interrupt setup fails, the mask keeps only [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20), because the hotplug service can poll its slot without an interrupt, as the comment above the call says.

Which slots receive an IRQ follows the mask. A slot whose service bit is absent keeps -1, the value the setup writes first, and the probe creates no instance for it. The figure shows a port whose mask holds hotplug, DPC and bandwidth control.

```text
    The five slots of irqs[] on a port whose services are hotplug, DPC and bandwidth control
    ────────────────────────────────────────────────────────────────────────────────────────

     [0] PME         [1] AER         [2] HP          [3] DPC         [4] BWCTRL
    ┌───────────────┬───────────────┬───────────────┬───────────────┬───────────────┐
    │ -1, a hole    │ -1, a hole    │ IRQ of HP     │ IRQ of DPC    │ IRQ of BWCTRL │
    └───────────────┴───────────────┴───────┬───────┴───────┬───────┴───────┬───────┘
                                            │               │               │
                                            ▼               ▼               ▼
                                     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
                                     │ service     │ │ service     │ │ service     │
                                     │ instance,   │ │ instance,   │ │ instance,   │
                                     │ irq = slot  │ │ irq = slot  │ │ irq = slot  │
                                     └─────────────┘ └─────────────┘ └─────────────┘

    with MSI-X or MSI, slots 0 and 1 keep -1, since their service bits are absent from the mask,
    and no instance exists for them
    slot i belongs to the service whose bit is 1 << i, i being its PCIE_PORT_SERVICE_*_SHIFT value
```

The array is thus a sparse map from service index to Linux IRQ, and the next subsection reads the function that fills it.

### One function settles the interrupt mode of the whole port

An interrupt mode belongs to the port function, and portdrv chooses it once for all the services of the port. [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177) makes that choice in a fixed order, the PME switch first, then the vector attempt, then the pin interrupt. Read the whole function for that order and for the value every slot starts from.

```c
/* drivers/pci/pcie/portdrv.c:169 */
/**
 * pcie_init_service_irqs - initialize irqs for PCI Express port services
 * @dev: PCI Express port to handle
 * @irqs: Array of irqs to populate
 * @mask: Bitmask of port capabilities returned by get_port_device_capability()
 *
 * Return value: Interrupt mode associated with the port
 */
static int pcie_init_service_irqs(struct pci_dev *dev, int *irqs, int mask)
{
	int ret, i;

	for (i = 0; i < PCIE_PORT_DEVICE_MAXSERVICES; i++)
		irqs[i] = -1;

	/*
	 * If we support PME but can't use MSI/MSI-X for it, we have to
	 * fall back to INTx or other interrupts, e.g., a system shared
	 * interrupt.
	 */
	if ((mask & PCIE_PORT_SERVICE_PME) && pcie_pme_no_msi())
		goto intx_irq;

	/* Try to use MSI-X or MSI if supported */
	if (pcie_port_enable_irq_vec(dev, irqs, mask) == 0)
		return 0;

intx_irq:
	/* fall back to INTX IRQ */
	ret = pci_alloc_irq_vectors(dev, 1, 1, PCI_IRQ_INTX);
	if (ret < 0)
		return -ENODEV;

	for (i = 0; i < PCIE_PORT_DEVICE_MAXSERVICES; i++)
		irqs[i] = pci_irq_vector(dev, 0);

	return 0;
}
```

Every slot of the parameter `irqs`, the caller's array, starts at -1. With the PME service in the parameter `mask` and [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) true, the function jumps to `intx_irq` without trying vectors. Otherwise [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) tries MSI-X and then MSI, and a nonzero return from it also reaches `intx_irq`, where one pin-interrupt vector is requested and its IRQ copied into all five slots. A refused pin request makes the function return -ENODEV, the one failure its caller sees.

The tests of this function and of the vector attempt it calls form one chain, and each failure leads to the pin interrupt. The flowchart draws that chain with the effect of each outcome on the slots.

```text
    How one port settles on MSI-X, MSI, its pin interrupt or no interrupt
    ─────────────────────────────────────────────────────────────────────

    ┌──────────────────────────────────────┐
    │ every slot of irqs[] set to -1       │
    └───────────────────┬──────────────────┘
                        │
    ┌───────────────────▼──────────────────┐ yes
    │ PME service with PME MSI disabled?   ├──────────────────────────────┐
    └───────────────────┬──────────────────┘                              │
                        │ no                                              │
    ┌───────────────────▼──────────────────┐ no                           │
    │ first MSI-X or MSI request granted?  ├──────────────────────────────┤
    └───────────────────┬──────────────────┘                              │
                        │ yes                                             │
    ┌───────────────────▼──────────────────┐ no                           │
    │ largest number + 1 within the grant? ├──────────────────────────────┤
    └───────────────────┬──────────────────┘                              │
                        │ yes                                             │
    ┌───────────────────▼──────────────────┐ no                           │
    │ exact count granted, where fewer?    ├──────────────────────────────┤
    └───────────────────┬──────────────────┘                              │
                        │ yes                                             ▼
    ┌───────────────────▼──────────────────┐          ┌──────────────────────────────────────────────────┐
    │ slots of the services in the mask    │          │ pci_dev.irq holds a pin IRQ, nonzero?            │
    │ get the IRQ of their vector          │          └───────┬───────────────────────────────┬──────────┘
    └──────────────────────────────────────┘                  │ yes                           │ no
                                                              ▼                               ▼
                                                        ┌──────────────────────────┐    ┌──────────────────────────┐
                                                        │ every slot = the pin IRQ │    │ -ENODEV, slots stay -1   │
                                                        └──────────────────────────┘    └──────────────────────────┘
```

The rest of the page follows the flowchart from the top, starting with the PME switch that can send a port to the pin interrupt before any vector is tried.

### A boot switch or a DMI match keeps PME off MSI

The PME service can force its port onto the pin interrupt. According to the comment in pme.c, "using MSI for PCIe PME signaling doesn't play well with PCIe PME-based wake-up from system sleep states", and the kernel keeps one global switch for the machines and users that need the pin interrupt.

The switch is [`pcie_pme_msi_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31), defined in [`pme.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c) beside [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33), the handler of the `pcie_pme=` boot parameter. Read the variable for its starting value and the handler for the value that sets it.

```c
/* drivers/pci/pcie/pme.c:25 */
/*
 * If this switch is set, MSI will not be used for PCIe PME signaling.  This
 * causes the PCIe port driver to use INTx interrupts only, but it turns out
 * that using MSI for PCIe PME signaling doesn't play well with PCIe PME-based
 * wake-up from system sleep states.
 */
bool pcie_pme_msi_disabled;

static int __init pcie_pme_setup(char *str)
{
	if (!strncmp(str, "nomsi", 5))
		pcie_pme_msi_disabled = true;

	return 1;
}
__setup("pcie_pme=", pcie_pme_setup);
```

The switch starts false as a global without an initializer, and [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33) sets it when the parameter's value begins with `nomsi`, comparing five characters. The switch came with commit [c39fae1416d5](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=c39fae1416d59fd565606793f090cebe3720d50d) ("PCI PM: Make it possible to force using INTx for PCIe PME signaling"). Its message reports a machine whose Root Port stopped generating PME interrupts after a resume while it used MSI, and worked with INTx.

Portdrv reads and sets the switch through two inlines of [`portdrv.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h), [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) and [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108), which exist in their working form only with [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117). Read the block for both branches of the option.

```c
/* drivers/pci/pcie/portdrv.h:105 */
#ifdef CONFIG_PCIE_PME
extern bool pcie_pme_msi_disabled;

static inline void pcie_pme_disable_msi(void)
{
	pcie_pme_msi_disabled = true;
}

static inline bool pcie_pme_no_msi(void)
{
	return pcie_pme_msi_disabled;
}

void pcie_pme_interrupt_enable(struct pci_dev *dev, bool enable);
#else /* !CONFIG_PCIE_PME */
static inline void pcie_pme_disable_msi(void) {}
static inline bool pcie_pme_no_msi(void) { return false; }
static inline void pcie_pme_interrupt_enable(struct pci_dev *dev, bool en) {}
#endif /* !CONFIG_PCIE_PME */
```

With [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) set, [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) returns the switch and [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108) sets it to true, while the prototype of [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) declares the PME service's enable helper. Without the option the stubs after the `#else` take their place, the test returning false and the setter doing nothing, so the pin interrupt is never forced for PME. [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) has no prompt of its own and follows two other options, as its Kconfig entry shows:

```c
/* drivers/pci/pcie/Kconfig:117 */
config PCIE_PME
	def_bool y
	depends on PCIEPORTBUS && PM
```

The PME service is therefore built whenever [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) and [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) are both set, and the x86-64 defconfig sets [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) through [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140).

The second writer is the DMI quirk, the seam at which portdrv matches the machine against its firmware's identification strings. [`dmi_pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L806) is the callback of the single entry of [`pcie_portdrv_dmi_table`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L814); read both for the call that sets the switch and the notice it prints.

```c
/* drivers/pci/pcie/portdrv.c:806 */
static int __init dmi_pcie_pme_disable_msi(const struct dmi_system_id *d)
{
	pr_notice("%s detected: will not use MSI for PCIe PME signaling\n",
		  d->ident);
	pcie_pme_disable_msi();
	return 0;
}

static const struct dmi_system_id pcie_portdrv_dmi_table[] __initconst = {
	/*
	 * Boxes that should not use MSI for PCIe PME signaling.
	 */
	{
	 .callback = dmi_pcie_pme_disable_msi,
	 .ident = "MSI Wind U-100",
	 .matches = {
		     DMI_MATCH(DMI_SYS_VENDOR,
				"MICRO-STAR INTERNATIONAL CO., LTD"),
		     DMI_MATCH(DMI_PRODUCT_NAME, "U-100"),
		     },
	 },
	 {}
};
```

A matching entry runs the callback, which logs a notice naming the entry's `ident` and calls [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108). The callback and the table are marked `__init` and `__initconst`, so the match runs once during boot and its code is discarded afterwards.

[`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) runs the match, and its order settles the switch before any port is probed. Read it for the place of `dmi_check_system()` between the service registrations and the driver registration.

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

The DMI check runs before [`pci_register_driver()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1683) registers the port driver, so the probe of every port, which that registration starts, reads a switch that no longer changes. With [`CONFIG_DMI`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/Kconfig#L944), which x86 sets by default, the check compares the firmware's DMI strings with each table entry.

The switch thus has two writers, both before the first port probe, and one reader per port that runs the PME service. The strip shows its value in each of the three cases.

```text
    pcie_pme_msi_disabled from the command line to the probe of each port
    ─────────────────────────────────────────────────────────────────────

    time ─────────────────────────────────────────────────────────────────────────────────────────────▶
    event                   command line         initcall, DMI check     each port probed
                            ▼                    ▼                       ▼
                          ┌────────────────────┬───────────────────────┬──────────────────────────────┐
    neither               │ false              │ false                 │ false: MSI-X or MSI tried    │
                          └────────────────────┴───────────────────────┴──────────────────────────────┘
                          ┌────────────────────┬──────────────────────────────────────────────────────┐
    pcie_pme=nomsi        │① true              │ true: INTx for a port with PME                       │
                          └────────────────────┴──────────────────────────────────────────────────────┘
                          ┌────────────────────┬───────────────────────┬──────────────────────────────┐
    a DMI entry matches   │ false              │② true                 │ true: INTx, as above         │
                          └────────────────────┴───────────────────────┴──────────────────────────────┘

    ① pcie_pme_setup        pme.c:36       sets the switch when the parameter value is nomsi
    ② pcie_pme_disable_msi  portdrv.h:110  sets the switch from the DMI match callback
```

① [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33) sets [`pcie_pme_msi_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31) to true when the command line carries `pcie_pme=nomsi`. ② [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108) sets it to true when [`dmi_pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L806) runs for a matching DMI entry.

Once true, the switch sends every port that runs the PME service to the pin interrupt for all its services. A port without the PME service still tries vectors. The next subsection follows such a vector attempt, which begins by reading the message numbers.

### Three capability registers name the vectors the services signal

Before the port asks for vectors it must know how many it needs, and that depends on numbers the hardware chooses. The PCI Express Capability, the AER Capability and the DPC Capability of a port each hold an Interrupt Message Number. The number is the MSI-X table entry, or the offset from the first MSI vector, that the interrupts of that capability use. [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads the numbers for the services in the mask and returns the count of vectors the largest one requires.

The function is read in three pieces, one per register, each beside the definition of the field it reads.

| piece | lines | stage |
|---|---|---|
| ❶ | portdrv.c:57-75 | reads the PCI Express Capabilities number for PME, hotplug and bandwidth control |
| ❷ | portdrv.c:76-89 | reads the AER number when the port has an AER Capability |
| ❸ | portdrv.c:90-102 | reads the DPC number and returns the count |

The first number is a five-bit field of the PCI Express Capabilities register, which [`PCI_EXP_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L483) locates in the capability and [`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496) masks. Read the register's definitions for the mask beside the register's other fields.

```c
/* include/uapi/linux/pci_regs.h:481 */
/* PCI Express capability registers */

#define PCI_EXP_FLAGS		0x02	/* Capabilities register */
#define  PCI_EXP_FLAGS_VERS	0x000f	/* Capability version */
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
#define  PCI_EXP_FLAGS_SLOT	0x0100	/* Slot implemented */
#define  PCI_EXP_FLAGS_IRQ	0x3e00	/* Interrupt message number */
#define  PCI_EXP_FLAGS_FLIT	0x8000	/* Flit Mode Supported */
```

[`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496) covers bits 13 to 9, so the number lies between 0 and 31, and the same register holds the Device/Port Type and the Slot Implemented bit.

❶ The first piece of [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads that field when the mask holds any of the three services that signal through the PCI Express Capability. Read it for the count it starts from.

```c
/* drivers/pci/pcie/portdrv.c:52 */
/*
 * Fill in *pme, *aer, *dpc with the relevant Interrupt Message Numbers if
 * services are enabled in "mask".  Return the number of MSI/MSI-X vectors
 * required to accommodate the largest Message Number.
 */
static int pcie_message_numbers(struct pci_dev *dev, int mask,
				u32 *pme, u32 *aer, u32 *dpc)
{
	u32 nvec = 0, pos;
	u16 reg16;

	/*
	 * The Interrupt Message Number indicates which vector is used, i.e.,
	 * the MSI-X table entry or the MSI offset between the base Message
	 * Data and the generated interrupt message.  See PCIe r3.1, sec
	 * 7.8.2, 7.10.10, 7.31.2.
	 */

	if (mask & (PCIE_PORT_SERVICE_PME | PCIE_PORT_SERVICE_HP |
		    PCIE_PORT_SERVICE_BWCTRL)) {
		pcie_capability_read_word(dev, PCI_EXP_FLAGS, &reg16);
		*pme = FIELD_GET(PCI_EXP_FLAGS_IRQ, reg16);
		nvec = *pme + 1;
	}
```

A mask with PME, hotplug or bandwidth control sets the output `*pme` to the field. The local `nvec` becomes that number plus one, the count of vectors that reaches it. The comment above the read gives the number's meaning, the MSI-X table entry, or the offset between the base Message Data and the generated message.

The AER number occupies the top five bits of the Root Error Status register, [`PCI_ERR_ROOT_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L826) of the AER Capability, and [`PCI_ERR_ROOT_AER_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L834) masks it. Read the register's definitions for the field.

```c
/* include/uapi/linux/pci_regs.h:826 */
#define PCI_ERR_ROOT_STATUS	0x30
#define  PCI_ERR_ROOT_COR_RCV		0x00000001 /* ERR_COR Received */
#define  PCI_ERR_ROOT_MULTI_COR_RCV	0x00000002 /* Multiple ERR_COR */
#define  PCI_ERR_ROOT_UNCOR_RCV		0x00000004 /* ERR_FATAL/NONFATAL */
#define  PCI_ERR_ROOT_MULTI_UNCOR_RCV	0x00000008 /* Multiple FATAL/NONFATAL */
#define  PCI_ERR_ROOT_FIRST_FATAL	0x00000010 /* First UNC is Fatal */
#define  PCI_ERR_ROOT_NONFATAL_RCV	0x00000020 /* Non-Fatal Received */
#define  PCI_ERR_ROOT_FATAL_RCV		0x00000040 /* Fatal Received */
#define  PCI_ERR_ROOT_AER_IRQ		0xf8000000 /* Advanced Error Interrupt Message Number */
```

Bits 31 to 27 hold the number, above the bits that record which error messages the Root Port received.

❷ The second piece of [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads that number and is compiled only with [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28). Read it for the guard on the capability's offset.

```c
/* drivers/pci/pcie/portdrv.c:76 */

#ifdef CONFIG_PCIEAER
	if (mask & PCIE_PORT_SERVICE_AER) {
		u32 reg32;

		pos = dev->aer_cap;
		if (pos) {
			pci_read_config_dword(dev, pos + PCI_ERR_ROOT_STATUS,
					      &reg32);
			*aer = FIELD_GET(PCI_ERR_ROOT_AER_IRQ, reg32);
			nvec = max(nvec, *aer + 1);
		}
	}
#endif
```

The offset is the one the PCI core cached in [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), and a zero offset skips the read. A larger AER number raises `nvec` through `max()`, and a kernel built without [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) reads no AER number at all.

The DPC number is the low five bits of the DPC Capability register, [`PCI_EXP_DPC_CAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1082), and [`PCI_EXP_DPC_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L1083) masks it. Read the definitions for the field.

```c
/* include/uapi/linux/pci_regs.h:1081 */
/* Downstream Port Containment */
#define PCI_EXP_DPC_CAP			0x04	/* DPC Capability */
#define PCI_EXP_DPC_IRQ			0x001F	/* Interrupt Message Number */
#define  PCI_EXP_DPC_CAP_RP_EXT		0x0020	/* Root Port Extensions */
#define  PCI_EXP_DPC_CAP_POISONED_TLP	0x0040	/* Poisoned TLP Egress Blocking Supported */
#define  PCI_EXP_DPC_CAP_SW_TRIGGER	0x0080	/* Software Triggering Supported */
#define  PCI_EXP_DPC_RP_PIO_LOG_SIZE	0x0F00	/* RP PIO Log Size [3:0] */
#define  PCI_EXP_DPC_CAP_DL_ACTIVE	0x1000	/* ERR_COR signal on DL_Active supported */
#define  PCI_EXP_DPC_RP_PIO_LOG_SIZE4	0x2000	/* RP PIO Log Size [4] */
```

Bits 4 to 0 hold the number, below the bits that announce the optional DPC features.

❸ The last piece of [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) looks the DPC Extended Capability up and reads its number. Read it for the count the function returns.

```c
/* drivers/pci/pcie/portdrv.c:90 */

	if (mask & PCIE_PORT_SERVICE_DPC) {
		pos = pci_find_ext_capability(dev, PCI_EXT_CAP_ID_DPC);
		if (pos) {
			pci_read_config_word(dev, pos + PCI_EXP_DPC_CAP,
					     &reg16);
			*dpc = FIELD_GET(PCI_EXP_DPC_IRQ, reg16);
			nvec = max(nvec, *dpc + 1);
		}
	}

	return nvec;
}
```

The DPC read has no configuration guard and runs whenever the mask holds [`PCIE_PORT_SERVICE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L22) and the capability exists. The function returns `nvec`, one more than the largest number it read, which is the count of vectors that reaches the entry of every service.

The numbers and the counts derived from them are positions on one axis that the five-bit fields bound. The figure places them for an example port.

```text
    An example port's message numbers and vector counts on one axis, from 0 to 32
    ─────────────────────────────────────────────────────────────────────────────

    0   1   2   3                         31  32
    ├───┬───┬───┬────── · · · ────────────┬───┬───▶
    │   │   │   │                         │   └─ PCIE_PORT_MAX_MSI_ENTRIES, the most the first request asks for
    │   │   │   │                         └─ 31, the largest value a five-bit number field holds
    │   │   │   └─ nvec = 3, the largest number plus one, the count the port keeps
    │   │   └─ d = 2, read from the DPC Capability register
    │   └─ a = 1, read from the Root Error Status register
    └─ m = 0, read from the PCI Express Capabilities register

    the first request grants nr_entries vectors, at most 32: nvec above nr_entries sends the port to INTx,
    nvec below it makes the port free its vectors and ask again for exactly nvec
```

The count is the smallest set of vectors the port can work with, and the next subsection compares it with what the port obtains.

### The port asks for up to 32 vectors, then exactly enough

The port reads its message numbers only after it holds vectors, and it turns numbers into Linux IRQs only after its final request. That order comes from commit commit [a579ba49a9e2](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a579ba49a9e27bfc1d5cb69b0ea3781d8df46b5b) ("PCI/portdrv: Compute MSI/MSI-X IRQ vectors after final allocation"), whose message notes that freeing the vectors invalidates their IRQs. [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) therefore asks for as many vectors as any number could need, reads the numbers, and asks again for exactly the count.

The function is read in three pieces, the last of them in the next subsection.

| piece | lines | stage |
|---|---|---|
| Ⓐ | portdrv.c:113-129 | asks for up to 32 vectors and tests the count against the grant |
| Ⓑ | portdrv.c:130-149 | frees the vectors and asks again for exactly the count |
| Ⓒ | portdrv.c:150-167 | gives each service slot the IRQ of its number |

[`PCIE_PORT_MAX_MSI_ENTRIES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L30) is the ceiling of the first request, and its comment derives the value from the specifications. Read it for the two limits it reconciles.

```c
/* drivers/pci/pcie/portdrv.c:25 */
/*
 * The PCIe Capability Interrupt Message Number (PCIe r3.1, sec 7.8.2) must
 * be one of the first 32 MSI-X entries.  Per PCI r3.0, sec 6.8.3.1, MSI
 * supports a maximum of 32 vectors per function.
 */
#define PCIE_PORT_MAX_MSI_ENTRIES	32
```

The PCI Express Capabilities number must fall within the first 32 MSI-X entries, and MSI allows at most 32 vectors per function. A request for 32 therefore reaches every number a five-bit field can hold.

Both requests go through [`pci_alloc_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L232), the PCI core's allocator, which takes a minimum, a maximum and the modes it may try. Read its kerneldoc for what the count it returns means.

```c
/* drivers/pci/msi/api.c:204 */
/**
 * pci_alloc_irq_vectors() - Allocate multiple device interrupt vectors
 * @dev:      the PCI device to operate on
 * @min_vecs: minimum required number of vectors (must be >= 1)
 * @max_vecs: maximum desired number of vectors
 * @flags:    One or more of:
 *
 *            * %PCI_IRQ_MSIX      Allow trying MSI-X vector allocations
 *            * %PCI_IRQ_MSI       Allow trying MSI vector allocations
 *
 *            * %PCI_IRQ_INTX      Allow trying INTx interrupts, if and
 *              only if @min_vecs == 1
 *
 *            * %PCI_IRQ_AFFINITY  Auto-manage IRQs affinity by spreading
 *              the vectors around available CPUs
 *
 * Allocate up to @max_vecs interrupt vectors on device. MSI-X irq
 * vector allocation has a higher precedence over plain MSI, which has a
 * higher precedence over legacy INTx emulation.
 *
 * Upon a successful allocation, the caller should use pci_irq_vector()
 * to get the Linux IRQ number to be passed to request_threaded_irq().
 * The driver must call pci_free_irq_vectors() on cleanup.
 *
 * Return: number of allocated vectors (which might be smaller than
 * @max_vecs), -ENOSPC if less than @min_vecs interrupt vectors are
 * available, other errnos otherwise.
 */
int pci_alloc_irq_vectors(struct pci_dev *dev, unsigned int min_vecs,
			  unsigned int max_vecs, unsigned int flags)
{
	return pci_alloc_irq_vectors_affinity(dev, min_vecs, max_vecs,
					      flags, NULL);
}
```

The allocator may return fewer vectors than the maximum, and it fails with -ENOSPC when fewer than the minimum are available. It passes no affinity description to [`pci_alloc_irq_vectors_affinity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L252), which tries the modes in a fixed order; read its stage for that order.

```c
/* drivers/pci/msi/api.c:252 */
int pci_alloc_irq_vectors_affinity(struct pci_dev *dev, unsigned int min_vecs,
				   unsigned int max_vecs, unsigned int flags,
				   struct irq_affinity *affd)
{
	struct irq_affinity msi_default_affd = {0};
	int nvecs = -ENOSPC;

	... /* 8 lines, to :267 */
	if (flags & PCI_IRQ_MSIX) {
		nvecs = __pci_enable_msix_range(dev, NULL, min_vecs, max_vecs,
						affd, flags);
		if (nvecs > 0)
			return nvecs;
	}

	if (flags & PCI_IRQ_MSI) {
		nvecs = __pci_enable_msi_range(dev, min_vecs, max_vecs, affd);
		if (nvecs > 0)
			return nvecs;
	}

	/* use INTx IRQ if allowed */
	if (flags & PCI_IRQ_INTX) {
		if (min_vecs == 1 && dev->irq) {
			/*
			 * Invoke the affinity spreading logic to ensure that
			 * the device driver can adjust queue configuration
			 * for the single interrupt case.
			 */
			if (affd)
				irq_create_affinity_masks(1, affd);
			pci_intx(dev, 1);
			return 1;
		}
	}

	return nvecs;
}
```

MSI-X comes first and returns at once with a positive count, and MSI comes next. The pin interrupt follows only when [`PCI_IRQ_INTX`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1166) is among the flags, the minimum is 1 and the port's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454) is nonzero, and the port's vector requests never pass that flag.

Both functions are built with [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44). Without it, include/linux/pci.h supplies an inline in their place; read it for its single branch.

```c
/* include/linux/pci.h:1802 */
static inline int
pci_alloc_irq_vectors_affinity(struct pci_dev *dev, unsigned int min_vecs,
			       unsigned int max_vecs, unsigned int flags,
			       struct irq_affinity *aff_desc)
{
	if ((flags & PCI_IRQ_INTX) && min_vecs == 1 && dev->irq)
		return 1;
	return -ENOSPC;
}
static inline int
pci_alloc_irq_vectors(struct pci_dev *dev, unsigned int min_vecs,
		      unsigned int max_vecs, unsigned int flags)
{
	return pci_alloc_irq_vectors_affinity(dev, min_vecs, max_vecs,
					      flags, NULL);
}
```

Without [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) each vector request of the port returns -ENOSPC, since it never passes [`PCI_IRQ_INTX`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1166), and every port with services ends on the pin interrupt.

Ⓐ The first piece of [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) asks for 1 to 32 vectors in MSI-X or MSI mode and then reads the numbers. Read it for the test that ends the attempt.

```c
/* drivers/pci/pcie/portdrv.c:104 */
/**
 * pcie_port_enable_irq_vec - try to set up MSI-X or MSI as interrupt mode
 * for given port
 * @dev: PCI Express port to handle
 * @irqs: Array of interrupt vectors to populate
 * @mask: Bitmask of port capabilities returned by get_port_device_capability()
 *
 * Return value: 0 on success, error code on failure
 */
static int pcie_port_enable_irq_vec(struct pci_dev *dev, int *irqs, int mask)
{
	int nr_entries, nvec, pcie_irq;
	u32 pme = 0, aer = 0, dpc = 0;

	/* Allocate the maximum possible number of MSI/MSI-X vectors */
	nr_entries = pci_alloc_irq_vectors(dev, 1, PCIE_PORT_MAX_MSI_ENTRIES,
			PCI_IRQ_MSIX | PCI_IRQ_MSI);
	if (nr_entries < 0)
		return nr_entries;

	/* See how many and which Interrupt Message Numbers we actually use */
	nvec = pcie_message_numbers(dev, mask, &pme, &aer, &dpc);
	if (nvec > nr_entries) {
		pci_free_irq_vectors(dev);
		return -EIO;
	}
```

The local `nr_entries` holds the grant, and [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) fills the locals `pme`, `aer` and `dpc` and returns the count the largest number needs. A count above the grant means a number names a vector the port does not hold. The function then frees what it got and returns -EIO, which sends the port to the pin interrupt.

[`pci_free_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L379) releases the vectors of either mode. Read it for the two disables it performs.

```c
/* drivers/pci/msi/api.c:366 */
/**
 * pci_free_irq_vectors() - Free previously allocated IRQs for a device
 * @dev: the PCI device to operate on
 *
 * Undo the interrupt vector allocations and possible device MSI/MSI-X
 * enablement earlier done through pci_alloc_irq_vectors_affinity() or
 * pci_alloc_irq_vectors().
 *
 * WARNING: Do not call this function if the device has been enabled
 * with pcim_enable_device(). In that case, IRQ vectors are automatically
 * managed via pcim_msi_release() and calling pci_free_irq_vectors() can
 * lead to double-free issues.
 */
void pci_free_irq_vectors(struct pci_dev *dev)
{
	pci_disable_msix(dev);
	pci_disable_msi(dev);
}
```

The free disables MSI-X and MSI in turn, and its kerneldoc says it undoes "the interrupt vector allocations and possible device MSI/MSI-X enablement".

Ⓑ The second piece of [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) handles a grant larger than the count. Read its comment for why the IRQs wait until after it.

```c
/* drivers/pci/pcie/portdrv.c:130 */

	/*
	 * If we allocated more than we need, free them and reallocate fewer.
	 *
	 * Reallocating may change the specific vectors we get, so
	 * pci_irq_vector() must be done *after* the reallocation.
	 *
	 * If we're using MSI, hardware is *allowed* to change the Interrupt
	 * Message Numbers when we free and reallocate the vectors, but we
	 * assume it won't because we allocate enough vectors for the
	 * biggest Message Number we found.
	 */
	if (nvec != nr_entries) {
		pci_free_irq_vectors(dev);

		nr_entries = pci_alloc_irq_vectors(dev, nvec, nvec,
				PCI_IRQ_MSIX | PCI_IRQ_MSI);
		if (nr_entries < 0)
			return nr_entries;
	}
```

When the count differs from the grant, the function frees every vector and asks for exactly `nvec`, as both the minimum and the maximum. A failure of that request returns its error. The comment records the assumption behind keeping the numbers read under the first grant. With MSI the hardware may change its numbers when the vector count changes, and the code assumes it does not, since the new count still covers the largest number.

The second request reshapes the port's set of vectors. The figure shows the set before and after it for an example port.

```text
    The port's vectors before and after the second request, for an example port with nvec = 3
    ─────────────────────────────────────────────────────────────────────────────────────────

    before: the first request granted nr_entries = 32, and only the message numbers are known
    ┌────┬────┬────┬────┬────┬───────────┬────┐
    │ 0  │ 1  │ 2  │ 3  │ 4  │   · · ·   │ 31 │
    └────┴────┴────┴────┴────┴─────┬─────┴────┘
                                   │ every vector freed, then exactly nvec = 3 requested
                                   ▼
                             ┌────┬────┬────┐
                             │ 0  │ 1  │ 2  │   after: nr_entries = 3, and pci_irq_vector()
                             └────┴────┴────┘   now turns m, a and d into Linux IRQs

    an IRQ looked up before the second request would name a vector that the free released
```

After the second request the port holds exactly `nvec` vectors, and only now does the function turn its numbers into Linux IRQs.

### PME, hotplug and bandwidth control share one vector

The PCI Express Capability raises PME, hotplug and link bandwidth interrupts through the one number its register holds, so the three services can only share a vector. AER and DPC have numbers of their own, and their slots receive separate IRQs whenever those numbers differ from the first.

[`pci_irq_vector()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L311) turns an index into a Linux IRQ. Read it for what the index means in each mode.

```c
/* drivers/pci/msi/api.c:299 */
/**
 * pci_irq_vector() - Get Linux IRQ number of a device interrupt vector
 * @dev: the PCI device to operate on
 * @nr:  device-relative interrupt vector index (0-based); has different
 *       meanings, depending on interrupt mode:
 *
 *         * MSI-X     the index in the MSI-X vector table
 *         * MSI       the index of the enabled MSI vectors
 *         * INTx      must be 0
 *
 * Return: the Linux IRQ number, or -EINVAL if @nr is out of range
 */
int pci_irq_vector(struct pci_dev *dev, unsigned int nr)
{
	unsigned int irq;

	if (!dev->msi_enabled && !dev->msix_enabled)
		return !nr ? dev->irq : -EINVAL;

	irq = msi_get_virq(&dev->dev, nr);
	return irq ? irq : -EINVAL;
}
EXPORT_SYMBOL(pci_irq_vector);
```

With MSI-X or MSI enabled, the index selects the MSI-X table entry or the MSI vector, and `msi_get_virq()` returns the Linux IRQ allocated for it. An index past the allocation gives -EINVAL. With neither enabled, index 0 returns the port's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454).

Ⓒ The last piece of [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) fills the slots. Read it for the slots that share one lookup.

```c
/* drivers/pci/pcie/portdrv.c:150 */

	/* PME, hotplug and bandwidth notification share an MSI/MSI-X vector */
	if (mask & (PCIE_PORT_SERVICE_PME | PCIE_PORT_SERVICE_HP |
		    PCIE_PORT_SERVICE_BWCTRL)) {
		pcie_irq = pci_irq_vector(dev, pme);
		irqs[PCIE_PORT_SERVICE_PME_SHIFT] = pcie_irq;
		irqs[PCIE_PORT_SERVICE_HP_SHIFT] = pcie_irq;
		irqs[PCIE_PORT_SERVICE_BWCTRL_SHIFT] = pcie_irq;
	}

	if (mask & PCIE_PORT_SERVICE_AER)
		irqs[PCIE_PORT_SERVICE_AER_SHIFT] = pci_irq_vector(dev, aer);

	if (mask & PCIE_PORT_SERVICE_DPC)
		irqs[PCIE_PORT_SERVICE_DPC_SHIFT] = pci_irq_vector(dev, dpc);

	return 0;
}
```

The slots of PME, hotplug and bandwidth control receive one value, the IRQ of the number `pme` held in the local `pcie_irq`, whenever the mask holds any of the three. The AER and DPC slots each receive the IRQ of their own number when their service is in the mask, and the other slots keep -1.

Whether AER and DPC end on vectors of their own depends on the hardware's numbers alone. The figure compares a port with three distinct numbers and a port whose three numbers are all 0.

```text
    The five slots under two sets of message numbers, with IRQ x, y and z for vectors 0, 1 and 2
    ────────────────────────────────────────────────────────────────────────────────────────────

    m = 0, a = 1, d = 2: nvec = 3                       m = a = d = 0: nvec = 1
    ┌──────────────┐                                    ┌──────────────┐
    │ vector 0  x  ├──┬─▶ [0] PME      x                │ vector 0  x  ├──┬─▶ [0] PME      x
    └──────────────┘  ├─▶ [2] HP       x                └──────────────┘  ├─▶ [1] AER      x
                      └─▶ [4] BWCTRL   x                                  ├─▶ [2] HP       x
    ┌──────────────┐                                                      ├─▶ [3] DPC      x
    │ vector 1  y  ├─────▶ [1] AER      y                                 └─▶ [4] BWCTRL   x
    └──────────────┘
    ┌──────────────┐
    │ vector 2  z  ├─────▶ [3] DPC      z
    └──────────────┘

    PME, HP and BWCTRL always take the vector of m; AER and DPC take their own vectors only when a and d differ from m
```

So far, the port has either settled on MSI-X or MSI with exactly `nvec` vectors, or it has failed a test on the way and turns to the pin interrupt. In the first case each present service's slot holds the IRQ of its number.

### The INTx fallback gives every service the pin interrupt

A port that cannot use vectors still signals through its Interrupt Pin, and its services then share the one IRQ that pin is routed to. The fallback lines of [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177) request that IRQ and copy it into every slot; read them again for the request and the copy.

```c
/* drivers/pci/pcie/portdrv.c:177 */
static int pcie_init_service_irqs(struct pci_dev *dev, int *irqs, int mask)
{
	int ret, i;
... /* 16 lines, to :196 */
intx_irq:
	/* fall back to INTX IRQ */
	ret = pci_alloc_irq_vectors(dev, 1, 1, PCI_IRQ_INTX);
	if (ret < 0)
		return -ENODEV;

	for (i = 0; i < PCIE_PORT_DEVICE_MAXSERVICES; i++)
		irqs[i] = pci_irq_vector(dev, 0);

	return 0;
}
```

The request asks for exactly one vector in pin mode, and [`pci_irq_vector()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L311) with index 0 returns the pin IRQ, which every slot receives, present services and holes alike. A refused request returns -ENODEV, and the slots keep -1.

The pin branch of [`pci_alloc_irq_vectors_affinity()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L252) grants that request. Read its two conditions again.

```c
/* drivers/pci/msi/api.c:252 */
int pci_alloc_irq_vectors_affinity(struct pci_dev *dev, unsigned int min_vecs,
				   unsigned int max_vecs, unsigned int flags,
				   struct irq_affinity *affd)
	... /* 25 lines, to :280 */
	/* use INTx IRQ if allowed */
	if (flags & PCI_IRQ_INTX) {
		if (min_vecs == 1 && dev->irq) {
			/*
			 * Invoke the affinity spreading logic to ensure that
			 * the device driver can adjust queue configuration
			 * for the single interrupt case.
			 */
			if (affd)
				irq_create_affinity_masks(1, affd);
			pci_intx(dev, 1);
			return 1;
		}
	}
```

The minimum of 1 holds for this request, so the port's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454) decides the outcome. A nonzero value enables the pin with [`pci_intx()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4321) and grants one vector, and a zero value fails the request.

The pin IRQ is assigned when the port is enabled. On x86, [`pcibios_enable_device()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/pci/common.c#L691) is the architecture's part of the [`pci_enable_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2120) call that opens the port's probe. It routes the pin unless MSI or MSI-X is enabled; read it for that test.

```c
/* arch/x86/pci/common.c:691 */
int pcibios_enable_device(struct pci_dev *dev, int mask)
{
	int err;

	if ((err = pci_enable_resources(dev, mask)) < 0)
		return err;

	if (!pci_dev_msi_enabled(dev))
		return pcibios_enable_irq(dev);
	return 0;
}
```

With neither mode enabled, the hook calls through the function pointer [`pcibios_enable_irq`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/pci/irq.c#L65), which [`pci_acpi_init()`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/pci/acpi.c#L606) points at the ACPI router when [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) is set. Read the stage that installs it.

```c
/* arch/x86/pci/acpi.c:606 */
int __init pci_acpi_init(void)
{
	struct pci_dev *dev = NULL;

	if (acpi_noirq)
		return -ENODEV;

	pr_info("Using ACPI for IRQ routing\n");
	acpi_irq_penalty_init();
	pcibios_enable_irq = acpi_pci_irq_enable;
	pcibios_disable_irq = acpi_pci_irq_disable;
```

Unless ACPI interrupt routing is turned off through `acpi_noirq`, the pointer becomes [`acpi_pci_irq_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_irq.c#L384), which looks the pin up in the firmware's `_PRT` routing table, a name the specification defines. Read the stage that registers the routed GSI and stores the result.

```c
/* drivers/acpi/pci_irq.c:384 */
int acpi_pci_irq_enable(struct pci_dev *dev)
{
	struct acpi_prt_entry *entry;
	u32 gsi;
	u8 pin;
	... /* 68 lines, to :457 */
	rc = acpi_register_gsi(&dev->dev, gsi, triggering, polarity);
	if (rc < 0) {
		dev_warn(&dev->dev, "PCI INT %c: failed to register GSI\n",
			 pin_name(pin));
		kfree(entry);
		return rc;
	}
	dev->irq = rc;
	dev->irq_managed = 1;

	if (link)
		snprintf(link_desc, sizeof(link_desc), " -> Link[%s]", link);
	else
		link_desc[0] = '\0';

	dev_dbg(&dev->dev, "PCI INT %c%s -> GSI %u (%s, %s) -> IRQ %d\n",
		pin_name(pin), link_desc, gsi,
		(triggering == ACPI_LEVEL_SENSITIVE) ? "level" : "edge",
		str_low_high(polarity == ACPI_ACTIVE_LOW), dev->irq);
```

The Linux IRQ that `acpi_register_gsi()` returns for the GSI becomes the port's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454). The `dev_dbg()` line after it prints the pin, the GSI and the IRQ, and with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) a reader enables it through the dynamic-debug control file.

MSI mode borrows [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454) while it is enabled, so a port that freed MSI vectors before it fell back must find the pin IRQ there again. The kerneldoc of [`pci_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L51), which the free calls, states that the field is restored; read it.

```c
/* drivers/pci/msi/api.c:40 */
 * pci_disable_msi() - Disable MSI interrupt mode on device
 * @dev: the PCI device to operate on
 *
 * Legacy device driver API to disable MSI interrupt mode on device,
 * free earlier allocated interrupt vectors, and restore INTx emulation.
 * The PCI device Linux IRQ (@dev->irq) is restored to its default
 * pin-assertion IRQ. This is the cleanup pair of pci_enable_msi().
 *
 * NOTE: The newer pci_alloc_irq_vectors() / pci_free_irq_vectors() API
 * pair should, in general, be used instead.
 */
void pci_disable_msi(struct pci_dev *dev)
{
	if (!pci_msi_enabled() || !dev || !dev->msi_enabled)
		return;

	guard(msi_descs_lock)(&dev->dev);
	pci_msi_shutdown(dev);
	pci_free_msi_irqs(dev);
}
```

The free that preceded a fallback thus leaves the pin IRQ in the port's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454), and [`pci_irq_vector()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L311) returns it for index 0. The figure draws the fallback's data path from the pin through the firmware's routing to that IRQ and into all five slots.

```text
    The pin IRQ that ACPI routing gives the port fills every slot on the INTx fallback
    ──────────────────────────────────────────────────────────────────────────────────

    ┌──────────────────┐   _PRT entry or   ┌──────────┐ acpi_register_gsi ┌──────────────────┐
    │ Interrupt Pin,   ├──────────────────▶│ GSI      ├──────────────────▶│ pci_dev.irq,     │
    │ pci_dev.pin      │   its link device └──────────┘                   │ the pin IRQ      │
    └──────────────────┘                                                  └────────┬─────────┘
                                                                                   │ pci_irq_vector(dev, 0), INTx mode
                                                                                   ▼
                         ┌────────────┬────────────┬────────────┬────────────┬────────────┐
                         │ [0] PME    │ [1] AER    │ [2] HP     │ [3] DPC    │ [4] BWCTRL │
                         │ pin IRQ    │ pin IRQ    │ pin IRQ    │ pin IRQ    │ pin IRQ    │
                         └────────────┴────────────┴────────────┴────────────┴────────────┘
```

Every service of such a port receives the same IRQ, and each of their handlers must test its own status bits on every interrupt of the line.

### The service instance carries its slot in irq

The slots are locals of the probe, and they reach the services only by being copied into the service instances. [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) is portdrv's service instance, one per service a port runs, and its [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) member is the field every service driver reads for its interrupt. Read the definition for the members beside it.

```c
/* drivers/pci/pcie/portdrv.h:59 */
struct pcie_device {
	int		irq;	    /* Service IRQ/MSI/MSI-X Vector */
	struct pci_dev *port;	    /* Root/Upstream/Downstream Port */
	u32		service;    /* Port service this device represents */
	void		*priv_data; /* Service Private Data */
	struct device	device;     /* Generic Device Interface */
};
#define to_pcie_device(d) container_of(d, struct pcie_device, device)
```

[`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) holds the Linux IRQ, of a vector or of the pin, that the service requests. [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) points at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) holds the service's bit, and [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) carries the service driver's own data. [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the embedded [`struct device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L703) that the driver model binds, and [`to_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) converts it back to the instance.

The probe creates the instances in a loop over the slots after the interrupt setup. Read the stage of [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) that pairs each present service with its slot.

```c
/* drivers/pci/pcie/portdrv.c:331 */
static int pcie_port_device_register(struct pci_dev *dev)
{
	int status, capabilities, i, nr_service;
	int irqs[PCIE_PORT_DEVICE_MAXSERVICES];
	... /* 26 lines, to :361 */
	/* Allocate child services if any */
	status = -ENODEV;
	nr_service = 0;
	for (i = 0; i < PCIE_PORT_DEVICE_MAXSERVICES; i++) {
		int service = 1 << i;
		if (!(capabilities & service))
			continue;
		if (!pcie_device_init(dev, service, irqs[i]))
			nr_service++;
	}
	if (!nr_service)
		goto error_cleanup_irqs;

	return 0;

error_cleanup_irqs:
	pci_free_irq_vectors(dev);
error_disable:
	pci_disable_device(dev);
	return status;
}
```

For each index `i` whose bit is in the mask, [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) receives the bit and the slot `irqs[i]`, and a port whose every instance fails frees its vectors with [`pci_free_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L379). A port that failed even the pin request reaches the loop with the hotplug bit alone and -1 in its slot.

[`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) allocates the instance and stores the slot in it. Read its first stage.

```c
/* drivers/pci/pcie/portdrv.c:284 */
/**
 * pcie_device_init - allocate and initialize PCI Express port service device
 * @pdev: PCI Express port to associate the service device with
 * @service: Type of service to associate with the service device
 * @irq: Interrupt vector to associate with the service device
 */
static int pcie_device_init(struct pci_dev *pdev, int service, int irq)
{
	int retval;
	struct pcie_device *pcie;
	struct device *device;

	pcie = kzalloc_obj(*pcie);
	if (!pcie)
		return -ENOMEM;
	pcie->port = pdev;
	pcie->irq = irq;
	pcie->service = service;
```

The instance comes zeroed from `kzalloc_obj()`. The assignment from the parameter `irq` of [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) is the one write of [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) in the tree at v7.2, and no service driver changes it afterwards.

Creating the instances moves the IRQs from the probe's array into one field per instance. The figure shows the slots before and the instances after, for the port of the model figure.

```text
    The slots of the probe become the irq of the service instances under the port
    ─────────────────────────────────────────────────────────────────────────────

    before, in the probe's local array            after, the instances the probe created
                                                  ┌──────────────────────────────────┐
    ┌────────────────────────┐                    │ struct pci_dev, the port         │◀───────────┐ port
    │ irqs[0] PME      IRQ x │                    └──────────────────────────────────┘            │
    │ irqs[1] AER      IRQ y │                                                                    │
    │ irqs[2] HP       IRQ x │ one instance per   ┌──────────────────────────────────────────┐    │
    │ irqs[3] DPC      IRQ z │ service bit ──▶    │ struct pcie_device  service PME    irq x ├────┤
    │ irqs[4] BWCTRL   IRQ x │                    └──────────────────────────────────────────┘    │
    └────────────────────────┘                    ┌──────────────────────────────────────────┐    │
                                                  │ struct pcie_device  service AER    irq y ├────┤
                                                  └──────────────────────────────────────────┘    │
                                                  ┌──────────────────────────────────────────┐    │
                                                  │ struct pcie_device  service HP     irq x ├────┤
                                                  └──────────────────────────────────────────┘    │
                                                  ┌──────────────────────────────────────────┐    │
                                                  │ struct pcie_device  service DPC    irq z ├────┤
                                                  └──────────────────────────────────────────┘    │
                                                  ┌──────────────────────────────────────────┐    │
                                                  │ struct pcie_device  service BWCTRL irq x ├────┘
                                                  └──────────────────────────────────────────┘

    each instance points at the port through its port member, and its irq holds the slot of its service bit
```

Each service thus finds both its interrupt and its port in its own instance, and the array goes away when the probe returns.

### Each service driver requests the IRQ its instance carries

Portdrv allocates vectors but installs no handler, and each service driver requests the IRQ of its instance in its own probe. Because that IRQ may serve other services too, every request passes `IRQF_SHARED`, and the table lists the five requests with the name each handler is registered under.

| service | requesting function | handler | flags and name |
|---|---|---|---|
| PME | [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) | [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) | `IRQF_SHARED`, "PCIe PME" |
| hotplug | [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), thread [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) | `IRQF_SHARED`, "pciehp" |
| bandwidth control | [`pcie_bwnotif_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L248) | [`pcie_bwnotif_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L211) | `IRQF_SHARED`, "PCIe bwctrl" |
| AER | [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) | [`aer_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1470), thread [`aer_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1449) | `IRQF_SHARED`, "aerdrv" |
| DPC | [`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) | [`dpc_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L386), thread [`dpc_handler()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L363) | `IRQF_SHARED`, "pcie-dpc" |

[`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) requests the IRQ after it has disabled the port's PME interrupt and cleared its PME status. Read the stage around the request.

```c
/* drivers/pci/pcie/pme.c:326 */
static int pcie_pme_probe(struct pcie_device *srv)
{
	struct pci_dev *port = srv->port;
	struct pcie_pme_service_data *data;
	int type = pci_pcie_type(port);
	int ret;
	... /* 15 lines, to :347 */
	pcie_pme_interrupt_enable(port, false);
	pcie_clear_root_pme_status(port);

	ret = request_irq(srv->irq, pcie_pme_irq, IRQF_SHARED, "PCIe PME", srv);
	if (ret) {
		kfree(data);
		return ret;
	}

	pci_info(port, "Signaling with IRQ %d\n", srv->irq);
```

The PME service passes its instance as the cookie and logs the IRQ at info level. The kernel log thus names the IRQ of the shared vector for every port that runs the PME service.

[`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) reads the same value through the hotplug controller's pointer to its instance. Read it for the polling alternative.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:58 */
static inline int pciehp_request_irq(struct controller *ctrl)
{
	int retval, irq = ctrl->pcie->irq;

	if (pciehp_poll_mode) {
		ctrl->poll_thread = kthread_run(&pciehp_poll, ctrl,
						"pciehp_poll-%s",
						slot_name(ctrl));
		return PTR_ERR_OR_ZERO(ctrl->poll_thread);
	}

	/* Installs the interrupt handler */
	retval = request_threaded_irq(irq, pciehp_isr, pciehp_ist,
				      IRQF_SHARED, "pciehp", ctrl);
	if (retval)
		ctrl_err(ctrl, "Cannot get irq %d for the hotplug controller\n",
			 irq);
	return retval;
}
```

With the module parameter [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) set, hotplug starts a polling thread and requests no IRQ. A port left with -1 in its slot can still serve hotplug that way. Otherwise it requests a threaded handler and reports a failure with the IRQ number.

[`pcie_bwnotif_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L248) requests the same IRQ for link bandwidth events. Read the stage that requests it.

```c
/* drivers/pci/pcie/bwctrl.c:248 */
static int pcie_bwnotif_probe(struct pcie_device *srv)
{
	struct pci_dev *port = srv->port;
	int ret;

	... /* 16 lines, to :269 */
	scoped_guard(rwsem_write, &pcie_bwctrl_setspeed_rwsem) {
		port->link_bwctrl = data;

		ret = request_irq(srv->irq, pcie_bwnotif_irq,
				  IRQF_SHARED, "PCIe bwctrl", srv);
		if (ret) {
			port->link_bwctrl = NULL;
			return ret;
		}

		pcie_bwnotif_enable(srv);
	}

	pci_dbg(port, "enabled with IRQ %d\n", srv->irq);
```

The bandwidth service logs its IRQ through [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896), a dynamic-debug line under [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120), so the line appears only when a reader enables it.

[`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) requests the IRQ of the AER slot with a threaded handler. Read the stage that requests it.

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

	cxl_rch_enable_rcec(port);
	aer_enable_rootport(rpc);
	pci_info(port, "enabled with IRQ %d\n", dev->irq);
```

The AER service ties the request to its instance's lifetime through `devm_request_threaded_irq()` and logs the IRQ at info level, or an error with the IRQ when the request fails.

[`dpc_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L473) does the same for the DPC slot and also prints the DPC number it reads from the capability. Read the stage.

```c
/* drivers/pci/pcie/dpc.c:473 */
static int dpc_probe(struct pcie_device *dev)
{
	struct pci_dev *pdev = dev->port;
	struct device *device = &dev->device;
	int status;
	u16 cap;
	... /* 4 lines, to :483 */
	status = devm_request_threaded_irq(device, dev->irq, dpc_irq,
					   dpc_handler, IRQF_SHARED,
					   "pcie-dpc", pdev);
	if (status) {
		pci_warn(pdev, "request IRQ%d failed: %d\n", dev->irq,
			 status);
		return status;
	}

	pci_read_config_word(pdev, pdev->dpc_cap + PCI_EXP_DPC_CAP, &cap);
	dpc_enable(dev);

	pci_info(pdev, "enabled with IRQ %d\n", dev->irq);
	pci_info(pdev, "error containment capabilities: Int Msg #%d, RPExt%c PoisonedTLP%c SwTrigger%c RP PIO Log %d, DL_ActiveErr%c\n",
		 cap & PCI_EXP_DPC_IRQ, FLAG(cap, PCI_EXP_DPC_CAP_RP_EXT),
		 FLAG(cap, PCI_EXP_DPC_CAP_POISONED_TLP),
		 FLAG(cap, PCI_EXP_DPC_CAP_SW_TRIGGER), pdev->dpc_rp_log_size,
		 FLAG(cap, PCI_EXP_DPC_CAP_DL_ACTIVE));
```

The second message prints `cap & PCI_EXP_DPC_IRQ` as `Int Msg #`, the number that chose the vector whose IRQ the first message prints, so the log pairs the number with its IRQ.

The five requests leave each IRQ with one action per service that uses it, and each action records the handler, the thread and the cookie of its request. The figure draws the actions for a port with three distinct numbers.

```text
    The actions each IRQ holds after the five requests, for a port with distinct numbers m, a and d
    ───────────────────────────────────────────────────────────────────────────────────────────────

               ┌──────────────────────────────────────────────────────────────────┐
    IRQ x ──┬─▶│ action "PCIe PME"     handler pcie_pme_irq                       │
            │  │                       dev_id: the PME instance                   │
            │  └──────────────────────────────────────────────────────────────────┘
            │  ┌──────────────────────────────────────────────────────────────────┐
            ├─▶│ action "pciehp"       handler pciehp_isr, thread pciehp_ist      │
            │  │                       dev_id: the hotplug controller of the port │
            │  └──────────────────────────────────────────────────────────────────┘
            │  ┌──────────────────────────────────────────────────────────────────┐
            └─▶│ action "PCIe bwctrl"  handler pcie_bwnotif_irq                   │
               │                       dev_id: the bandwidth control instance     │
               └──────────────────────────────────────────────────────────────────┘

               ┌──────────────────────────────────────────────────────────────────┐
    IRQ y ────▶│ action "aerdrv"       handler aer_irq, thread aer_isr            │
               │                       dev_id: the AER instance                   │
               └──────────────────────────────────────────────────────────────────┘

               ┌──────────────────────────────────────────────────────────────────┐
    IRQ z ────▶│ action "pcie-dpc"     handler dpc_irq, thread dpc_handler        │
               │                       dev_id: the port's struct pci_dev          │
               └──────────────────────────────────────────────────────────────────┘

    the three actions of IRQ x are drawn in slot order; the IRQ core calls every one of them for each interrupt
    with m = a = d, or on the pin interrupt, all five actions belong to one IRQ
```

The IRQ of the PCI Express Capability's number thus carries up to three handlers. On the pin interrupt, or with all numbers equal, the handlers of all five services share one IRQ.

### Handlers on a shared vector test their own status

A shared IRQ tells a handler only that some source on the line fired. Each service handler therefore reads its own status register and claims the interrupt only when its bits are set. The IRQ core runs every handler registered on the line in turn; read the stages of [`__handle_irq_event_percpu()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L185) that run them.

```c
/* kernel/irq/handle.c:185 */
irqreturn_t __handle_irq_event_percpu(struct irq_desc *desc)
{
	irqreturn_t retval = IRQ_NONE;
	unsigned int irq = desc->irq_data.irq;
	struct irqaction *action;

	for_each_action_of_desc(desc, action) {
		irqreturn_t res;
		... /* 8 lines, to :201 */
		trace_irq_handler_entry(irq, action);

		if (static_branch_unlikely(&irqhandler_duration_check_enabled)) {
			u64 ts_start = local_clock();

			res = action->handler(irq, action->dev_id);
			irqhandler_duration_check(ts_start, irq, action);
		} else {
			res = action->handler(irq, action->dev_id);
		}

		trace_irq_handler_exit(irq, action, res);
		... /* 5 lines, to :218 */
		switch (res) {
		case IRQ_WAKE_THREAD:
			/*
			 * Catch drivers which return WAKE_THREAD but
			 * did not set up a thread function
			 */
			if (unlikely(!action->thread_fn)) {
				warn_no_thread(irq, action);
				break;
			}

			__irq_wake_thread(desc, action);
			break;

		default:
			break;
		}

		retval |= res;
	}
```

The loop calls the handler of each action, fires `trace_irq_handler_entry()` before it and `trace_irq_handler_exit()` after it, and wakes the action's thread on `IRQ_WAKE_THREAD`. The results are combined into `retval`, so an `IRQ_NONE` from one handler does not stop the next.

[`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) reads Root Status and returns `IRQ_NONE` without a pending PME. Read its first stage.

```c
/* drivers/pci/pcie/pme.c:266 */
static irqreturn_t pcie_pme_irq(int irq, void *context)
{
	struct pci_dev *port;
	struct pcie_pme_service_data *data;
	u32 rtsta;
	unsigned long flags;

	port = ((struct pcie_device *)context)->port;
	data = get_service_data((struct pcie_device *)context);

	spin_lock_irqsave(&data->lock, flags);
	pcie_capability_read_dword(port, PCI_EXP_RTSTA, &rtsta);

	if (PCI_POSSIBLE_ERROR(rtsta) || !(rtsta & PCI_EXP_RTSTA_PME)) {
		spin_unlock_irqrestore(&data->lock, flags);
		return IRQ_NONE;
	}
```

Without a set PME Status bit the handler returns `IRQ_NONE` after one configuration read, so an interrupt from another source on the line costs the PME service that read.

[`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) reads Slot Status, keeps the event bits, clears them and saves them for its thread. Read the stages that decide.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	struct device *parent = pdev->dev.parent;
	u16 status, events = 0;
	... /* 25 lines, to :654 */
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &status);
	if (PCI_POSSIBLE_ERROR(status)) {
		ctrl_info(ctrl, "%s: no response from device\n", __func__);
		if (parent)
			pm_runtime_put(parent);
		return IRQ_NONE;
	}
	... /* 18 lines, to :679 */
	events |= status;
	if (!events) {
		if (parent)
			pm_runtime_put(parent);
		return IRQ_NONE;
	}

	if (status) {
		pcie_capability_write_word(pdev, PCI_EXP_SLTSTA, status);

		/*
		 * In MSI mode, all event bits must be zero before the port
		 * will send a new interrupt (PCIe Base Spec r5.0 sec 6.7.3.4).
		 * So re-read the Slot Status register in case a bit was set
		 * between read and write.
		 */
		if (pci_dev_msi_enabled(pdev) && !pciehp_poll_mode)
			goto read_status;
	}
	... /* 25 lines, to :723 */
	/* Save pending events for consumption by IRQ thread. */
	atomic_or(events, &ctrl->pending_events);
	return IRQ_WAKE_THREAD;
}
```

No event bit means `IRQ_NONE`. Set bits are written back to clear them. With MSI or MSI-X enabled the handler then reads Slot Status again, since the comment cites a rule that a port in MSI mode sends no new interrupt until every event bit is zero. The events then reach the IRQ thread through `IRQ_WAKE_THREAD`.

[`pcie_bwnotif_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L211) reads Link Status for the two bandwidth bits. Read its first stage.

```c
/* drivers/pci/pcie/bwctrl.c:211 */
static irqreturn_t pcie_bwnotif_irq(int irq, void *context)
{
	struct pcie_device *srv = context;
	struct pci_dev *port = srv->port;
	u16 link_status, events;
	int ret;

	ret = pcie_capability_read_word(port, PCI_EXP_LNKSTA, &link_status);
	if (ret != PCIBIOS_SUCCESSFUL)
		return IRQ_NONE;

	events = link_status & (PCI_EXP_LNKSTA_LBMS | PCI_EXP_LNKSTA_LABS);
	if (!events)
		return IRQ_NONE;
```

Without Link Bandwidth Management Status or Link Autonomous Bandwidth Status set, the handler returns `IRQ_NONE` and leaves the line to the other handlers.

The figure follows one hotplug event across the port, the IRQ core and the three handlers that share IRQ x.

```text
    One hotplug event on the vector that PME, hotplug and bandwidth control share
    ─────────────────────────────────────────────────────────────────────────────
    time ↓
    port hardware     ╎ IRQ core, IRQ x       ╎ PME handler          ╎ hotplug handler       ╎ bwctrl handler
    ──────────────────┼───────────────────────┼──────────────────────┼───────────────────────┼──────────────────
    Slot Status event ╎                       ╎                      ╎                       ╎
    bit set, message  ╎                       ╎                      ╎                       ╎
    m sent ──────────▶╎ ➊ runs each           ╎                      ╎                       ╎
                      ╎ handler on IRQ x      ╎                      ╎                       ╎
                      ╎ ──────────────────────▶ ➋ Root Status        ╎                       ╎
                      ╎                       ╎ PME clear:           ╎                       ╎
                      ╎                       ╎ IRQ_NONE             ╎                       ╎
                      ╎ ─────────────────────────────────────────────▶ ➌ event bits          ╎
                      ╎                       ╎                      ╎ cleared in Slot       ╎
                      ╎                       ╎                      ╎ Status: thread woken  ╎
                      ╎ ─────────────────────────────────────────────────────────────────────▶ ➍ LBMS and LABS
                      ╎                       ╎                      ╎                       ╎ clear: IRQ_NONE
                      ╎                       ╎                      ╎                       ╎
                      ╎ the pciehp IRQ        ╎                      ╎                       ╎
                      ╎ thread handles        ╎                      ╎                       ╎
                      ╎ the event             ╎                      ╎                       ╎
                      ╎                       ╎                      ╎                       ╎

    ➊ __handle_irq_event_percpu  handle.c:209       calls the handler of each action in turn
    ➋ pcie_pme_irq               pme.c:281          returns IRQ_NONE when no PME is pending
    ➌ pciehp_isr                 pciehp_hpc.c:687   clears the event bits it read
    ➍ pcie_bwnotif_irq           bwctrl.c:224       returns IRQ_NONE without a link event
```

➊ [`__handle_irq_event_percpu()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L185) calls the handler of each action registered on IRQ x in turn. ➋ [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) finds no pending PME in Root Status and returns `IRQ_NONE`. ➌ [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) clears the event bits it read from Slot Status and saves them for its thread. ➍ [`pcie_bwnotif_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L211) finds neither bandwidth bit set and returns `IRQ_NONE`.

So far, each service of the port holds its IRQ in its instance and has requested it with `IRQF_SHARED`. Its handler claims only the interrupts its own status bits explain.

### Messages, tracepoints and files expose the distribution

The distribution prints one notice of its own and fires no tracepoint. What a reader sees of it comes from the services' probe messages, the IRQ core's tracepoints and the files of the port. The table lists each class with its sites and names an absent class as absent.

| class | on these paths | sites |
|---|---|---|
| tracepoints | none in portdrv.c or in the allocator; `irq:irq_handler_entry` and `irq:irq_handler_exit` fire for every handler of a shared IRQ, the exit event recording `handled` or `unhandled` | [`irq_handler_entry`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/irq.h#L53), [`irq_handler_exit`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/irq.h#L83), [`handle.c:201`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L201), [`handle.c:212`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L212) |
| messages | the DMI notice; the IRQ lines of PME, AER and DPC at info level; the AER and hotplug errors on a failed request; the DPC warning on a failed request | [`portdrv.c:808`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L808), [`pme.c:356`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L356), [`aer.c:1641`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1641), [`dpc.c:495-500`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L495), [`aer.c:1635`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1635), [`pciehp_hpc.c:73`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L73), [`dpc.c:487`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L487) |
| dynamic-debug sites | the bandwidth service's IRQ line and the pin routing line, switchable at run time with [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | [`bwctrl.c:282`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L282), [`pci_irq.c:472`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_irq.c#L472) |
| asynchronous hand-offs | none in the distribution, which runs inside the port's probe; after the handlers, the IRQ threads of hotplug, AER and DPC and the PME work item take the events | [`handle.c:229`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L229), [`pme.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L288) |
| debugging surfaces | the `pcie_pme=nomsi` and `pci=nomsi` boot parameters, the [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) module parameter, the port's `irq` file and `msi_irqs/` directory, /proc/interrupts with the handler names of the table above, and the AER injector; no debugfs file covers the distribution | [`pme.c:40`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L40), [`pci.c:6752`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6752), [`pciehp_core.c:41`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L41), [`pci-sysfs.c:59`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-sysfs.c#L59) |

The global switch behind `pci=nomsi` is [`pci_msi_enable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L18), which [`pci_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L985) clears. Read the setter and then the first stage of [`pci_msi_supported()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L29), the test every MSI-X and MSI request makes.

```c
/* drivers/pci/msi/msi.c:985 */
void pci_no_msi(void)
{
	pci_msi_enable = false;
}
```

The setter only clears the global. [`pci_msi_supported()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/msi.c#L29) reads it before anything else, and it also rejects a port whose own bit forbids MSI; read its first stage.

```c
/* drivers/pci/msi/msi.c:29 */
static int pci_msi_supported(struct pci_dev *dev, int nvec)
{
	struct pci_bus *bus;

	/* MSI must be globally enabled and supported by the device */
	if (!pci_msi_enable)
		return 0;

	if (!dev || dev->no_msi)
		return 0;
```

With the switch clear, or with the port's [`no_msi`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L465) bit set by a quirk, the test fails. Both vector requests of [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) then fail, and every service of the port runs on the pin interrupt.

The port's sysfs `irq` file tells which IRQ a reader should look for in /proc/interrupts. Read [`irq_show()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-sysfs.c#L59) for the mode it reports.

```c
/* drivers/pci/pci-sysfs.c:59 */
static ssize_t irq_show(struct device *dev,
			struct device_attribute *attr,
			char *buf)
{
	struct pci_dev *pdev = to_pci_dev(dev);

#ifdef CONFIG_PCI_MSI
	/*
	 * For MSI, show the first MSI IRQ; for all other cases including
	 * MSI-X, show the legacy INTx IRQ.
	 */
	if (pdev->msi_enabled)
		return sysfs_emit(buf, "%u\n", pci_irq_vector(pdev, 0));
#endif

	return sysfs_emit(buf, "%u\n", pdev->irq);
}
static DEVICE_ATTR_RO(irq);
```

In MSI mode the file prints the IRQ of vector 0, which is the shared IRQ of PME, hotplug and bandwidth control only when their number is 0. In MSI-X mode and on the pin interrupt it prints [`irq`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L454), the pin IRQ. The vectors of an MSI-X port appear as the files of `msi_irqs/`, one per allocated vector.

With [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) set, the AER error injector raises the AER service's IRQ directly. Read the stage of [`aer_inject()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L319) that finds the instance and injects its interrupt.

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

The injector finds the AER instance of the Root Port with [`pcie_port_find_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L483) and raises its [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) through `irq_inject_interrupt()`. The AER handler then runs on the IRQ the distribution gave AER, shared or private.

A reader can thus count the vectors in `msi_irqs/` and read each service's IRQ in its probe message and in /proc/interrupts. The `irq:irq_handler_exit` events show every handler's verdict on a shared IRQ.
