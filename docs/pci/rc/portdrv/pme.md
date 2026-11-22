# PCIe native PME service

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe device in a low-power state asks to be woken by sending a PME Message toward the Root Complex, and software then has to find that device and bring it back to working power. When firmware grants the operating system native PME control, recorded in [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656), the Root Port or Root Complex Event Collector that receives the message latches the requester's ID in Root Status, [`PCI_EXP_RTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L653), and raises an interrupt. The PCIe port driver answers that interrupt through its PME service, [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456), which queues a runtime resume of the requester with [`pm_request_resume()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L454). This page traces which ports run the service, how it arms the port, how one interrupt becomes a resume request, and how system sleep and removal change the interrupt's state.

```text
    One native PME, from the requester to a queued resume request
    ─────────────────────────────────────────────────────────────
    time ↓
    requester             ╎ Root Port               ╎ hardirq handler     ╎ work item               ╎ runtime PM
    ──────────────────────┼─────────────────────────┼─────────────────────┼─────────────────────────┼──────────────────
    PME_Status 1          ╎                         ╎                     ╎                         ╎
    PME Message ────────▶ ╎ Root Status: PME 1,     ╎                     ╎                         ╎
                          ╎ Requester ID latched    ╎                     ╎                         ╎
                          ╎ PMEIE 1, interrupt ───▶ ╎ PME 1 read          ╎                         ╎
                          ╎ PMEIE 0 ◀───────────────┤ masked              ╎                         ╎
                          ╎                         ╎ work queued ──────▶ ╎ PME Status cleared      ╎
                          ╎ PME 0 ◀─────────────────┼─────────────────────┤ by a write              ╎
    PME_Status 0, ◀───────┼─────────────────────────┼─────────────────────┤ source found by its ID  ╎
    PME_En 0              ╎                         ╎                     ╎ resume queued ────────▶ ╎ resume request
                          ╎                         ╎                     ╎                         ╎ queued on pm_wq
                          ╎ PMEIE 1 ◀───────────────┼─────────────────────┤ Root Status drained     ╎

    PME_Status and PME_En are bits of the requester's PM Control/Status register;
    PME and PMEIE are bits of the port's Root Status and Root Control registers
```

## SUMMARY

The journey above passes between the requester, the port and two kernel contexts, and the table pairs each PCIe term with the kernel object that stands for it. The rest of the page uses the names in its first column.

