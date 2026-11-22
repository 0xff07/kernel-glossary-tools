# PCIe native hot-plug interrupt

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe port with a hot-plug slot reports a card arriving, a link going down or a button press by setting event bits in its Slot Status register, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), and raising an interrupt. Acknowledging those bits is quick work that belongs in interrupt context, while acting on them powers the slot and scans the bus beneath it, which sleeps. The native hot-plug driver, pciehp, therefore splits its interrupt handling into a hard-interrupt stage and a threaded stage that meet in the [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) word of its [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91). This page traces how the pair is installed on the vector the port shares, what each stage does with the events, how requests, poll mode and system sleep reach the same path, and how removal takes it down.

```text
    The two stages of the hot-plug interrupt and the word between them
    ──────────────────────────────────────────────────────────────────

    ┌──────────────────────────────────────────┐
    │ hot-plug port: a Root Port or a Switch   │
    │ Downstream Port with a slot              │
    │   Slot Control: event enables, HPIE gate │
    │   Slot Status: ABP PFD PDC CC DLLSC      │
    └─────────────────────┬────────────────────┘
                          │ MSI, MSI-X or INTx on the vector the port
                          │ shares with PME and bandwidth notification
                          ▼
    ┌──────────────────────────────────────────┐
    │ hard stage, interrupt context            │
    │   claims the interrupt, reads Slot       ├──▶ Command Completed ends here:
    │   Status and writes the events back      │    the Slot Control writer is woken
    └─────────────────────┬────────────────────┘
                          │ ORs the other events in and wakes the thread
                          ▼
    ┌───────────┬──────────────┬───────────────────────┐
    │ RERUN_ISR │ DISABLE_SLOT │ Slot Status events    │◀── requests from process
    │ bit 17    │ bit 16       │ bits 15:0             │    context, thread woken
    └───────────┴──────────────┴───────────┬───────────┘
      pending_events of struct controller  │ exchanged for zero
                          ┌────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │ IRQ thread, process context              │
    │   button press, power fault, disable     │
    │   request, presence and link change      │
    └──────────────────────────────────────────┘

    in poll mode no vector is requested: a kernel thread runs both stages
    every pciehp_poll_time seconds
```

## SUMMARY

pciehp keeps a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) for a hot-plug slot and its controller, and the port driver hands it the interrupt through a service object. The table settles which kernel object stands for which term of the specification, and the rest of the page uses these names.

| Specification term | Kernel object | How the interrupt paths reach it |
|---|---|---|
| Hot-Plug Controller and its slot | [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), one object for both | the service object's [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) |
| Port service of a Root Port or Switch Downstream Port | [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), the port driver's service instance | its [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) is the vector pciehp requests |
| Software notification enables | the enable bits of Slot Control, [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610) | cached in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) |
| Hot-plug events | the event bits of Slot Status, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633) | latched into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) |
| Software notification, the interrupt | the hard stage [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) and the IRQ thread [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) | requested together on the service's vector |
| Polling for events | the poll thread [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) | selected by [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) |

The hard stage reads Slot Status, writes the event bits back and ORs them into the word, and the IRQ thread exchanges the word for zero and hands the events to the slot's handlers. Requests from process context OR their bits into the same word and wake the same thread, so the slot is enabled and disabled from the thread stage in drivers/pci/hotplug at v7.2. Slot Control's interrupt enables stay open from probe to removal, inside the time the handler is installed.

## SPECIFICATIONS

- PCI Express Base Specification, revision 5.0, section 6.7.3.4: Software Notification of Hot-Plug Events, cited by the comment at [`pciehp_hpc.c:690-691`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L690) for the rule that a port in MSI mode sends no new interrupt until every event bit reads zero; commit [8edf5332c393](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=8edf5332c39340b9583cf9cba659eb7ec71f75b5) ("PCI: pciehp: Fix MSI interrupt race") gives the title
- PCI Express Base Specification, revision 4.0, section 6.7.3.4, cited by the comment at [`pciehp_hpc.c:631-632`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L631) for interrupts occurring only in D3hot or shallower and only when Slot Control enables them, and by the comment at [`pciehp_core.c:160-165`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L160) for the optional interrupt on events that occurred while generation was disabled
- PCI Express Base Specification, revision 4.0, section 6.7.3.2, cited by the comment at [`pciehp.h:58-60`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L58) for spacing Slot Control writes by one second when no Command Completed interrupt arrives
- PCI Express Base Specification, revision 5.0, section 6.7.1.8, quoted by commit [23584c1ed3e1](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=23584c1ed3e15a6f4bfab8dc5a88d94ab929ee12) ("PCI: pciehp: Fix infinite loop in IRQ handler upon power fault") for the main power fault latch that turning off slot power clears
- PCI Express Base Specification, revision 3.1, sections 7.8.2, 7.10.10 and 7.31.2, cited by the comment at [`portdrv.c:66-67`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L66) for the Interrupt Message Number that picks a port's vector

The specification defines the Slot Control and Slot Status registers and the rules of hot-plug software notification. The split into a hard stage and a thread that share an atomic word is the kernel's own design, a synthesis this page draws from [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c), [`pciehp_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c), [`pciehp_ctrl.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c) and [`portdrv.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c) at v7.2.

## COVERAGE

### Installing and removing the two stages (drivers/pci/hotplug/pciehp_hpc.c)

- [`'\<pcie_init_notification\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960): requests the handler pair or the poll thread, then opens the Slot Control enables
- [`'\<pciehp_request_irq\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58): starts the poll thread in poll mode, otherwise requests the threaded interrupt on the shared vector
- [`'\<pcie_enable_notification\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821): computes the enables from the slot's capabilities and the mode and writes them without waiting
- [`'\<pcie_shutdown_notification\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969): clears the enables, then releases the handler pair or stops the poll thread
- [`'\<pcie_disable_notification\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861): clears every event and interrupt enable and waits for the command to complete
- [`'\<pciehp_free_irq\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78): stops the poll thread or frees the interrupt, by the same mode test

### The two stages and the word between them (drivers/pci/hotplug/pciehp_hpc.c, pciehp.h)

- [`'pciehp_isr'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623): the hard stage, which claims, acknowledges and latches Slot Status events
- [`'pciehp_ist'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728): the IRQ thread, which empties the word and dispatches the events to the slot's handlers
- [`'controller.pending_events'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104): the atomic word of latched events and requests between the stages
- [`'controller.power_fault_detected'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106): the flag that keeps the hard stage from reporting a power fault again until slot power returns
- [`'controller.ist_running'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116): the flag that keeps a sysfs request waiting while the thread runs
- [`'DISABLE_SLOT'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153): the request bit that asks the thread to disable the slot
- [`'RERUN_ISR'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154): the request bit that tells the thread to rerun the hard stage after resuming the port's parents

### Poll mode (drivers/pci/hotplug/pciehp_hpc.c, pciehp_core.c)

- [`'pciehp_poll'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800): the kernel thread that runs both stages on a timer in place of the vector
- [`'\<pciehp_poll_mode\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34): the module parameter that selects polling
- [`'\<pciehp_poll_time\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35): the module parameter that sets the poll interval in seconds

### Suspend and resume (drivers/pci/hotplug/pciehp_hpc.c)

- [`'\<pcie_disable_interrupt\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L890): clears Hot-Plug Interrupt Enable and the link-change enable before the port sleeps
- [`'\<pcie_clear_hotplug_events\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L874): clears stale presence and link events from Slot Status on resume
- [`'\<pcie_enable_interrupt\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L880): sets the link-change enable, and Hot-Plug Interrupt Enable outside poll mode, on resume

### Slot Control interrupt enables (include/uapi/linux/pci_regs.h)

- [`'PCI_EXP_SLTCTL_ABPE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611): Attention Button Pressed Enable
- [`'PCI_EXP_SLTCTL_PFDE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L612): Power Fault Detected Enable, which pciehp clears and leaves clear
- [`'PCI_EXP_SLTCTL_PDCE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614): Presence Detect Changed Enable
- [`'PCI_EXP_SLTCTL_CCIE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615): Command Completed Interrupt Enable
- [`'PCI_EXP_SLTCTL_HPIE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616): Hot-Plug Interrupt Enable, the gate of the hot-plug interrupt
- [`'PCI_EXP_SLTCTL_DLLSCE'`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630): Data Link Layer State Changed Enable

## DOCUMENTATION

- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver and its service drivers; its section "MSI and MSI-X Vector Resource" tells a service driver to request and free its interrupt through the [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) of [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59)
- [`Documentation/core-api/genericirq.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/core-api/genericirq.rst): the generic interrupt layer, whose kernel-doc includes [`request_threaded_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L2123)
- [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst): the `pci:pci_hp_event` tracepoint, emitted from the IRQ thread's presence and link handling
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the `pcie_ports=` parameter, which decides whether PME is native and so whether suspend masks the interrupt, and `pcie_pme=nomsi`, which puts every service of a Root Port on INTx
- [`Documentation/admin-guide/dynamic-debug-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/dynamic-debug-howto.rst): enabling the [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) sites behind pciehp's debug messages

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI: pciehp: Fix MSI interrupt race (commit 8edf5332c393)](https://lore.kernel.org/r/78b4ced5072bfe6e369d20e8b47c279b8c7af12e.1582121613.git.lukas@wunner.de)
- [PCI: pciehp: Fix infinite loop in IRQ handler upon power fault (commit 23584c1ed3e1)](https://lore.kernel.org/r/66eaeef31d4997ceea357ad93259f290ededecfd.1637187226.git.lukas@wunner.de)
- [PCI: pciehp: Avoid returning prematurely from sysfs requests (commit 157c1062fcd8)](https://lore.kernel.org/r/4174210466e27eb7e2243dd1d801d5f75baaffd8.1565345211.git.lukas@wunner.de)
- [PCI: pciehp: Don't enable HPIE when resuming in poll mode (commit 527664f738af)](https://lore.kernel.org/r/20250321162114.3939-1-ilpo.jarvinen@linux.intel.com)
- [PCI: pciehp: Enable Command Completed Interrupt only if supported (commit 6d4671b534f6)](https://lore.kernel.org/r/20220927141926.8895-2-kabel@kernel.org)
- [PCI: pciehp: Disable Data Link Layer State Changed event on suspend (commit bbe54ea5330d)](https://bugzilla.kernel.org/show_bug.cgi?id=202593)
- [PCI: pciehp: Ignore Link Down/Up caused by DPC (commit a97396c6eb13)](https://lore.kernel.org/r/0be565d97438fe2a6d57354b3aa4e8626952a00b.1619857124.git.lukas@wunner.de)

## REGISTERS

The interrupt paths read and write four registers of the port's PCIe capability. pciehp reaches them through [`pcie_capability_read_word()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/access.c#L427) and its relatives at the offsets [`PCI_EXP_FLAGS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L483), [`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597), [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610) and [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), and the drawings name the member of [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) that caches a register where one does.

The Interrupt Message Number of the PCI Express Capabilities register, [`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496), decides which MSI or MSI-X entry the port uses for PME, hot-plug and bandwidth notification. [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads it, and every hot-plug interrupt this page follows arrives on the vector of that entry.

```text
    PCI Express Capabilities register, offset 0x02 of the PCIe capability
    ─────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x02  │F│·│   irq   │S│  type │  vers │
          │ │ │  (13:9) │ │ (7:4) │ (3:0) │
          └─┴─┴─────────┴─┴───────┴───────┘

    irq  = PCI_EXP_FLAGS_IRQ (0x3e00, Interrupt Message Number: the MSI or MSI-X entry that PME,
           hot-plug and bandwidth notification share)
    type = PCI_EXP_FLAGS_TYPE (Device/Port Type: a Root Port or a Switch Downstream Port carries the slot)
    S    = PCI_EXP_FLAGS_SLOT (Slot Implemented)    vers = PCI_EXP_FLAGS_VERS (capability version)
    F    = PCI_EXP_FLAGS_FLIT (Flit Mode Supported, unread here)    · = bit 14, which pci_regs.h does not name
```

Slot Capabilities decides which enables pciehp opens. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) caches it in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) tests Attention Button Present to choose between button and presence events, and [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) tests No Command Completed Support to decide whether Command Completed interrupts are enabled and awaited. Power Controller Present, tested by [`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157), decides whether the slot is ever powered on by pciehp, and with it whether the power fault flag is ever cleared.

```text
    Slot Capabilities register, offset 0x14 of the PCIe capability
    ──────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x14  │           PSN           │N│E│ LS│      SPLV     │C│S│I│T│M│W│B│
          │         (31:19)         │ │ │   │     (14:7)    │ │ │ │ │ │ │ │
          └─────────────────────────┴─┴─┴───┴───────────────┴─┴─┴─┴─┴─┴─┴─┘

    B    = PCI_EXP_SLTCAP_ABP (0x00000001, Attention Button Present, tested by ATTN_BUTTN)
    N    = PCI_EXP_SLTCAP_NCCS (0x00040000, No Command Completed Support, tested by NO_CMD_CMPL)
    W    = PCI_EXP_SLTCAP_PCP (0x00000002, Power Controller Present, tested by POWER_CTRL)
    M    = PCI_EXP_SLTCAP_MRLSP (MRL Sensor Present)     T = PCI_EXP_SLTCAP_AIP (Attention Indicator Present)
    I    = PCI_EXP_SLTCAP_PIP (Power Indicator Present)  S = PCI_EXP_SLTCAP_HPS (Hot-Plug Surprise)
    C    = PCI_EXP_SLTCAP_HPC (Hot-Plug Capable)         E = PCI_EXP_SLTCAP_EIP (Electromechanical Interlock Present)
    SPLV = PCI_EXP_SLTCAP_SPLV (14:7, Slot Power Limit Value)
    LS   = PCI_EXP_SLTCAP_SPLS (16:15, Slot Power Limit Scale)
    PSN  = PCI_EXP_SLTCAP_PSN (31:19, Physical Slot Number)
    the register is cached whole in slot_cap of struct controller; B and N decide enables, and W decides
    whether the power fault flag is ever cleared
```

Slot Control holds the enables that decide which events raise the interrupt and whether it is raised at all. [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) opens Hot-Plug Interrupt Enable, the link-change enable, one of the presence and button enables and the Command Completed enable, [`pcie_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L890) and [`pcie_enable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L880) close and reopen the gate and the link-change enable around a suspend, and [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) clears all of them at removal. Every Slot Control write pciehp makes goes through [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), which keeps the register's last value in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), the copy the hard stage tests.

```text
    Slot Control register, offset 0x18 of the PCIe capability
    ─────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │·│I│S│L│E│W│PIC│AIC│H│C│P│M│F│A│
          └─┴─┴─┴─┴─┴─┴───┴───┴─┴─┴─┴─┴─┴─┘

    A   = PCI_EXP_SLTCTL_ABPE (0x0001, Attention Button Pressed Enable, set when the slot has a button)
    F   = PCI_EXP_SLTCTL_PFDE (0x0002, Power Fault Detected Enable, kept clear by pciehp)
    M   = PCI_EXP_SLTCTL_MRLSCE (0x0004, MRL Sensor Changed Enable, cleared when notification ends)
    P   = PCI_EXP_SLTCTL_PDCE (0x0008, Presence Detect Changed Enable, set when the slot has no button)
    C   = PCI_EXP_SLTCTL_CCIE (0x0010, Command Completed Interrupt Enable, set outside poll mode
          when the slot reports Command Completed)
    H   = PCI_EXP_SLTCTL_HPIE (0x0020, Hot-Plug Interrupt Enable, the gate of the interrupt, set
          outside poll mode and cleared across suspend)
    L   = PCI_EXP_SLTCTL_DLLSCE (0x1000, Data Link Layer State Changed Enable, set while notification
          is on, cleared across suspend)
    AIC = PCI_EXP_SLTCTL_AIC (7:6, Attention Indicator Control)
    PIC = PCI_EXP_SLTCTL_PIC (9:8, Power Indicator Control)
    W   = PCI_EXP_SLTCTL_PCC (0x0400, Power Controller Control)
    E   = PCI_EXP_SLTCTL_EIC (0x0800, Electromechanical Interlock Control)
    S   = PCI_EXP_SLTCTL_ASPL_DISABLE (0x2000, Auto Slot Power Limit Disable)
    I   = PCI_EXP_SLTCTL_IBPD_DISABLE (0x4000, In-band Presence Detect Disable)
    AIC, PIC, W, E, S and I are commands the interrupt paths leave alone; slot_ctrl caches the whole register
    ·   = bit 15, which pci_regs.h does not name
```

Slot Status carries the events. The hard stage keeps the five event bits it handles, writes them back to clear them and passes all but Command Completed to the thread, and [`pcie_clear_hotplug_events()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L874) clears the presence and link events left over from a sleep.

```text
    Slot Status register, offset 0x1a of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1a  │      ·      │L│E│D│S│C│P│M│F│A│
          │    (15:9)   │ │ │ │ │ │ │ │ │ │
          └─────────────┴─┴─┴─┴─┴─┴─┴─┴─┴─┘

    A = PCI_EXP_SLTSTA_ABP (0x0001, Attention Button Pressed, an event bit)
    F = PCI_EXP_SLTSTA_PFD (0x0002, Power Fault Detected, an event bit the hardware sets again while the fault lasts)
    M = PCI_EXP_SLTSTA_MRLSC (0x0004, MRL Sensor Changed, outside the hard stage's mask)
    P = PCI_EXP_SLTSTA_PDC (0x0008, Presence Detect Changed, an event bit)
    C = PCI_EXP_SLTSTA_CC (0x0010, Command Completed, an event bit finished in the hard stage)
    S = PCI_EXP_SLTSTA_MRLSS (0x0020, MRL Sensor State)    D = PCI_EXP_SLTSTA_PDS (0x0040, Presence Detect State)
    E = PCI_EXP_SLTSTA_EIS (0x0080, Electromechanical Interlock Status); S, D and E are state bits
    L = PCI_EXP_SLTSTA_DLLSC (0x0100, Data Link Layer State Changed, an event bit)
    the event bits are cleared by writing 1 to them; · = bits 15:9, which pci_regs.h does not name
```

## DETAILS

DETAILS first follows the port driver as it creates the hot-plug service object of a port and gives it a vector that PME and bandwidth notification share. It then sets out the controller fields the two stages share and the probe that installs both stages and opens Slot Control's enables. The hard stage comes next, from the test that claims an interrupt through the parent check, the Slot Status read, the power fault mask, the acknowledgement loop and Command Completed to the latch into the word. The IRQ thread follows with its rerun of the hard stage, the exchange of the word and the dispatch, and then the requests that process context ORs into the same word, poll mode, suspend and resume, and removal. The last subsection lists the tracepoints, messages, hand-offs and parameters that expose both stages.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at commit 8d3ae59288f1 with the options the campaign adds, among them native PCIe hot-plug and dynamic debug, on x86-64 with ACPI. The table lists the options the prose below names, the value the page assumes and what each decides on the interrupt paths.

| option | assumed | what it decides here |
|---|---|---|
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y | the PCI hot-plug core that pciehp's option depends on |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | the port driver that creates the hot-plug service object and its vector |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | builds pciehp; unset, the port driver clears the hot-plug interrupt enables firmware left |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | lets the hard stage test MSI mode and loop until Slot Status reads zero |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | gives the thread a real test for link changes caused by containment |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | compiles the runtime suspend and resume callbacks that mask and unmask the interrupt |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y | compiles the system sleep callbacks of pciehp |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the debug messages of both stages dynamic-debug sites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would define `DEBUG` for the files of pciehp |

The table indexes the prose. Each option's effect is stated where it applies in the subsections below.

### The port driver gives the hot-plug service an object

pciehp never finds a hot-plug port by itself. The port driver, portdrv, decides which services a Root Port or Switch Downstream Port offers and creates a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) for each, the port driver's service instance, which stands for a service of a port and is not a PCIe device of its own. pciehp is the driver that binds to the hot-plug service object, and the object brings the vector that the rest of this page follows.

The hot-plug service exists only where [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) grants it. Read its first test for the ports that qualify and for what the port driver does to Slot Control when pciehp is not built.

```c
/* drivers/pci/pcie/portdrv.c:218 */
static int get_port_device_capability(struct pci_dev *dev)
{
	struct pci_host_bridge *host = pci_find_host_bridge(dev->bus);
	int services = 0;

	if (dev->is_pciehp &&
	    (pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT ||
	     pci_pcie_type(dev) == PCI_EXP_TYPE_DOWNSTREAM) &&
	    (pcie_ports_native || host->native_pcie_hotplug)) {
		services |= PCIE_PORT_SERVICE_HP;

		/*
		 * Disable hot-plug interrupts in case they have been enabled
		 * by the BIOS and the hot-plug service driver won't be loaded
		 * to handle them.
		 */
		if (!IS_ENABLED(CONFIG_HOTPLUG_PCI_PCIE))
			pcie_capability_clear_word(dev, PCI_EXP_SLTCTL,
				PCI_EXP_SLTCTL_CCIE | PCI_EXP_SLTCTL_HPIE);
	}
```

A port gets the service when the PCI core marked it [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484), it is a Root Port or a Switch Downstream Port, and the OS controls hot-plug natively, through `pcie_ports=native` or the host bridge's [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654). When [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) is unset, the same branch clears [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) and [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) in Slot Control, so that a hot-plug interrupt firmware enabled finds no port left raising it. The option itself is a boolean that depends on [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) and [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), as its entry in [`Kconfig`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig) shows.

```c
/* drivers/pci/pcie/Kconfig:16 */
config HOTPLUG_PCI_PCIE
	bool "PCI Express Hotplug driver"
	depends on HOTPLUG_PCI && PCIEPORTBUS
	default y if USB4
	help
	  Say Y here if you have a motherboard that supports PCIe native
	  hotplug.

	  Thunderbolt/USB4 PCIe tunneling depends on native PCIe hotplug.

	  When in doubt, say N.
```

pciehp is therefore built into the kernel or absent, and the page assumes it built in. The object the port driver creates for the granted service is a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59); read it for the member that carries the vector.

```c
/* drivers/pci/pcie/portdrv.h:59 */
struct pcie_device {
	int		irq;	    /* Service IRQ/MSI/MSI-X Vector */
	struct pci_dev *port;	    /* Root/Upstream/Downstream Port */
	u32		service;    /* Port service this device represents */
	void		*priv_data; /* Service Private Data */
	struct device	device;     /* Generic Device Interface */
};
```

[`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) is the Linux interrupt number the service uses, and pciehp passes it to the interrupt core unchanged. [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) is the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) of the port whose registers pciehp reads, [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) is the service bit, [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) holds the [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) that pciehp's probe stores there, and [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the device-model device pciehp binds to. [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) fills these members from the port and the vector the port driver chose for the service; read its first stage for the copy of the vector.

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
```

The vector comes from the array the port driver filled before it created the services, indexed by the service's bit number. The next subsection shows how that array gives the hot-plug service the same vector as two other services.

### PME, hot-plug and bandwidth notification share one vector

A port signals PME, hot-plug events and bandwidth changes through one MSI or MSI-X entry, the one its PCI Express Capabilities register names in [`PCI_EXP_FLAGS_IRQ`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L496). The port driver maps that entry to a Linux vector and gives the vector to all three services, so the hard stage of pciehp shares its interrupt with the handlers of the other two. [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57) reads the entry number; read its first block for the three services it groups.

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

The Interrupt Message Number becomes `pme`, and `nvec`, a local of [`pcie_message_numbers()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L57), counts the vectors needed to reach it. AER and DPC read their own message numbers from their own capabilities further down the function. [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) allocates the vectors and assigns them; read the stage that gives the three services their vector.

```c
/* drivers/pci/pcie/portdrv.c:113 */
static int pcie_port_enable_irq_vec(struct pci_dev *dev, int *irqs, int mask)
{
	int nr_entries, nvec, pcie_irq;
	u32 pme = 0, aer = 0, dpc = 0;

	... /* 33 lines, to :151 */
	/* PME, hotplug and bandwidth notification share an MSI/MSI-X vector */
	if (mask & (PCIE_PORT_SERVICE_PME | PCIE_PORT_SERVICE_HP |
		    PCIE_PORT_SERVICE_BWCTRL)) {
		pcie_irq = pci_irq_vector(dev, pme);
		irqs[PCIE_PORT_SERVICE_PME_SHIFT] = pcie_irq;
		irqs[PCIE_PORT_SERVICE_HP_SHIFT] = pcie_irq;
		irqs[PCIE_PORT_SERVICE_BWCTRL_SHIFT] = pcie_irq;
	}
```

The three slots of `irqs`, the array the caller passed in, receive the same `pcie_irq`, the vector of entry `pme`. A port without MSI or MSI-X, or a Root Port under `pcie_pme=nomsi`, takes the INTx path of [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177); read it for the fallback and for the value a service keeps when no interrupt is found.

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

Under INTx every service of the port gets the port's one INTx vector, [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) answering for the `pcie_pme=nomsi` parameter. When even INTx fails, the slots keep -1 and the function returns `-ENODEV`. [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) then keeps the hot-plug service alone; read the stage where it narrows the services.

```c
/* drivers/pci/pcie/portdrv.c:331 */
static int pcie_port_device_register(struct pci_dev *dev)
{
	int status, capabilities, i, nr_service;
	int irqs[PCIE_PORT_DEVICE_MAXSERVICES];
	... /* 12 lines, to :347 */
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

The comment names pciehp's poll mode as the reason the hot-plug service survives without an interrupt. The figure summarizes the sharing on a Root Port whose services use MSI or MSI-X.

```text
    One Interrupt Message Number serves three services of a port
    ────────────────────────────────────────────────────────────

    ┌───────────────────────────────────────────────────────────────┐
    │ struct pci_dev of a Root Port with a slot                     │
    │   PCI Express Capabilities: Interrupt Message Number n        │
    │   AER and DPC capabilities: message numbers of their own      │
    └───────────────────────────────┬───────────────────────────────┘
                                    │ MSI or MSI-X entry n becomes one vector v
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
    ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
    │ PME service       │ │ hot-plug service  │ │ bandwidth service │
    │ irq = v           │ │ irq = v           │ │ irq = v           │
    │ shared action     │ │ hard stage, thread│ │ shared action     │
    └───────────────────┘ └───────────────────┘ └───────────────────┘

    each service is a struct pcie_device that names the port and holds irq; all three
    request v with IRQF_SHARED, so the interrupt core calls each action when v fires
    a Switch Downstream Port has no PME service, and the bandwidth service exists only on a
    link with Link Bandwidth Notification and more than one speed
    with INTx every service of the port gets the port's INTx vector; with no vector at all
    only the hot-plug service is kept, its irq left at -1 for poll mode
```

On a Root Port the hot-plug service therefore shares its vector with the PME service, and on either kind of port with the bandwidth service when the link has one. The PME service requests the vector with `IRQF_SHARED`, as [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) shows, and pciehp must do the same.

```c
/* drivers/pci/pcie/pme.c:326 */
static int pcie_pme_probe(struct pcie_device *srv)
{
	... /* 22 lines, to :350 */
	ret = request_irq(srv->irq, pcie_pme_irq, IRQF_SHARED, "PCIe PME", srv);
	if (ret) {
		kfree(data);
		return ret;
	}
```

A shared vector runs every handler registered on it, so the hard stage must recognize an interrupt its port did not raise, the first thing it tests.

### The controller holds the word the two stages share

The two stages run in different contexts and at different times, so what the hard stage learns has to wait somewhere for the thread. pciehp keeps that state, with everything else it knows about a slot, in a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), one object for the controller and its slot, since the comment above the definition notes that the two stand in a one-to-one relationship. Read the definition for the members the interrupt paths read and write.

```c
/* drivers/pci/hotplug/pciehp.h:91 */
struct controller {
	struct pcie_device *pcie;
	u64 dsn;

	u32 slot_cap;				/* capabilities and quirks */
	unsigned int inband_presence_disabled:1;

	u16 slot_ctrl;				/* control register access */
	struct mutex ctrl_lock;
	unsigned long cmd_started;
	unsigned int cmd_busy:1;
	wait_queue_head_t queue;

	atomic_t pending_events;		/* event handling */
	unsigned int notification_enabled:1;
	unsigned int power_fault_detected;
	struct task_struct *poll_thread;

	u8 state;				/* state machine */
	struct mutex state_lock;
	struct delayed_work button_work;

	struct hotplug_slot hotplug_slot;	/* hotplug core interface */
	struct rw_semaphore reset_lock;
	unsigned int depth;
	unsigned int ist_running;
	int request_result;
	wait_queue_head_t requester;
};
```

[`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) is the word between the stages, an `atomic_t` that the hard stage and the requesters OR bits into and the thread empties. [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) records that the handler pair or the poll thread is installed, [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) keeps a power fault from being reported twice, and [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) holds the poll thread in poll mode. [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116), [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) and [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) let a sysfs request wait for the thread and collect its result. The group under the comment `control register access` holds the Slot Control protocol: [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) caches the register, [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) serializes writes, and [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100), [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) and [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) track and await Command Completed. The rest serve other paths, [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) and [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) the service object and the serial number of the device in the slot, [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) and [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) the capabilities, the state machine group the slot's state, and [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) with [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) the reset serialization.

Both stages receive the controller as their cookie, and they reach the port's registers from it through the service object, the two steps [`ctrl_dev()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L49) takes.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:49 */
static inline struct pci_dev *ctrl_dev(struct controller *ctrl)
{
	return ctrl->pcie->port;
}
```

[`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) leads to the service object and its [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) to the port, the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose PCIe capability holds the Slot registers. The figure links the three objects by the members that join them.

```text
    The objects the two stages reach from their cookie
    ──────────────────────────────────────────────────

    ┌──────────────────────────────┐   priv_data   ┌──────────────────────────────┐
    │ struct pcie_device           ├──────────────▶│ struct controller            │
    │   irq: the vector to request │◀──────────────┤   pending_events, its flags  │
    │                              │     pcie      │   slot_ctrl, slot_cap        │
    └──────────────┬───────────────┘               │   hotplug_slot, embedded     │
                   │ port                          └──────────────────────────────┘
                   ▼                                              ▲
    ┌──────────────────────────────┐                              │ dev_id: both stages receive
    │ struct pci_dev of the port   │                              │ the controller as cookie
    │   PCIe capability with the   │
    │   Slot registers             │
    └──────────────────────────────┘

    the hard stage and the thread reach the port from the controller in two steps,
    through pcie and then port
```

The service object's [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) points back at the controller, which is how the suspend and resume callbacks, called with the service object, find it.

The thread needs a way to learn about work that no Slot Status bit describes. pciehp stores such requests in the same word above the 16 bits of Slot Status, with the two flags [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) and [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) that the header defines after the slot states; read the comment for the reason they start at bit 16.

```c
/* drivers/pci/hotplug/pciehp.h:140 */
/**
 * DOC: Flags to request an action from the IRQ thread
 *
 * These are stored together with events read from the Slot Status register,
 * hence must be greater than its 16-bit width.
 *
 * %DISABLE_SLOT: Disable the slot in response to a user request via sysfs or
 *	an Attention Button press after the 5 second delay
 * %RERUN_ISR: Used by the IRQ handler to inform the IRQ thread that the
 *	hotplug port was inaccessible when the interrupt occurred, requiring
 *	that the IRQ handler is rerun by the IRQ thread after it has made the
 *	hotplug port accessible by runtime resuming its parents to D0
 */
#define DISABLE_SLOT		(1 << 16)
#define RERUN_ISR		(1 << 17)
```

[`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) carries a disable request from sysfs or from the end of the button delay, and [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) carries the hard stage's note that it could not read Slot Status. Both are placed above bit 15 because the word also holds Slot Status event bits, which are 16 bits wide. The plot shows which bits the word can hold on these paths.

```text
    The bits of ctrl->pending_events, the word between the two stages
    ─────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    word  │           unused          │R│D│    unused   │L│  ·  │·│P│·│F│A│
          │          (31:18)          │ │ │    (15:9)   │ │(7:5)│ │ │ │ │ │
          └───────────────────────────┴─┴─┴─────────────┴─┴─────┴─┴─┴─┴─┴─┘

    A      = PCI_EXP_SLTSTA_ABP (0x0001, Attention Button Pressed, latched from Slot Status)
    F      = PCI_EXP_SLTSTA_PFD (0x0002, Power Fault Detected, latched once until slot power returns)
    P      = PCI_EXP_SLTSTA_PDC (0x0008, Presence Detect Changed, latched or ORed in by a request)
    L      = PCI_EXP_SLTSTA_DLLSC (0x0100, Data Link Layer State Changed, latched or ORed in by a request)
    D      = DISABLE_SLOT (1 << 16, a request to disable the slot, from sysfs or the button delay)
    R      = RERUN_ISR (1 << 17, the hard stage found the port's parent suspended)
    ·      = never set: Command Completed (bit 4) is finished in the hard stage; MRL Sensor
             Changed (bit 2) and the state bits 7:5 fall outside the hard stage's mask
    unused = bits 31:18 and 15:9, which no writer sets
```

At v7.2 Command Completed never reaches the word because the hard stage finishes it and no requester asks for it, and the bits of Slot Status outside the hard stage's mask never enter it. The controller begins its life zeroed, as the start of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) shows.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1006 */
struct controller *pcie_init(struct pcie_device *dev)
{
	struct controller *ctrl;
	u32 slot_cap, slot_cap2;
	u8 poweron;
	struct pci_dev *pdev = dev->port;
	struct pci_bus *subordinate = pdev->subordinate;

	ctrl = kzalloc_obj(*ctrl);
	if (!ctrl)
		return NULL;

	ctrl->pcie = dev;
```

`kzalloc_obj()` returns the controller zeroed, so the word is empty and every flag is clear before the port driver's service object is stored in [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92). From here several functions write the four fields the two stages share, at the events the strip follows.

```text
    Four controller fields through one run, from allocation to removal
    ──────────────────────────────────────────────────────────────────
    fields: pending_events, power_fault_detected, ist_running and notification_enabled of struct controller

    time ───────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event                alloc   enable  irq     pass    rerun     xchg    done    request  pass 2         remove
                         ▼       ▼       ▼       ▼       ▼         ▼       ▼       ▼        ▼              ▼
                         ┌───────────────┬───────┬───────┬─────────┬───────────────┬────────┬───────────────────────┐
    pending_events       │ «1» 0         │ «3» R │ «8» 0 │ «6» F|P │ «9» 0         │ «11» P │ «9» 0                 │
                         └───────────────┴───────┴───────┴─────────┴───────────────┴────────┴───────────────────────┘
                         ┌───────────────────────────────┬──────────────────────────────────┬───────────────────────┐
    power_fault_detected │ «1» 0                         │ «4» 1                            │ «5» 0                 │
                         └───────────────────────────────┴──────────────────────────────────┴───────────────────────┘
                         ┌───────────────────────┬─────────────────────────┬────────────────┬───────────────────────┐
    ist_running          │ «1» 0                 │ «7» 1                   │ «10» 0         │ «7» 1, «10» 0         │
                         └───────────────────────┴─────────────────────────┴────────────────┴───────────────────────┘
                         ┌───────┬─────────────────────────────────────────────────────────────────────────┬────────┐
    notification_enabled │ «1» 0 │ «2» 1                                                                   │ «12» 0 │
                         └───────┴─────────────────────────────────────────────────────────────────────────┴────────┘

    R = RERUN_ISR, F = PCI_EXP_SLTSTA_PFD, P = PCI_EXP_SLTSTA_PDC; pass 2 is the thread pass that serves the request

    «1»  pcie_init                  pciehp_hpc.c:1014  allocates the controller zeroed through kzalloc_obj
    «2»  pcie_init_notification     :965               sets notification_enabled once both stages are installed
    «3»  pciehp_isr                 :648               ORs RERUN_ISR into the word through atomic_or
    «4»  pciehp_isr                 :677               sets power_fault_detected on the first fault read
    «5»  pciehp_power_on_slot       :545               clears power_fault_detected before powering the slot
    «6»  pciehp_isr                 :724               ORs the remaining Slot Status events through atomic_or
    «7»  pciehp_ist                 :735               sets ist_running as a thread pass begins
    «8»  pciehp_ist                 :739               clears RERUN_ISR through atomic_fetch_and before the rerun
    «9»  pciehp_ist                 :747               exchanges the word for zero through atomic_xchg
    «10» pciehp_ist                 :795               clears ist_running as the thread pass ends
    «11» pciehp_request             pciehp_ctrl.c:143  ORs a process-context request through atomic_or
    «12» pcie_shutdown_notification pciehp_hpc.c:974   clears notification_enabled after the handler is freed
```

«1» [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller zeroed through `kzalloc_obj()`. «2» [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) sets [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) once both stages are installed. «3» [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) ORs [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) into the word through `atomic_or()` when the port's parent is suspended. «4» `pciehp_isr()` sets [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) on the first fault it reads. «5» [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) clears the flag before it powers the slot. «6» `pciehp_isr()` ORs the remaining Slot Status events into the word through `atomic_or()`. «7» [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) sets [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) as a thread pass begins. «8» `pciehp_ist()` clears [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) through `atomic_fetch_and()` before it reruns the hard stage. «9» `pciehp_ist()` exchanges the word for zero through `atomic_xchg()`. «10» `pciehp_ist()` clears [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) as the pass ends. «11» [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) ORs a request from process context into the word through `atomic_or()`. «12» [`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969) clears [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) after the handler is freed.

The marks follow the order in which the page reads their sites, while the strip runs in time, so two stretches stand out of numeric order. In this run the hard stage reruns inside the thread's pass, which puts «4» and «6» after «7» and «8», and the power-on «5», read beside the fault mask it undoes, happens in the pass that serves the request «11». Two writers of the word are left out of the strip. [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) in pciehp_hpc.c masks link and presence bits that a containment or a reset caused, and [`remove_board()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L112) in pciehp_ctrl.c masks those a power-off caused, both with `atomic_and()` on paths this page does not follow. [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), which the hard stage also writes, belongs to the Slot Control protocol, whose other writers are [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), [`pcie_poll_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L86) and the resume callbacks in [`pciehp_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c), and is left out with it.

### Probe installs both stages before it opens the enables

An interrupt that arrives with no handler installed is lost, and on a shared vector it could be blamed on the other services. pciehp's probe therefore requests the handler pair first and opens Slot Control's enables after it, once the controller and the slot are set up. Read [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) from the call that installs the stages to the end, with the earlier setup folded.

```c
/* drivers/pci/hotplug/pciehp_core.c:185 */
static int pciehp_probe(struct pcie_device *dev)
{
	int rc;
	struct controller *ctrl;
	... /* 29 lines, to :218 */
	/* Enable events after we have setup the data structures */
	rc = pcie_init_notification(ctrl);
	if (rc) {
		ctrl_err(ctrl, "Notification initialization failed (%d)\n", rc);
		goto err_out_free_ctrl_slot;
	}

	/* Publish to user space */
	rc = pci_hp_add(&ctrl->hotplug_slot);
	if (rc) {
		ctrl_err(ctrl, "Publication to user space failed (%d)\n", rc);
		goto err_out_shutdown_notification;
	}

	pciehp_check_presence(ctrl);

	return 0;

err_out_shutdown_notification:
	pcie_shutdown_notification(ctrl);
err_out_free_ctrl_slot:
	cleanup_slot(ctrl);
err_out_release_ctlr:
	pciehp_release_ctrl(ctrl);
	return -ENODEV;
}
```

[`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) runs after the slot is set up and before the slot is published to user space, and a failure of the publication unwinds through [`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969). [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) then synthesizes an event when the slot's occupancy and its state disagree, the first request the thread receives. [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) itself requests and then enables.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:960 */
int pcie_init_notification(struct controller *ctrl)
{
	if (pciehp_request_irq(ctrl))
		return -1;
	pcie_enable_notification(ctrl);
	ctrl->notification_enabled = 1;
	return 0;
}
```

The request comes first and the enables second, and [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) is set only when both are done, which is «2» on the strip. A failed request returns -1 before any enable is written. [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) chooses between the two ways of running the stages.

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

With [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) set, no vector is requested, and `kthread_run()` starts [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) in a thread named after the slot, whose pointer lands in [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107). Otherwise [`request_threaded_irq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L2123) installs [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) as the hard stage and [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) as the thread on [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60), with `IRQF_SHARED` and the controller as the cookie both handlers receive. Without `IRQF_ONESHOT` the vector stays unmasked while the thread runs, which commit [7b4ce26bcf69](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=7b4ce26bcf697e3a4aa9ba2a5b456562e0fb7af4) ("PCI: pciehp: Convert to threaded IRQ") gives as the reason the hard stage acknowledges the events itself, so that the devices sharing the vector are not starved until the thread finishes.

```text
    Probe attaches the two stages, then opens Slot Control
    ──────────────────────────────────────────────────────

    before                                      after
    ┌───────────────────────────────────┐       ┌───────────────────────────────────┐
    │ vector v                          │       │ vector v                          │
    │   actions of the other services   │       │   actions of the other services   │
    │   no hot-plug action, no thread   │  ──▶  │   plus the hot-plug hard stage    │
    │                                   │       │   and its thread irq/v-pciehp     │
    ├───────────────────────────────────┤       ├───────────────────────────────────┤
    │ Slot Control enables              │       │ Slot Control enables              │
    │   as firmware left them           │       │   HPIE 1, DLLSCE 1, PFDE 0        │
    │                                   │       │   PDCE 1, or ABPE 1 with a button │
    │                                   │       │   CCIE 1 unless NCCS is set       │
    ├───────────────────────────────────┤       ├───────────────────────────────────┤
    │ notification_enabled 0            │       │ notification_enabled 1            │
    └───────────────────────────────────┘       └───────────────────────────────────┘

    in poll mode the after side holds the kernel thread pciehp_poll-<slot> in place of
    the hard stage's action and its thread, and HPIE and CCIE stay 0
```

After probe the vector carries the hard stage beside the actions of the other services, and the interrupt core has created the thread; read the stage of [`setup_irq_thread()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L1402) that names it.

```c
/* kernel/irq/manage.c:1401 */
static int
setup_irq_thread(struct irqaction *new, unsigned int irq, bool secondary)
{
	struct task_struct *t;

	if (!secondary) {
		t = kthread_create(irq_thread, new, "irq/%d-%s", irq,
				   new->name);
	} else {
		t = kthread_create(irq_thread, new, "irq/%d-s-%s", irq,
				   new->name);
```

The thread is named `irq/`, the vector's number, `-` and the `pciehp` that [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) passed as the action's name. Which enables the second half of [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) opens is the subject of the next subsection.

### The enables follow the slot's capabilities and the mode

Slot Control decides which events set their Slot Status bit into an interrupt and whether an interrupt is raised at all. pciehp opens a different set of enables depending on what the slot has and on whether it polls, and the set it chooses decides which bits the hard stage later finds. The enables are bits of [`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610), defined with the other Slot Control fields in pci_regs.h; read the block for the six enables and the gate.

```c
/* include/uapi/linux/pci_regs.h:610 */
#define PCI_EXP_SLTCTL		0x18	/* Slot Control */
#define  PCI_EXP_SLTCTL_ABPE	0x0001	/* Attention Button Pressed Enable */
#define  PCI_EXP_SLTCTL_PFDE	0x0002	/* Power Fault Detected Enable */
#define  PCI_EXP_SLTCTL_MRLSCE	0x0004	/* MRL Sensor Changed Enable */
#define  PCI_EXP_SLTCTL_PDCE	0x0008	/* Presence Detect Changed Enable */
#define  PCI_EXP_SLTCTL_CCIE	0x0010	/* Command Completed Interrupt Enable */
#define  PCI_EXP_SLTCTL_HPIE	0x0020	/* Hot-Plug Interrupt Enable */
#define  PCI_EXP_SLTCTL_AIC	0x00c0	/* Attention Indicator Control */
#define  PCI_EXP_SLTCTL_ATTN_IND_SHIFT 6      /* Attention Indicator shift */
#define  PCI_EXP_SLTCTL_ATTN_IND_ON    0x0040 /* Attention Indicator on */
#define  PCI_EXP_SLTCTL_ATTN_IND_BLINK 0x0080 /* Attention Indicator blinking */
#define  PCI_EXP_SLTCTL_ATTN_IND_OFF   0x00c0 /* Attention Indicator off */
#define  PCI_EXP_SLTCTL_PIC	0x0300	/* Power Indicator Control */
#define  PCI_EXP_SLTCTL_PWR_IND_ON     0x0100 /* Power Indicator on */
#define  PCI_EXP_SLTCTL_PWR_IND_BLINK  0x0200 /* Power Indicator blinking */
#define  PCI_EXP_SLTCTL_PWR_IND_OFF    0x0300 /* Power Indicator off */
#define  PCI_EXP_SLTCTL_PCC	0x0400	/* Power Controller Control */
#define  PCI_EXP_SLTCTL_PWR_ON         0x0000 /* Power On */
#define  PCI_EXP_SLTCTL_PWR_OFF        0x0400 /* Power Off */
#define  PCI_EXP_SLTCTL_EIC	0x0800	/* Electromechanical Interlock Control */
#define  PCI_EXP_SLTCTL_DLLSCE	0x1000	/* Data Link Layer State Changed Enable */
#define  PCI_EXP_SLTCTL_ASPL_DISABLE	0x2000 /* Auto Slot Power Limit Disable */
```

[`PCI_EXP_SLTCTL_ABPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611), [`PCI_EXP_SLTCTL_PFDE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L612), [`PCI_EXP_SLTCTL_MRLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L613), [`PCI_EXP_SLTCTL_PDCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614) and [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) enable notification of single events, and [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) enables the interrupt for Command Completed. [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) is the gate, without which no event raises the hot-plug interrupt. The other fields drive indicators, power and the interlock. pciehp tests the slot's capabilities through macros over the cached Slot Capabilities, among them [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) and [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161); read the two that decide enables beside their neighbours.

```c
/* drivers/pci/hotplug/pciehp.h:156 */
#define ATTN_BUTTN(ctrl)	((ctrl)->slot_cap & PCI_EXP_SLTCAP_ABP)
#define POWER_CTRL(ctrl)	((ctrl)->slot_cap & PCI_EXP_SLTCAP_PCP)
#define MRL_SENS(ctrl)		((ctrl)->slot_cap & PCI_EXP_SLTCAP_MRLSP)
#define ATTN_LED(ctrl)		((ctrl)->slot_cap & PCI_EXP_SLTCAP_AIP)
#define PWR_LED(ctrl)		((ctrl)->slot_cap & PCI_EXP_SLTCAP_PIP)
#define NO_CMD_CMPL(ctrl)	((ctrl)->slot_cap & PCI_EXP_SLTCAP_NCCS)
#define PSN(ctrl)		(((ctrl)->slot_cap & PCI_EXP_SLTCAP_PSN) >> 19)
```

[`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) tests Attention Button Present and [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) tests No Command Completed Support in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95). The table gives the enables [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) opens and the condition behind each, before the function itself.

| enable | opened when | in poll mode |
|---|---|---|
| [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) | always | opened |
| [`PCI_EXP_SLTCTL_ABPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611) | [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) is true | opened under the same test |
| [`PCI_EXP_SLTCTL_PDCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614) | [`ATTN_BUTTN()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) is false | opened under the same test |
| [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) | always | left clear |
| [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) | [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) is false | left clear |
| [`PCI_EXP_SLTCTL_PFDE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L612) | never | left clear |

Read [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) for the comment that keeps power fault notification off and for the mask that bounds the write.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:821 */
static void pcie_enable_notification(struct controller *ctrl)
{
	u16 cmd, mask;

	/*
	 * TBD: Power fault detected software notification support.
	 *
	 * Power fault detected software notification is not enabled
	 * now, because it caused power fault detected interrupt storm
	 * on some machines. On those machines, power fault detected
	 * bit in the slot status register was set again immediately
	 * when it is cleared in the interrupt service routine, and
	 * next power fault detected interrupt was notified again.
	 */

	/*
	 * Always enable link events: thus link-up and link-down shall
	 * always be treated as hotplug and unplug respectively. Enable
	 * presence detect only if Attention Button is not present.
	 */
	cmd = PCI_EXP_SLTCTL_DLLSCE;
	if (ATTN_BUTTN(ctrl))
		cmd |= PCI_EXP_SLTCTL_ABPE;
	else
		cmd |= PCI_EXP_SLTCTL_PDCE;
	if (!pciehp_poll_mode)
		cmd |= PCI_EXP_SLTCTL_HPIE;
	if (!pciehp_poll_mode && !NO_CMD_CMPL(ctrl))
		cmd |= PCI_EXP_SLTCTL_CCIE;

	mask = (PCI_EXP_SLTCTL_PDCE | PCI_EXP_SLTCTL_ABPE |
		PCI_EXP_SLTCTL_PFDE |
		PCI_EXP_SLTCTL_HPIE | PCI_EXP_SLTCTL_CCIE |
		PCI_EXP_SLTCTL_DLLSCE);

	pcie_write_cmd_nowait(ctrl, cmd, mask);
	ctrl_dbg(ctrl, "%s: SLOTCTRL %x write cmd %x\n", __func__,
		 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL, cmd);
}
```

`cmd`, a local of the function, is the value and `mask` the set of bits the write may change, so the write sets the chosen enables, clears [`PCI_EXP_SLTCTL_PFDE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L612) and leaves the indicator, power and interlock fields as they are. Link events are always enabled, so a link going up or down counts as a hot-add or a removal, and a slot with an attention button reports its button and leaves presence changes unreported. [`PCI_EXP_SLTCTL_PFDE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L612) stays clear because, according to the comment, enabling it caused an interrupt storm on machines whose power fault bit was set again as soon as it was cleared, the change commit [5651c48cfafe](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=5651c48cfafef1b9a7ebdc00ebeb32f2af887a89) ("PCI pciehp: fix power fault interrupt storm problem") made. [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) follows [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) since commit [6d4671b534f6](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6d4671b534f6c084e92ef167a52dc47e55f636c4) ("PCI: pciehp: Enable Command Completed Interrupt only if supported"). The write goes through [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219), which with [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) wraps the Slot Control protocol.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:207 */
/**
 * pcie_write_cmd - Issue controller command
 * @ctrl: controller to which the command is issued
 * @cmd:  command value written to slot control register
 * @mask: bitmask of slot control register to be modified
 */
static void pcie_write_cmd(struct controller *ctrl, u16 cmd, u16 mask)
{
	pcie_do_write_cmd(ctrl, cmd, mask, true);
}

/* Same as above without waiting for the hardware to latch */
static void pcie_write_cmd_nowait(struct controller *ctrl, u16 cmd, u16 mask)
{
	pcie_do_write_cmd(ctrl, cmd, mask, false);
}
```

Both wrappers call [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), which takes [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99), waits for the previous command, writes the masked value and stores it in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98). [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) also waits for this command to complete, and the enables at probe use the variant that does not.

So far, the port driver has given the hot-plug service object a vector shared with PME and bandwidth notification, pciehp has allocated a zeroed controller, installed the hard stage and the thread on that vector and opened Slot Control's enables, and [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) is set. An event in the slot now raises the interrupt, and the hard stage is the first code that sees it.

### The hard stage claims only interrupts its port raised

A vector shared by several services carries interrupts that are not the hot-plug port's, and the interrupt core cannot tell them apart. It runs every action registered on the vector and lets each handler decide, which [`__handle_irq_event_percpu()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L185) shows; read the loop for the call of each handler, the tracepoints around it and what a handler's return value sets off.

```c
/* kernel/irq/handle.c:185 */
irqreturn_t __handle_irq_event_percpu(struct irq_desc *desc)
{
	irqreturn_t retval = IRQ_NONE;
	unsigned int irq = desc->irq_data.irq;
	struct irqaction *action;

	for_each_action_of_desc(desc, action) {
		... /* 9 lines, to :201 */
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

	return retval;
}
```

Every action on the vector runs with its own `dev_id`, which for pciehp is the [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), and the `irq:irq_handler_entry` and `irq:irq_handler_exit` tracepoints, defined at [`irq.h:53`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/irq.h#L53) and [`irq.h:83`](https://elixir.bootlin.com/linux/v7.2/source/include/trace/events/irq.h#L83), fire around each call. A return of `IRQ_WAKE_THREAD` wakes the thread of that action alone through [`__irq_wake_thread()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L61), and the results of the actions are ORed together. pciehp's hard stage, [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), is a sequence of decisions that ends either with a return that lets the core move on or with the events latched for the thread, as the chart shows.

```text
    What the hard stage decides on each call
    ────────────────────────────────────────

    ┌─────────────────────────────────────┐
    │ port in D3cold, or HPIE clear       ├──────▶ IRQ_NONE: not this port's interrupt
    │ outside poll mode?                  │
    └──────────────────┬──────────────────┘
                       │ no
    ┌──────────────────▼──────────────────┐
    │ parent runtime-suspended?           ├──────▶ mask the vector, set RERUN_ISR,
    └──────────────────┬──────────────────┘
                       │ no                        IRQ_WAKE_THREAD
    ┌──────────────────▼──────────────────┐
    │ read Slot Status                    │◀──────────────────────────┐
    │ read failed (all ones)?             ├──────▶ IRQ_NONE           │
    └──────────────────┬──────────────────┘                           │
                       │ no                                           │
    ┌──────────────────▼──────────────────┐                           │
    │ keep the event bits, drop a power   │                           │
    │ fault already reported, add the     │                           │
    │ rest to the events seen             │                           │
    └──────────────────┬──────────────────┘                           │
                       │                                              │
    ┌──────────────────▼──────────────────┐                           │
    │ no event seen at all?               ├──────▶ IRQ_NONE           │
    └──────────────────┬──────────────────┘                           │
                       │ no                                           │
    ┌──────────────────▼──────────────────┐                           │
    │ write the bits just read back       │                           │
    └──────────────────┬──────────────────┘                           │
                       │                                              │
    ┌──────────────────▼──────────────────┐                           │
    │ bits written, MSI on and not poll   ├──────▶ yes, read again ───┘
    │ mode?                               │
    └──────────────────┬──────────────────┘
                       │ no
    ┌──────────────────▼──────────────────┐
    │ Command Completed? clear cmd_busy   │
    │ and wake the Slot Control writer    │
    └──────────────────┬──────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │ only Command Completed was seen, or ├──────▶ IRQ_HANDLED
    │ the port ignores hot-plug?          │
    └──────────────────┬──────────────────┘
                       │ no
    ┌──────────────────▼──────────────────┐
    │ OR the events into pending_events   │
    └──────────────────┬──────────────────┘
                       ▼
                IRQ_WAKE_THREAD

    each arrow to the right leaves the handler with the value it names
```

The handler is read in six pieces, each a stage of the chart.

| piece | lines | stage |
|---|---|---|
| ❶ | pciehp_hpc.c:623-637 | refuses an interrupt the port cannot have raised |
| ❷ | pciehp_hpc.c:638-652 | sends the work to the thread while the parent is suspended |
| ❸ | pciehp_hpc.c:653-669 | reads Slot Status and keeps its event bits |
| ❹ | pciehp_hpc.c:670-685 | reports a power fault once and gives up on an empty read |
| ❺ | pciehp_hpc.c:686-702 | writes the bits back, again while an MSI port holds bits |
| ❻ | pciehp_hpc.c:703-726 | finishes Command Completed and latches the rest |

Piece ❶ of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) recovers the controller and the port from the cookie and applies the test the comment derives from the specification.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:623 */
static irqreturn_t pciehp_isr(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	struct device *parent = pdev->dev.parent;
	u16 status, events = 0;

	/*
	 * Interrupts only occur in D3hot or shallower and only if enabled
	 * in the Slot Control register (PCIe r4.0, sec 6.7.3.4).
	 */
	if (pdev->current_state == PCI_D3cold ||
	    (!(ctrl->slot_ctrl & PCI_EXP_SLTCTL_HPIE) && !pciehp_poll_mode))
		return IRQ_NONE;

```

A port in D3cold cannot have raised the interrupt, and outside poll mode neither can a port whose cached Slot Control has [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) clear, so both return `IRQ_NONE`. The second test reads [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), the copy every Slot Control write leaves, and it decides the case where suspend has closed the gate and the PME service's interrupt still arrives on the shared vector, the case commit [720d6a671a6e](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=720d6a671a6e2cf2b9ed032279b7c21c122bed7e) ("PCI: pciehp: Do not handle events if interrupts are masked") added it for. pciehp leaves the gate closed in poll mode, so the test is skipped there. A port that passes may still be unreachable, which the next piece handles.

### A suspended parent defers the Slot Status read

Slot Status is part of the port's configuration space, which is reachable only while the bridges above the port are in D0. A port can raise its interrupt while its parents are runtime-suspended, which commit [6b08c3854cfd](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6b08c3854cfdc5d13165880e2b54642c47edc405) ("PCI: pciehp: Support interrupts sent from D3hot") reports for a class of hot-plug port, and resuming a parent sleeps, which the hard stage may not do. Piece ❷ of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) holds the parent awake or hands the read over.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:638 */
	/*
	 * Keep the port accessible by holding a runtime PM ref on its parent.
	 * Defer resume of the parent to the IRQ thread if it's suspended.
	 * Mask the interrupt until then.
	 */
	if (parent) {
		pm_runtime_get_noresume(parent);
		if (!pm_runtime_active(parent)) {
			pm_runtime_put(parent);
			disable_irq_nosync(irq);
			atomic_or(RERUN_ISR, &ctrl->pending_events);
			return IRQ_WAKE_THREAD;
		}
	}

```

`pm_runtime_get_noresume()` takes a runtime PM reference on the parent without resuming it. When the parent is active, the reference keeps it so until the hard stage puts it back after the read. When the parent is suspended, the stage drops the reference, masks the vector with `disable_irq_nosync()`, ORs [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), which is «3» on the strip, and returns `IRQ_WAKE_THREAD` without touching Slot Status. The commit chose to mask the vector by hand in place of requesting it with `IRQF_ONESHOT`, to keep the masked interval as short as possible. The thread unmasks the vector after it has rerun the hard stage, as its first piece shows later.

### The hard stage keeps event bits and reports faults once

Slot Status, [`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633), holds two kinds of bit. Event bits latch a change until software writes 1 to them, and state bits report the present condition of the slot. The hard stage needs the events, and the bit definitions in pci_regs.h tell the kinds apart; read them for the five event bits pciehp handles.

```c
/* include/uapi/linux/pci_regs.h:633 */
#define PCI_EXP_SLTSTA		0x1a	/* Slot Status */
#define  PCI_EXP_SLTSTA_ABP	0x0001	/* Attention Button Pressed */
#define  PCI_EXP_SLTSTA_PFD	0x0002	/* Power Fault Detected */
#define  PCI_EXP_SLTSTA_MRLSC	0x0004	/* MRL Sensor Changed */
#define  PCI_EXP_SLTSTA_PDC	0x0008	/* Presence Detect Changed */
#define  PCI_EXP_SLTSTA_CC	0x0010	/* Command Completed */
#define  PCI_EXP_SLTSTA_MRLSS	0x0020	/* MRL Sensor State */
#define  PCI_EXP_SLTSTA_PDS	0x0040	/* Presence Detect State */
#define  PCI_EXP_SLTSTA_EIS	0x0080	/* Electromechanical Interlock Status */
#define  PCI_EXP_SLTSTA_DLLSC	0x0100	/* Data Link Layer State Changed */
```

[`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634), [`PCI_EXP_SLTSTA_PFD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L635), [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637), [`PCI_EXP_SLTSTA_CC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L638) and [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) are the events this page follows. [`PCI_EXP_SLTSTA_MRLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L636) is an event pciehp leaves alone, and [`PCI_EXP_SLTSTA_MRLSS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L639), [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640) and [`PCI_EXP_SLTSTA_EIS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L641) are states. Piece ❸ of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) reads the register at the `read_status` label, which the acknowledgement loop jumps back to.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:653 */
read_status:
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &status);
	if (PCI_POSSIBLE_ERROR(status)) {
		ctrl_info(ctrl, "%s: no response from device\n", __func__);
		if (parent)
			pm_runtime_put(parent);
		return IRQ_NONE;
	}

	/*
	 * Slot Status contains plain status bits as well as event
	 * notification bits; right now we only want the event bits.
	 */
	status &= PCI_EXP_SLTSTA_ABP | PCI_EXP_SLTSTA_PFD |
		  PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_CC |
		  PCI_EXP_SLTSTA_DLLSC;

```

A read that returns all ones, the value [`PCI_POSSIBLE_ERROR()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L175) tests for, means the port did not answer, and the stage prints `no response from device`, puts the parent back and returns `IRQ_NONE`. Otherwise `status`, a local of the handler, keeps the five event bits. Piece ❹ of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) treats Power Fault Detected apart from the others.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:670 */
	/*
	 * If we've already reported a power fault, don't report it again
	 * until we've done something to handle it.
	 */
	if (ctrl->power_fault_detected)
		status &= ~PCI_EXP_SLTSTA_PFD;
	else if (status & PCI_EXP_SLTSTA_PFD)
		ctrl->power_fault_detected = true;

	events |= status;
	if (!events) {
		if (parent)
			pm_runtime_put(parent);
		return IRQ_NONE;
	}

```

Power Fault Detected differs from the other events because writing it back does not clear it while the fault lasts. commit [23584c1ed3e1](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=23584c1ed3e15a6f4bfab8dc5a88d94ab929ee12) ("PCI: pciehp: Fix infinite loop in IRQ handler upon power fault") quotes the specification's main power fault latch, which only turning slot power off clears, and records that the acknowledgement loop spun on the bit while the thread was expected to set the flag. Since that commit the hard stage sets [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) itself, «4» on the strip, and masks the bit from every later read. `events`, the handler's running set across loop iterations, collects what is left, and an empty set ends the call with `IRQ_NONE`. The flag is cleared in one place at v7.2, when the slot is powered on, at the start of [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534).

```c
/* drivers/pci/hotplug/pciehp_hpc.c:534 */
int pciehp_power_on_slot(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;
	int retval;

	/* Clear power-fault bit from previous power failures */
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	if (slot_status & PCI_EXP_SLTSTA_PFD)
		pcie_capability_write_word(pdev, PCI_EXP_SLTSTA,
					   PCI_EXP_SLTSTA_PFD);
	ctrl->power_fault_detected = 0;
```

[`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) writes Power Fault Detected back and clears the flag, «5» on the strip, before it turns slot power on, so a fault that persists is read and reported again. Its caller at v7.2 is [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62), and only for a slot whose Slot Capabilities report a power controller; read the stage that powers the slot and later tests the flag.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:62 */
static int board_added(struct controller *ctrl)
{
	int retval = 0;
	struct pci_bus *parent = ctrl->pcie->port->subordinate;

	if (POWER_CTRL(ctrl)) {
		/* Power on slot */
		retval = pciehp_power_on_slot(ctrl);
		if (retval)
			return retval;
	}
	... /* 9 lines, to :82 */
	/* Check for a power fault */
	if (ctrl->power_fault_detected || pciehp_query_power_fault(ctrl)) {
		ctrl_err(ctrl, "Slot(%s): Power fault\n", slot_name(ctrl));
		retval = -EIO;
		goto err_exit;
	}
```

[`POWER_CTRL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157) guards the power-on, while the test of [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) runs on every slot. On a slot without Power Controller Present nothing at v7.2 clears the flag after the controller's allocation, so once the hard stage has latched a fault there, [`board_added()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L62) refuses the slot with `-EIO` until the controller is removed and probed again. What remains in `events` after this piece is acknowledged next.

### The hard stage acknowledges events until Slot Status reads zero

Writing an event bit back with 1 clears it and lets the port signal the next change. The comment in the next piece cites the specification's rule that a port in MSI mode sends no new interrupt until every event bit reads zero. Piece ❺ of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) writes back what it read and goes back to the read while that rule could hold an event hostage.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:686 */
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

	ctrl_dbg(ctrl, "pending interrupts %#06x from Slot Status\n", events);
	if (parent)
		pm_runtime_put(parent);

```

The write clears exactly the bits read, which is `status`, and with MSI enabled and poll mode off the handler jumps back to `read_status`. A bit that rose between the read and the write is then read, added to `events` and written back in turn, and the loop ends when a read returns no event bit. [`pci_dev_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L829) answers whether the port uses MSI or MSI-X, and [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) decides what it can answer.

```c
/* include/linux/pci.h:828 */
#ifdef CONFIG_PCI_MSI
static inline bool pci_dev_msi_enabled(struct pci_dev *pci_dev)
{
	return pci_dev->msi_enabled || pci_dev->msix_enabled;
}
#else
static inline bool pci_dev_msi_enabled(struct pci_dev *pci_dev) { return false; }
#endif
```

With [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) set the test reads the port's [`msi_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L469) and [`msix_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L470), and without it the stub returns false and the handler never loops. The race the loop closes, which commit [8edf5332c393](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=8edf5332c39340b9583cf9cba659eb7ec71f75b5) ("PCI: pciehp: Fix MSI interrupt race") fixed after the presence and link bits were seen rising together, is drawn below.

```text
    A bit set between the read and the write-back keeps an MSI port silent
    ──────────────────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────▶
    hard stage   reads Slot Status                writes PDC back
                 PDC ├──────────────────────────────┤ Slot Status still holds DLLSC
                                    ▲
    port                            │ sets DLLSC

    Slot Status is not zero after the write, so an MSI port sends no new message for
    DLLSC; the hard stage reads again, finds DLLSC and writes it back, and leaves the
    loop when a read returns no event bit
```

Under INTx and in poll mode the handler writes once and goes on. After the loop it prints the collected set, `pending interrupts %#06x from Slot Status`, at the debug level and puts the parent's runtime PM reference back.

### The hard stage finishes Command Completed and latches the rest

A write to Slot Control is a command, and the port reports that it has carried one out by setting Command Completed. pciehp spaces commands by waiting for that report in [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112), which sleeps on [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) when the interrupt can deliver the report and polls Slot Status otherwise; read it for the two ways of waiting and the timeout.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:112 */
static void pcie_wait_cmd(struct controller *ctrl)
{
	unsigned int msecs = pciehp_poll_mode ? 2500 : 1000;
	unsigned long duration = msecs_to_jiffies(msecs);
	unsigned long cmd_timeout = ctrl->cmd_started + duration;
	unsigned long now, timeout;
	int rc;

	/*
	 * If the controller does not generate notifications for command
	 * completions, we never need to wait between writes.
	 */
	if (NO_CMD_CMPL(ctrl))
		return;

	if (!ctrl->cmd_busy)
		return;

	/*
	 * Even if the command has already timed out, we want to call
	 * pcie_poll_cmd() so it can clear PCI_EXP_SLTSTA_CC.
	 */
	now = jiffies;
	if (time_before_eq(cmd_timeout, now))
		timeout = 1;
	else
		timeout = cmd_timeout - now;

	if (ctrl->slot_ctrl & PCI_EXP_SLTCTL_HPIE &&
	    ctrl->slot_ctrl & PCI_EXP_SLTCTL_CCIE)
		rc = wait_event_timeout(ctrl->queue, !ctrl->cmd_busy, timeout);
	else
		rc = pcie_poll_cmd(ctrl, jiffies_to_msecs(timeout));

	if (!rc)
		ctrl_info(ctrl, "Timeout on hotplug command %#06x (issued %u msec ago)\n",
			  ctrl->slot_ctrl,
			  jiffies_to_msecs(jiffies - ctrl->cmd_started));
}
```

A slot that reports No Command Completed Support returns at once through [`NO_CMD_CMPL()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161), and so does a writer with no command outstanding. Otherwise the wait lasts until [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) is clear or the timeout ends, 1000 ms after [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) outside poll mode and 2500 ms in it. It sleeps on the queue only while both [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) and [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) are set in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), and a timeout prints `Timeout on hotplug command`. Piece ❻ of [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) is where the interrupt delivers the report and where the other events are handed on.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:703 */
	/*
	 * Command Completed notifications are not deferred to the
	 * IRQ thread because it may be waiting for their arrival.
	 */
	if (events & PCI_EXP_SLTSTA_CC) {
		ctrl->cmd_busy = 0;
		smp_mb();
		wake_up(&ctrl->queue);

		if (events == PCI_EXP_SLTSTA_CC)
			return IRQ_HANDLED;

		events &= ~PCI_EXP_SLTSTA_CC;
	}

	if (pdev->ignore_hotplug) {
		ctrl_dbg(ctrl, "ignoring hotplug event %#06x\n", events);
		return IRQ_HANDLED;
	}

	/* Save pending events for consumption by IRQ thread. */
	atomic_or(events, &ctrl->pending_events);
	return IRQ_WAKE_THREAD;
}
```

On Command Completed the stage clears [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), orders the store with `smp_mb()` and wakes [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102), then returns `IRQ_HANDLED` when nothing else was seen and strips the bit otherwise. The comment gives the reason it is not deferred: the thread may be the writer waiting for it. A port marked [`ignore_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L424) has its events acknowledged and dropped with the message `ignoring hotplug event %#06x`. Everything else is ORed into [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), «6» on the strip, and `IRQ_WAKE_THREAD` makes the interrupt core wake pciehp's thread. The swimlane shows why a Command Completed left to the thread could not be delivered in time.

```text
    A Slot Control write waits for Command Completed from the hard stage
    ────────────────────────────────────────────────────────────────────

    time ↓
    Slot Control writer          ╎ port                        ╎ hard stage
    ─────────────────────────────┼─────────────────────────────┼──────────────────────────
    cmd_busy = 1                 ╎                             ╎
    writes Slot Control ───────────▶ runs the command          ╎
    sleeps on ctrl->queue, up to ╎ sets CC, sends a message ─────▶ reads CC, writes it back
    1 s after the write          ╎                             ╎ cmd_busy = 0
    woken, writes the next ◀─────╎─────────────────────────────╎── wakes ctrl->queue
    command                      ╎                             ╎

    the IRQ thread is a Slot Control writer when it sets indicators or powers the slot, so a
    Command Completed left to the thread would keep it asleep until the timeout
```

The flag on the port comes from [`pci_ignore_hotplug()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339), which a driver calls on its own device to mark the hot-plug port above it as well.

```c
/* drivers/pci/pci.c:6339 */
void pci_ignore_hotplug(struct pci_dev *dev)
{
	struct pci_dev *bridge = dev->bus->self;

	dev->ignore_hotplug = 1;
	/* Propagate the "ignore hotplug" setting to the parent bridge. */
	if (bridge)
		bridge->ignore_hotplug = 1;
}
EXPORT_SYMBOL_GPL(pci_ignore_hotplug);
```

At v7.2 its callers are the runtime suspend callbacks of four graphics drivers under drivers/gpu/drm, and from that call on the hard stage drops the events of the port above their device.

So far, an interrupt on the shared vector has been claimed by the hard stage only when the port could have raised it, read with the parent held awake or handed to the thread with [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154), acknowledged until an MSI port's Slot Status reads zero, and stripped of Command Completed. The events that remain are held in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), and the thread is awake.

### The thread reruns the hard stage after resuming the parents

The thread is the half of the handler that may sleep, and the interrupt core runs it after the hard stage returned `IRQ_WAKE_THREAD` or after a requester woke it. Before it reads or writes the port it makes the port reachable, through the configuration-access helpers of the PCI core; read [`pci_config_pm_runtime_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2868) and its counterpart for what reaching the port takes.

```c
/* drivers/pci/pci.c:2868 */
void pci_config_pm_runtime_get(struct pci_dev *pdev)
{
	struct device *dev = &pdev->dev;
	struct device *parent = dev->parent;

	if (parent)
		pm_runtime_get_sync(parent);
	pm_runtime_get_noresume(dev);
	/*
	 * pdev->current_state is set to PCI_D3cold during suspending,
	 * so wait until suspending completes
	 */
	pm_runtime_barrier(dev);
	/*
	 * Only need to resume devices in D3cold, because config
	 * registers are still accessible for devices suspended but
	 * not in D3cold.
	 */
	if (pdev->current_state == PCI_D3cold)
		pm_runtime_resume(dev);
}

void pci_config_pm_runtime_put(struct pci_dev *pdev)
{
	struct device *dev = &pdev->dev;
	struct device *parent = dev->parent;

	pm_runtime_put(dev);
	if (parent)
		pm_runtime_put_sync(parent);
}
```

[`pci_config_pm_runtime_get()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2868) resumes the port's parent with `pm_runtime_get_sync()`, which sleeps until the parent is in D0, then holds a reference on the port itself and resumes the port too when it is in D3cold. [`pci_config_pm_runtime_put()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2890) drops both references. The thread, [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728), is read in four pieces.

| piece | lines | stage |
|---|---|---|
| Ⓐ | pciehp_hpc.c:728-745 | marks the pass, reaches the port and reruns the hard stage when asked |
| Ⓑ | pciehp_hpc.c:746-763 | takes the word and handles button and power fault events |
| Ⓒ | pciehp_hpc.c:764-780 | drops link changes caused by containment or a reset |
| Ⓓ | pciehp_hpc.c:781-798 | dispatches disable requests and presence or link changes, then ends the pass |

Piece Ⓐ of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) opens the pass and takes over a Slot Status read the hard stage could not do.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:728 */
static irqreturn_t pciehp_ist(int irq, void *dev_id)
{
	struct controller *ctrl = (struct controller *)dev_id;
	struct pci_dev *pdev = ctrl_dev(ctrl);
	irqreturn_t ret;
	u32 events;

	ctrl->ist_running = true;
	pci_config_pm_runtime_get(pdev);

	/* rerun pciehp_isr() if the port was inaccessible on interrupt */
	if (atomic_fetch_and(~RERUN_ISR, &ctrl->pending_events) & RERUN_ISR) {
		ret = pciehp_isr(irq, dev_id);
		enable_irq(irq);
		if (ret != IRQ_WAKE_THREAD)
			goto out;
	}

```

[`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) is set first, «7» on the strip, so that a sysfs requester sees the pass from its start. `atomic_fetch_and()` clears [`RERUN_ISR`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L154) and returns the word as it was, «8» on the strip, and a set bit makes the thread call [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) itself, now with the parents in D0. `enable_irq()` then undoes the hard stage's `disable_irq_nosync()`, and a rerun that found nothing to latch ends the pass through the `out` label. The swimlane follows one interrupt through this path.

```text
    A suspended parent moves the Slot Status read into the thread
    ─────────────────────────────────────────────────────────────

    time ↓
    vector v        ╎ hard stage                ╎ IRQ thread                 ╎ port's parents
    ────────────────┼───────────────────────────┼────────────────────────────┼─────────────────
    fires ─────────────▶ parent not active      ╎                            ╎ runtime-suspended
    masked ┃ ◀──────╎── disables v              ╎                            ╎
           ┃        ╎ ORs RERUN_ISR, returns    ╎                            ╎
           ┃        ╎ IRQ_WAKE_THREAD ─────────────▶ ist_running = 1         ╎
           ┃        ╎                           ╎ takes runtime PM refs ─────────▶ resumed to D0
           ┃        ╎                           ╎ clears RERUN_ISR           ╎
           ┃        ╎ runs again ◀──────────────╎── reruns the hard stage    ╎
           ┃        ╎ reads Slot Status, ORs    ╎                            ╎
           ┃        ╎ the events into the word  ╎                            ╎
    unmasked ◀──────╎───────────────────────────╎── enables v                ╎
                    ╎                           ╎ empties the word and       ╎
                    ╎                           ╎ dispatches the events      ╎

    ┃ marks the interval in which v stays masked; with INTx, the devices sharing the line
    receive no interrupt in that interval
```

The masked interval runs from the first call of the hard stage to the thread's `enable_irq()`, and it includes the time the parents take to resume. commit [6b08c3854cfd](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6b08c3854cfdc5d13165880e2b54642c47edc405) ("PCI: pciehp: Support interrupts sent from D3hot") accepts that interval and notes that the devices sharing an INTx line are starved for its length. With the port reachable and every event in the word, the thread can take the word.

### The thread empties the word and dispatches by priority

The word may hold the events of several interrupts and requests by the time the thread reads it, and new bits may arrive while the thread works. The thread therefore takes the whole word in one atomic exchange and acts on its private copy, leaving the word empty for the next pass. Piece Ⓑ of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) takes the word and handles the events that need no slot state change.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:746 */
	synchronize_hardirq(irq);
	events = atomic_xchg(&ctrl->pending_events, 0);
	if (!events) {
		ret = IRQ_NONE;
		goto out;
	}

	/* Check Attention Button Pressed */
	if (events & PCI_EXP_SLTSTA_ABP)
		pciehp_handle_button_press(ctrl);

	/* Check Power Fault Detected */
	if (events & PCI_EXP_SLTSTA_PFD) {
		ctrl_err(ctrl, "Slot(%s): Power fault\n", slot_name(ctrl));
		pciehp_set_indicators(ctrl, PCI_EXP_SLTCTL_PWR_IND_OFF,
				      PCI_EXP_SLTCTL_ATTN_IND_ON);
	}

```

[`synchronize_hardirq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L105) waits for a hard stage running on another CPU to return, so the events it is latching are in the word when the exchange takes it. `atomic_xchg()` then moves the word into `events`, a local of the thread, and leaves zero behind, «9» on the strip. An empty word ends the pass with `IRQ_NONE`. Attention Button Pressed goes to [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167), and a power fault prints `Slot(%s): Power fault` and sets the Power Indicator off and the Attention Indicator on through [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513), a Slot Control write that waits for Command Completed. The figure shows the word and the thread's copy on each side of the exchange.

```text
    The exchange empties the word before the thread acts on what it held
    ────────────────────────────────────────────────────────────────────

    before the exchange                      after the exchange
    ┌──────────────────────────────┐         ┌──────────────────────────────┐
    │ ctrl->pending_events         │   ──▶   │ ctrl->pending_events         │
    │   DISABLE_SLOT | PDC | DLLSC │         │   0                          │◀── a request or an event that
    └──────────────────────────────┘         └──────────────────────────────┘    arrives now waits here for
                                                                                 the next pass
    ┌──────────────────────────────┐         ┌──────────────────────────────┐
    │ events, the thread's local   │         │ events, the thread's local   │
    │   not yet read               │         │   DISABLE_SLOT | PDC | DLLSC │
    └──────────────────────────────┘         └──────────────────────────────┘

    only events reaches the button, power fault, disable and presence or link handling;
    the word is free for new bits from the moment of the exchange
```

Presence and link events can be side effects of the kernel's own actions, a recovery by Downstream Port Containment or a bus reset, and the slot must not be torn down for them. Piece Ⓒ of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) drops such events on a slot that is on.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:764 */
	/*
	 * Ignore Link Down/Up events caused by Downstream Port Containment
	 * if recovery succeeded, or caused by Secondary Bus Reset,
	 * suspend to D3cold, firmware update, FPGA reconfiguration, etc.
	 */
	if ((events & (PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC)) &&
	    (pci_dpc_recovered(pdev) || pci_hp_spurious_link_change(pdev)) &&
	    ctrl->state == ON_STATE) {
		u16 ignored_events = PCI_EXP_SLTSTA_DLLSC;

		if (!ctrl->inband_presence_disabled)
			ignored_events |= PCI_EXP_SLTSTA_PDC;

		events &= ~ignored_events;
		pciehp_ignore_link_change(ctrl, pdev, irq, ignored_events);
	}

```

[`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) answers whether containment recovered the link, and [`pci_hp_spurious_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L552) whether a reset or a similar operation marked the link change to be ignored. The link-change bit is always dropped, and Presence Detect Changed too unless [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) is set. [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) then finishes the job, and its protocol, shared with containment and the bus reset, is outside this page, which stops at the call; the behavior came with commit [a97396c6eb13](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=a97396c6eb13f65bea894dbe7739b2e883d40a3e) ("PCI: pciehp: Ignore Link Down/Up caused by DPC"). [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) decides whether the containment test can answer true, as the declarations in [`pci.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h) show.

```c
/* drivers/pci/pci.h:882 */
#ifdef CONFIG_PCIE_DPC
void pci_save_dpc_state(struct pci_dev *dev);
void pci_restore_dpc_state(struct pci_dev *dev);
void pci_dpc_init(struct pci_dev *pdev);
void dpc_process_error(struct pci_dev *pdev);
pci_ers_result_t dpc_reset_link(struct pci_dev *pdev);
bool pci_dpc_recovered(struct pci_dev *pdev);
unsigned int dpc_tlp_log_len(struct pci_dev *dev);
#else
static inline void pci_save_dpc_state(struct pci_dev *dev) { }
static inline void pci_restore_dpc_state(struct pci_dev *dev) { }
static inline void pci_dpc_init(struct pci_dev *pdev) { }
static inline bool pci_dpc_recovered(struct pci_dev *pdev) { return false; }
#endif
```

With [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) set, [`pci_dpc_recovered()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L103) is the containment driver's function, and without it a stub that returns false, which leaves the reset test alone to drop events. Piece Ⓓ of [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) dispatches what is left and ends the pass.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:781 */
	/*
	 * Disable requests have higher priority than Presence Detect Changed
	 * or Data Link Layer State Changed events.
	 */
	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	if (events & DISABLE_SLOT)
		pciehp_handle_disable_request(ctrl);
	else if (events & (PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC))
		pciehp_handle_presence_or_link_change(ctrl, events);
	up_read(&ctrl->reset_lock);

	ret = IRQ_HANDLED;
out:
	pci_config_pm_runtime_put(pdev);
	ctrl->ist_running = false;
	wake_up(&ctrl->requester);
	return ret;
}
```

The dispatch runs under the read side of [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114), which a slot reset takes for writing, with [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) as the lock subclass. A [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) request goes to [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) and wins over presence and link events, which the comment states and the `else` enforces, and those events otherwise go to [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232), where hot-add and hot-remove begin. The table lists what the thread does with each bit it can find.

| bit in `events` | what the thread does | where |
|---|---|---|
| [`PCI_EXP_SLTSTA_ABP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L634) | handles the button press | [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) |
| [`PCI_EXP_SLTSTA_PFD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L635) | logs the fault and sets the indicators | [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) |
| [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637), [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) caused by containment or a reset | drops them | [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) |
| [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) | disables the slot, leaving presence and link bits of this pass unhandled | [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) |
| [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637), [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) | brings the slot up or down by its present state | [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) |

At the `out` label the thread drops its runtime PM references, clears [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116), «10» on the strip, and wakes [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118). The slot handlers this page stops at are the only callers of the functions that enable and disable the slot in drivers/pci/hotplug at v7.2, so slot enabling and disabling happen in the thread stage.

### Process-context requests enter through the same word

Code that runs in process context also needs slot work done: a sysfs write, the end of the button delay, a resume that finds the slot changed. pciehp serializes all of it through the thread by having such code OR a bit into the word and wake the thread, the design commit [32a8cef274fe](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=32a8cef274feacd00b748a4f13b84d60aa6d82ff) ("PCI: pciehp: Enable/disable exclusively from IRQ thread") introduced. [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) is that entry; read it for the two steps.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:141 */
void pciehp_request(struct controller *ctrl, int action)
{
	atomic_or(action, &ctrl->pending_events);
	if (!pciehp_poll_mode)
		irq_wake_thread(ctrl->pcie->irq, ctrl);
}
```

`atomic_or()` adds `action`, the caller's bits, to the word, «11» on the strip. Outside poll mode [`irq_wake_thread()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L1293) wakes the thread of pciehp's action on the vector, found by the controller as cookie, with no interrupt involved. In poll mode the poll thread finds the bits at its next pass. Seven functions call [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) at v7.2, from eight call sites in pciehp_core.c, pciehp_ctrl.c and pciehp_hpc.c.

| caller | bits requested | when |
|---|---|---|
| [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | probe or resume finds the slot's occupancy and its state in disagreement |
| [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | the device in the slot was replaced during system sleep |
| [`pciehp_queue_pushbutton_work()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148) | [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) or [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | the delay after a button press ends |
| [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) | [`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637) | user space asks to enable the slot |
| [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432) | [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) | user space asks to disable the slot |
| [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) | the presence and link bits it dropped | the link is down or the device replaced after an ignored change |
| [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) | [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642) | the link stays down after a reset for error recovery |

A sysfs request must not return before the thread has carried it out, because user space reads its result. Read the enable branch of [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) for the request and the wait.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:393 */
int pciehp_sysfs_enable_slot(struct hotplug_slot *hotplug_slot)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);

	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGON_STATE:
	case OFF_STATE:
		mutex_unlock(&ctrl->state_lock);
		/*
		 * The IRQ thread becomes a no-op if the user pulls out the
		 * card before the thread wakes up, so initialize to -ENODEV.
		 */
		ctrl->request_result = -ENODEV;
		pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);
		wait_event(ctrl->requester,
			   !atomic_read(&ctrl->pending_events) &&
			   !ctrl->ist_running);
		return ctrl->request_result;
```

The requester seeds [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) with `-ENODEV`, requests a presence check and sleeps on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) until the word is empty and [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) is clear. The word alone would not do, since the thread empties it at the exchange, before it acts; commit [157c1062fcd8](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=157c1062fcd86ade3c674503705033051fd3d401) ("PCI: pciehp: Avoid returning prematurely from sysfs requests") added the flag for that window, which the figure draws.

```text
    A sysfs request tests the word and ist_running together
    ───────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────────▶
    IRQ thread
    ist_running                     ├─────────────────────────────────────────┤ 0, wakes requester
    word              PDC ├─────────────────────┤ 0 from the exchange on
                                                ╎ enables the slot, writes request_result
                                                          ▲
    sysfs writer      ORs PDC                             │ tests: word 0, ist_running 1,
                                                            so it sleeps on requester

    the test lands after the exchange and before the slot is enabled; on the word alone
    it would pass there and return a request_result the thread has not written yet
```

The thread wakes [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) at the end of every pass, and the requester returns when a wake finds both conditions true. The same word thus carries interrupts and requests, and the thread serves both in one order.

### Poll mode runs both stages from a kernel thread

A port with no usable interrupt can still serve its slot if something reads Slot Status from time to time, which is why the port driver keeps the hot-plug service alive without a vector. pciehp offers that polling through two parameters, [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) and [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35); read their definitions for the names, types and permissions.

```c
/* drivers/pci/hotplug/pciehp_core.c:33 */
/* Global variables */
bool pciehp_poll_mode;
int pciehp_poll_time;

/*
 * not really modular, but the easiest way to keep compat with existing
 * bootargs behaviour is to continue using module_param here.
 */
module_param(pciehp_poll_mode, bool, 0644);
module_param(pciehp_poll_time, int, 0644);
MODULE_PARM_DESC(pciehp_poll_mode, "Using polling mechanism for hot-plug events or not");
MODULE_PARM_DESC(pciehp_poll_time, "Polling mechanism frequency, in seconds");
```

[`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) selects polling and [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35) sets the interval in seconds. The comment explains `module_param()` in built-in code by compatibility with existing boot arguments, so the parameters are set as `pciehp.pciehp_poll_mode=1` and `pciehp.pciehp_poll_time=` on the kernel command line, and mode 0644 makes them writable under /sys/module/pciehp/parameters. The poll thread calls both stages with [`IRQ_NOTCONNECTED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L152), a number that names no interrupt; read its definition and comment.

```c
/* include/linux/interrupt.h:144 */
/*
 * If a (PCI) device interrupt is not connected we set dev->irq to
 * IRQ_NOTCONNECTED. This causes request_irq() to fail with -ENOTCONN, so we
 * can distinguish that case from other error returns.
 *
 * 0x80000000 is guaranteed to be outside the available range of interrupts
 * and easy to distinguish from other possible incorrect values.
 */
#define IRQ_NOTCONNECTED	(1U << 31)
```

[`IRQ_NOTCONNECTED`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/interrupt.h#L152) lies outside the range of interrupts, according to the comment, so the interrupt-core calls inside the two stages, `disable_irq_nosync()`, `enable_irq()` and [`synchronize_hardirq()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L105), find no interrupt to act on in poll mode. [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) is the thread [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) starts in place of the vector.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:800 */
static int pciehp_poll(void *data)
{
	struct controller *ctrl = data;

	schedule_timeout_idle(10 * HZ); /* start with 10 sec delay */

	while (!kthread_should_stop()) {
		/* poll for interrupt events or user requests */
		while (pciehp_isr(IRQ_NOTCONNECTED, ctrl) == IRQ_WAKE_THREAD ||
		       atomic_read(&ctrl->pending_events))
			pciehp_ist(IRQ_NOTCONNECTED, ctrl);

		if (pciehp_poll_time <= 0 || pciehp_poll_time > 60)
			pciehp_poll_time = 2; /* clamp to sane value */

		schedule_timeout_idle(pciehp_poll_time * HZ);
	}

	return 0;
}
```

The thread first sleeps 10 seconds. A pass runs the hard stage and, while it returns `IRQ_WAKE_THREAD` or the word holds bits, the thread stage, then the hard stage again, so requests ORed in by [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) are served at the next pass. Before each sleep the thread resets [`pciehp_poll_time`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L35) to 2 when it is 0 or less or above 60, so the variable it reads is also a variable it writes, and `kthread_should_stop()` ends the loop at removal. The timeline places the passes.

```text
    The poll thread's schedule from probe to removal
    ────────────────────────────────────────────────

    time ─────────────────────────────────────────────────────────────────────────▶
         probe              10 s                10 s + T            10 s + 2T
         ├──── idle 10 s ────┼───── sleep T ──────┼───── sleep T ──────┼──── ...
                             ▲                    ▲                    ▲
                             pass                 pass                 pass

    pass   the hard stage runs; while it returns IRQ_WAKE_THREAD or the word holds bits,
           the thread stage runs and the hard stage runs again
    T      pciehp_poll_time seconds, reset to 2 when it is 0 or less or above 60
    ...    passes continue until removal stops the thread
```

The mode changes behavior at ten sites in pciehp_hpc.c and pciehp_ctrl.c at v7.2, each a test of [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) on a path this page follows.

| site | function | what poll mode changes |
|---|---|---|
| [`pciehp_hpc.c:62`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L62) | [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) | starts the poll thread and requests no vector |
| [`pciehp_hpc.c:80`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L80) | [`pciehp_free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78) | stops the poll thread |
| [`pciehp_hpc.c:114`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L114) | [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) | allows 2500 ms for Command Completed, against 1000 ms |
| [`pciehp_hpc.c:607`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L607) | [`pciehp_ignore_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L596) | writes the dropped bits back to Slot Status |
| [`pciehp_hpc.c:635`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L635) | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) | accepts the call with the gate clear |
| [`pciehp_hpc.c:695`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L695) | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) | writes events back once, with no MSI loop |
| [`pciehp_hpc.c:846`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L846) | [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) | leaves [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) clear |
| [`pciehp_hpc.c:848`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L848) | [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) | leaves [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) clear |
| [`pciehp_hpc.c:885`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L885) | [`pcie_enable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L880) | leaves [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) clear on resume |
| [`pciehp_ctrl.c:144`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L144) | [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) | wakes no interrupt thread |

With the gate clear the port raises no hot-plug interrupt, and with Command Completed Interrupt Enable clear [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) polls Slot Status for the report. Each site reads the parameter when it runs. Setting it after probe changes the sites that run later but leaves the mechanism probe installed, and [`pciehp_free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78) tests it again at removal to choose what to release, so the value at removal must be the value probe saw.

### Suspend closes the gate and keeps the events armed

A port that goes into D3hot takes its link to the slot down. With the gate and the link-change enable open, that link-down would raise the hot-plug interrupt at once, and commit [eb34da60edee](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=eb34da60edee8cf7bac691a406a1ddaa4175e5bc) ("PCI: pciehp: Disable hotplug interrupt during suspend") reports that it woke the system and brought the link back up. pciehp therefore closes both before the port suspends; read [`pcie_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L890) for the two bits and the comment's reasons.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:890 */
void pcie_disable_interrupt(struct controller *ctrl)
{
	u16 mask;

	/*
	 * Mask hot-plug interrupt to prevent it triggering immediately
	 * when the link goes inactive (we still get PME when any of the
	 * enabled events is detected). Same goes with Link Layer State
	 * changed event which generates PME immediately when the link goes
	 * inactive so mask it as well.
	 */
	mask = PCI_EXP_SLTCTL_HPIE | PCI_EXP_SLTCTL_DLLSCE;
	pcie_write_cmd(ctrl, 0, mask);
}
```

The write clears [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) and [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) and waits for Command Completed, and leaves [`PCI_EXP_SLTCTL_PDCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614) or [`PCI_EXP_SLTCTL_ABPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611) set. The commit quotes the specification's rule that clearing Hot-Plug Interrupt Enable alone keeps wakeup generation for the enabled events, and expects the port to wake and send a PME when such an event occurs during sleep. The link-change enable is cleared as well, because, according to the comment, a link going inactive generates a PME at once, the problem commit [bbe54ea5330d](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=bbe54ea5330d828cc396d451c0e1e5c3f9764c1e) ("PCI: pciehp: Disable Data Link Layer State Changed event on suspend") addressed. The port driver calls pciehp's suspend callbacks, which reach the function through [`pciehp_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L264) when PME is native; read it with [`pme_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256).

```c
/* drivers/pci/hotplug/pciehp_core.c:255 */
#ifdef CONFIG_PM
static bool pme_is_native(struct pcie_device *dev)
{
	const struct pci_host_bridge *host;

	host = pci_find_host_bridge(dev->port->bus);
	return pcie_ports_native || host->native_pme;
}

static void pciehp_disable_interrupt(struct pcie_device *dev)
{
	/*
	 * Disable hotplug interrupt so that it does not trigger
	 * immediately when the downstream link goes down.
	 */
	if (pme_is_native(dev))
		pcie_disable_interrupt(get_service_data(dev));
}
```

PME is native when `pcie_ports=native` is given, which sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), or when the host bridge granted PME control to the OS in [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656). When firmware keeps PME, nothing is masked, and the commit limited the masking that way so that older systems that depend on interrupts sent from D3hot keep working. The block is compiled under [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217), set in the page's configuration, and system suspend reaches it from [`pciehp_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L275) under [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140).

```c
/* drivers/pci/hotplug/pciehp_core.c:274 */
#ifdef CONFIG_PM_SLEEP
static int pciehp_suspend(struct pcie_device *dev)
{
	/*
	 * If the port is already runtime suspended we can keep it that
	 * way.
	 */
	if (dev_pm_skip_suspend(&dev->port->dev))
		return 0;

	pciehp_disable_interrupt(dev);
	return 0;
}
```

A port already runtime-suspended stays as it is, since the runtime suspend callback closed the gate when it suspended. The figure shows what holds across a system suspend of a port whose slot is on.

```text
    What holds while a port with a slot sleeps through a system suspend
    ───────────────────────────────────────────────────────────────────

    time ────────────────────────────────────────────────────────────────────────────▶
                       suspend      asleep              resume_noirq   resume
                       ╎            ╎                   ╎              ╎
    HPIE, DLLSCE  1    ├────────────────────── 0 ──────────────────────┤ 1
    port in D0    yes  ╎            ├─────── no ────────┤              ╎
    PDCE or ABPE  1    ╎ 1: slot events stay armed for a wake          ╎
    PDC, DLLSC    0    ╎            ╎ set as the link   ╎ cleared      ╎ presence
                       ╎            ╎ goes down         ╎              ╎ re-checked

    HPIE and DLLSCE are cleared and set again only when PME is native to the OS; the stale
    events are cleared only when the slot was on or blinking off
```

Events that occur while the port sleeps set their Slot Status bits with the gate closed, and resume has to deal with them before it opens it again.

### Resume clears stale events before it reopens the gate

A presence or link event recorded during sleep describes the transition into sleep or out of it, and handling it as a hot-plug event would tear down a slot that is still occupied. pciehp clears those bits on resume, before it reopens the gate, and then checks the slot's occupancy by reading it. [`pcie_clear_hotplug_events()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L874) does the clearing.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:874 */
void pcie_clear_hotplug_events(struct controller *ctrl)
{
	pcie_capability_write_word(ctrl_dev(ctrl), PCI_EXP_SLTSTA,
				   PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC);
}
```

The write clears Presence Detect Changed and Data Link Layer State Changed and leaves the other event bits latched. The system resume callback that runs with interrupts off, [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288), calls it for a slot that was on.

```c
/* drivers/pci/hotplug/pciehp_core.c:288 */
static int pciehp_resume_noirq(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	/* pci_restore_state() just wrote to the Slot Control register */
	ctrl->cmd_started = jiffies;
	ctrl->cmd_busy = true;

	/* clear spurious events from rediscovery of inserted card */
	if (ctrl->state == ON_STATE || ctrl->state == BLINKINGOFF_STATE) {
		pcie_clear_hotplug_events(ctrl);

		/*
		 * If hotplugged device was replaced with a different one
		 * during system sleep, mark the old device disconnected
		 * (to prevent its driver from accessing the new device)
		 * and synthesize a Presence Detect Changed event.
		 */
		if (pciehp_device_replaced(ctrl)) {
			ctrl_dbg(ctrl, "device replaced during system sleep\n");
			pci_walk_bus(ctrl->pcie->port->subordinate,
				     pci_dev_set_disconnected, NULL);
			pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);
		}
	}

	return 0;
}
```

The callback first marks a command outstanding, [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) set and [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) at the current time, because the comment notes that `pci_restore_state()` has just written Slot Control, so the next writer waits for its Command Completed. The stale events are cleared only for a slot in `ON_STATE` or `BLINKINGOFF_STATE`, and when [`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) finds another device in the slot, the old device is marked disconnected and a presence request goes to the thread. [`pcie_enable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L880) reopens what suspend closed.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:880 */
void pcie_enable_interrupt(struct controller *ctrl)
{
	u16 mask;

	mask = PCI_EXP_SLTCTL_DLLSCE;
	if (!pciehp_poll_mode)
		mask |= PCI_EXP_SLTCTL_HPIE;
	pcie_write_cmd(ctrl, mask, mask);
}
```

The write sets [`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630) always and [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) only outside poll mode, the test commit [527664f738af](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=527664f738afb6f2c58022cd35e63801e5dc7aec) ("PCI: pciehp: Don't enable HPIE when resuming in poll mode") added to match the enables of probe. The resume callbacks reach it under the same [`pme_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256) test as suspend; read [`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318) and the runtime callbacks after it.

```c
/* drivers/pci/hotplug/pciehp_core.c:318 */
static int pciehp_resume(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	if (pme_is_native(dev))
		pcie_enable_interrupt(ctrl);

	pciehp_check_presence(ctrl);

	return 0;
}

static int pciehp_runtime_suspend(struct pcie_device *dev)
{
	pciehp_disable_interrupt(dev);
	return 0;
}

static int pciehp_runtime_resume(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	/* pci_restore_state() just wrote to the Slot Control register */
	ctrl->cmd_started = jiffies;
	ctrl->cmd_busy = true;

	/* clear spurious events from rediscovery of inserted card */
	if ((ctrl->state == ON_STATE || ctrl->state == BLINKINGOFF_STATE) &&
	     pme_is_native(dev))
		pcie_clear_hotplug_events(ctrl);

	return pciehp_resume(dev);
}
```

[`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318) reopens the gate and then calls [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167), which probe calls too; read it for the reason resume reads the slot's occupancy itself.

```c
/* drivers/pci/hotplug/pciehp_core.c:156 */
/**
 * pciehp_check_presence() - synthesize event if presence has changed
 * @ctrl: controller to check
 *
 * On probe and resume, an explicit presence check is necessary to bring up an
 * occupied slot or bring down an unoccupied slot.  This can't be triggered by
 * events in the Slot Status register, they may be stale and are therefore
 * cleared.  Secondly, sending an interrupt for "events that occur while
 * interrupt generation is disabled [when] interrupt generation is subsequently
 * enabled" is optional per PCIe r4.0, sec 6.7.3.4.
 */
static void pciehp_check_presence(struct controller *ctrl)
{
	int occupied;

	down_read_nested(&ctrl->reset_lock, ctrl->depth);
	mutex_lock(&ctrl->state_lock);

	occupied = pciehp_card_present_or_link_active(ctrl);
	if ((occupied > 0 && (ctrl->state == OFF_STATE ||
			  ctrl->state == BLINKINGON_STATE)) ||
	    (!occupied && (ctrl->state == ON_STATE ||
			   ctrl->state == BLINKINGOFF_STATE)))
		pciehp_request(ctrl, PCI_EXP_SLTSTA_PDC);

	mutex_unlock(&ctrl->state_lock);
	up_read(&ctrl->reset_lock);
}
```

The comment calls the events stale and notes that the specification makes an interrupt for events that occurred while generation was disabled optional. The function reads occupancy through [`pciehp_card_present_or_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463) under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) and requests a presence check from the thread when an occupied slot is off or blinking on, or an empty slot is on or blinking off. The runtime pair closes and reopens the gate around every runtime suspend of the port, and [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336) clears stale events only when PME is native, a condition the system resume path does not have.

So far, an event in the slot has gone from the hard stage through the word to the thread, requests from process context have joined it there, poll mode has replaced the vector with a kernel thread, and suspend and resume have closed and reopened the gate while stale events were cleared. What is left is the end of the controller.

### Removal clears the enables before it frees the handler

Removal undoes probe in reverse, so the port stops raising the interrupt before the handler that would answer it goes away. pciehp's remove callback, [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245), unpublishes the slot and then shuts notification down.

```c
/* drivers/pci/hotplug/pciehp_core.c:245 */
static void pciehp_remove(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	pci_hp_del(&ctrl->hotplug_slot);
	pcie_shutdown_notification(ctrl);
	cleanup_slot(ctrl);
	pciehp_release_ctrl(ctrl);
}
```

[`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969) runs after the slot has left user space and before the controller is freed by [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096). It clears the enables, releases the stages and records that it did.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:969 */
void pcie_shutdown_notification(struct controller *ctrl)
{
	if (ctrl->notification_enabled) {
		pcie_disable_notification(ctrl);
		pciehp_free_irq(ctrl);
		ctrl->notification_enabled = 0;
	}
}
```

A controller whose stages were never installed has [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) clear and skips both steps, and otherwise the flag is cleared last, «12» on the strip. [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) clears the enables of Slot Control in one command.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:861 */
static void pcie_disable_notification(struct controller *ctrl)
{
	u16 mask;

	mask = (PCI_EXP_SLTCTL_PDCE | PCI_EXP_SLTCTL_ABPE |
		PCI_EXP_SLTCTL_MRLSCE | PCI_EXP_SLTCTL_PFDE |
		PCI_EXP_SLTCTL_HPIE | PCI_EXP_SLTCTL_CCIE |
		PCI_EXP_SLTCTL_DLLSCE);
	pcie_write_cmd(ctrl, 0, mask);
	ctrl_dbg(ctrl, "%s: SLOTCTRL %x write cmd %x\n", __func__,
		 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL, 0);
}
```

The mask names the six enables of probe and [`PCI_EXP_SLTCTL_MRLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L613), and the value is zero, so the write closes the gate and every event enable whatever firmware or probe set. The write goes through [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) and waits for Command Completed while the hard stage is still installed. The wait polls Slot Status, because [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) has already stored the new value, gate closed, in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), which [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) tests. [`pciehp_free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78) then releases what [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) installed.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:78 */
static inline void pciehp_free_irq(struct controller *ctrl)
{
	if (pciehp_poll_mode)
		kthread_stop(ctrl->poll_thread);
	else
		free_irq(ctrl->pcie->irq, ctrl);
}
```

In poll mode `kthread_stop()` stops [`pciehp_poll()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L800) and waits for it to return, and otherwise `free_irq()` removes pciehp's action from the shared vector, found by the controller as cookie, which leaves the other services' actions in place. The figure places the two brackets of probe and removal on one axis.

```text
    The enables stay open only inside the lifetime of the handler
    ─────────────────────────────────────────────────────────────

    time ────────────────────────────────────────────────────────────────────────────▶
                            request       write               clear         free
                            handler       enables             enables       handler
                            ╎             ╎                   ╎             ╎
    handler installed       ├───────────────────────────────────────────────┤
    enables open            ╎             ├───────────────────┤             ╎
    notification_enabled    ╎ 0           ╎ 1                 ╎             ╎ 0
    Slot Control enables    ╎ firmware's  ╎ pciehp's          ╎ all 0       ╎ all 0

    probe opens the brackets in this order, and removal or a failed publication closes them in
    reverse; clearing the enables waits, polling, for Command Completed while the handler is installed
```

The other caller of [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) at v7.2 clears the enables before any handler exists. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) powers off an empty slot whose power is on, and the comment explains that the interrupt is not requested yet, so the enables are cleared first to keep the power-off command from triggering a notification.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1006 */
struct controller *pcie_init(struct pcie_device *dev)
{
	struct controller *ctrl;
	u32 slot_cap, slot_cap2;
	u8 poweron;
	struct pci_dev *pdev = dev->port;
	struct pci_bus *subordinate = pdev->subordinate;

	... /* 62 lines, to :1076 */
	/*
	 * If empty slot's power status is on, turn power off.  The IRQ isn't
	 * requested yet, so avoid triggering a notification with this command.
	 */
	if (POWER_CTRL(ctrl)) {
		pciehp_get_power_status(ctrl, &poweron);
		if (!pciehp_card_present_or_link_active(ctrl) && poweron) {
			pcie_disable_notification(ctrl);
			pciehp_power_off_slot(ctrl);
		}
	}
```

After removal the vector carries the other services' actions alone, Slot Control has no enable set, and the controller is freed with the word in it.

### Tracepoints, messages and parameters expose both stages

The two stages leave traces in the interrupt core's tracepoints, in pciehp's messages and in the names of the threads that run them. The table lists the classes for the paths of this page, with their sites.

| class | on these paths | sites |
|---|---|---|
| tracepoints | `irq:irq_handler_entry` and `irq:irq_handler_exit` around every call of the hard stage by the interrupt core, with the action's name `pciehp`; `pci:pci_hp_event` from the presence and link handling the thread dispatches to; no tracepoint of pciehp's own in the two stages | [`handle.c:201`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L201), [`handle.c:212`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/handle.c#L212), [`pciehp_ctrl.c:251`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L251) |
| errors and notices | `Cannot get irq %d for the hotplug controller` at probe, `no response from device` from the hard stage, `Slot(%s): Power fault` from the thread, `Slot(%s): Link Down/Up ignored` from the ignore path, `Timeout on hotplug command` from the Slot Control wait | [`pciehp_hpc.c:73`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L73), [`pciehp_hpc.c:656`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L656), [`pciehp_hpc.c:759`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L759), [`pciehp_hpc.c:610`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L610), [`pciehp_hpc.c:147`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L147) |
| dynamic-debug sites | `pending interrupts %#06x from Slot Status` and `ignoring hotplug event %#06x` from the hard stage, `%s: SLOTCTRL %x write cmd %x` from the enable and disable writes | [`pciehp_hpc.c:699`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L699), [`pciehp_hpc.c:719`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L719), [`pciehp_hpc.c:857`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L857), [`pciehp_hpc.c:870`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L870) |
| hand-offs | the interrupt core's thread `irq/<vector>-pciehp`, woken by the hard stage or by [`irq_wake_thread()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/manage.c#L1293); the poll thread `pciehp_poll-<slot>`; the wait queues [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) and [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118); the parents' runtime PM; the button delay's work item, whose end requests through the word; no RCU, notifier chain or timer of their own | [`pciehp_hpc.c:70`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L70), [`pciehp_hpc.c:63`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L63), [`pciehp_ctrl.c:148`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L148) |
| surfaces | the vector's line in /proc/interrupts, which names `pciehp` beside the other services' actions; the parameters `pciehp.pciehp_poll_mode` and `pciehp.pciehp_poll_time`, also under /sys/module/pciehp/parameters; `pcie_ports=` and `pcie_pme=nomsi`; no debugfs file and no fault injection | [`pciehp_core.c:41`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L41), [`pciehp_core.c:42`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L42) |

The debug messages come from [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) and its siblings, pciehp's own macros over the PCI core's message helpers; read their definitions with the comment that tells how to turn them on.

```c
/* drivers/pci/hotplug/pciehp.h:31 */
/*
 * Set CONFIG_DYNAMIC_DEBUG=y and boot with 'dyndbg="file pciehp* +p"' to
 * enable debug messages.
 */
#define ctrl_dbg(ctrl, format, arg...)					\
	pci_dbg(ctrl->pcie->port, format, ## arg)
#define ctrl_err(ctrl, format, arg...)					\
	pci_err(ctrl->pcie->port, format, ## arg)
#define ctrl_info(ctrl, format, arg...)					\
	pci_info(ctrl->pcie->port, format, ## arg)
#define ctrl_warn(ctrl, format, arg...)					\
	pci_warn(ctrl->pcie->port, format, ## arg)
```

[`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) prints through [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) on the port, so a message carries the port's name, and the messages of [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) also carry the `pciehp: ` prefix that the file sets with `dev_fmt`. [`pci_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2896) is [`dev_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L164) on the port's device, and what a [`dev_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/dev_printk.h#L164) site becomes depends on the configuration.

```c
/* include/linux/dev_printk.h:162 */
#if defined(CONFIG_DYNAMIC_DEBUG) || \
	(defined(CONFIG_DYNAMIC_DEBUG_CORE) && defined(DYNAMIC_DEBUG_MODULE))
#define dev_dbg(dev, fmt, ...)						\
	dynamic_dev_dbg(dev, dev_fmt(fmt), ##__VA_ARGS__)
#elif defined(DEBUG)
#define dev_dbg(dev, fmt, ...)						\
	dev_printk(KERN_DEBUG, dev, dev_fmt(fmt), ##__VA_ARGS__)
#else
#define dev_dbg(dev, fmt, ...)						\
	dev_no_printk(KERN_DEBUG, dev, dev_fmt(fmt), ##__VA_ARGS__)
#endif

```

With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, each [`ctrl_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) call on these paths is a dynamic-debug site, off until a reader enables it through /sys/kernel/debug/dynamic_debug/control or with `dyndbg="file pciehp* +p"` at boot, as the comment says. [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), unset here, adds `-DDEBUG` for the PCI directories in [`Makefile`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Makefile), which defines the `DEBUG` that the second branch of the definitions above tests.

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

With the option unset the sites start disabled. Enabled, the hard stage's site prints the event set of every interrupt it latched, the ignore site shows events dropped for a port marked by [`pci_ignore_hotplug()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6339), and the two Slot Control sites print the register's offset and the value probe and removal wrote.