| Name on this page | PCIe meaning | Kernel representation |
|---|---|---|
| the port | a Root Port or a Root Complex Event Collector (RCEC), the function that receives PME Messages | a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) is [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488) or [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494) |
| the service instance | the port's PME function as portdrv divides a port into services, with no PCIe object of its own | a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance, whose [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) is [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) |
| the service data | the PME service's own state, with no PCIe object | a [`struct pcie_pme_service_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L42), held in the instance's [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) |
| native PME control | the control that firmware grants through the ACPI `_OSC` method | [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) of the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) above the port |
| a latched request | a PME Message the port recorded | [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655) and [`PCI_EXP_RTSTA_PME_RQ_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L654) in Root Status, [`PCI_EXP_RTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L653) |
| the requester | the function that sent the PME Message | the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose PM Control/Status register has [`PCI_PM_CTRL_PME_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L268) set |

The hardirq handler [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) masks the port and defers, and the work item [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214) clears each latched request, finds its requester and queues its resume. The governing invariant is that [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) stays clear while the work item owns Root Status, and the work item sets it again only while [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) is false. System sleep either keeps the interrupt armed as a wakeup source or disables it and sets that flag, and resume reverses the choice.

## SPECIFICATIONS

The PCI Express Base Specification defines the PME Message, the Root Control and Root Status registers and the Requester ID the service reads. The tree cites it for this mechanism by revision and section number, without section titles.

- PCI Express Base Specification, Rev. 2.0, Section 6.1.9, no title given: cited by the comment in [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) at [`pme.c:146-153`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L146) for a Root Port that reports a PME on behalf of a conventional PCI device below it.
- PCI Express Base Specification, r4.0, sec 6.1.6, no title given: cited by commit [3620c71484f7](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=3620c71484f7a19b2588e577ea732f55719f5b1f) ("PCI/PM: Clear PCIe PME Status bit for Root Complex Event Collectors") for RCECs that generate PME interrupts on behalf of Root Complex Integrated Endpoints.
- PCI Express Base Specification, r7.0, sec 7.4, no title given: cited by commit [699722468a0f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=699722468a0fca8b1b9ce1ffe2532171ddcaff95) ("PCI/PME: Replace RMW of Root Status register with direct write") for the RW1C PME Status bit and the RsvdZ bits of Root Status.
- PCIe r3.1, sec 7.8.2, 7.10.10 and 7.31.2, no titles given: cited by the comment in [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) at [`portdrv.c:63-67`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L63) for the Interrupt Message Number that selects the vector the PME service shares.

## COVERAGE

### Boot parameter and driver registration (drivers/pci/pcie/pme.c)

- [`'\<pcie_pme_msi_disabled\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31): the flag that keeps a port with the PME service off MSI and MSI-X.
- [`'\<pcie_pme_setup\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33): the parser of the `pcie_pme=` boot parameter.
- [`'\<pcie_pme_driver\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456): the PME service driver that portdrv binds to PME service instances.
- [`'\<pcie_pme_init\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470): registers the service driver during portdrv's initialization.

### Service data, probe and removal (drivers/pci/pcie/pme.c)

- [`'\<struct pcie_pme_service_data\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L42): the state one service instance keeps from probe to removal.
- [`'pcie_pme_service_data.noirq'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46): keeps the PME interrupt disabled while set.
- [`'\<pcie_pme_probe\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326): allocates the state, installs the handler and arms the port.
- [`'\<pcie_pme_can_wakeup\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L298): marks one device wakeup-capable.
- [`'\<pcie_pme_mark_devices\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L312): marks the port and the devices that report through it.
- [`'\<pcie_pme_remove\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L446): disables the interrupt, then frees the handler, the work item and the state.

### Root Control and Root Status access (drivers/pci/pcie/pme.c, drivers/pci/pci.c)

- [`'\<pcie_pme_interrupt_enable\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54): sets or clears the PME Interrupt Enable bit of Root Control.
- [`'\<pcie_clear_root_pme_status\>':'drivers/pci/pci.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2252): clears the latched PME Status bit of Root Status.

### Interrupt, work item and source search (drivers/pci/pcie/pme.c)

- [`'\<pcie_pme_irq\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266): the hardirq handler that claims a latched request, masks the port and queues the work item.
- [`'\<pcie_pme_work_fn\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214): the work item that drains Root Status and unmasks the port.
- [`'\<pcie_pme_handle_request\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130): resolves a Requester ID to its requester and queues the resume.
- [`'\<pcie_pme_from_pci_bridge\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L102): tests whether a PCIe-to-PCI bridge reported the request.
- [`'\<pcie_pme_walk_bus\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L70): scans buses for conventional PCI devices with PME Status set.

### System sleep (drivers/pci/pcie/pme.c)

- [`'\<pcie_pme_check_wakeup\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L363): looks for a wakeup-enabled device below the port.
- [`'\<pcie_pme_disable_interrupt\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L378): masks the port, clears Root Status and sets the flag that keeps it masked.
- [`'\<pcie_pme_suspend\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L392): keeps the vector as a wakeup interrupt or disables the service.
- [`'\<pcie_pme_resume\>':'drivers/pci/pcie/pme.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L423): re-arms a disabled service or turns the wakeup interrupt off.

### Root Control and Root Status registers (include/uapi/linux/pci_regs.h)

- [`'PCI_EXP_RTCTL'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L643): the offset of Root Control in the PCI Express Capability.
- [`'PCI_EXP_RTCTL_PMEIE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647): the PME Interrupt Enable bit.
- [`'PCI_EXP_RTSTA'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L653): the offset of Root Status in the PCI Express Capability.
- [`'PCI_EXP_RTSTA_PME_RQ_ID'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L654): the latched PME Requester ID field.
- [`'PCI_EXP_RTSTA_PME'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655): the PME Status bit.
- [`'PCI_EXP_RTSTA_PENDING'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L656): the PME Pending bit.

## DOCUMENTATION

- [`Documentation/power/pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/power/pci.rst): native PCI Express PME signaling, the Requester ID a Root Port records for the interrupt handler, the RCEC that reports for integrated endpoints, and the ACPI condition for using native signaling.
- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver and its service drivers, the PME service among them.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the `pcie_pme=nomsi` and `pcie_ports=` boot parameters.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI/PME: Replace RMW of Root Status register with direct write (commit 699722468a0f)](https://patch.msgid.link/39f87c99f6c44be3c0371c79e454e6fde7be0d4d.1761497583.git.lukas@wunner.de)
- [PM: sleep: Do not flag runtime PM workqueue as freezable (commit 4fb352df14de)](https://patch.msgid.link/12794222.O9o76ZdvQC@rafael.j.wysocki)
- [PCI/PME: Use FIELD_GET() (commit ec302b118a59)](https://lore.kernel.org/r/20231010204436.1000644-8-helgaas@kernel.org)
- [PCI: Add locking to RMW PCI Express Capability Register accessors (commit 5e70d0acf082)](https://lore.kernel.org/r/20230717120503.15276-2-ilpo.jarvinen@linux.intel.com)
- [PCI/PME: Use PCI_POSSIBLE_ERROR() to check config reads (commit aa66ea10ba84)](https://lore.kernel.org/r/679ce049bccf10df3ca9ef4918ee2c3235afdaea.1637243717.git.naveennaidu479@gmail.com)
- [PCI/PME: Add pcie_walk_rcec() to RCEC PME handling (commit 9a2f604f4497)](https://lore.kernel.org/r/20201121001036.8560-15-sean.v.kelley@intel.com)
- [PCI/PME: Replace dev_printk(KERN_DEBUG) with dev_info() (commit 00ebf1348cb3)](https://lore.kernel.org/lkml/20190509141456.223614-3-helgaas@kernel.org)
- [PCI/PME: Fix hotplug/sysfs remove deadlock in pcie_pme_remove() (commit 95c80bc6952b)](https://lore.kernel.org/linux-pci/c7697e7c-e1af-13e4-8491-0a3996e6ab5d@huawei.com)
- [Revert "PCI/PME: Implement runtime PM callbacks" (commit c528f7bd362b)](https://bugzilla.kernel.org/show_bug.cgi?id=202103)

## REGISTERS

The service gates its interrupt in Root Control and reads latched requests from Root Status, both in the PCI Express Capability of the port, and the source search reads the PM Control/Status register in the requester's Power Management Capability. [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) and [`pcie_clear_root_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2252) are the service's accessors for the port's registers, and [`pci_check_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2265) reads and writes the requester's register.

```text
    Root Control, PCI_EXP_RTCTL: 16 bits at 0x1c in the PCI Express Capability
    ──────────────────────────────────────────────────────────────────────────
    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    RTCTL │          ·          │V│P│F│N│C│
          └─────────────────────┴┬┴┬┴┬┴┬┴┬┘
                                 │ │ │ │ └── SECEE (0)
                                 │ │ │ └──── SENFEE (1)
                                 │ │ └────── SEFEE (2)
                                 │ └──────── PMEIE (3)
                                 └────────── RRS_SVE (4)

    C = SECEE = PCI_EXP_RTCTL_SECEE (System Error on Correctable Error)
    N = SENFEE = PCI_EXP_RTCTL_SENFEE (System Error on Non-Fatal Error)
    F = SEFEE = PCI_EXP_RTCTL_SEFEE (System Error on Fatal Error)
    P = PMEIE = PCI_EXP_RTCTL_PMEIE (PME Interrupt Enable)
    V = RRS_SVE = PCI_EXP_RTCTL_RRS_SVE (Configuration RRS Software Visibility Enable)
    15:5 = no field macro in pci_regs.h; no struct member caches the register
```

In Root Control, [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) decides whether the port raises an interrupt when it latches a PME. [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) sets it once the handler is installed, [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) clears it before deferring to the work item, and [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214) sets it again once Root Status is drained. The system-error enables [`PCI_EXP_RTCTL_SECEE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L644), [`PCI_EXP_RTCTL_SENFEE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L645) and [`PCI_EXP_RTCTL_SEFEE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L646) and [`PCI_EXP_RTCTL_RRS_SVE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L648) share the register, and the locked read-modify-write of the PME accessor leaves them as they were.

```text
    Root Status, PCI_EXP_RTSTA: 32 bits at 0x20 in the PCI Express Capability
    ─────────────────────────────────────────────────────────────────────────
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    RTSTA │      no macro (31:18)     │N│P│        PME_RQ_ID (15:0)       │
          └───────────────────────────┴─┴─┴───────────────────────────────┘

    N = PENDING = PCI_EXP_RTSTA_PENDING (PME Pending, bit 17)
    P = PME = PCI_EXP_RTSTA_PME (PME Status, bit 16)
    PME_RQ_ID = PCI_EXP_RTSTA_PME_RQ_ID (PME Requester ID: bus number 15:8, devfn 7:0)
    31:18 = no field macro in pci_regs.h; no struct member caches the register
```

In Root Status, [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655) decides whether the handler claims the interrupt and whether the work item hands a request on, [`PCI_EXP_RTSTA_PME_RQ_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L654) names the requester as a bus number above a devfn, and [`PCI_EXP_RTSTA_PENDING`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L656) decides whether the work item waits for a further request. Software clears PME Status by writing the set bit back through [`pcie_clear_root_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2252), and the other bits are read-only or RsvdZ according to commit [699722468a0f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=699722468a0fca8b1b9ce1ffe2532171ddcaff95) ("PCI/PME: Replace RMW of Root Status register with direct write").

```text
    PM Control/Status, PCI_PM_CTRL: 16 bits at 4 in the Power Management Capability
    ───────────────────────────────────────────────────────────────────────────────
    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    PMCSR │S│ C │   D   │E│   ·   │R│·│ W │
          └┬┴──┬┴────┬──┴┬┴───────┴┬┴─┴──┬┘
           │   │     │   │         │     └── STATE (1:0)
           │   │     │   │         └──────── NO_SOFT_RESET (3)
           │   │     │   └────────────────── PME_ENABLE (8)
           │   │     └────────────────────── DATA_SEL (12:9)
           │   └──────────────────────────── DATA_SCALE (14:13)
           └──────────────────────────────── PME_STATUS (15)

    S = PME_STATUS = PCI_PM_CTRL_PME_STATUS (PME Status)
    C = DATA_SCALE = PCI_PM_CTRL_DATA_SCALE_MASK (Data Scale)
    D = DATA_SEL = PCI_PM_CTRL_DATA_SEL_MASK (Data Select)
    E = PME_ENABLE = PCI_PM_CTRL_PME_ENABLE (PME Enable)
    R = NO_SOFT_RESET = PCI_PM_CTRL_NO_SOFT_RESET (No Soft Reset)
    W = STATE = PCI_PM_CTRL_STATE_MASK (current power state, D0 to D3)
    7:4 and 2 = no field macro in pci_regs.h; the register is at pm_cap + PCI_PM_CTRL
```

In the requester's register, [`PCI_PM_CTRL_PME_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L268) decides whether [`pci_check_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2265) treats the device as a requester and is cleared by writing the set bit back, and [`PCI_PM_CTRL_PME_ENABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L265) decides whether the requester counts as armed, the same write clearing it. The power state, Data Select, Data Scale and No Soft Reset fields keep the values the read returned on this path.

## DETAILS

The subsections after the configuration index follow the service in run order, starting with the firmware grant and the port type that decide which ports get a PME service instance, the boot parameter that moves those ports onto INTx, and the registration and binding of [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456). The Root Control and Root Status accessors come next, then probe with its [`struct pcie_pme_service_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L42) and the wakeup marks it sets on the devices below the port. One PME then runs through the hardirq handler, the work item, the search for the requester, the bus scans for conventional PCI requesters, the requester's own status check and the end of polling for it. The page ends with system suspend and resume, removal, and the messages, hand-offs and files that make the service visible.

### Kconfig assumptions

The page documents the x86-64 default configuration resolved at the pinned commit, with the options the campaign adds, among them [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44), [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16), [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) and [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120). The architecture is x86-64 with ACPI, so firmware grants PME control through the ACPI `_OSC` method of the host bridge.

| Option | Value assumed | What it decides on these paths |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds portdrv, which offers the PME service to ports |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | turns on [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) together with the port bus option and compiles portdrv's PM fan-out |
| [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) | y | builds pme.o; without it the portdrv.h stubs do nothing |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | lets the port signal PME through MSI or MSI-X unless `pcie_pme=nomsi` is given |
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | runs the `_OSC` negotiation whose result clears or keeps [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | binds the hotplug service that shares the PME vector |
| [`CONFIG_SUSPEND`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L2) | y | compiles the PCI core's early clear of Root Status on resume |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y | follows [`CONFIG_SUSPEND`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L2) and selects [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | turns on the debug sites of the paths; pme.c has none |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would define `DEBUG` for drivers/pci and print the same debug sites unconditionally |

The table indexes the prose, and each option's effect is stated again in the subsection where it applies.

### Firmware ownership and port type decide where PME runs

The PME service runs on a port when two conditions hold: the operating system owns native PME signaling below the port's host bridge, and the port is a kind that latches PME requests. Ownership is a bit of the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628), and the port's kind is its PCIe Device/Port Type, which [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) reads. Both are settled before any service driver runs.

[`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659) gives a new [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) its defaults. Read its first lines for the native-control bits, which start out granted.

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
	bridge->native_pcie_hotplug = 1;
	bridge->native_shpc_hotplug = 1;
	bridge->native_pme = 1;
```

[`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) starts at 1 beside the AER, hotplug, LTR and DPC bits, and the comment says a platform can keep these features through `_OSC`. On x86 with ACPI, [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) takes each control back that the `_OSC` negotiation did not grant; read the stage where the host bridge's bits follow the granted set.

```c
/* drivers/acpi/pci_root.c:995 */
struct pci_bus *acpi_pci_root_create(struct acpi_pci_root *root,
				     struct acpi_pci_root_ops *ops,
				     struct acpi_pci_root_info *info,
				     void *sysdata)
{
	int ret, busnum = root->secondary.start;
	struct acpi_device *device = root->device;
	... /* 27 lines, to :1029 */
	host_bridge = to_pci_host_bridge(bus->bridge);
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_NATIVE_HP_CONTROL))
		host_bridge->native_pcie_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_SHPC_NATIVE_HP_CONTROL))
		host_bridge->native_shpc_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_AER_CONTROL))
		host_bridge->native_aer = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_PME_CONTROL))
		host_bridge->native_pme = 0;
```

[`osc_control_set`](https://elixir.bootlin.com/linux/v7.2/source/include/acpi/acpi_bus.h#L739) holds the controls that the ACPI `_OSC` method of the host bridge granted, and a missing [`OSC_PCI_EXPRESS_PME_CONTROL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/acpi.h#L642) clears [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656). With [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) set, the x86 host bridge scan in arch/x86/pci/acpi.c creates its root buses through this function. portdrv reads the bit when it builds a port's service mask in [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218); read the stage that decides the PME bit.

```c
/* drivers/pci/pcie/portdrv.c:218 */
static int get_port_device_capability(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	int services = 0;
	... /* 25 lines, to :247 */
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

The PME bit, [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16), is set for a port whose [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) is [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488) or [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494), when [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) is set or [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) overrides it. The same branch calls [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) with false, so an interrupt that firmware enabled stays off until the PME driver's probe enables it. The type test selects the ports that carry Root Control and Root Status, which [`pcie_cap_has_rtctl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L378) decides for the capability accessors.

```c
/* drivers/pci/access.c:378 */
bool pcie_cap_has_rtctl(const struct pci_dev *dev)
{
	int type = pci_pcie_type(dev);

	return type == PCI_EXP_TYPE_ROOT_PORT ||
	       type == PCI_EXP_TYPE_RC_EC;
}
```

[`pcie_capability_reg_implemented()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L386) consults that test for the Root Control, Root Capabilities and Root Status offsets; read the stage that sends those three offsets to it.

```c
/* drivers/pci/access.c:386 */
static bool pcie_capability_reg_implemented(struct pci_dev *dev, int pos)
{
	if (!pci_is_pcie(dev))
		return false;

	switch (pos) {
	... /* 14 lines, to :406 */
	case PCI_EXP_RTCTL:
	case PCI_EXP_RTCAP:
	case PCI_EXP_RTSTA:
		return pcie_cap_has_rtctl(dev);
```

A port of another type has no Root Control or Root Status that the PME code could use, so the service is offered to Root Ports and RCECs and to nothing below them. The override comes from the command line, where [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) parses `pcie_ports=`.

```c
/* drivers/pci/pcie/portdrv.c:622 */
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

`pcie_ports=native` sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), and portdrv then offers PME on a port whose host bridge did not get native control. `pcie_ports=compat` sets [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607), which keeps portdrv from registering its service drivers. The figure places these conditions on two hierarchies.

```text
    Which ports get a PME service instance below two host bridges
    ─────────────────────────────────────────────────────────────
    ┌────────────────────────────────────────────────────┐             ╎   ┌────────────────────────────────────────┐
    │ host bridge A: native_pme 1                        │             ╎   │ host bridge B: native_pme 0            │
    │ _OSC granted PME control                           │             ╎   │ firmware kept PME control              │
    └───────┬─────────────────────────┬──────────────────┘             ╎   └─────────┬──────────────────────────────┘
            │                         │                                ╎             │
            │                         │         rcec_ea                ╎             │
    ┌───────┴────────────┐    ┌───────┴────────┐    ┌───────────────┐  ╎   ┌─────────┴──────────────────────────────┐
    │ Root Port          │    │ RCEC           ├╌╌╌▶│ RCiEP         │  ╎   │ Root Port                              │
    │ instance: yes      │    │ instance: yes  │    │ instance: no  │  ╎   │ instance: only when booted with        │
    └───────┬────────────┘    └────────────────┘    └───────────────┘  ╎   │ pcie_ports=native                      │
            │                                                          ╎   └────────────────────────────────────────┘
            │                                                          ╎
    ┌───────┴────────────┐                                             ╎
    │ Switch Ports       │                                             ╎
    │ instance: no       │                                             ╎
    └───────┬────────────┘                                             ╎
            │
            │
    ┌───────┴──────────────┐
    │ Endpoint, requester  │
    └──────────────────────┘

    instance = PCIE_PORT_SERVICE_PME set in the port's service mask, and a struct pcie_device made for it
    yes for PCI_EXP_TYPE_ROOT_PORT and PCI_EXP_TYPE_RC_EC whose host bridge has native_pme 1, or with pcie_ports=native
    ╌╌▶ = an RCEC's association with the RCiEPs its rcec_ea describes; ╎ = the boundary between the two hierarchies
```

A Root Port or RCEC below a host bridge with native PME control thus gets the PME bit in its service mask, and switch ports and endpoints get none from this test.

### pcie_pme=nomsi moves a PME port's services onto INTx

A port's services share the port's interrupt vectors, and the PME service settles one question about them before any driver binds: whether the port may use MSI at all. [`pcie_pme_msi_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31) records the answer, and [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33) sets it from the `pcie_pme=nomsi` boot parameter. The comment above the flag gives the reason for the switch, and the parser follows it.

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
```

[`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33) sets [`pcie_pme_msi_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31) when the parameter's value starts with `nomsi`, and any other value leaves the flag false. The comment attributes the switch to PME-based wakeup from system sleep, which MSI signaling did not serve. The line after the parser registers it for the `pcie_pme=` prefix.

```c
/* drivers/pci/pcie/pme.c:40 */
__setup("pcie_pme=", pcie_pme_setup);
```

`__setup()` registers [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33) as the handler of the `pcie_pme=` prefix on the kernel command line. portdrv reads the flag through [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113), one of the PME helpers that portdrv.h declares; read the block for what a kernel without [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) gets.

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

With [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) set, [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) returns the flag and [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108) sets it. Without the option, the stubs return false or do nothing, and [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) becomes an empty inline. The flag acts in [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177), which picks the vectors for the services of one port.

```c
/* drivers/pci/pcie/portdrv.c:177 */
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

A port whose mask holds [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) skips MSI and MSI-X when the flag is set and allocates one INTx vector, which the second loop copies into the `irqs[]` slots of every service. Without the flag, [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) decides with [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) set; read the stage where it hands the PME service its vector.

```c
/* drivers/pci/pcie/portdrv.c:113 */
static int pcie_port_enable_irq_vec(struct pci_dev *dev, int *irqs, int mask)
{
	int nr_entries, nvec, pcie_irq;
	u32 pme = 0, aer = 0, dpc = 0;
	... /* 34 lines, to :151 */
	/* PME, hotplug and bandwidth notification share an MSI/MSI-X vector */
	if (mask & (PCIE_PORT_SERVICE_PME | PCIE_PORT_SERVICE_HP |
		    PCIE_PORT_SERVICE_BWCTRL)) {
		pcie_irq = pci_irq_vector(dev, pme);
		irqs[PCIE_PORT_SERVICE_PME_SHIFT] = pcie_irq;
		irqs[PCIE_PORT_SERVICE_HP_SHIFT] = pcie_irq;
		irqs[PCIE_PORT_SERVICE_BWCTRL_SHIFT] = pcie_irq;
	}
```

PME, hotplug and bandwidth notification get the same vector, the one at index `pme`, a local of [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113). [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) fills that local with the Interrupt Message Number of the PCI Express Capabilities register; read the stage that reads it.

```c
/* drivers/pci/pcie/portdrv.c:57 */
static int pcie_message_numbers(struct pci_dev *dev, int mask,
				u32 *pme, u32 *aer, u32 *dpc)
{
	u32 nvec = 0, pos;
	u16 reg16;
	... /* 8 lines, to :70 */
	if (mask & (PCIE_PORT_SERVICE_PME | PCIE_PORT_SERVICE_HP |
		    PCIE_PORT_SERVICE_BWCTRL)) {
		pcie_capability_read_word(dev, PCI_EXP_FLAGS, &reg16);
		*pme = FIELD_GET(PCI_EXP_FLAGS_IRQ, reg16);
		nvec = *pme + 1;
	}
```

The PME vector is the one [`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496) names, read once for the three services, so the PME handler shares its vector with the hotplug handler of [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) in either mode. One DMI quirk sets the flag too, through [`dmi_pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L806), the callback of portdrv's DMI table.

```c
/* drivers/pci/pcie/portdrv.c:806 */
static int __init dmi_pcie_pme_disable_msi(const struct dmi_system_id *d)
{
	pr_notice("%s detected: will not use MSI for PCIe PME signaling\n",
		  d->ident);
	pcie_pme_disable_msi();
	return 0;
}
```

The callback prints a notice naming the matched system and calls [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108). [`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) checks the table after the service drivers register and before the port driver registers, so the quirk acts before the first port is probed.

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

`device_initcall()` runs [`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) at boot, and with `pcie_ports=compat` the function returns `-EACCES` before anything else. The figure shows the vectors one Root Port's services get in the two modes.

```text
    The vector each service of one Root Port gets, without and with pcie_pme=nomsi
    ──────────────────────────────────────────────────────────────────────────────
    MSI or MSI-X, pcie_pme_msi_disabled false
    ┌────────────────────────┐
    │ PME                    ├────┐
    │ hotplug                ├────┼───────▶ vector of the Interrupt Message Number in PCI Express Capabilities
    │ bandwidth notification ├────┘
    │ AER                    ├────────────▶ vector of the Interrupt Message Number in AER Root Error Status
    │ DPC                    ├────────────▶ vector of the Interrupt Message Number in DPC Capability
    └────────────────────────┘


    pcie_pme=nomsi, pcie_pme_msi_disabled true
    ┌────────────────────────┐
    │ PME                    ├────┐
    │ hotplug                ├────┤
    │ bandwidth notification ├────┼───────▶ the one INTx vector of the port
    │ AER                    ├────┤
    │ DPC                    ├────┘
    └────────────────────────┘

    each service of the port is a bit of its service mask; the vector lands in irqs[] at the bit's shift,
    and portdrv hands it to the service instance as its irq
```

Either way the PME handler arrives on a vector it may share, which is why its request passes [`IRQF_SHARED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L74) and its first act is to check that its own port latched a request.

### pcie_pme_init registers the driver portdrv matches by service

Before a port can bind the PME service, the service needs a driver on portdrv's bus. That driver is [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456), a [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78) defined at the end of pme.c, filled with the service value it serves, the port types it accepts and the callbacks portdrv may call.

```c
/* drivers/pci/pcie/pme.c:456 */
static struct pcie_port_service_driver pcie_pme_driver = {
	.name		= "pcie_pme",
	.port_type	= PCIE_ANY_PORT,
	.service	= PCIE_PORT_SERVICE_PME,

	.probe		= pcie_pme_probe,
	.suspend	= pcie_pme_suspend,
	.resume		= pcie_pme_resume,
	.remove		= pcie_pme_remove,
};
```

[`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) is [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) and [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) is [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57), so binding accepts any port type and the service bit alone decides. The driver fills [`probe`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L80), [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L82), [`resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L84) and [`remove`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L81), and leaves [`resume_noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L83), [`runtime_suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L85) and [`runtime_resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L86) NULL. Runtime callbacks were added once and reverted by commit [c528f7bd362b](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=c528f7bd362b097eeeafa6fbbeccd9750b79c7ba) ("Revert "PCI/PME: Implement runtime PM callbacks""), whose message reports a network adapter that could no longer wake the system through PME. [`pcie_pme_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470) hands the driver to portdrv.

```c
/* drivers/pci/pcie/pme.c:467 */
/**
 * pcie_pme_init - Register the PCIe PME service driver.
 */
int __init pcie_pme_init(void)
{
	return pcie_port_service_register(&pcie_pme_driver);
}
```

It is `__init` and returns what [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) returns. Its prototype in portdrv.h carries a stub for a kernel without [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117).

```c
/* drivers/pci/pcie/portdrv.h:42 */
#ifdef CONFIG_PCIE_PME
int pcie_pme_init(void);
#else
static inline int pcie_pme_init(void) { return 0; }
#endif
```

Without the option the call compiles to a return of 0, and pme.o is not built. The option has no prompt; [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) follows the port bus and PM options.

```c
/* drivers/pci/pcie/Kconfig:117 */
config PCIE_PME
	def_bool y
	depends on PCIEPORTBUS && PM
```

With [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) and [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) set, as they are on x86-64 where [`CONFIG_SUSPEND`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L2) turns on [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140), which selects PM, the option is y and the Makefile builds the file.

```c
/* drivers/pci/pcie/Makefile:13 */
obj-$(CONFIG_PCIE_PME)		+= pme.o
```

portdrv calls [`pcie_pme_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470) from [`pcie_init_services()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L830), after the AER service and before DPC, bandwidth control and hotplug.

```c
/* drivers/pci/pcie/portdrv.c:830 */
static void __init pcie_init_services(void)
{
	pcie_aer_init();
	pcie_pme_init();
	pcie_dpc_init();
	pcie_bwctrl_init();
	pcie_hp_init();
}
```

[`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) runs this before it registers the port driver, so the PME driver is on the bus when the first port's probe creates its service instances. [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) is the step that puts the driver on portdrv's bus.

```c
/* drivers/pci/pcie/portdrv.c:582 */
/**
 * pcie_port_service_register - register PCI Express port service driver
 * @new: PCI Express port service driver to register
 */
int pcie_port_service_register(struct pcie_port_service_driver *new)
{
	if (pcie_ports_disabled)
		return -ENODEV;

	new->driver.name = new->name;
	new->driver.bus = &pcie_port_bus_type;

	return driver_register(&new->driver);
}
```

The embedded [`driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L93) joins [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) under the name `pcie_pme`, and [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) refuses a registration with `-ENODEV` when `pcie_ports=compat` was given. After registration the PME driver waits on the bus for a service instance whose service value matches.

### portdrv binds a PME service instance to the PME driver

portdrv splits a port into service instances so that each service binds a driver of its own. The instance is a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), which is portdrv's service instance and no PCIe device: one is created for each bit of the port's service mask, and the PME callbacks receive it as their argument. The struct and its accessors are in portdrv.h, read here for what the PME callbacks reach through it.

```c
/* drivers/pci/pcie/portdrv.h:56 */
/* Port Type */
#define PCIE_ANY_PORT			(~0)

struct pcie_device {
	int		irq;	    /* Service IRQ/MSI/MSI-X Vector */
	struct pci_dev *port;	    /* Root/Upstream/Downstream Port */
	u32		service;    /* Port service this device represents */
	void		*priv_data; /* Service Private Data */
	struct device	device;     /* Generic Device Interface */
};
#define to_pcie_device(d) container_of(d, struct pcie_device, device)

static inline void set_service_data(struct pcie_device *dev, void *data)
{
	dev->priv_data = data;
}

static inline void *get_service_data(struct pcie_device *dev)
{
	return dev->priv_data;
}
```

[`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) is the vector portdrv chose for the service, [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) is the Root Port or RCEC, and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) is the service bit. [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) is the slot that [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) fills and [`get_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73) reads, and the PME code keeps its state there. [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the instance's own [`struct device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L703) on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575), whose parent is the port, and [`to_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) recovers the instance from it; [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) is the all-ones port type a driver gives to accept any port. The driver side is [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78), read for the slots the PME driver fills and the two values that matching compares.

```c
/* drivers/pci/pcie/portdrv.h:78 */
struct pcie_port_service_driver {
	const char *name;
	int (*probe)(struct pcie_device *dev);
	void (*remove)(struct pcie_device *dev);
	int (*suspend)(struct pcie_device *dev);
	int (*resume_noirq)(struct pcie_device *dev);
	int (*resume)(struct pcie_device *dev);
	int (*runtime_suspend)(struct pcie_device *dev);
	int (*runtime_resume)(struct pcie_device *dev);

	int (*slot_reset)(struct pcie_device *dev);

	int port_type;  /* Type of the port this driver can handle */
	u32 service;    /* Port service this device represents */

	struct device_driver driver;
};
#define to_service_driver(d) \
	container_of(d, struct pcie_port_service_driver, driver)
```

[`name`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L79) becomes the driver's name on the bus, and the callback slots run at probe, removal, system sleep, runtime PM and slot reset. [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) are the values matching compares, and [`driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L93) is the embedded [`struct device_driver`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/driver.h#L100) that [`to_service_driver()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L95) turns back into the service driver. Matching is [`pcie_port_bus_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511), the match callback of [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575).

```c
/* drivers/pci/pcie/portdrv.c:511 */
static int pcie_port_bus_match(struct device *dev, const struct device_driver *drv)
{
	struct pcie_device *pciedev = to_pcie_device(dev);
	const struct pcie_port_service_driver *driver = to_service_driver(drv);

	if (driver->service != pciedev->service)
		return 0;

	if (driver->port_type != PCIE_ANY_PORT &&
	    driver->port_type != pci_pcie_type(pciedev->port))
		return 0;

	return 1;
}
```

A PME instance matches [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456) because both service values are [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16), and [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) skips the port-type test, so the PME probe repeats the type check itself. The bus's probe callback then calls the driver's probe and takes a reference when it succeeds.

```c
/* drivers/pci/pcie/portdrv.c:526 */
/**
 * pcie_port_bus_probe - probe driver for given PCI Express port service
 * @dev: PCI Express port service device to probe against
 *
 * If PCI Express port service driver is registered with
 * pcie_port_service_register(), this function will be called by the driver core
 * whenever match is found between the driver and a port service device.
 */
static int pcie_port_bus_probe(struct device *dev)
{
	struct pcie_device *pciedev;
	struct pcie_port_service_driver *driver;
	int status;

	driver = to_service_driver(dev->driver);
	if (!driver || !driver->probe)
		return -ENODEV;

	pciedev = to_pcie_device(dev);
	status = driver->probe(pciedev);
	if (status)
		return status;

	get_device(dev);
	return 0;
}
```

[`pcie_port_bus_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534) passes the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) to [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) and holds a reference on the instance's device while the driver is bound, which the bus's remove callback drops. The figure shows the links one bound instance holds.

```text
    One PME service instance and the objects it links
    ─────────────────────────────────────────────────
    struct pci_dev, the Root Port           struct pcie_device, portdrv's service instance
    ┌────────────────────────────┐          ┌────────────────────────────────────────────────────────────┐
    │ dev, its struct device     │◀─────────┼─ device.parent                                             │
    │ Root Control, Root Status  │◀─────────┼─ port                                                      │
    └────────────────────────────┘          │  irq            the PME vector of the port                 │
                                            │  service        PCIE_PORT_SERVICE_PME                      │
                                            │  device.driver ───────────────────────────┐                │
                                            │  priv_data ─┐                             │                │
                                            └─────────────┼─────────────────────────────┼────────────────┘
                                                          │                    ▲        │
                                                          │                    │        │
                                                          ▼                    │        ▼
                                        ┌────────────────────────────────────┐ │ ┌──────────────────────────────────┐
                                        │ lock     spinlock_t                │ │ │ driver    struct device_driver   │
                                        │ srv ───────────────────────────────┼─┘ │ name      "pcie_pme"             │
                                        │ work     the PME work item         │   │ service   PCIE_PORT_SERVICE_PME  │
                                        │ noirq    keeps PMEIE clear         │   │ port_type PCIE_ANY_PORT          │
                                        └────────────────────────────────────┘   │ probe suspend resume remove      │
                                        struct pcie_pme_service_data             └──────────────────────────────────┘
                                                                                 pcie_pme_driver, its service driver

    portdrv binds the instance to pcie_pme_driver when the two service values are equal and the driver
    accepts any port type; the driver's probe then stores the service data in priv_data
```

So far, a Root Port or RCEC with native PME control has a service instance whose [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) is [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16), a vector that the hotplug and bandwidth services can share, and a bound [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456) whose probe is about to run.

### Root Control gates the interrupt and a write clears Root Status

Two registers of the port's PCI Express Capability carry the PME mechanism. Root Status, [`PCI_EXP_RTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L653), latches a request and its requester's ID, and the PME Interrupt Enable bit of Root Control, [`PCI_EXP_RTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L643), decides whether a latched request interrupts. pci_regs.h names their offsets and fields.

```c
/* include/uapi/linux/pci_regs.h:643 */
#define PCI_EXP_RTCTL		0x1c	/* Root Control */
#define  PCI_EXP_RTCTL_SECEE	0x0001	/* System Error on Correctable Error */
#define  PCI_EXP_RTCTL_SENFEE	0x0002	/* System Error on Non-Fatal Error */
#define  PCI_EXP_RTCTL_SEFEE	0x0004	/* System Error on Fatal Error */
#define  PCI_EXP_RTCTL_PMEIE	0x0008	/* PME Interrupt Enable */
#define  PCI_EXP_RTCTL_RRS_SVE	0x0010	/* Config RRS Software Visibility Enable */
#define  PCI_EXP_RTCTL_CRSSVE PCI_EXP_RTCTL_RRS_SVE /* compatibility */
#define PCI_EXP_RTCAP		0x1e	/* Root Capabilities */
#define  PCI_EXP_RTCAP_RRS_SV	0x0001	/* Config RRS Software Visibility */
#define  PCI_EXP_RTCAP_CRSVIS PCI_EXP_RTCAP_RRS_SV /* compatibility */
#define PCI_EXP_RTSTA		0x20	/* Root Status */
#define  PCI_EXP_RTSTA_PME_RQ_ID 0x0000ffff /* PME Requester ID */
#define  PCI_EXP_RTSTA_PME	0x00010000 /* PME status */
#define  PCI_EXP_RTSTA_PENDING	0x00020000 /* PME pending */
```

[`PCI_EXP_RTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L643) and [`PCI_EXP_RTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L653) are offsets in the capability, 0x1c and 0x20. [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) is bit 3 of Root Control, and in Root Status [`PCI_EXP_RTSTA_PME_RQ_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L654) covers bits 15:0, [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655) is bit 16 and [`PCI_EXP_RTSTA_PENDING`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L656) bit 17. The other Root Control bits are the AER system-error enables and RRS Software Visibility, which pme.c does not touch. The figure shows how the two registers combine on the port.

```text
    Root Status latches the request and Root Control decides whether it interrupts
    ──────────────────────────────────────────────────────────────────────────────
                        ┌────────────────────────────────┐
    PME Message ───────▶│ Root Status, PCI_EXP_RTSTA     │
    from the            │ PME (16)          1            ├────┐
    requester           │ PME_RQ_ID (15:0)  requester    │    │      ┌────────────────────────────┐
                        └────────────────────────────────┘    │ both │ interrupt on the port's    │
                                                              ├─────▶│ PME vector, srv->irq       │
                        ┌────────────────────────────────┐    │      │ shared with hotplug        │
                        │ Root Control, PCI_EXP_RTCTL    │    │      └────────────────────────────┘
                        │ PMEIE (3)         1            ├────┘
                        └────────────────────────────────┘
```

A latched request interrupts while [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) is set, so the PME code masks the port by clearing that bit and leaves the latch to Root Status. [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) writes the bit, and within drivers/pci/pcie/ it is the one function that does; it sets or clears the bit through the capability accessors.

```c
/* drivers/pci/pcie/pme.c:49 */
/**
 * pcie_pme_interrupt_enable - Enable/disable PCIe PME interrupt generation.
 * @dev: PCIe root port or event collector.
 * @enable: Enable or disable the interrupt.
 */
void pcie_pme_interrupt_enable(struct pci_dev *dev, bool enable)
{
	if (enable)
		pcie_capability_set_word(dev, PCI_EXP_RTCTL,
					 PCI_EXP_RTCTL_PMEIE);
	else
		pcie_capability_clear_word(dev, PCI_EXP_RTCTL,
					   PCI_EXP_RTCTL_PMEIE);
}
```

The function changes [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) alone, because both accessors read the register, change the given bits and write it back. They are wrappers of [`pcie_capability_clear_and_set_word()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1371), which sends a few offsets to a locked variant.

```c
/* include/linux/pci.h:1359 */
/**
 * pcie_capability_clear_and_set_word - RMW accessor for PCI Express Capability Registers
 * @dev:	PCI device structure of the PCI Express device
 * @pos:	PCI Express Capability Register
 * @clear:	Clear bitmask
 * @set:	Set bitmask
 *
 * Perform a Read-Modify-Write (RMW) operation using @clear and @set
 * bitmasks on PCI Express Capability Register at @pos. Certain PCI Express
 * Capability Registers are accessed concurrently in RMW fashion, hence
 * require locking which is handled transparently to the caller.
 */
static inline int pcie_capability_clear_and_set_word(struct pci_dev *dev,
						     int pos,
						     u16 clear, u16 set)
{
	switch (pos) {
	case PCI_EXP_LNKCTL:
	case PCI_EXP_LNKCTL2:
	case PCI_EXP_RTCTL:
		return pcie_capability_clear_and_set_word_locked(dev, pos,
								 clear, set);
	default:
		return pcie_capability_clear_and_set_word_unlocked(dev, pos,
								   clear, set);
	}
}

static inline int pcie_capability_set_word(struct pci_dev *dev, int pos,
					   u16 set)
{
	return pcie_capability_clear_and_set_word(dev, pos, 0, set);
}
```

[`PCI_EXP_RTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L643) is one of the offsets the switch sends to [`pcie_capability_clear_and_set_word_locked()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L530). [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) calls [`pcie_capability_set_word()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1387) to enable, and [`pcie_capability_clear_word()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1399) to disable, which passes the bits as the clear mask.

```c
/* include/linux/pci.h:1399 */
static inline int pcie_capability_clear_word(struct pci_dev *dev, int pos,
					     u16 clear)
{
	return pcie_capability_clear_and_set_word(dev, pos, clear, 0);
}
```

Both reach the locked variant for Root Control, which wraps the plain read-modify-write in the port's [`pcie_cap_lock`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L516).

```c
/* drivers/pci/access.c:514 */
int pcie_capability_clear_and_set_word_unlocked(struct pci_dev *dev, int pos,
						u16 clear, u16 set)
{
	int ret;
	u16 val;

	ret = pcie_capability_read_word(dev, pos, &val);
	if (ret)
		return ret;

	val &= ~clear;
	val |= set;
	return pcie_capability_write_word(dev, pos, val);
}
EXPORT_SYMBOL(pcie_capability_clear_and_set_word_unlocked);

int pcie_capability_clear_and_set_word_locked(struct pci_dev *dev, int pos,
					      u16 clear, u16 set)
{
	unsigned long flags;
	int ret;

	spin_lock_irqsave(&dev->pcie_cap_lock, flags);
	ret = pcie_capability_clear_and_set_word_unlocked(dev, pos, clear, set);
	spin_unlock_irqrestore(&dev->pcie_cap_lock, flags);

	return ret;
}
EXPORT_SYMBOL(pcie_capability_clear_and_set_word_locked);
```

The lock keeps a PME enable and an AER enable written at the same time from losing each other's bit. commit [5e70d0acf082](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=5e70d0acf0825f439079736080350371f8d6699a) ("PCI: Add locking to RMW PCI Express Capability Register accessors") added it and names Root Control, written by AER and PME, among the registers that need it. Clearing a latched request is a plain write. [`pcie_clear_root_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2252) writes [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655) as the whole dword.

```c
/* drivers/pci/pci.c:2248 */
/**
 * pcie_clear_root_pme_status - Clear root port PME interrupt status.
 * @dev: PCIe root port or event collector.
 */
void pcie_clear_root_pme_status(struct pci_dev *dev)
{
	pcie_capability_write_dword(dev, PCI_EXP_RTSTA, PCI_EXP_RTSTA_PME);
}
```

PME Status is a write-one-to-clear bit, and the rest of Root Status is read-only or RsvdZ, so writing the bit alone clears it and changes nothing else. commit [699722468a0f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=699722468a0fca8b1b9ce1ffe2532171ddcaff95) ("PCI/PME: Replace RMW of Root Status register with direct write") replaced an earlier read-modify-write with this write on that reasoning. The write goes through [`pcie_capability_write_dword()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L502), which checks that the port has the register.

```c
/* drivers/pci/access.c:502 */
int pcie_capability_write_dword(struct pci_dev *dev, int pos, u32 val)
{
	if (pos & 3)
		return PCIBIOS_BAD_REGISTER_NUMBER;

	if (!pcie_capability_reg_implemented(dev, pos))
		return 0;

	return pci_write_config_dword(dev, pci_pcie_cap(dev) + pos, val);
}
EXPORT_SYMBOL(pcie_capability_write_dword);
```

On a port without Root Status the accessor returns 0 without a configuration write. The figure follows one Root Status value through the clearing write.

```text
    Root Status before and after the write that clears PME Status
    ─────────────────────────────────────────────────────────────
                  31:18          PENDING (17)   PME (16)   PME_RQ_ID (15:0)
                  ┌─────────────┬──────────────┬──────────┬───────────────────┐
    read          │ RsvdZ 0     │ 0            │ 1        │ requester         │ one PME latched, none pending
                  └─────────────┴──────────────┴──────────┴───────────────────┘
                                                   ▼ write the dword PCI_EXP_RTSTA_PME
                  ┌─────────────┬──────────────┬──────────┬───────────────────┐
    written       │ 0           │ 0            │ 1        │ 0                 │ zeros in RsvdZ and read-only bits
                  └─────────────┴──────────────┴──────────┴───────────────────┘
                                                   ▼ RW1C: a 1 in bit 16 clears it
                  ┌─────────────┬──────────────┬──────────┬───────────────────┐
    after         │ RsvdZ 0     │ 0            │ 0        │ unused, PME 0     │ the port can latch again
                  └─────────────┴──────────────┴──────────┴───────────────────┘

    with PENDING 1 at the read, the comment in the work item says the status is set again
    for the next request; the write changes bit 16 alone
```

The service now has a gate it sets and clears by name and a latch it empties by writing one bit, and its probe uses both before it installs the handler.

### Probe installs the handler before it unmasks the port

A bound instance needs state that the interrupt handler, the work item and the sleep callbacks share. That state is a [`struct pcie_pme_service_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L42), one per service instance, which probe allocates and removal frees; the struct holds a lock, a pointer back to the instance, the work item and one flag.

```c
/* drivers/pci/pcie/pme.c:42 */
struct pcie_pme_service_data {
	spinlock_t lock;
	struct pcie_device *srv;
	struct work_struct work;
	bool noirq; /* If set, keep the PME interrupt disabled. */
};
```

[`lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L43) serializes the handler, the work item and the sleep callbacks around Root Status and Root Control. [`srv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L44) leads back to the service instance and through its [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) to the port, and [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) is the deferred half of the interrupt handling. [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) tells the work item to leave the PME interrupt disabled, as its comment says. [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) builds this state and arms the port in an order that keeps a stale request from interrupting before the handler exists.

```c
/* drivers/pci/pcie/pme.c:322 */
/**
 * pcie_pme_probe - Initialize PCIe PME service for given root port.
 * @srv: PCIe service to initialize.
 */
static int pcie_pme_probe(struct pcie_device *srv)
{
	struct pci_dev *port = srv->port;
	struct pcie_pme_service_data *data;
	int type = pci_pcie_type(port);
	int ret;

	/* Limit to Root Ports or Root Complex Event Collectors */
	if (type != PCI_EXP_TYPE_RC_EC &&
	    type != PCI_EXP_TYPE_ROOT_PORT)
		return -ENODEV;

	data = kzalloc_obj(*data);
	if (!data)
		return -ENOMEM;

	spin_lock_init(&data->lock);
	INIT_WORK(&data->work, pcie_pme_work_fn);
	data->srv = srv;
	set_service_data(srv, data);

	pcie_pme_interrupt_enable(port, false);
	pcie_clear_root_pme_status(port);

	ret = request_irq(srv->irq, pcie_pme_irq, IRQF_SHARED, "PCIe PME", srv);
	if (ret) {
		kfree(data);
		return ret;
	}

	pci_info(port, "Signaling with IRQ %d\n", srv->irq);

	pcie_pme_mark_devices(port);
	pcie_pme_interrupt_enable(port, true);
	return 0;
}
```

Probe refuses a port that is no Root Port or RCEC with `-ENODEV`, since [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) let binding accept any type. It then zeroes the new state, so [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) starts false, binds [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) to [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214), and stores the instance in [`srv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L44) and the state in [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63). The mask through [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) and the clear through [`pcie_clear_root_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2252) come before [`request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L173), so a request latched before boot cannot interrupt a vector with no PME handler.

[`request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L173) installs [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) on [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) with [`IRQF_SHARED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L74), the name `PCIe PME` and the instance as its cookie. A failure frees the state and leaves the port masked, and the bus's probe callback then leaves the driver unbound. On success, probe prints the vector, marks the devices below the port and sets [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) as its last write. The strip follows one service data object from this probe to its removal, through the writes of the functions this page shows.

```text
    One struct pcie_pme_service_data from probe to removal
    ──────────────────────────────────────────────────────
    fields: the object itself, srv, work and noirq of struct pcie_pme_service_data

    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event           probe             PME irq     work ran    suspend, no wakeup    resume      remove
                    ▼                 ▼           ▼           ▼                     ▼           ▼
                    ┌───────────────────────────────────────────────────────────────────────────┬───────────┐
    object          │① zeroed, filled                                                           │⑨ freed    │
                    └───────────────────────────────────────────────────────────────────────────┴───────────┘
                    ┌───────────────────────────────────────────────────────────────────────────┬───────────┐
    srv             │③ the service instance                                                     │⑨ freed    │
                    └───────────────────────────────────────────────────────────────────────────┴───────────┘
                    ┌─────────────────┬───────────┬─────────────────────────────────────────────┬───────────┐
    work            │② idle           │⑤ pending  │  idle                                       │⑧ idle ⑨   │
                    └─────────────────┴───────────┴─────────────────────────────────────────────┴───────────┘
                    ┌─────────────────────────────────────────┬─────────────────────┬───────────┬───────────┐
    noirq           │① false                                  │⑥ true               │⑦ false    │⑥ true ⑨   │
                    └─────────────────────────────────────────┴─────────────────────┴───────────┴───────────┘
                    ┌───────────┬───────────┐
    if request_irq  │① zeroed   │④ freed    │
    fails           └───────────┴───────────┘

    ① pcie_pme_probe            pme.c:338  allocates the object zeroed through kzalloc_obj, so noirq starts false
    ② pcie_pme_probe            :343       binds work to the PME work function through INIT_WORK
    ③ pcie_pme_probe            :344       stores the service instance in srv
    ④ pcie_pme_probe            :352       frees the object with kfree when request_irq fails
    ⑤ pcie_pme_irq              :288       makes work pending on the system workqueue through schedule_work
    ⑥ pcie_pme_disable_interrupt :384      sets noirq under the lock, on suspend and on removal
    ⑦ pcie_pme_resume           :433       clears noirq after unmasking the port
    ⑧ pcie_pme_remove           :452       waits through cancel_work_sync until work is idle
    ⑨ pcie_pme_remove           :453       frees the object with kfree
```

① [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) allocates the object zeroed through `kzalloc_obj()`, so [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) starts false. ② `pcie_pme_probe()` binds [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) to the PME work function through `INIT_WORK()`. ③ `pcie_pme_probe()` stores the service instance in [`srv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L44). ④ `pcie_pme_probe()` frees the object with `kfree()` when [`request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L173) fails. ⑤ [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) makes [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) pending on the system workqueue through [`schedule_work()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/workqueue.h#L758). ⑥ [`pcie_pme_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L378) sets [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) under the lock, on suspend and on removal. ⑦ [`pcie_pme_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L423) clears [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) after unmasking the port. ⑧ [`pcie_pme_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L446) waits through `cancel_work_sync()` until [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) is idle. ⑨ `pcie_pme_remove()` frees the object with `kfree()`.

The workqueue core in kernel/workqueue.c clears the pending state of [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) when a worker starts the item, which the strip draws as the return to idle without a mark, because that file is outside the PCI code this page reads. [`lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L43) is initialized by `spin_lock_init()` in probe and afterwards taken and released by its holders, so the strip leaves it out. From ③ on, the handler and the work item reach the port through [`srv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L44), and after probe's last line the port interrupts on its PME vector.

### Probe marks the port and the devices below wakeup-capable

The PM core treats a device as able to wake the system when [`can_wakeup`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L668) of its [`struct device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L703) is set, and the sysfs wakeup file appears for a device with the flag. Probe sets the flag on the devices whose PMEs this port reports, beyond those that enumeration marked already. [`pci_pm_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3161) does that marking for a device whose PM capability lists PME support; read the stage that also sets the poll flag a native PME later clears.

```c
/* drivers/pci/pci.c:3161 */
void pci_pm_init(struct pci_dev *dev)
{
	int pm;
	u16 pmc;
	... /* 40 lines, to :3205 */
	pmc &= PCI_PM_CAP_PME_MASK;
	if (pmc) {
		pci_info(dev, "PME# supported from%s%s%s%s%s\n",
			 (pmc & PCI_PM_CAP_PME_D0) ? " D0" : "",
			 (pmc & PCI_PM_CAP_PME_D1) ? " D1" : "",
			 (pmc & PCI_PM_CAP_PME_D2) ? " D2" : "",
			 (pmc & PCI_PM_CAP_PME_D3hot) ? " D3hot" : "",
			 (pmc & PCI_PM_CAP_PME_D3cold) ? " D3cold" : "");
		dev->pme_support = FIELD_GET(PCI_PM_CAP_PME_MASK, pmc);
		dev->pme_poll = true;
		/*
		 * Make device's PM flags reflect the wake-up capability, but
		 * let the user space enable it to wake up the system as needed.
		 */
		device_set_wakeup_capable(&dev->dev, true);
		/* Disable the PME# generation functionality */
		pci_pme_active(dev, false);
	}
```

A device with PME support gets [`pme_support`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L408), [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) set and the wakeup capability during enumeration, and [`pci_pme_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2435) leaves its PME generation off. The PME probe extends the capability to the devices that report through the port, with [`pcie_pme_can_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L298) as the callback for one device.

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
```

The callback ignores its second argument and returns 0, so a bus walk that calls it does not stop early. It hands the device's embedded [`struct device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L703) to [`device_set_wakeup_capable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/wakeup.c#L471), the PM core's setter of the flag.

```c
/* drivers/base/power/wakeup.c:471 */
void device_set_wakeup_capable(struct device *dev, bool capable)
{
	if (!!dev->power.can_wakeup == !!capable)
		return;

	dev->power.can_wakeup = capable;
	if (device_is_registered(dev) && !list_empty(&dev->power.entry)) {
		if (capable) {
			int ret = wakeup_sysfs_add(dev);

			if (ret)
				dev_info(dev, "Wakeup sysfs attributes not added\n");
		} else {
			wakeup_sysfs_remove(dev);
		}
	}
}
```

The setter returns at once when the flag already has the requested value, so a device that enumeration marked costs one test. For a registered device it adds the wakeup attributes to sysfs. [`pcie_pme_mark_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L312) chooses the set of devices by port type.

```c
/* drivers/pci/pcie/pme.c:304 */
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

The port is marked first. An RCEC then marks the RCiEPs associated with it through [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134), and a Root Port marks the devices on and under its [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus through [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461). [`pcie_walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L134) belongs to the RCEC code and visits the RCiEPs that the RCEC's [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) describes.

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

An RCEC without [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374) has no associated RCiEPs, and the call marks nothing beyond the RCEC. [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) is the PCI core's recursive bus walk, run under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading.

```c
/* drivers/pci/bus.c:461 */
void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *), void *userdata)
{
	down_read(&pci_bus_sem);
	__pci_walk_bus(top, cb, userdata);
	up_read(&pci_bus_sem);
}
```

The walk takes the semaphore itself, which is why [`pcie_pme_mark_devices()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L312) calls it without holding [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17). The figure shows the two shapes of the marked set.

```text
    The devices a PME service probe marks wakeup-capable
    ────────────────────────────────────────────────────
    ┌──────────────────────┐                                      ┌────────────────────┐    ┌────────────────────┐
    │ Root Port         ●  │                                      │ RCEC             ● ├╌╌╌▶│ RCiEP            ● │
    └───────┬──────────────┘                                      └────────────────────┘    │ RCiEP            ● │
            │ subordinate                                                                   └────────────────────┘
            │                                                                           the RCiEPs rcec_ea covers
    ╔═══════╧════════════════════════════════════════════╗
    ║ the bus below the port and every bus under it      ║
    ║                                                    ║
    ║ ┌──────────────────┐    ┌──────────────────────┐   ║
    ║ │ Endpoint       ● │    │ Switch Port        ● │   ║        ┌────────────────────────┐
    ║ └──────────────────┘    └───────────┬──────────┘   ║        │ RCiEP outside rcec_ea  │
    ║                                     │              ║        └────────────────────────┘
    ║                         ┌───────────┴──────────┐   ║          unmarked by this probe
    ║                         │ device below it    ● │   ║
    ║                         └──────────────────────┘   ║
    ╚════════════════════════════════════════════════════╝

    ● = the device's power.can_wakeup set by the PME service's probe
    ╔═╗ = the subtree that the walk from the Root Port's subordinate bus reaches
    ╌╌▶ = the RCiEPs an RCEC's rcec_ea association covers, the only devices marked beside an RCEC
```

With the devices marked and [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) set at the end of probe, the port is armed, and a PME Message from below now raises the PME interrupt.

### The hardirq handler claims a latched PME and masks the port

The PME vector is shared, so the handler first decides whether its port latched a request, and the search for the requester takes a semaphore that hardirq context cannot. [`pcie_pme_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L266) therefore claims the interrupt, masks the port and hands the rest to the work item. It receives the service instance as its cookie; read it for the test that claims the interrupt and for the hand-off.

```c
/* drivers/pci/pcie/pme.c:261 */
/**
 * pcie_pme_irq - Interrupt handler for PCIe root port PME interrupt.
 * @irq: Interrupt vector.
 * @context: Interrupt context pointer.
 */
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

	pcie_pme_interrupt_enable(port, false);
	spin_unlock_irqrestore(&data->lock, flags);

	/* We don't use pm_wq, because it's freezable. */
	schedule_work(&data->work);

	return IRQ_HANDLED;
}
```

The handler reads [`PCI_EXP_RTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L653) under [`lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L43) with interrupts saved. A read that [`PCI_POSSIBLE_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L175) flags, all ones from a port that does not answer, returns `IRQ_NONE`, and so does a clear [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655), which leaves the shared vector to the hotplug or bandwidth handler. commit [3ad3f8ce5091](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=3ad3f8ce50914288731a3018b27ee44ab803e170) ("PCI/PME: Handle invalid data when reading Root Status") added the all-ones test after such a read was taken for a latched request and looped the work item forever.

A latched request clears [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) before the lock is dropped, and [`schedule_work()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/workqueue.h#L758) queues [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45). The comment says the item avoids [`pm_wq`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/main.c#L1123) because that workqueue is freezable. At v7.2 the reason no longer holds, since [`pm_start_workqueues()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/main.c#L1126) allocates [`pm_wq`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/main.c#L1123) without `WQ_FREEZABLE`.

```c
/* kernel/power/main.c:1126 */
static int __init pm_start_workqueues(void)
{
	pm_wq = alloc_workqueue("pm", WQ_UNBOUND, 0);
	if (!pm_wq)
		return -ENOMEM;
```

commit [4fb352df14de](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=4fb352df14de4b5277f38a9874f7c19cf641ae4d) ("PM: sleep: Do not flag runtime PM workqueue as freezable") dropped the flag, and the PME code still queues on the system workqueue. [`schedule_work()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/workqueue.h#L758) is the helper that names that workqueue, [`system_percpu_wq`](https://elixir.bootlin.com/linux/v7.2/source/kernel/workqueue.c#L526).

```c
/* include/linux/workqueue.h:758 */
static inline bool schedule_work(struct work_struct *work)
{
	return queue_work(system_percpu_wq, work);
}
```

The item runs later in a kworker, in process context, where the search may sleep on [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17). The figure lays the handler's lock span and the masked interval on one time axis.

```text
    One PME interrupt: the handler's lock span and the interval PMEIE stays clear
    ─────────────────────────────────────────────────────────────────────────────
    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶

    hardirq         ├─────────────────────────┤   work queued, IRQ_HANDLED
                    data->lock, irqs saved            ╎
                    RTSTA read, PME 1, PMEIE ← 0      ╎ system_percpu_wq
                                                      ▼

    work item                                         ├───────────────┤                     ├─────────┤
                                                      lock: read, clear   unlocked: search  lock: drain,
                                                                                            PMEIE ← 1

    PMEIE           1             ├──────────────────────────────────────────────────────────────────┤  1
                                                                0: the port raises no PME interrupt
    Root Status     PME 1                               PME 0 after the clear, or 1 again for a pending request
```

Between the handler and the end of the work item [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) stays clear, so the port raises no second PME interrupt while the work item reads and clears Root Status.

### The work item drains Root Status before it unmasks the port

The work item owns Root Status while the port is masked. It clears and hands on latched requests one at a time, waits while the port reports another request pending, and unmasks the port when nothing is left, unless [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) asks it to keep the interrupt disabled. [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214) reads in three pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | pme.c:214-222 | finds its state and port and takes the lock |
| ❷ | pme.c:223-245 | leaves on noirq or a failed read, or clears and hands on a latched request |
| ❸ | pme.c:246-259 | waits on a pending request, then unmasks the port unless noirq is set |

❶ [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214) first recovers its state from the work item and takes the lock.

```c
/* drivers/pci/pcie/pme.c:210 */
/**
 * pcie_pme_work_fn - Work handler for PCIe PME interrupt.
 * @work: Work structure giving access to service data.
 */
static void pcie_pme_work_fn(struct work_struct *work)
{
	struct pcie_pme_service_data *data =
			container_of(work, struct pcie_pme_service_data, work);
	struct pci_dev *port = data->srv->port;
	u32 rtsta;

	spin_lock_irq(&data->lock);

```

`container_of()` turns the [`work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L45) pointer back into the [`struct pcie_pme_service_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L42), and [`srv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L44) leads to the port. The lock is taken with local interrupts disabled, so the PME handler cannot run on this CPU while the item holds it. ❷ [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214) then loops over Root Status.

```c
/* drivers/pci/pcie/pme.c:223 */
	for (;;) {
		if (data->noirq)
			break;

		pcie_capability_read_dword(port, PCI_EXP_RTSTA, &rtsta);
		if (PCI_POSSIBLE_ERROR(rtsta))
			break;

		if (rtsta & PCI_EXP_RTSTA_PME) {
			/*
			 * Clear PME status of the port.  If there are other
			 * pending PMEs, the status will be set again.
			 */
			pcie_clear_root_pme_status(port);

			spin_unlock_irq(&data->lock);
			pcie_pme_handle_request(port,
				    FIELD_GET(PCI_EXP_RTSTA_PME_RQ_ID, rtsta));
			spin_lock_irq(&data->lock);

			continue;
		}

```

A set [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) ends the loop at once, and so does an all-ones read. A set [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655) is cleared by [`pcie_clear_root_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2252) before the request is handed on, and the comment says the port sets the status again for a further pending request. The Requester ID goes to [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) with the lock dropped, because the search takes [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) and may sleep, and the loop then reads the register again. ❸ [`pcie_pme_work_fn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L214) ends the loop when no request is pending and unmasks the port.

```c
/* drivers/pci/pcie/pme.c:246 */
		/* No need to loop if there are no more PMEs pending. */
		if (!(rtsta & PCI_EXP_RTSTA_PENDING))
			break;

		spin_unlock_irq(&data->lock);
		cpu_relax();
		spin_lock_irq(&data->lock);
	}

	if (!data->noirq)
		pcie_pme_interrupt_enable(port, true);

	spin_unlock_irq(&data->lock);
}
```

With [`PCI_EXP_RTSTA_PME`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L655) clear, a clear [`PCI_EXP_RTSTA_PENDING`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L656) ends the loop. A set one makes the item drop the lock, call `cpu_relax()` and read again, waiting for the port to latch the pending request. After the loop [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) is set again unless [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) is true, under the lock that suspend and removal also take. The figure follows Root Status through one run over two requests.

```text
    One run of the work item over two requests the port latched back to back
    ────────────────────────────────────────────────────────────────────────
    time ────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    Root Status     read 1                read 2                read 3                read 4
    read by         ▼                     ▼                     ▼                     ▼
                    ┌─────────────────────┬─────────────────────┬─────────────────────┬─────────────────────┐
    PME (16)        │ 1                   │ 0                   │ 1                   │ 0                   │
                    └─────────────────────┴─────────────────────┴─────────────────────┴─────────────────────┘
                    ┌─────────────────────┬─────────────────────┬─────────────────────┬─────────────────────┐
    PENDING (17)    │ 1                   │ 1                   │ 0                   │ 0                   │
                    └─────────────────────┴─────────────────────┴─────────────────────┴─────────────────────┘
                    ┌─────────────────────┬─────────────────────┬─────────────────────┬─────────────────────┐
    PME_RQ_ID       │ requester A         │ unused, PME 0       │ requester B         │ unused, PME 0       │
                    └─────────────────────┴─────────────────────┴─────────────────────┴─────────────────────┘
                    ┌─────────────────────┬─────────────────────┬─────────────────────┬─────────────────────┐
    work item       │ clear, search A     │ wait, read again    │ clear, search B     │ leave, PMEIE ← 1    │
                    └─────────────────────┴─────────────────────┴─────────────────────┴─────────────────────┘

    each column is one pass of the loop; a clear lets the port load the pending request,
    and a read that finds PME 0 with PENDING 1 waits with the lock dropped before it reads again
```

So far, a latched request has been claimed by the handler, the port masked, and the request cleared and handed on by the work item, which unmasks the port once Root Status is empty and [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) is false.

### The Requester ID leads the search to the requester

[`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) turns the 16-bit Requester ID that Root Status latched into the device that sent the PME. The ID packs a bus number above a devfn, the device and function numbers of the requester, in the layout the figure draws.

```text
    The Requester ID as the source search splits it
    ───────────────────────────────────────────────
    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    RQ_ID │      bus      │   dev   │ fn  │
          │    (15:8)     │  (7:3)  │(2:0)│
          └───────────────┴─────────┴─────┘

    RQ_ID = PCI_EXP_RTSTA_PME_RQ_ID (Root Status 15:0), taken from the value the work item read
    bus = req_id >> 8, compared with the port's bus number and passed to the bus lookup
    dev, fn = devfn = req_id & 0xff; PCI_SLOT(devfn) is dev and PCI_FUNC(devfn) is fn
```

The bus number and the devfn feed the tests the search makes in turn, and the places they look at follow the topology below the port.

```text
    The requester's place below the port decides which test finds it
    ────────────────────────────────────────────────────────────────
                                  ┌────────────────────────────────────────────────┐
                                  │ Root Port                                      │
                                  │ A: RQ_ID is the port's own ID                  │
                                  └─────────┬──────────────────────────────────────┘
                                            │ bus below the port
                  ┌─────────────────────────┴─────────────────────────────┐
                  │                                                       │
    ┌─────────────┴──────────────────────┐              ┌─────────────────┴──────────────────┐
    │ Endpoint, RQ_ID = N:dev.fn         │              │ PCIe-to-PCI bridge                 │
    │ C: listed at that devfn on bus N   │              │ type PCI_EXP_TYPE_PCI_BRIDGE       │
    └────────────────────────────────────┘              └─────────────────┬──────────────────┘
                                                                          │ secondary bus M
                                                ┌─────────────────────────┴──────────────────────────┐
    A also covers a conventional                │ conventional PCI devices on bus M                  │
    device whose PME the port                   │ B: RQ_ID = M:00.0, the bridge reports for them     │
    reports with its own ID                     │ D: RQ_ID = M:dev.fn naming no listed device        │
                                                └────────────────────────────────────────────────────┘

    A to D are the tests in the order the search makes them; A, B and D end in a scan of the bus below
    the port or the bridge, and C checks the one listed device the Requester ID names
```

The function reads in three pieces, one per place it tests.

| piece | lines | stage |
|---|---|---|
| Ⓐ | pme.c:130-160 | splits the ID and tests the port itself, scanning below it when the port is not the requester |
| Ⓑ | pme.c:161-170 | finds the bus the ID names and tests for a PCIe-to-PCI bridge |
| Ⓒ | pme.c:171-208 | finds the device at the devfn, checks it, and falls back to the bridge test |

Ⓐ [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) splits the ID and tests whether the port itself is the requester.

```c
/* drivers/pci/pcie/pme.c:125 */
/**
 * pcie_pme_handle_request - Find device that generated PME and handle it.
 * @port: Root port or event collector that generated the PME interrupt.
 * @req_id: PCIe Requester ID of the device that generated the PME.
 */
static void pcie_pme_handle_request(struct pci_dev *port, u16 req_id)
{
	u8 busnr = req_id >> 8, devfn = req_id & 0xff;
	struct pci_bus *bus;
	struct pci_dev *dev;
	bool found = false;

	/* First, check if the PME is from the root port itself. */
	if (port->devfn == devfn && port->bus->number == busnr) {
		if (port->pme_poll)
			port->pme_poll = false;

		if (pci_check_pme_status(port)) {
			pm_request_resume(&port->dev);
			found = true;
		} else {
			/*
			 * Apparently, the root port generated the PME on behalf
			 * of a non-PCIe device downstream.  If this is done by
			 * a root port, the Requester ID field in its status
			 * register may contain either the root port's, or the
			 * source device's information (PCI Express Base
			 * Specification, Rev. 2.0, Section 6.1.9).
			 */
			down_read(&pci_bus_sem);
			found = pcie_pme_walk_bus(port->subordinate);
			up_read(&pci_bus_sem);
		}
		goto out;
	}

```

`busnr` and `devfn` are locals of [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130), the upper and lower bytes of `req_id`. A match with the port's own [`devfn`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L361) and bus [`number`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L718) clears the port's [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) and tests its PME Status with [`pci_check_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2265), and a set status queues the port's resume. A clear status means the port reported for a conventional PCI device below it, as the comment's citation of the 2.0 specification says, and [`pcie_pme_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L70) scans the port's [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17). Ⓑ [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) next looks up the bus with [`pci_find_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L143) and asks whether a PCIe-to-PCI bridge reported.

```c
/* drivers/pci/pcie/pme.c:161 */
	/* Second, find the bus the source device is on. */
	bus = pci_find_bus(pci_domain_nr(port->bus), busnr);
	if (!bus)
		goto out;

	/* Next, check if the PME is from a PCIe-PCI bridge. */
	found = pcie_pme_from_pci_bridge(bus, devfn);
	if (found)
		goto out;

```

The lookup uses the port's domain, so it stays in the port's hierarchy, and [`pcie_pme_from_pci_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L102) answers for a request with devfn 0 on a bridge's secondary bus. [`pci_find_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L143) searches the buses of that domain for the bus number.

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

A bus number with no [`struct pci_bus`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L702) behind it ends the search with the spurious-interrupt message. Ⓒ [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) then looks for a listed device at the devfn.

```c
/* drivers/pci/pcie/pme.c:171 */
	/* Finally, try to find the PME source on the bus. */
	down_read(&pci_bus_sem);
	list_for_each_entry(dev, &bus->devices, bus_list) {
		pci_dev_get(dev);
		if (dev->devfn == devfn) {
			found = true;
			break;
		}
		pci_dev_put(dev);
	}
	up_read(&pci_bus_sem);

	if (found) {
		/* The device is there, but we have to check its PME status. */
		found = pci_check_pme_status(dev);
		if (found) {
			if (dev->pme_poll)
				dev->pme_poll = false;

			pci_wakeup_event(dev);
			pm_request_resume(&dev->dev);
		}
		pci_dev_put(dev);
	} else if (devfn) {
		/*
		 * The device is not there, but we can still try to recover by
		 * assuming that the PME was reported by a PCIe-PCI bridge that
		 * used devfn different from zero.
		 */
		pci_info(port, "interrupt generated for non-existent device %02x:%02x.%d\n",
			 busnr, PCI_SLOT(devfn), PCI_FUNC(devfn));
		found = pcie_pme_from_pci_bridge(bus, 0);
	}

 out:
	if (!found)
		pci_info(port, "Spurious native interrupt!\n");
}
```

The scan of the bus's [`devices`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L706) list runs under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) and keeps a reference on the device it stops at. A found device has its PME Status checked, and a set status clears its [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410), reports a wakeup event through [`pci_wakeup_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L294) and queues its resume. A devfn with no listed device prints the non-existent device message at the info level and retries the bridge test with devfn 0, and a search that finds nothing prints `Spurious native interrupt!`. The search thus ends with a resume request queued for the requester, or with a message and no request.

### Bus scans find conventional PCI requesters behind bridges

A conventional PCI device signals PME on a sideband wire, and the PCIe-to-PCI bridge or Root Port above it sends the PME Message in its place, so the Requester ID does not name the device. Two helpers find such requesters by scanning a bus. [`pcie_pme_from_pci_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L102) decides whether a PCIe-to-PCI bridge reported, which its comment says it does with devfn 0 on its secondary bus.

```c
/* drivers/pci/pcie/pme.c:93 */
/**
 * pcie_pme_from_pci_bridge - Check if PCIe-PCI bridge generated a PME.
 * @bus: Secondary bus of the bridge.
 * @devfn: Device/function number to check.
 *
 * PME from PCI devices under a PCIe-PCI bridge may be converted to an in-band
 * PCIe PME message.  In such that case the bridge should use the Requester ID
 * of device/function number 0 on its secondary bus.
 */
static bool pcie_pme_from_pci_bridge(struct pci_bus *bus, u8 devfn)
{
	struct pci_dev *dev;
	bool found = false;

	if (devfn)
		return false;

	dev = pci_dev_get(bus->self);
	if (!dev)
		return false;

	if (pci_is_pcie(dev) && pci_pcie_type(dev) == PCI_EXP_TYPE_PCI_BRIDGE) {
		down_read(&pci_bus_sem);
		if (pcie_pme_walk_bus(bus))
			found = true;
		up_read(&pci_bus_sem);
	}

	pci_dev_put(dev);
	return found;
}
```

A nonzero devfn returns false at once. The bridge is the bus's [`self`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L707), held by a reference for the test, and a bridge whose type is [`PCI_EXP_TYPE_PCI_BRIDGE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L491) has its secondary bus scanned under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) by [`pcie_pme_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L70), the recursive scan of both helpers.

```c
/* drivers/pci/pcie/pme.c:64 */
/**
 * pcie_pme_walk_bus - Scan a PCI bus for devices asserting PME#.
 * @bus: PCI bus to scan.
 *
 * Scan given PCI bus and all buses under it for devices asserting PME#.
 */
static bool pcie_pme_walk_bus(struct pci_bus *bus)
{
	struct pci_dev *dev;
	bool ret = false;

	list_for_each_entry(dev, &bus->devices, bus_list) {
		/* Skip PCIe devices in case we started from a root port. */
		if (!pci_is_pcie(dev) && pci_check_pme_status(dev)) {
			if (dev->pme_poll)
				dev->pme_poll = false;

			pci_wakeup_event(dev);
			pm_request_resume(&dev->dev);
			ret = true;
		}

		if (dev->subordinate && pcie_pme_walk_bus(dev->subordinate))
			ret = true;
	}

	return ret;
}
```

The scan checks the PME Status of a device that [`pci_is_pcie()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2660) reports as conventional and skips PCIe devices, which a scan from a Root Port meets first, as the comment says. A device whose status and enable were both set gets [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) cleared, a wakeup event and a queued resume. A device with a [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus has that bus scanned in turn, and the function returns true when it queued at least one resume. The scan takes no lock, unlike [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461), and its two callers hold [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading around it. The figure shows one scan from a Root Port's subordinate bus.

```text
    The scan below a port: what it skips, what it checks, and the requests it leaves
    ────────────────────────────────────────────────────────────────────────────────
                      00.0                  01.0
                    ┌─────────────────────┬─────────────────────┐
    bus below       │ PCIe Endpoint       │ PCIe-to-PCI bridge  │
    the port        │ PME_Status 1        │ subordinate bus M   │
                    └─────────────────────┴─────────────────────┘
                      skipped: PCIe         skipped: PCIe,
                                            descends to bus M
                                                    │
                                                    │
                                                    ▼
                      00.0                  01.0                  02.0
                    ┌─────────────────────┬─────────────────────┬─────────────────────┐
    bus M           │ PCI, PME_Status 1   │ PCI, PME_Status 0   │ PCI, PME_Status 1   │
                    │ PME_En 1            │                     │ PME_En 0            │
                    └─────────────────────┴─────────────────────┴─────────────────────┘
    cursor            ▼ checked             ▼ checked             ▼ checked, bits cleared
                    ┌────────────────────┐
    left behind     │ wakeup event,      │  nothing               nothing
                    │ resume queued      │
                    └────────────────────┘

    a PCIe device is never checked, and every subordinate bus is scanned; the scan of test B starts at bus M
    the scan returns true when it left at least one request behind
```

One Requester ID can thus leave several resume requests behind, one for each conventional device whose PME Status and PME enable were both set.

### pci_check_pme_status clears the requester's PME bits

The tests of the search end in [`pci_check_pme_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2265), the PCI core's check of a device's own PM Control/Status register. It decides whether the device is a requester and clears the device's PME state in the same access, reading the register at [`pm_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L407) plus [`PCI_PM_CTRL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L262).

```c
/* drivers/pci/pci.c:2257 */
/**
 * pci_check_pme_status - Check if given device has generated PME.
 * @dev: Device to check.
 *
 * Check the PME status of the device and if set, clear it and clear PME enable
 * (if set).  Return 'true' if PME status and PME enable were both set or
 * 'false' otherwise.
 */
bool pci_check_pme_status(struct pci_dev *dev)
{
	int pmcsr_pos;
	u16 pmcsr;
	bool ret = false;

	if (!dev->pm_cap)
		return false;

	pmcsr_pos = dev->pm_cap + PCI_PM_CTRL;
	pci_read_config_word(dev, pmcsr_pos, &pmcsr);
	if (!(pmcsr & PCI_PM_CTRL_PME_STATUS))
		return false;

	/* Clear PME status. */
	pmcsr |= PCI_PM_CTRL_PME_STATUS;
	if (pmcsr & PCI_PM_CTRL_PME_ENABLE) {
		/* Disable PME to avoid interrupt flood. */
		pmcsr &= ~PCI_PM_CTRL_PME_ENABLE;
		ret = true;
	}

	pci_write_config_word(dev, pmcsr_pos, pmcsr);

	return ret;
}
```

A device without a PM capability, [`pm_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L407) zero, returns false, and a clear [`PCI_PM_CTRL_PME_STATUS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L268) returns false without a write. A set status is written back as 1, which the comment calls clearing it, and a set [`PCI_PM_CTRL_PME_ENABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L265) is cleared in the same write against an interrupt flood. The function returns true when both were set. The figure shows the three outcomes.

```text
    The requester's PM Control/Status register before and after the check
    ─────────────────────────────────────────────────────────────────────
                    read                                  written back                          returns
                ┌────────────────┬────────────┐          ┌────────────────┬────────────┐
    armed       │ PME_Status 1   │ PME_En 1   │ ───────▶ │ PME_Status 1   │ PME_En 0   │        true
                └────────────────┴────────────┘          └────────────────┴────────────┘

                ┌────────────────┬────────────┐          ┌────────────────┬────────────┐
    unarmed     │ PME_Status 1   │ PME_En 0   │ ───────▶ │ PME_Status 1   │ PME_En 0   │        false
                └────────────────┴────────────┘          └────────────────┴────────────┘

                ┌────────────────┬────────────┐
    quiet       │ PME_Status 0   │ PME_En 1   │   no write                                      false
                └────────────────┴────────────┘

    PME_Status = PCI_PM_CTRL_PME_STATUS (bit 15), written back as 1 to clear it, as the comment says
    PME_En = PCI_PM_CTRL_PME_ENABLE (bit 8), cleared in the written value against an interrupt flood
    after either write the register reads PME_Status 0 and PME_En 0; a device with no pm_cap returns false unread
```

A confirmed requester then gets two calls. [`pci_wakeup_event()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L294) reports a wakeup event with a 100 ms window.

```c
/* drivers/pci/pci.h:294 */
static inline void pci_wakeup_event(struct pci_dev *dev)
{
	/* Wait 100 ms before the system can be put into a sleep state. */
	pm_wakeup_event(&dev->dev, 100);
}
```

[`pm_wakeup_event()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_wakeup.h#L213) counts the event against the device's wakeup source, and the comment says the system waits 100 ms before it can sleep again. [`pm_request_resume()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L454) then queues the runtime resume.

```c
/* include/linux/pm_runtime.h:454 */
static inline int pm_request_resume(struct device *dev)
{
	return __pm_runtime_resume(dev, RPM_ASYNC);
}
```

`RPM_ASYNC` asks the runtime PM core for an asynchronous resume, so the work item queues the request and goes on to the next one without waiting for the requester's driver. The requester now has PME Status and PME enable clear and a resume queued.

### A native PME ends polling for its requester

Some devices set PME Status without sending a PME Message, and some ports latch a message without interrupting, so the PCI core also polls PME Status of suspended devices. A device takes part in the poll while [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) is set, and a native PME clears the flag to take the device out. The poll keeps a list of [`struct pci_pme_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L62) entries, a mutex, a delayed work item and an interval at the top of pci.c.

```c
/* drivers/pci/pci.c:58 */
static LIST_HEAD(pci_pme_list);
static DEFINE_MUTEX(pci_pme_list_mutex);
static DECLARE_DELAYED_WORK(pci_pme_work, pci_pme_list_scan);

struct pci_pme_device {
	struct list_head list;
	struct pci_dev *dev;
};

#define PME_TIMEOUT 1000 /* How long between PME checks */
```

[`pci_pme_list`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L58) holds one entry per polled device, [`pci_pme_list_mutex`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L59) protects it, and [`pci_pme_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L60) runs [`pci_pme_list_scan()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2337) every [`PME_TIMEOUT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L67) milliseconds, 1000 at v7.2. [`pci_pme_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2435) puts a device on the list when PME generation is enabled for it; read the stage where its comment explains the poll and the device is listed.

```c
/* drivers/pci/pci.c:2435 */
void pci_pme_active(struct pci_dev *dev, bool enable)
{
	__pci_pme_active(dev, enable);

	/*
	 * PCI (as opposed to PCIe) PME requires that the device have
	 * its PME# line hooked up correctly. Not all hardware vendors
	 * do this, so the PME never gets delivered and the device
	 * remains asleep. The easiest way around this is to
	 * periodically walk the list of suspended devices and check
	 * whether any have their PME flag set. The assumption is that
	 * we'll wake up often enough anyway that this won't be a huge
	 * hit, and the power savings from the devices will still be a
	 * win.
	 *
	 * Although PCIe uses in-band PME message instead of PME# line
	 * to report PME, PME does not work for some PCIe devices in
	 * reality.  For example, there are devices that set their PME
	 * status bits, but don't really bother to send a PME message;
	 * there are PCI Express Root Ports that don't bother to
	 * trigger interrupts when they receive PME messages from the
	 * devices below.  So PME poll is used for PCIe devices too.
	 */

	if (dev->pme_poll) {
		struct pci_pme_device *pme_dev;
		if (enable) {
			pme_dev = kmalloc_obj(struct pci_pme_device);
			if (!pme_dev) {
				pci_warn(dev, "can't enable PME#\n");
				return;
			}
			pme_dev->dev = dev;
			mutex_lock(&pci_pme_list_mutex);
			list_add(&pme_dev->list, &pci_pme_list);
			if (list_is_singular(&pci_pme_list))
				queue_delayed_work(system_freezable_wq,
						   &pci_pme_work,
						   msecs_to_jiffies(PME_TIMEOUT));
			mutex_unlock(&pci_pme_list_mutex);
```

A device is listed only while [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) is set, and the first entry starts the delayed work on `system_freezable_wq`. The comment gives the reason for polling PCIe devices as well: devices that set PME Status without a message and Root Ports that do not interrupt. Besides the native path, the PCI core has its own wakeup helpers, [`pci_pme_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2300) for one device and [`pci_pme_wakeup_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2316) for a subtree.

```c
/* drivers/pci/pci.c:2292 */
/**
 * pci_pme_wakeup - Wake up a PCI device if its PME Status bit is set.
 * @dev: Device to handle.
 * @pme_poll_reset: Whether or not to reset the device's pme_poll flag.
 *
 * Check if @dev has generated PME and queue a resume request for it in that
 * case.
 */
static int pci_pme_wakeup(struct pci_dev *dev, void *pme_poll_reset)
{
	if (pme_poll_reset && dev->pme_poll)
		dev->pme_poll = false;

	if (pci_check_pme_status(dev)) {
		pci_wakeup_event(dev);
		pm_request_resume(&dev->dev);
	}
	return 0;
}

/**
 * pci_pme_wakeup_bus - Walk given bus and wake up devices on it, if necessary.
 * @bus: Top bus of the subtree to walk.
 */
void pci_pme_wakeup_bus(struct pci_bus *bus)
{
	if (bus)
		pci_walk_bus(bus, pci_pme_wakeup, (void *)true);
}
```

[`pci_pme_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2300) does what the native search does for a found device, with the [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) reset left to its argument, and [`pci_pme_wakeup_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2316) passes true for it. The poll itself is [`pci_pme_list_scan()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2337); read its first lines and the branch that drops a device whose flag a native PME cleared.

```c
/* drivers/pci/pci.c:2337 */
static void pci_pme_list_scan(struct work_struct *work)
{
	struct pci_pme_device *pme_dev, *n;

	mutex_lock(&pci_pme_list_mutex);
	list_for_each_entry_safe(pme_dev, n, &pci_pme_list, list) {
		struct pci_dev *pdev = pme_dev->dev;

		if (pdev->pme_poll) {
		... /* 32 lines, to :2378 */
		} else {
			list_del(&pme_dev->list);
			kfree(pme_dev);
		}
	}
	if (!list_empty(&pci_pme_list))
		queue_delayed_work(system_freezable_wq, &pci_pme_work,
				   msecs_to_jiffies(PME_TIMEOUT));
	mutex_unlock(&pci_pme_list_mutex);
}
```

A listed device whose [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) is clear is unlinked and its entry freed, and the work re-queues itself while the list holds entries. The strip follows one device's flag and list entry through these writers.

```text
    One device's pme_poll, from enumeration to the poll that drops it
    ─────────────────────────────────────────────────────────────────
    fields: pme_poll of one struct pci_dev, and its entry on the poll list

    time ──────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event           PM capability found     PME enabled       native PME or bus wakeup      next poll
                    ▼                       ▼                 ▼                             ▼
                    ┌─────────────────────────────────────────┬─────────────────────────────────────────────┐
    pme_poll        │ ➊ true                                  │ ➋ ➌ ➍ ➏ false                               │
                    └─────────────────────────────────────────┴─────────────────────────────────────────────┘
                    ┌───────────────────────┬───────────────────────────────────────────────┬───────────────┐
    entry on        │ none                  │ ➎ listed, polled every                        │ ➐ unlinked,   │
    pci_pme_list    │                       │   PME_TIMEOUT ms                              │   freed       │
                    └───────────────────────┴───────────────────────────────────────────────┴───────────────┘

    ➊ pci_pm_init              pci.c:3214  sets pme_poll when the PM capability lists PME support
    ➋ pcie_pme_handle_request  pme.c:140   clears it for a port that is its own requester
    ➌ pcie_pme_handle_request  :188        clears it for the listed device the Requester ID names
    ➍ pcie_pme_walk_bus        :79         clears it for a conventional device the scan finds
    ➎ pci_pme_active           pci.c:2469  links the entry onto pci_pme_list while pme_poll is set
    ➏ pci_pme_wakeup           :2303       clears pme_poll when a bus wakeup asks for the reset
    ➐ pci_pme_list_scan        :2379       unlinks the entry with list_del once pme_poll is false
```

➊ [`pci_pm_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3161) sets [`pme_poll`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L410) when the PM capability lists PME support. ➋ [`pcie_pme_handle_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L130) clears it for a port that is its own requester. ➌ `pcie_pme_handle_request()` clears it for the listed device the Requester ID names. ➍ [`pcie_pme_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L70) clears it for a conventional device the scan finds. ➎ [`pci_pme_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2435) links the device's entry onto [`pci_pme_list`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L58) while the flag is set. ➏ [`pci_pme_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2300) clears the flag when a bus wakeup asks for the reset. ➐ [`pci_pme_list_scan()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2337) unlinks the entry with `list_del()` once the flag is false.

Two writers are not shown. [`pci_pme_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2435) also unlinks the entry when PME generation is disabled, in lines after the stage above that this page leaves out, since pme.c does not call it. The ACPI wakeup notification work function [`pci_acpi_wake_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-acpi.c#L847) in pci-acpi.c clears the flag for a device that ACPI reports, a path outside native PME, and one Ethernet driver under drivers/net/ethernet/ sets it for its own device from its probe.

So far, one native PME has been traced from the port's latch through the handler, the work item and the search to a requester whose PME bits are clear, whose resume is queued and whose poll entry the next scan drops.

### portdrv fans system sleep out to the PME callbacks

The PME service has no [`struct dev_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L288) of its own. System sleep reaches it through the port's PCI driver, portdrv, whose [`pcie_portdrv_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L656) calls one slot of each bound service driver per PM phase, so the phases the PME driver sees are the ones portdrv maps onto its four filled slots.

```c
/* drivers/pci/pcie/portdrv.c:656 */
static const struct dev_pm_ops pcie_portdrv_pm_ops = {
	.suspend	= pcie_port_device_suspend,
	.resume_noirq	= pcie_port_device_resume_noirq,
	.resume		= pcie_port_device_resume,
	.freeze		= pcie_port_device_suspend,
	.thaw		= pcie_port_device_resume,
	.poweroff	= pcie_port_device_suspend,
	.restore_noirq	= pcie_port_device_resume_noirq,
	.restore	= pcie_port_device_resume,
	.runtime_suspend = pcie_port_runtime_suspend,
	.runtime_resume	= pcie_port_device_runtime_resume,
	.runtime_idle	= pcie_port_runtime_idle,
};
```

Suspend, freeze and poweroff share [`pcie_port_device_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L405), and resume, thaw and restore share [`pcie_port_device_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L421). The two noirq resume phases go to [`pcie_port_device_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L411), and runtime suspend and resume have their own entries. The fan-out is [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385), which reads the slot at a given offset of each child's service driver.

```c
/* drivers/pci/pcie/portdrv.c:383 */
typedef int (*pcie_callback_t)(struct pcie_device *);

static int pcie_port_device_iter(struct device *dev, void *data)
{
	struct pcie_port_service_driver *service_driver;
	size_t offset = *(size_t *)data;
	pcie_callback_t cb;

	if ((dev->bus == &pcie_port_bus_type) && dev->driver) {
		service_driver = to_service_driver(dev->driver);
		cb = *(pcie_callback_t *)((void *)service_driver + offset);
		if (cb)
			return cb(to_pcie_device(dev));
	}
	return 0;
}
```

A child on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) with a bound driver gets the callback at the offset, and a NULL slot is skipped. The phase functions pass the offset of their slot, under [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217).

```c
/* drivers/pci/pcie/portdrv.c:400 */
#ifdef CONFIG_PM
/**
 * pcie_port_device_suspend - suspend port services associated with a PCIe port
 * @dev: PCI Express port to handle
 */
static int pcie_port_device_suspend(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, suspend);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}

static int pcie_port_device_resume_noirq(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, resume_noirq);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}

/**
 * pcie_port_device_resume - resume port services associated with a PCIe port
 * @dev: PCI Express port to handle
 */
static int pcie_port_device_resume(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, resume);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}
```

[`device_for_each_child()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4089) visits the port's service instances, and for a PME instance the suspend phase reaches [`pcie_pme_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L392) and the resume phase [`pcie_pme_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L423). The noirq resume phase finds NULL in the PME driver's [`resume_noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L83) slot and does nothing for it. Runtime suspend of the port passes through one more test.

```c
/* drivers/pci/pcie/portdrv.c:637 */
#ifdef CONFIG_PM
static int pcie_port_runtime_suspend(struct device *dev)
{
	if (!to_pci_dev(dev)->bridge_d3)
		return -EBUSY;

	return pcie_port_device_runtime_suspend(dev);
}

static int pcie_port_runtime_idle(struct device *dev)
{
	/*
	 * Assume the PCI core has set bridge_d3 whenever it thinks the port
	 * should be good to go to D3.  Everything else, including moving
	 * the port to D3, is handled by the PCI core.
	 */
	return to_pci_dev(dev)->bridge_d3 ? 0 : -EBUSY;
}
```

A port without [`bridge_d3`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L418) refuses runtime suspend with `-EBUSY`, and an allowed one reaches the [`runtime_suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L85) slot, which the PME driver leaves NULL. The PME interrupt therefore stays armed across the port's runtime suspend. The figure maps each phase onto the PME driver's slots.

```text
    Which PM phase of the port reaches which callback of the PME service
    ────────────────────────────────────────────────────────────────────
    the port's dev_pm_ops slot              service driver slot                 in pcie_pme_driver
    ┌────────────────────────┐              ┌────────────────────┐              ┌──────────────────────────────┐
    │ suspend                ├────┐         │                    │              │                              │
    │ freeze                 ├────┼────────▶│ suspend            ├────────────▶ │ the PME suspend callback     │
    │ poweroff               ├────┘         │                    │              │                              │
    │                        │              │                    │              │                              │
    │ resume_noirq           ├────┬────────▶│ resume_noirq       ├────────────▶ │ NULL: nothing runs           │
    │ restore_noirq          ├────┘         │                    │              │                              │
    │                        │              │                    │              │                              │
    │ resume                 ├────┐         │                    │              │                              │
    │ thaw                   ├────┼────────▶│ resume             ├────────────▶ │ the PME resume callback      │
    │ restore                ├────┘         │                    │              │                              │
    │                        │              │                    │              │                              │
    │ runtime_suspend        ├─────────────▶│ runtime_suspend    ├────────────▶ │ NULL: nothing runs           │
    │ runtime_resume         ├─────────────▶│ runtime_resume     ├────────────▶ │ NULL: nothing runs           │
    └────────────────────────┘              └────────────────────┘              └──────────────────────────────┘

    runtime_suspend reaches the service slot only when the port's bridge_d3 allows D3;
    runtime_idle has no service slot
```

System suspend and resume are thus the PM transitions that change the PME interrupt, through the two callbacks the next subsections read.

### Suspend keeps the interrupt armed only for a wakeup path

During system suspend the port's PME interrupt is either a wakeup source or a hazard. The PME suspend callback keeps it armed and marks its vector as a wakeup interrupt when a device below the port may wake the system, and disables it otherwise, so a PME cannot interrupt a suspended system for nothing. [`pcie_pme_check_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L363) answers whether such a device exists, recursing over subordinate buses.

```c
/* drivers/pci/pcie/pme.c:363 */
static bool pcie_pme_check_wakeup(struct pci_bus *bus)
{
	struct pci_dev *dev;

	if (!bus)
		return false;

	list_for_each_entry(dev, &bus->devices, bus_list)
		if (device_may_wakeup(&dev->dev)
		    || pcie_pme_check_wakeup(dev->subordinate))
			return true;

	return false;
}
```

A NULL bus answers false, and the first device for which [`device_may_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_wakeup.h#L82) is true, or whose subordinate bus holds one, answers true. That helper combines the capability probe set with the user's choice.

```c
/* include/linux/pm_wakeup.h:82 */
static inline bool device_may_wakeup(struct device *dev)
{
	return dev->power.can_wakeup && !!dev->power.wakeup;
}
```

[`can_wakeup`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L668) is the capability, and [`wakeup`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L683) is the wakeup source that exists while wakeup is enabled, the setting user space writes to the device's power/wakeup file. The disabling half of suspend is [`pcie_pme_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L378), which removal shares.

```c
/* drivers/pci/pcie/pme.c:378 */
static void pcie_pme_disable_interrupt(struct pci_dev *port,
				       struct pcie_pme_service_data *data)
{
	spin_lock_irq(&data->lock);
	pcie_pme_interrupt_enable(port, false);
	pcie_clear_root_pme_status(port);
	data->noirq = true;
	spin_unlock_irq(&data->lock);
}
```

Under the lock it masks the port, clears Root Status and sets [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46), so a work item that runs afterwards leaves its loop at once and does not unmask the port. [`pcie_pme_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L392) chooses between the two outcomes.

```c
/* drivers/pci/pcie/pme.c:388 */
/**
 * pcie_pme_suspend - Suspend PCIe PME service device.
 * @srv: PCIe service device to suspend.
 */
static int pcie_pme_suspend(struct pcie_device *srv)
{
	struct pcie_pme_service_data *data = get_service_data(srv);
	struct pci_dev *port = srv->port;
	bool wakeup;
	int ret;

	if (device_may_wakeup(&port->dev)) {
		wakeup = true;
	} else {
		down_read(&pci_bus_sem);
		wakeup = pcie_pme_check_wakeup(port->subordinate);
		up_read(&pci_bus_sem);
	}
	if (wakeup) {
		ret = enable_irq_wake(srv->irq);
		if (!ret)
			return 0;
	}

	pcie_pme_disable_interrupt(port, data);

	synchronize_irq(srv->irq);

	return 0;
}
```

A port that may wake the system keeps its interrupt armed, and otherwise the subtree below it is searched under [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17). When a wakeup path exists and [`enable_irq_wake()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L486) succeeds, the callback returns with the interrupt armed and the vector marked as a wakeup interrupt. Otherwise it disables the service and calls [`synchronize_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L145), which waits for a handler running on the vector to finish, so no handler is left between the mask and the sleep. The figure collects the states an instance's interrupt can be in across a sleep.

```text
    Interrupt states of one PME service instance across system sleep
    ────────────────────────────────────────────────────────────────
                            probe
                              ▼
                        ┌────────────────────────┐    PME latched           ┌──────────────────────────┐
                        │ armed                  ├─────────────────────────▶│ masked                   │
                        │ PMEIE 1, noirq false   │◀─────────────────────────┤ PMEIE 0, work pending    │
                        └─┬───────────────────┬──┘  Root Status drained     └──────────────────────────┘
                          │ ▲     suspend, no │ ▲                                         ▲
          suspend with a  │ │     wakeup path │ │                                         │
          wakeup path     │ │                 │ │ resume: Root Status cleared             │
                          │ │ resume          │ │                                         │
                          ▼ │                 ▼ │                                         │
    ┌───────────────────────┴────┐          ┌───┴────────────────────────┐                │
    │ armed for wakeup           │          │ disabled                   │                │
    │ PMEIE 1, IRQ wake on       │          │ PMEIE 0, noirq true        │                │
    └─────────┬──────────────────┘          └────────────────────────────┘                │
              │                                                                           │
              │                                                                           │
              └───────────────────────────────────────────────────────────────────────────┘
                                  a PME latched while suspended masks the port as usual

    suspend in the masked state takes the same two branches; noirq true then stops the work item
    from setting PMEIE again; removal takes any state to disabled before it frees the handler and the data
```

A suspended instance is thus either armed for wakeup with [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) false, or disabled with the flag true, and resume reads the flag to tell the two apart.

### Resume re-arms the port after the PCI core clears Root Status

Firmware can leave a PME latched across a sleep, and a latched PME Status keeps the port from reporting the next request, as commit [fe31e69740ed](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=fe31e69740eddc7316071ed5165fed6703c8cd12) ("PCI/PCIe: Clear Root PME Status bits early during system resume") reports. With [`CONFIG_SUSPEND`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L2) set, the PCI core therefore clears Root Status of a Root Port or RCEC in the noirq phase, before the PME resume callback decides whether to unmask. [`pcie_pme_root_status_cleanup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L799) is that clear.

```c
/* drivers/pci/pci-driver.c:798 */
#ifdef CONFIG_SUSPEND
static void pcie_pme_root_status_cleanup(struct pci_dev *pci_dev)
{
	/*
	 * Some BIOSes forget to clear Root PME Status bits after system
	 * wakeup, which breaks ACPI-based runtime wakeup on PCI Express.
	 * Clear those bits now just in case (shouldn't hurt).
	 */
	if (pci_is_pcie(pci_dev) &&
	    (pci_pcie_type(pci_dev) == PCI_EXP_TYPE_ROOT_PORT ||
	     pci_pcie_type(pci_dev) == PCI_EXP_TYPE_RC_EC))
		pcie_clear_root_pme_status(pci_dev);
}
```

The comment blames firmware that forgets the bits after a wakeup. commit [3620c71484f7](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=3620c71484f7a19b2588e577ea732f55719f5b1f) ("PCI/PM: Clear PCIe PME Status bit for Root Complex Event Collectors") added the RCEC case. [`pci_pm_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L979), the PCI bus's noirq resume callback, calls it for a PCI device whose resume is not skipped and lets the port type decide.

```c
/* drivers/pci/pci-driver.c:979 */
static int pci_pm_resume_noirq(struct device *dev)
{
	struct pci_dev *pci_dev = to_pci_dev(dev);
	const struct dev_pm_ops *pm = dev->driver ? dev->driver->pm : NULL;
	pci_power_t prev_state = pci_dev->current_state;
	bool skip_bus_pm = pci_dev->skip_bus_pm;

	if (dev_pm_skip_resume(dev))
		return 0;

	/*
	 * In the suspend-to-idle case, devices left in D0 during suspend will
	 * stay in D0, so it is not necessary to restore or update their
	 * configuration here and attempting to put them into D0 again is
	 * pointless, so avoid doing that.
	 */
	if (!(skip_bus_pm && pm_suspend_no_platform()))
		pci_pm_default_resume_early(pci_dev);

	pci_fixup_device(pci_fixup_resume_early, pci_dev);
	pcie_pme_root_status_cleanup(pci_dev);

	if (!skip_bus_pm && prev_state == PCI_D3cold)
		pci_pm_bridge_power_up_actions(pci_dev);

	if (pci_has_legacy_pm_support(pci_dev))
		return 0;

	if (pm && pm->resume_noirq)
		return pm->resume_noirq(dev);

	return 0;
}
```

The clear runs after the port is restored and its early fixups have run, and before the port driver's own noirq callback, which for portdrv is [`pcie_port_device_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L411) and finds no PME slot. The resume phase then reaches [`pcie_pme_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L423).

```c
/* drivers/pci/pcie/pme.c:419 */
/**
 * pcie_pme_resume - Resume PCIe PME service device.
 * @srv: PCIe service device to resume.
 */
static int pcie_pme_resume(struct pcie_device *srv)
{
	struct pcie_pme_service_data *data = get_service_data(srv);

	spin_lock_irq(&data->lock);
	if (data->noirq) {
		struct pci_dev *port = srv->port;

		pcie_clear_root_pme_status(port);
		pcie_pme_interrupt_enable(port, true);
		data->noirq = false;
	} else {
		disable_irq_wake(srv->irq);
	}
	spin_unlock_irq(&data->lock);

	return 0;
}
```

A set [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) means suspend disabled the service, and resume clears Root Status again, sets [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) and clears the flag under the lock. A clear flag means the interrupt stayed armed for wakeup, and resume turns the wakeup marking of the vector off with [`disable_irq_wake()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L491). commit [c7b5a4e6e8fb](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=c7b5a4e6e8fbef8fdf2c529f953000d24c561339) ("PCI / PM: Fix native PME handling during system suspend/resume") gave the function this shape, after a PME taken during suspend left the interrupt disabled and PME Status set. The figure orders the two resume phases.

```text
    System resume of a Root Port: the PCI core clears Root Status before the PME service runs
    ─────────────────────────────────────────────────────────────────────────────────────────
    time ↓
    PM core phase   ╎ PCI core, for the port        ╎ PME service of the port             ╎ Root Port registers
    ────────────────┼───────────────────────────────┼─────────────────────────────────────┼────────────────────────
    resume_noirq    ╎ port restored                 ╎                                     ╎ PME may still be 1
                    ╎ Root Port or RCEC: write      ╎                                     ╎
                    ╎ PCI_EXP_RTSTA_PME ────────────┼─────────────────────────────────────▶ PME 0
                    ╎ driver resume_noirq ────────▶ ╎ empty slot, nothing runs            ╎
    resume          ╎ driver resume ──────────────▶ ╎ noirq true: clear PME, PMEIE 1,     ╎ PME 0, PMEIE 1
                    ╎                               ╎ noirq false                         ╎
                    ╎                               ╎ noirq false: IRQ wake off only      ╎ PMEIE as it was

    the PCI core's write is built with CONFIG_SUSPEND and runs on resume from suspend; a restore from
    hibernation reaches the PME resume callback without it
```

After resume, an instance is armed again with [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46) false whichever way it was suspended, and a PME that arrived while the system slept is handled by the work item it queued.

### Removal disables the interrupt before freeing handler and data

Removing the port, or unbinding the PME driver, has to stop the interrupt and the work item before the state they use is freed. portdrv's bus removes a service through [`pcie_port_bus_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L562).

```c
/* drivers/pci/pcie/portdrv.c:553 */
/**
 * pcie_port_bus_remove - detach driver from given PCI Express port service
 * @dev: PCI Express port service device to handle
 *
 * If PCI Express port service driver is registered with
 * pcie_port_service_register(), this function will be called by the driver core
 * when device_unregister() is called for the port service device associated
 * with the driver.
 */
static void pcie_port_bus_remove(struct device *dev)
{
	struct pcie_device *pciedev;
	struct pcie_port_service_driver *driver;

	pciedev = to_pcie_device(dev);
	driver = to_service_driver(dev->driver);
	if (driver && driver->remove)
		driver->remove(pciedev);

	put_device(dev);
}
```

The callback calls the driver's remove and drops the reference the bus's probe took. [`pcie_pme_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L446) tears the PME service down in an order that keeps the handler and the work item off freed memory.

```c
/* drivers/pci/pcie/pme.c:442 */
/**
 * pcie_pme_remove - Prepare PCIe PME service device for removal.
 * @srv: PCIe service device to remove.
 */
static void pcie_pme_remove(struct pcie_device *srv)
{
	struct pcie_pme_service_data *data = get_service_data(srv);

	pcie_pme_disable_interrupt(srv->port, data);
	free_irq(srv->irq, srv);
	cancel_work_sync(&data->work);
	kfree(data);
}
```

[`pcie_pme_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L378) masks the port, clears Root Status and sets [`noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L46), which closes the inlet. [`free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L2006) then removes the handler, waiting for a running instance of it, and [`cancel_work_sync()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/workqueue.c#L4529) waits for a queued or running work item, which finds the flag set and leaves the port masked. commit [95c80bc6952b](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=95c80bc6952b6a5badc7b702d23e5bf14d251e7c) ("PCI/PME: Fix hotplug/sysfs remove deadlock in pcie_pme_remove()") replaced an earlier call of the suspend callback here, whose [`synchronize_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L145) waited on the vector shared with the hotplug handler while that handler waited for the remove path's lock. commit [7cf58b79b307](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=7cf58b79b3072029af127ae865ffc6f00f34b1f8) ("PCI/PME: Fix possible use-after-free on remove") added the wait for the work item before `kfree()`. The figure shows the order as a drain.

```text
    Removal closes the inlet, drains the handler and the work item, then frees the data
    ───────────────────────────────────────────────────────────────────────────────────
    new PME interrupts ────┤ closed: PMEIE 0, Root Status cleared, noirq true
                                                      ╎                           ╎
                ┌──────────────────────┐              ╎ gate 1: the handler       ╎
    in flight   │ a running PME        │ ───────────▶ ╎ is released from          ╎
                │ hardirq handler      │              ╎ srv->irq                  ╎
                └──────────────────────┘              ╎                           ╎
                                                                                  ╎
                ┌──────────────────────┐                                          ╎ gate 2: the work item
                │ a queued or running  │ ───────────────────────────────────────▶ ╎ is idle; then the
                │ PME work item        │                                          ╎ data is freed
                └──────────────────────┘                                          ╎
                                                                                  ╎
                the work item keeps PMEIE clear on its way out, because noirq is true
```

So far, the service has been followed from the firmware grant through probe, one PME, system sleep and removal, which leaves the port masked, Root Status clear and the service data freed.

### Messages, tracepoints and hand-offs expose the PME path

The PME paths print three messages of their own, hand work to a workqueue and to the runtime PM core, and fire no tracepoint of their own, while the generic interrupt, workqueue, runtime PM and wakeup tracepoints see them. The messages carry a `PME: ` prefix, which [`dev_fmt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L10) at the top of pme.c defines.

```c
/* drivers/pci/pcie/pme.c:10 */
#define dev_fmt(fmt) "PME: " fmt
```

The three messages of pme.c go through [`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895), one of the PCI core's wrappers around the device printing macros.

```c
/* include/linux/pci.h:2888 */
#define pci_emerg(pdev, fmt, arg...)	dev_emerg(&(pdev)->dev, fmt, ##arg)
#define pci_alert(pdev, fmt, arg...)	dev_alert(&(pdev)->dev, fmt, ##arg)
#define pci_crit(pdev, fmt, arg...)	dev_crit(&(pdev)->dev, fmt, ##arg)
#define pci_err(pdev, fmt, arg...)	dev_err(&(pdev)->dev, fmt, ##arg)
#define pci_warn(pdev, fmt, arg...)	dev_warn(&(pdev)->dev, fmt, ##arg)
#define pci_warn_once(pdev, fmt, arg...) dev_warn_once(&(pdev)->dev, fmt, ##arg)
#define pci_notice(pdev, fmt, arg...)	dev_notice(&(pdev)->dev, fmt, ##arg)
#define pci_info(pdev, fmt, arg...)	dev_info(&(pdev)->dev, fmt, ##arg)
#define pci_dbg(pdev, fmt, arg...)	dev_dbg(&(pdev)->dev, fmt, ##arg)
```

[`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) is [`dev_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L159) on the function's embedded device, and [`dev_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L159) passes its format through `dev_fmt()`.

```c
/* include/linux/dev_printk.h:159 */
#define dev_info(dev, fmt, ...) \
	dev_printk_index_wrap(_dev_info, KERN_INFO, dev, dev_fmt(fmt), ##__VA_ARGS__)
```

A message of pme.c therefore reads `pcieport <port>: PME: <text>`, the form the example in commit [00ebf1348cb3](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=00ebf1348cb332941dab52948f29480592bfbe6a) ("PCI/PME: Replace dev_printk(KERN_DEBUG) with dev_info()") shows. [`pci_info()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2895) prints at the info level whatever the configuration, and pme.c holds no [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896), `dev_dbg()` or `pr_debug()` site, so [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) adds no switchable message to the PME paths and [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), unset here, would add none either. The table lists the classes with their sites.

| class | on these paths | sites |
|---|---|---|
| tracepoints | no PME tracepoint; the hardirq handler fires `irq:irq_handler_entry` and `irq:irq_handler_exit`, the queueing fires `workqueue:workqueue_queue_work` and the item `workqueue:workqueue_execute_start`, the resume request `rpm:rpm_resume`, and the wakeup event `power:wakeup_source_activate` for a requester with wakeup enabled | [`handle.c:201`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L201), [`workqueue.c:2383`](https://elixir.bootlin.com/linux/v7.2/source/kernel/workqueue.c#L2383), [`workqueue.c:3321`](https://elixir.bootlin.com/linux/v7.2/source/kernel/workqueue.c#L3321), [`runtime.c:793`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L793), [`wakeup.c:570`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/wakeup.c#L570) |
| messages | `Signaling with IRQ %d` at probe, `interrupt generated for non-existent device %02x:%02x.%d` and `Spurious native interrupt!` from the search, all at the info level; portdrv's notice when the DMI quirk turns MSI off | [`pme.c:356`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L356), [`pme.c:200`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L200), [`pme.c:207`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L207), [`portdrv.c:808`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L808) |
| dynamic-debug sites | none in pme.c; the poll's [`pci_pme_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2435) prints `PME# %s` through [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) when PME generation changes | [`pci.c:2488`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2488) |
| deferred hand-offs | the hardirq handler to the work item on [`system_percpu_wq`](https://elixir.bootlin.com/linux/v7.2/source/kernel/workqueue.c#L526); the work item to the runtime PM core through an asynchronous resume request; the wakeup event's 100 ms window; the poll's delayed work every [`PME_TIMEOUT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L67) ms | [`pme.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L288), [`pme.c:191`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L191), [`drivers/pci/pci.h:297`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L297), [`pci.c:2384`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2384) |
| timers, RCU, notifier chains | none in pme.c | |

The probe message gives the vector, which is the line of /proc/interrupts to watch, and the spurious-interrupt message tells a reader that a latched request named no device the search could find. The search's own steps print nothing, so a reader follows a PME through the tracepoints: an `irq_handler_entry` for the vector, a `workqueue_execute_start` for the PME work function and an `rpm_resume` for the requester.

### sysfs, /proc/interrupts and boot parameters expose the service

User space sees the service through the files of its service instance, the interrupt line it requested, the wakeup files of the devices it marked and the boot parameters it reads. The instance is a device on the `pci_express` bus, whose name portdrv builds from the port's name and the descriptor that [`get_descriptor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L32) computes from type and service.

```c
/* drivers/pci/pcie/portdrv.c:32 */
#define get_descriptor_id(type, service) (((type - 4) << 8) | service)
```

The descriptor subtracts 4 from the port type and adds the service bit, so a Root Port's PME instance gets the suffix `pcie001` and an RCEC's `pcie601`. [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) applies it when it creates the instance; read the stage that names and parents the device.

```c
/* drivers/pci/pcie/portdrv.c:290 */
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

	/* Initialize generic device interface */
	device = &pcie->device;
	device->bus = &pcie_port_bus_type;
	device->release = release_pcie_device;	/* callback to free pcie dev */
	dev_set_name(device, "%s:pcie%03x",
		     pci_name(pdev),
		     get_descriptor_id(pci_pcie_type(pdev), service));
	device->parent = &pdev->dev;
	device_enable_async_suspend(device);
```

The instance appears as /sys/bus/pci_express/devices/<port>:pcie001 below the port's own directory, and the bound driver as /sys/bus/pci_express/drivers/pcie_pme. The bus name comes from [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575).

```c
/* drivers/pci/pcie/portdrv.c:575 */
const struct bus_type pcie_port_bus_type = {
	.name = "pci_express",
	.match = pcie_port_bus_match,
	.probe = pcie_port_bus_probe,
	.remove = pcie_port_bus_remove,
};
```

The request in probe names the handler `PCIe PME`, so /proc/interrupts shows that name on the port's PME vector, beside the hotplug and bandwidth handlers that share it, and its count grows by one per PME interrupt. A device that probe marked has a power/wakeup file, and writing `enabled` there makes [`device_may_wakeup()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_wakeup.h#L82) true for it, which decides whether suspend keeps the port armed. `pcie_pme=nomsi` and `pcie_ports=native` or `compat` are the boot parameters the service reads, and [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt) documents both. No debugfs file and no fault-injection point covers the service.
