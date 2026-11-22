# pciehp controller and port service

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe Root Port or Downstream Port whose slot accepts cards while the system runs needs one owner for the slot's registers, events and user interface. In the PCI subsystem that owner is the native PCIe hotplug driver, pciehp, which the PCIe port bus driver binds to the port as one of its services. The driver keeps what it knows about the slot in a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91), between the port bus driver below it and the PCI hotplug core that shows the slot in sysfs. This page traces how the service binds, how probe builds, registers and publishes the controller, how the power management hooks keep the slot's interrupt consistent across sleep, and how remove takes the controller apart.

```text
    A hot-plug capable port, its hotplug service device, its controller and the slot it registers
    ─────────────────────────────────────────────────────────────────────────────────────────────

    struct pci_dev, the Root Port or Downstream Port                 struct pci_bus, the secondary bus
    ┌────────────────────────────────────────────┐                   ┌────────────────────────────────────────┐
    │ is_pciehp     1, Hot-Plug Capable          │                   │ devices   functions behind the slot    │
    │ subordinate ───────────────────────────────┼──────────────────▶│ slots     the slots on this bus        │
    │ dev           the port's struct device     │                   │ self      the port above               │
    └────────────────────────────────────────────┘                   └────────────────────────────────────────┘
             ▲                                                                ▲
             │    struct pcie_device, portdrv's service instance              │   struct pci_slot
    ┌────────┼───────────────────────────────────┐                   ┌────────┼───────────────────────────────┐
    │ port ──┘                                   │                   │ bus ───┘                               │
    │ service   PCIE_PORT_SERVICE_HP             │                ┌─▶│ number    PCI_SLOT_ALL_DEVICES         │
    │ irq       the vector portdrv assigned      │                │  │ hotplug ─────────────────────────────┐ │
    │ priv_data ──────────┐                      │                │  │ kobj      the slot's sysfs directory │ │
    └─────────────────────┼──────────────────────┘                │  └──────────────────────────────────────┼─┘
               ▲          │                                       │                                       ▲ │
               │          │                                       │  struct pci_dev, a function           │ │
               │          ▼ struct controller                     │  ┌──────────────────────────────────┐ │ │
    ┌──────────┼───────────────────────────────────────────────┐  │  │ bus_list  on the devices list    │ │ │
    │ pcie ────┘                                               │  │  │ slot ────────────────────────────┼─┘ │
    │ slot_cap        cached Slot Capabilities                 │  │  └──────────────────────────────────┘   │
    │ state           OFF_STATE ... ON_STATE                   │  │                                         │
    │ ctrl_lock, state_lock, reset_lock                        │  │                                         │
    │ pending_events, button_work, depth, ...                  │  │                                         │
    │                                                          │  │                                         │
    │ hotplug_slot, an embedded struct hotplug_slot            │  │                                         │
    │ ┌────────────────────────────────────────────┐           │  │                                         │
    │ │ ops        the callbacks init_slot fills   │           │  │                                         │
    │ │ pci_slot ──────────────────────────────────┼───────────┼──┘                                         │
    │ │ owner, mod_name                            │◀──────────┼────────────────────────────────────────────┘
    │ └────────────────────────────────────────────┘           │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
```

## SUMMARY

On x86 with ACPI firmware, the PCIe port bus driver gives a hot-plug capable port a service device, and pciehp's probe attaches a [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) to it. The controller stands for both the hot-plug controller and the slot of the specification, and the table maps the specification's terms to the kernel objects.

| specification term | kernel representation | how they relate |
|---|---|---|
| Root Port or Downstream Port with Hot-Plug Capable set | [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) with [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) set | the port itself, bound to the port bus driver |
| the port's hot-plug service | [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) with [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20) | portdrv's service instance, a child device of the port and no PCIe device |
| hot-plug controller and its slot | [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) | one object for both, since the port has one slot |
| the slot as the hotplug core sees it | [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57), embedded as [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) | [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) steps back to the controller |
| the slot in sysfs, named by the Physical Slot Number | [`struct pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L85) numbered [`PCI_SLOT_ALL_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L82) | it covers every function on the port's secondary bus |
| Slot Capabilities register | [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) | a copy read once at probe, with port adjustments |

Probe allocates the controller, registers the slot, requests the interrupt and then publishes the slot to user space, and remove undoes those steps in reverse order. The slot's files therefore exist only while an IRQ thread or a poll thread can serve their requests, and across suspend the hooks mask the slot's interrupt when the OS owns PME for the port's host bridge.

## SPECIFICATIONS

The PCI Express Base Specification defines the slot registers and the hot-plug event rules the controller follows, and the tree cites it by revision and section number without section titles. [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) itself is a kernel object that no specification defines, read here from drivers/pci/hotplug/ and drivers/pci/pcie/.

- PCIe r6.2, sec 7.9.3, cited by [`pciehp.h:49-51`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L49) for the Device Serial Number that [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) caches.
- PCIe r5.0, appendix I implementation note, cited by [`pciehp.h:53-55`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L53) for the In-Band Presence Detect disable that [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) records.
- PCIe r4.0, sec 6.7.3.2, cited by [`pciehp.h:58-60`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L58) for the wait after a Slot Control write that no Command Completed event ends.
- PCIe r4.0, sec 6.7.3.4, cited by [`pciehp_core.c:160-165`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L160) for events that occur while interrupt generation is disabled.
- PCI Express Base Specification 1.0a, sections 7.8.2, 7.8.9 and 7.9 - 7.11, cited by [`portdrv.c:212-214`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L212) for the port registers the port bus driver reads to find a port's services.

## COVERAGE

### Port service binding (drivers/pci/hotplug/pciehp_core.c)

- [`'\<hpdriver_portdrv\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353): the port service driver for the hotplug service, naming the probe, remove, power management and error recovery hooks.
- [`'\<pcie_hp_init\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374): registers the service driver on the PCIe port bus at boot.

### The controller (drivers/pci/hotplug/pciehp.h)

- [`'\<struct controller\>':'drivers/pci/hotplug/pciehp.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91): the per-port object that is both the hot-plug controller and its slot.
- [`'controller.ctrl_lock'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99): serializes writes to Slot Control and the wait for their completion.
- [`'controller.state_lock'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110): orders reads and writes of the slot state and the button work.
- [`'controller.reset_lock'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114): keeps occupancy readers out while a slot reset makes the link flap.
- [`'OFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133): the slot is powered off and nothing below it is enumerated.
- [`'BLINKINGON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134): the slot waits out the button delay before it powers on.
- [`'BLINKINGOFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135): the slot waits out the button delay before it powers off.
- [`'POWERON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136): the slot is being brought up.
- [`'POWEROFF_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137): the slot is being brought down.
- [`'ON_STATE'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138): the slot is powered and its devices are enumerated.
- [`'ATTN_BUTTN'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156): tests Attention Button Present in the cached Slot Capabilities.
- [`'POWER_CTRL'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157): tests Power Controller Present.
- [`'MRL_SENS'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158): tests MRL Sensor Present.
- [`'ATTN_LED'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159): tests Attention Indicator Present.
- [`'PWR_LED'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160): tests Power Indicator Present.
- [`'NO_CMD_CMPL'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161): tests No Command Completed Support.
- [`'PSN'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162): extracts the Physical Slot Number.
- [`'\<to_ctrl\>':'drivers/pci/hotplug/pciehp.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207): returns the controller around an embedded hotplug core slot.
- [`'\<slot_name\>':'drivers/pci/hotplug/pciehp.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202): returns the name of the slot the PCI core created.

### Probe and the bus-wide slot

- [`'\<pciehp_probe\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185): builds, registers, enables and publishes the controller of a hotplug service device.
- [`'\<pcie_init\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006): allocates the controller, caches Slot Capabilities and quiets the slot.
- [`'\<pcie_hotplug_depth\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L992): counts the hot-plug capable ports above a port.
- [`'\<init_slot\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51): fills the hotplug core callbacks and registers the slot for in-kernel use.
- [`'PCI_SLOT_ALL_DEVICES'`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L82): the slot number of a slot that covers every device on its bus.
- [`'\<pciehp_check_presence\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167): requests a presence event when occupancy and state disagree.

### Remove

- [`'\<pciehp_remove\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245): takes the controller apart in the reverse of probe's order.
- [`'\<cleanup_slot\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L91): destroys the slot and frees the callback table.
- [`'\<pciehp_release_ctrl\>':'drivers/pci/hotplug/pciehp_hpc.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096): cancels the button work and frees the controller.

### Power management hooks

- [`'\<pme_is_native\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256): reports whether the OS owns PME for the port's host bridge.
- [`'\<pciehp_disable_interrupt\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L264): masks the slot interrupt when PME is native.
- [`'\<pciehp_suspend\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L275): the system suspend hook.
- [`'\<pciehp_resume_noirq\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288): the early resume hook that accounts for the restored Slot Control write.
- [`'\<pciehp_resume\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318): the resume hook that unmasks the interrupt and checks presence.
- [`'\<pciehp_runtime_suspend\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L330): the runtime suspend hook.
- [`'\<pciehp_runtime_resume\>':'drivers/pci/hotplug/pciehp_core.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336): the runtime resume hook.

## DOCUMENTATION

- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the PCIe port bus driver guide, which describes port services and how a service driver registers for one.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): documents the `pcie_ports=` boot parameter and its native and compat settings.
- [`Documentation/trace/events-pci.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/trace/events-pci.rst): documents the `pci:pci_hp_event` tracepoint that the IRQ thread's event handlers fire.
- [`Documentation/ABI/testing/sysfs-bus-pci`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/ABI/testing/sysfs-bus-pci): documents the module link of a slot directory under /sys/bus/pci/slots.

## OTHER SOURCES

### Added by Claude Opus 5.5

- [PCI: Allow all bus devices to use the same slot (commit 102c8b26b54e)](https://patch.msgid.link/20260217160836.2709885-3-kbusch@meta.com)
- [PCI: pciehp: Detect device replacement during system sleep (commit 9d573d19547b)](https://lore.kernel.org/r/a1afaa12f341d146ecbea27c1743661c71683833.1716992815.git.lukas@wunner.de)
- [PCI: pciehp: Avoid unnecessary device replacement check (commit e3260237aaad)](https://lore.kernel.org/r/02f166e24c87d6cde4085865cce9adfdfd969688.1741674172.git.lukas@wunner.de)
- [PCI: pciehp: Use down_read/write_nested(reset_lock) to fix lockdep errors (commit 085a9f43433f)](https://lore.kernel.org/r/20211217141709.379663-1-hdegoede@redhat.com)
- [PCI: pciehp: Fix AB-BA deadlock between reset_lock and device_lock (commit f5eff5591b8f)](https://lore.kernel.org/r/fef2b2e9edf245c049a8c5b94743c0f74ff5008a.1681191902.git.lukas@wunner.de)
- [PCI: pciehp: Do not disable interrupt twice on suspend (commit 75fcc0ce72e5)](https://lore.kernel.org/r/20191029170022.57528-1-mika.westerberg@linux.intel.com)
- [PCI: pciehp: Disable in-band presence detect when possible (commit 202853595e53)](https://lore.kernel.org/r/20191025190047.38130-2-stuart.w.hayes@gmail.com)

## REGISTERS

The controller reaches its slot through three registers of the port's PCI Express Capability, Slot Capabilities ([`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597)), Slot Control ([`PCI_EXP_SLTCTL`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L610)) and Slot Status ([`PCI_EXP_SLTSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L633)). Probe also reads Slot Capabilities 2 ([`PCI_EXP_SLTCAP2`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L716)), and the presence check reads the Data Link Layer Link Active bit of Link Status ([`PCI_EXP_LNKSTA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L577)) as a second sign of occupancy. Each drawing shows the fields that pci_regs.h names, and the paragraph after it says which of them probe, remove and the power management hooks touch.

```text
    Slot Capabilities, PCIe Capability offset 0x14
    ──────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x14 │       PSN (31:19)       │N│E│LS │  SPLV (14:7)  │H│S│P│A│M│C│B│
          └─────────────────────────┴┬┴┬┴─┬─┴───────────────┴┬┴┬┴┬┴┬┴┬┴┬┴┬┘
                                     │ │  │                  │ │ │ │ │ │ │
                              NCCS ──┘ │  │                  │ │ │ │ │ │ │
                                 EIP ──┘  │                  │ │ │ │ │ │ │
                           SPLS (16:15) ──┘                  │ │ │ │ │ │ │
                                                       HPC ──┘ │ │ │ │ │ │
                                                         HPS ──┘ │ │ │ │ │
                                                           PIP ──┘ │ │ │ │
                                                             AIP ──┘ │ │ │
                                                             MRLSP ──┘ │ │
                                                                 PCP ──┘ │
                                                                   ABP ──┘

    PSN = PCI_EXP_SLTCAP_PSN (Physical Slot Number)
    NCCS = PCI_EXP_SLTCAP_NCCS (No Command Completed Support)
    EIP = PCI_EXP_SLTCAP_EIP (Electromechanical Interlock Present)
    SPLS = PCI_EXP_SLTCAP_SPLS (Slot Power Limit Scale)   SPLV = PCI_EXP_SLTCAP_SPLV (Slot Power Limit Value)
    HPC = PCI_EXP_SLTCAP_HPC (Hot-Plug Capable)   HPS = PCI_EXP_SLTCAP_HPS (Hot-Plug Surprise)
    PIP = PCI_EXP_SLTCAP_PIP (Power Indicator Present)   AIP = PCI_EXP_SLTCAP_AIP (Attention Indicator Present)
    MRLSP = PCI_EXP_SLTCAP_MRLSP (MRL Sensor Present)   PCP = PCI_EXP_SLTCAP_PCP (Power Controller Present)
    ABP = PCI_EXP_SLTCAP_ABP (Attention Button Present)
    cached in controller.slot_cap by pcie_init; SPLS and SPLV are not read on these paths
```

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) reads Slot Capabilities once into [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), and the paths of this page test that copy and leave the register alone. Hot-Plug Capable ([`PCI_EXP_SLTCAP_HPC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L604)) set [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) during enumeration, which qualifies the port for the hotplug service. Attention Button Present ([`ATTN_BUTTN`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156)) chooses between button and presence events when probe enables them, and Power Controller Present ([`POWER_CTRL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L157)) lets [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) power off an empty slot. MRL Sensor Present ([`MRL_SENS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158)) and Attention Indicator Present ([`ATTN_LED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159)) decide whether [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installs the latch and attention callbacks, and Power Indicator Present ([`PWR_LED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160)) decides whether an indicator write touches the Power Indicator Control field. No Command Completed Support ([`NO_CMD_CMPL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161)) decides whether a Slot Control write waits for completion, and the Physical Slot Number ([`PSN`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162)) names the slot. Within drivers/pci/hotplug/pciehp*.c at v7.2, Hot-Plug Surprise ([`PCI_EXP_SLTCAP_HPS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L603)) and Electromechanical Interlock Present ([`PCI_EXP_SLTCAP_EIP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L607)) appear in the probe message alone, and no line reads the slot power limit fields ([`PCI_EXP_SLTCAP_SPLV`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L605), [`PCI_EXP_SLTCAP_SPLS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L606)).

```text
    Slot Capabilities 2, PCIe Capability offset 0x34, bits 7:0
    ──────────────────────────────────────────────────────────

    bit    7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┐
    +0x34 │·│·│·│·│·│·│·│I│
          └─┴─┴─┴─┴─┴─┴─┴┬┘
                         │
                  IBPD ──┘

    IBPD = PCI_EXP_SLTCAP2_IBPD (In-band PD Disable Supported)
    bits 31:8 are not drawn; pci_regs.h names no bit of this register but bit 0
```

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) reads Slot Capabilities 2 for In-band PD Disable Supported ([`PCI_EXP_SLTCAP2_IBPD`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L717)). When the bit is set, the driver disables in-band presence detection in Slot Control and records that in [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96), and the probe message prints the bit as IbPresDis.

```text
    Slot Control, PCIe Capability offset 0x18
    ─────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x18 │·│I│L│D│E│W│PIC│AIC│H│C│P│M│F│B│
          └─┴┬┴┬┴┬┴┬┴┬┴─┬─┴─┬─┴┬┴┬┴┬┴┬┴┬┴┬┘
             │ │ │ │ │  │   │  │ │ │ │ │ │
      IBPD ──┘ │ │ │ │  │   │  │ │ │ │ │ │
        ASPL ──┘ │ │ │  │   │  │ │ │ │ │ │
        DLLSCE ──┘ │ │  │   │  │ │ │ │ │ │
             EIC ──┘ │  │   │  │ │ │ │ │ │
               PCC ──┘  │   │  │ │ │ │ │ │
            PIC (9:8) ──┘   │  │ │ │ │ │ │
                AIC (7:6) ──┘  │ │ │ │ │ │
                        HPIE ──┘ │ │ │ │ │
                          CCIE ──┘ │ │ │ │
                            PDCE ──┘ │ │ │
                            MRLSCE ──┘ │ │
                                PFDE ──┘ │
                                  ABPE ──┘

    IBPD = PCI_EXP_SLTCTL_IBPD_DISABLE (In-band PD disable)
    ASPL = PCI_EXP_SLTCTL_ASPL_DISABLE (Auto Slot Power Limit Disable)
    DLLSCE = PCI_EXP_SLTCTL_DLLSCE (Data Link Layer State Changed Enable)
    EIC = PCI_EXP_SLTCTL_EIC (Electromechanical Interlock Control)
    PCC = PCI_EXP_SLTCTL_PCC (Power Controller Control, 1 = off)
    PIC = PCI_EXP_SLTCTL_PIC (Power Indicator Control)
    AIC = PCI_EXP_SLTCTL_AIC (Attention Indicator Control)
    HPIE = PCI_EXP_SLTCTL_HPIE (Hot-Plug Interrupt Enable)
    CCIE = PCI_EXP_SLTCTL_CCIE (Command Completed Interrupt Enable)
    PDCE = PCI_EXP_SLTCTL_PDCE (Presence Detect Changed Enable)
    MRLSCE = PCI_EXP_SLTCTL_MRLSCE (MRL Sensor Changed Enable)
    PFDE = PCI_EXP_SLTCTL_PFDE (Power Fault Detected Enable)
    ABPE = PCI_EXP_SLTCTL_ABPE (Attention Button Pressed Enable)
    bit 15 carries no name in pci_regs.h; the last value written is cached in controller.slot_ctrl
```

The controller writes Slot Control through [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), which keeps the last value it wrote in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98). Probe enables Data Link Layer State Changed ([`PCI_EXP_SLTCTL_DLLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L630)), then either Attention Button Pressed ([`PCI_EXP_SLTCTL_ABPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L611)) or Presence Detect Changed ([`PCI_EXP_SLTCTL_PDCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L614)), and outside poll mode Hot-Plug Interrupt Enable ([`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616)) and Command Completed Interrupt Enable ([`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615)). Remove clears those enables together with MRL Sensor Changed and Power Fault Detected ([`PCI_EXP_SLTCTL_MRLSCE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L613), [`PCI_EXP_SLTCTL_PFDE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L612)), while suspend and resume flip Hot-Plug Interrupt Enable and Data Link Layer State Changed Enable and leave the other fields. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) sets In-band PD Disable ([`PCI_EXP_SLTCTL_IBPD_DISABLE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L632)) and can set Power Controller Control ([`PCI_EXP_SLTCTL_PCC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L626)) to off, and the slot's attention file writes Attention Indicator Control ([`PCI_EXP_SLTCTL_AIC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L617)).

```text
    Slot Status, PCIe Capability offset 0x1a
    ────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x1a │·│·│·│·│·│·│·│L│E│S│R│C│D│M│F│B│
          └─┴─┴─┴─┴─┴─┴─┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴┬┘
                         │ │ │ │ │ │ │ │ │
                 DLLSC ──┘ │ │ │ │ │ │ │ │
                     EIS ──┘ │ │ │ │ │ │ │
                       PDS ──┘ │ │ │ │ │ │
                       MRLSS ──┘ │ │ │ │ │
                            CC ──┘ │ │ │ │
                             PDC ──┘ │ │ │
                             MRLSC ──┘ │ │
                                 PFD ──┘ │
                                   ABP ──┘

    DLLSC = PCI_EXP_SLTSTA_DLLSC (Data Link Layer State Changed)
    EIS = PCI_EXP_SLTSTA_EIS (Electromechanical Interlock Status)
    PDS = PCI_EXP_SLTSTA_PDS (Presence Detect State)   MRLSS = PCI_EXP_SLTSTA_MRLSS (MRL Sensor State)
    CC = PCI_EXP_SLTSTA_CC (Command Completed)   PDC = PCI_EXP_SLTSTA_PDC (Presence Detect Changed)
    MRLSC = PCI_EXP_SLTSTA_MRLSC (MRL Sensor Changed)   PFD = PCI_EXP_SLTSTA_PFD (Power Fault Detected)
    ABP = PCI_EXP_SLTSTA_ABP (Attention Button Pressed)
    bits 15:9 carry no name in pci_regs.h
```

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) writes the event bits of Slot Status back to clear them before any interrupt exists, and the resume hooks clear Presence Detect Changed and Data Link Layer State Changed ([`PCI_EXP_SLTSTA_PDC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L637), [`PCI_EXP_SLTSTA_DLLSC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L642)) of an occupied slot. The presence check reads Presence Detect State ([`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640)). The positions of the event bits double as event codes in [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104), where [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) stores a synthetic Presence Detect Changed.

```text
    Link Status, PCIe Capability offset 0x12
    ────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    +0x12 │A│B│D│S│T│·│ NLW (9:4) │  CLS  │
          └┬┴┬┴┬┴┬┴┬┴─┴───────────┴───┬───┘
           │ │ │ │ │                  │
    LABS ──┘ │ │ │ │                  │
      LBMS ──┘ │ │ │                  │
       DLLLA ──┘ │ │                  │
           SLC ──┘ │                  │
              LT ──┘                  │
                          CLS (3:0) ──┘

    LABS = PCI_EXP_LNKSTA_LABS (Link Autonomous Bandwidth Status)
    LBMS = PCI_EXP_LNKSTA_LBMS (Link Bandwidth Management Status)
    DLLLA = PCI_EXP_LNKSTA_DLLLA (Data Link Layer Link Active)
    SLC = PCI_EXP_LNKSTA_SLC (Slot Clock Configuration)   LT = PCI_EXP_LNKSTA_LT (Link Training)
    NLW = PCI_EXP_LNKSTA_NLW (Negotiated Link Width)   CLS = PCI_EXP_LNKSTA_CLS (Current Link Speed)
    bit 10 carries no name in pci_regs.h; only DLLLA is read on these paths
```

Link Status contributes the Data Link Layer Link Active bit ([`PCI_EXP_LNKSTA_DLLLA`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L593)) to this page. [`pciehp_card_present_or_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463) counts a slot as occupied when the link is up even if Presence Detect State reads clear, and [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) keeps that read away from the flap a slot reset causes.

## DETAILS

The first subsections show which ports qualify for the hotplug service, how the port bus driver turns that service into a child device, and how [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) binds pciehp to it. The next ones read [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91) by field group, with its lifecycle and the conversions between the controller and its slot. The probe subsections then follow [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) through [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006), the Slot Control command protocol, the bus-wide slot of [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) and the order of interrupt setup and publication. They end with the presence check and the state values and reset lock it relies on. The power management subsections read suspend, early resume, resume and runtime power management, and the last ones read remove and the messages, hand-offs and files that expose these paths.

### Kconfig assumptions

The page documents the x86-64 defconfig resolved at the v7.2 tag, on x86-64 with ACPI firmware, with the PCIe port, hotplug and dynamic debug options of the table set on top of it. The defconfig leaves [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) unset, and the page assumes it set, since without it pciehp is not built.

| option | assumed value | what it decides here |
|---|---|---|
| [`CONFIG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L21) | y | builds the PCI core, whose host bridge setup starts with every native flag set |
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y, set in the x86-64 defconfig | builds the port bus driver that creates the hotplug service device |
| [`CONFIG_HOTPLUG_PCI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/Kconfig#L6) | y, set in the x86-64 defconfig | builds the hotplug core whose slot registration [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) uses |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y; the x86-64 defconfig leaves it unset | builds pciehp; unset, [`pcie_hp_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374) is an empty stub and portdrv masks the slot interrupts |
| [`CONFIG_ACPI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/Kconfig#L9) | y | builds the root bridge driver that clears the native flags _OSC withholds |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y, selected through hibernation in the x86-64 defconfig | builds [`pme_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256) and the runtime hooks |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y, the same way | builds the system suspend and resume hooks |
| [`CONFIG_DMI`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/Kconfig#L944) | y, its x86 default | lets [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) match the in-band presence table |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the debug messages of these paths switchable at run time |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | n | would compile drivers/pci with -DDEBUG and print the debug messages unconditionally |

The table indexes the prose. Each subsection below names the option at the point where its effect applies.

### Slot ports qualify for the hotplug service through two tests

A PCIe port can carry several services at once, among them error reporting, PME and native hotplug, and the port bus driver decides at probe which of them a port gets. The hotplug service needs a port that can host a slot and an OS that owns hotplug for the port's hierarchy. On x86 the second condition comes from the ACPI _OSC handshake of the host bridge, so the decision combines a bit of each port with a flag of its host bridge.

The per-port half is recorded during enumeration. [`set_pcie_hotplug_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L1688) reads Slot Capabilities through [`PCI_EXP_SLTCAP`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L597) and marks a port whose Hot-Plug Capable bit is set; read it for the two flags it sets together.

```c
/* drivers/pci/probe.c:1688 */
void set_pcie_hotplug_bridge(struct pci_dev *pdev)
{
	u32 reg32;

	pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP, &reg32);
	if (reg32 & PCI_EXP_SLTCAP_HPC)
		pdev->is_hotplug_bridge = pdev->is_pciehp = 1;
}
```

The port gets both [`is_hotplug_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L483), which the field's kerneldoc describes as a hotplug bridge of any kind, and [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484), the flag that the port bus driver and pciehp test. The host-bridge half starts in [`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659), which sets every native flag of a new host bridge on the assumption its comment states; read the stage for [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654) and [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656).

```c
/* drivers/pci/probe.c:659 */
static void pci_init_host_bridge(struct pci_host_bridge *bridge)
{
	... /* 4 lines, to :665 */
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

Both flags start at 1, and the comment names _OSC as the way an ACPI BIOS keeps a feature for itself. On x86 the ACPI root bridge driver applies the firmware's answer when it creates the root bus in [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995); read the stage that clears each flag whose control bit _OSC did not grant.

```c
/* drivers/acpi/pci_root.c:995 */
struct pci_bus *acpi_pci_root_create(struct acpi_pci_root *root,
				     struct acpi_pci_root_ops *ops,
				     struct acpi_pci_root_info *info,
				     void *sysdata)
{
	int ret, busnum = root->secondary.start;
	... /* 28 lines, to :1029 */
	host_bridge = to_pci_host_bridge(bus->bridge);
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_NATIVE_HP_CONTROL))
		host_bridge->native_pcie_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_SHPC_NATIVE_HP_CONTROL))
		host_bridge->native_shpc_hotplug = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_AER_CONTROL))
		host_bridge->native_aer = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_PME_CONTROL))
		host_bridge->native_pme = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_LTR_CONTROL))
		host_bridge->native_ltr = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_DPC_CONTROL))
		host_bridge->native_dpc = 0;
```

`osc_control_set` holds the control bits the firmware granted, and a missing native hotplug bit leaves [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654) at 0 for every port below this host bridge. [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) follows its own bit, and the suspend hooks read it later. [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) combines the two halves; read its first stage for the hotplug test.

```c
/* drivers/pci/pcie/portdrv.c:208 */
/**
 * get_port_device_capability - discover capabilities of a PCI Express port
 * @dev: PCI Express port to examine
 *
 * The capabilities are read from the port's PCI Express configuration registers
 * as described in PCI Express Base Specification 1.0a sections 7.8.2, 7.8.9 and
 * 7.9 - 7.11.
 *
 * Return value: Bitmask of discovered port capabilities
 */
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

A port qualifies when [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) is set, its type is [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488) or [`PCI_EXP_TYPE_DOWNSTREAM`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L490), and either [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) forces native services or the host bridge kept [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654). A Switch Upstream Port never qualifies, whatever its Slot Capabilities hold, because the type test excludes it. With [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) unset, the function still adds the hotplug bit and then clears Command Completed and Hot-Plug Interrupt Enable, so interrupts the BIOS enabled stay quiet. With the option set, as this page assumes, `IS_ENABLED()` makes that branch dead, and pciehp takes over the register.

The figure places the two tests in a hierarchy, the host bridge flag as a boundary that covers everything below it and the Hot-Plug Capable bit as a property of each port.

```text
    Which ports get a hotplug service device
    ────────────────────────────────────────

    native_pcie_hotplug is per host bridge; Hot-Plug Capable is per port
                                                       ╎
      ┌──────────────────────────────────────────┐     ╎    ┌────────────────────────────────────────────┐
      │ host bridge, _OSC granted native hotplug │     ╎    │ host bridge, _OSC kept native hotplug      │
      │ native_pcie_hotplug 1                    │     ╎    │ native_pcie_hotplug 0                      │
      └─────────┬───────────────────────┬────────┘     ╎    └─────────┬──────────────────────────────────┘
                │                       │              ╎              │
                │                       │              ╎              │
        ┌───────┴───────┐       ┌───────┴───────┐      ╎      ┌───────┴───────┐
        │ Root Port     │       │ Root Port     │      ╎      │ Root Port     │
        │ HPC set       │       │ HPC clear     │      ╎      │ HPC set       │
        └───────┬───────┘       └───────────────┘      ╎      └───────────────┘
                │               no hotplug service     ╎      no hotplug service, unless
                │ hotplug service                      ╎      pcie_ports=native
                │                                      ╎
        ┌───────┴───────┐
        │ Upstream Port │ no hotplug service: not a Root
        │ of a Switch   │ or Downstream Port
        └───────┬───────┘
                │
            ┌───┴─────────────────────┐
    ┌───────┴─────────┐      ┌────────┴────────┐
    │ Downstream Port │      │ Downstream Port │
    │ HPC set         │      │ HPC clear       │
    └─────────────────┘      └─────────────────┘
    hotplug service          no hotplug service
```

A Root Port with Hot-Plug Capable set under a granting host bridge gets the service, and so does a Downstream Port below it, while the Switch Upstream Port between them fails the type test. Under a host bridge whose firmware kept native hotplug, no port gets the service unless the `pcie_ports=native` boot parameter set [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614).

### Each service bit becomes a child device of the port

The port bus driver models each service of a port as a device of its own, so that a service driver binds to it through the driver core. That device is a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), portdrv's service instance: a child of the port's `struct device` on a bus of portdrv's, with no configuration space of its own. Read the definition for what a service driver receives through it.

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

[`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) is the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) the interrupt vector portdrv assigned to the service, and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) the one service bit this device stands for. [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) is a pointer the service driver owns, and [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the embedded driver-model device the driver core matches and binds. Two inline helpers, [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) and [`get_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73), write and read the private pointer; pciehp keeps its controller there.

```c
/* drivers/pci/pcie/portdrv.h:68 */
static inline void set_service_data(struct pcie_device *dev, void *data)
{
	dev->priv_data = data;
}

static inline void *get_service_data(struct pcie_device *dev)
{
	return dev->priv_data;
}
```

The helpers touch [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) and nothing else, so the controller pointer is valid exactly as long as pciehp keeps it valid. [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) creates one service device per bit of the port's service mask; read the stage that handles a port without interrupts and then loops over the bits.

```c
/* drivers/pci/pcie/portdrv.c:331 */
static int pcie_port_device_register(struct pci_dev *dev)
{
	int status, capabilities, i, nr_service;
	int irqs[PCIE_PORT_DEVICE_MAXSERVICES];
	... /* 19 lines, to :354 */
	status = pcie_init_service_irqs(dev, irqs, capabilities);
	if (status) {
		capabilities &= PCIE_PORT_SERVICE_HP;
		if (!capabilities)
			goto error_disable;
	}

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
```

When the port cannot get interrupt vectors, the mask keeps only [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20), since the comment says pciehp can poll instead. The loop then calls [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) for each bit left in `capabilities`, a local of this function, with the vector chosen for that service. The name of each device carries a suffix from [`get_descriptor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L32), a macro of portdrv.c that combines the port type and the service bit.

```c
/* drivers/pci/pcie/portdrv.c:32 */
#define get_descriptor_id(type, service) (((type - 4) << 8) | service)
```

A Root Port has type 4, so its hotplug device ends in pcie004, and a Downstream Port, type 6, gets pcie204. [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) allocates the service device and fills it; read it for the bus, the parent and the name it gives.

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

	retval = device_register(device);
	if (retval) {
		put_device(device);
		return retval;
	}

	pm_runtime_no_callbacks(device);

	return 0;
}
```

[`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) copies the port, the vector and the service bit, puts the device on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) with the port's device as its parent, and registers it, which lets the driver core look for a driver at once. The release callback frees the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) at the last reference, and `pm_runtime_no_callbacks()` leaves runtime power management of the child to the port's own callbacks.

```text
    Each service of a port becomes a child device on the PCIe port bus
    ──────────────────────────────────────────────────────────────────

    struct pci_dev 0000:00:1c.0, a Root Port bound to pcieport
    ┌────────────────────────────────────────────────────────────────────────────────────────────┐
    │ dev, the port's struct device: the parent of every service device                          │
    └────────────────────────────────────────────────────────────────────────────────────────────┘
              ▲                       ▲                       ▲                       ▲
              │ parent                │ parent                │ parent                │ parent
              │                       │                       │                       │
    ┌─────────┴──────────┐  ┌─────────┴──────────┐  ┌─────────┴──────────┐  ┌─────────┴──────────┐
    │ struct pcie_device │  │ struct pcie_device │  │ struct pcie_device │  │ struct pcie_device │
    │ name   ..:pcie001  │  │ name   ..:pcie002  │  │ name   ..:pcie004  │  │ name   ..:pcie008  │
    │ service PME        │  │ service AER        │  │ service HP         │  │ service DPC        │
    │ bus    port bus    │  │ bus    port bus    │  │ bus    port bus    │  │ bus    port bus    │
    └────────────────────┘  └────────────────────┘  └────────────────────┘  └────────────────────┘
    bound by the other service                      binds pciehp: probe gets
    drivers, never by pciehp                        this pcie_device
```

The figure shows a Root Port that qualifies for four services; the hotplug child is the one pciehp binds, and its parent link leads back to the port that [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) also names.

### hpdriver_portdrv binds pciehp to every hotplug service device

A service device needs a service driver, and pciehp registers one at boot, before the port bus driver binds to any port. The driver core then matches each hotplug service device to it by service bit, and every later callback of the port reaches pciehp through the same structure. Read [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) for the hooks it installs and for the two fields that matching compares.

```c
/* drivers/pci/hotplug/pciehp_core.c:353 */
static struct pcie_port_service_driver hpdriver_portdrv = {
	.name		= "pciehp",
	.port_type	= PCIE_ANY_PORT,
	.service	= PCIE_PORT_SERVICE_HP,

	.probe		= pciehp_probe,
	.remove		= pciehp_remove,

#ifdef	CONFIG_PM
#ifdef	CONFIG_PM_SLEEP
	.suspend	= pciehp_suspend,
	.resume_noirq	= pciehp_resume_noirq,
	.resume		= pciehp_resume,
#endif
	.runtime_suspend = pciehp_runtime_suspend,
	.runtime_resume	= pciehp_runtime_resume,
#endif	/* PM */

	.slot_reset	= pciehp_slot_reset,
};
```

[`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20) and [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) select the devices, and [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) and [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245) bind and unbind. The power management hooks exist only under [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) and [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140), both set here. The error recovery hook at [`pciehp_hpc.c:915`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915) suppresses the link change that an upstream reset causes, a path this page leaves out because it belongs to the link-change suppression protocol. [`pcie_hp_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374) registers the structure; read it for the registration and its two debug messages.

```c
/* drivers/pci/hotplug/pciehp_core.c:374 */
int __init pcie_hp_init(void)
{
	int retval = 0;

	retval = pcie_port_service_register(&hpdriver_portdrv);
	pr_debug("pcie_port_service_register = %d\n", retval);
	if (retval)
		pr_debug("Failure to register service\n");

	return retval;
}
```

The result of [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) is printed by a `pr_debug()` site and returned. Read [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) for the bus it puts the driver on and for the boot parameter that stops it.

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

With `pcie_ports=compat`, [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1889) is set and registration fails with -ENODEV; otherwise the driver joins [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) through its embedded `struct device_driver`. At v7.2 [`pcie_hp_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374) has one caller, [`pcie_init_services()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L830), which the port bus driver's initcall runs before it registers itself.

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

The service drivers register before [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) does, so a service device created when the port driver binds finds its driver already on the bus. A build without [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) reaches the empty stub of portdrv.h instead.

```c
/* drivers/pci/pcie/portdrv.h:36 */
#ifdef CONFIG_HOTPLUG_PCI_PCIE
int pcie_hp_init(void);
#else
static inline int pcie_hp_init(void) { return 0; }
#endif
```

The swimlane shows the order across the boot initcall, the port's PCI driver, the port bus and pciehp, from registration to the probe of one port.

```text
    pciehp registers at boot, and each port's binding reaches pciehp_probe
    ──────────────────────────────────────────────────────────────────────

    time ↓
    boot, device_initcall   ╎ pcieport PCI driver     ╎ PCIe port bus           ╎ pciehp
    ────────────────────────┼─────────────────────────┼─────────────────────────┼──────────────────────────
    pcie_portdrv_init       ╎                         ╎                         ╎
    service drivers ────────────────────────────────────────────────────────────▶ hpdriver_portdrv
                            ╎                         ╎                         ╎ registered, no
                            ╎                         ╎                         ╎ device to probe
    pcie_portdriver ────────▶ registered              ╎                         ╎
                            ╎ binds each port         ╎                         ╎
                            ╎ service devices ────────▶ ..:pcie004 added        ╎
                            ╎                         ╎ service and port        ╎
                            ╎                         ╎ type match ─────────────▶ pciehp_probe runs
                            ╎                         ╎                         ╎ with this device
                            ╎                         ╎                         ╎
                            ╎ a port found later      ╎                         ╎
                            ╎ binds the same way      ╎                         ╎
                            ╎                         ╎                         ╎
```

When a service device is registered, the driver core asks the bus whether a driver fits. [`pcie_port_bus_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511) answers; read it for its two comparisons.

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

The service bits must be equal, and the port type must match unless the driver accepts any port, which [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) does for pciehp. The port-type filter therefore never refuses pciehp, and the type test of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) alone keeps Upstream Ports out. [`pcie_port_bus_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534) then calls the driver's hook; read it for the reference it takes.

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

The bus probe passes the service device to [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) and, when the hook succeeds, takes a reference on the device, which [`pcie_port_bus_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L562) drops after the remove hook. The figure maps each caller in portdrv to the member of [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) it reaches.

```text
    Each portdrv caller reaches one pciehp hook through one member
    ──────────────────────────────────────────────────────────────

    callers in portdrv                                    hpdriver_portdrv, a struct pcie_port_service_driver
                                                          ┌────────────────────────────────────────────────┐
    pcie_port_bus_probe ─────────────────────────────────▶│ probe            pciehp_probe                  │
    pcie_port_bus_remove ────────────────────────────────▶│ remove           pciehp_remove                 │
                                                          ├────────────────────────────────────────────────┤
    port .suspend .freeze .poweroff ─────────────────────▶│ suspend          pciehp_suspend                │
    port .resume_noirq .restore_noirq ───────────────────▶│ resume_noirq     pciehp_resume_noirq           │
    port .resume .thaw .restore ─────────────────────────▶│ resume           pciehp_resume                 │
    port .runtime_suspend, bridge_d3 ────────────────────▶│ runtime_suspend  pciehp_runtime_suspend        │
    port .runtime_resume ────────────────────────────────▶│ runtime_resume   pciehp_runtime_resume         │
                                                          ├────────────────────────────────────────────────┤
    port error .slot_reset ──────────────────────────────▶│ slot_reset       pciehp_slot_reset             │
                                                          ├────────────────────────────────────────────────┤
    pcie_port_bus_match compares ────────────────────────▶│ service          PCIE_PORT_SERVICE_HP          │
    these two with the device                             │ port_type        PCIE_ANY_PORT                 │
                                                          └────────────────────────────────────────────────┘

    the PM and error rows reach every service child of the port through pcie_port_device_iter
```

The binding and unbinding rows run through the driver core for one service device, while the power management and error rows run through [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) for every bound child of the port. From here on, each hook receives the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) of the slot's port, and pciehp finds its controller through [`get_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73).

### struct controller holds one slot's state in member groups

Once probe has run, everything pciehp knows about a slot is in one [`struct controller`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L91). The kerneldoc above the definition states the design, "PCIe hotplug has a 1:1 relationship between controller and slot, hence unlike other drivers, the two aren't represented by separate structures." The table says what each member holds and which code writes it, so the definition below reads as a map of who touches the slot's state.

| member | what it holds | written by |
|---|---|---|
| [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) | the port's service device, and through it the port | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) at probe |
| [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) | the Device Serial Number of the function at 00.0 | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006), and [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) after each hot-add |
| [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) | Slot Capabilities with the port adjustments | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) |
| [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) | whether in-band presence detection is off | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) |
| [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98) | the last value written to Slot Control | [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) |
| [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) | the mutex that serializes Slot Control writes | initialized by [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) |
| [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) | the jiffies of the last Slot Control write | [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) and the resume hooks |
| [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) | whether that write still awaits Command Completed | [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157), the completion paths and the resume hooks |
| [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) | where a writer sleeps until Command Completed | woken by [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) |
| [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) | events and requests waiting for the IRQ thread | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) and [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141) by atomic operations |
| [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) | whether the IRQ or the poll thread was set up | [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) and [`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969) |
| [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) | a power fault the user has not cleared | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) and [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) |
| [`poll_thread`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L107) | the thread that polls Slot Status in poll mode | [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) | the slot state, one of six values | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) and the event handlers of [`pciehp_ctrl.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c) |
| [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) | the mutex over state and the button work | initialized by [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) |
| [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) | the delayed work that acts 5 seconds after a button press | initialized by [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006), scheduled by [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) |
| [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113) | the slot as the hotplug core knows it | [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) and the hotplug core |
| [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) | the rwsem that keeps occupancy reads out of a slot reset | initialized by [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) |
| [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) | the hot-plug ports above this one, the lock subclass | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) |
| [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) | whether the IRQ thread is handling events | [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) |
| [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) | the result of the last request from sysfs | the event handlers and [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) |
| [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) | where a request from sysfs sleeps until the IRQ thread ends | woken by [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) |

The definition shows the same members in source order, with the comments that name the groups.

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

The comments split the members after [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) and [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) into five groups in pciehp.h at v7.2: capabilities and quirks, control register access, event handling, state machine and hotplug core interface. The groups differ in who writes them and what orders the writes, which the figure draws group by group.

```text
    struct controller by field group, with who writes each group and what orders it
    ───────────────────────────────────────────────────────────────────────────────

                              struct controller
                              ┌───────────────────────────────┐
    port and device           │ pcie, dsn                     │◀──── pcie_init at probe; dsn again
                              │                               │      after each hot-add
                              ├───────────────────────────────┤
    capabilities and quirks   │ slot_cap,                     │◀──── pcie_init, before any IRQ
                              │ inband_presence_disabled      │      exists; read-only after
                              ├───────────────────────────────┤
    control register access   │ slot_ctrl, ctrl_lock,         │◀──── each Slot Control write,
                              │ cmd_started, cmd_busy, queue  │      holding ctrl_lock
                              ├───────────────────────────────┤
    event handling            │ pending_events,               │◀──── pending_events by atomic ops of
                              │ notification_enabled,         │      the interrupt handler and the
                              │ power_fault_detected,         │      requesters; notification_enabled
                              │ poll_thread                   │      by probe and remove
                              ├───────────────────────────────┤
    state machine             │ state, state_lock,            │◀──── event handlers and
                              │ button_work                   │      button work, holding
                              │                               │      state_lock
                              ├───────────────────────────────┤
    hotplug core interface    │ hotplug_slot, reset_lock,     │◀──── hotplug core for the slot;
                              │ depth, ist_running,           │      slot reset holds reset_lock
                              │ request_result, requester     │      to write, readers to read
                              └───────────────────────────────┘
```

The capability group is written before an interrupt exists and only read afterwards, so it needs no lock. [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) orders the command group, [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) the state group, and [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) guards the occupancy reads of the hotplug core group against a slot reset; the event group relies on atomic operations instead. The strip follows one controller from probe to remove through the members that two or more of the functions this page shows write.

```text
    One struct controller from probe to remove, and the writes to its lifecycle fields
    ──────────────────────────────────────────────────────────────────────────────────

    fields: the object itself, slot_cap, state, dsn, cmd_busy, cmd_started, hotplug_slot.ops,
    hotplug_slot.pci_slot and notification_enabled

    time ─────────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event                  alloc      writes         slot       IRQ on   resume         IRQ off  slot off  free
                           ▼          ▼              ▼          ▼        ▼              ▼        ▼         ▼
                          ┌───────────────────────────────────────────────────────────────────────────────┬───────────┐
    object                │ «1» allocated zeroed by pcie_init, then filled                                │ «17» freed│
                          └───────────────────────────────────────────────────────────────────────────────┴───────────┘
                          ┌───────────────────────────────────────────────────────────────────────────────────────────┐
    slot_cap              │ «2» Slot Capabilities after the port adjustments                                          │
                          └───────────────────────────────────────────────────────────────────────────────────────────┘
                          ┌────────────────────────────────────┬──────────────────────────────────────────────────────┐
    state                 │ «3» OFF or ON                      │ moved by the event handlers                          │
                          └────────────────────────────────────┴──────────────────────────────────────────────────────┘
                          ┌───────────────────────────────────────────────────────────────────────────────────────────┐
    dsn                   │ «4» Device Serial Number of the function at 00.0                                          │
                          └───────────────────────────────────────────────────────────────────────────────────────────┘
                          ┌──────────┬──────────────────────────────────┬──────────────┬──────────────────────────────┐
    cmd_busy              │ 0        │ «5» 1 per write, «7» 0 on erratum│ «12» «14» 1  │                              │
                          └──────────┴──────────────────────────────────┴──────────────┴──────────────────────────────┘
                          ┌──────────┬──────────────────────────────────┬──────────────┬──────────────────────────────┐
    cmd_started           │ 0        │ «6» time of each write           │ «11» «13» now│                              │
                          └──────────┴──────────────────────────────────┴──────────────┴──────────────────────────────┘
                          ┌─────────────────────────┬─────────────────────────────────────────────────────────────────┐
    hotplug_slot.ops      │ NULL                    │ «8» pciehp's callback table                                     │
                          └─────────────────────────┴─────────────────────────────────────────────────────────────────┘
                          ┌─────────────────────────┬───────────────────────────────────────────┬─────────────────────┐
    hotplug_slot.pci_slot │ NULL                    │ «9» the bus-wide pci_slot                 │ «16» NULL           │
                          └─────────────────────────┴───────────────────────────────────────────┴─────────────────────┘
                          ┌────────────────────────────────────┬───────────────────────┬──────────────────────────────┐
    notification_enabled  │ 0                                  │ «10» 1                │ «15» 0                       │
                          └────────────────────────────────────┴───────────────────────┴──────────────────────────────┘

    «1»  pcie_init                   pciehp_hpc.c:1014       allocates the controller zeroed with kzalloc_obj
    «2»  pcie_init                   :1032                   stores the adjusted copy of Slot Capabilities
    «3»  pcie_init                   :1042                   seeds state from whether the secondary bus has devices
    «4»  pcie_init                   :1090                   caches the serial number of the function at 00.0
    «5»  pcie_do_write_cmd           :179                    marks a Slot Control command as in flight
    «6»  pcie_do_write_cmd           :183                    records the time the command was written
    «7»  pcie_do_write_cmd           :194                    clears the busy flag on a port with the erratum
    «8»  init_slot                   pciehp_core.c:78        points ops at the table it filled
    «9»  __pci_hp_initialize         pci_hotplug_core.c:408  links the pci_slot the PCI core created
    «10» pcie_init_notification      pciehp_hpc.c:965        records that the IRQ or the poll thread exists
    «11» pciehp_resume_noirq         pciehp_core.c:293       dates the Slot Control write of the restore
    «12» pciehp_resume_noirq         :294                    marks that restored write as in flight
    «13» pciehp_runtime_resume       :341                    dates the restore write after runtime resume
    «14» pciehp_runtime_resume       :342                    marks that restored write as in flight
    «15» pcie_shutdown_notification  pciehp_hpc.c:974        records that the IRQ or the poll thread is gone
    «16» pci_hp_destroy              pci_hotplug_core.c:485  unlinks the pci_slot before destroying it
    «17» pciehp_release_ctrl         pciehp_hpc.c:1099       frees the controller with kfree
```

«1» [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller zeroed through `kzalloc_obj()`. «2» `pcie_init()` stores the adjusted Slot Capabilities in [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95). «3» `pcie_init()` seeds [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) from whether the secondary bus already has devices. «4» `pcie_init()` caches the serial number of the function at 00.0 in [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93). «5» [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) sets [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) before it writes Slot Control. «6» `pcie_do_write_cmd()` records the time of that write in [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100). «7» `pcie_do_write_cmd()` clears the busy flag again on a port with the Command Completed erratum when the write changed no control field. «8» [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) points [`ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L58) at the callback table it filled. «9» [`__pci_hp_initialize()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L385) stores the slot the PCI core created in [`pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L61). «10» [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) sets [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) once the IRQ or the poll thread exists. «11» [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) dates the Slot Control write of the PCI core's restore. «12» `pciehp_resume_noirq()` marks that restored write as in flight. «13» [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336) dates the restore write after a runtime resume. «14» `pciehp_runtime_resume()` marks that write as in flight. «15» [`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969) clears the notification flag once the IRQ or the poll thread is gone. «16» [`pci_hp_destroy()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L481) sets the slot pointer back to NULL before it destroys the slot. «17» [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) frees the controller with `kfree()`.

The callers of these writers reach the same writes through them, [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) through «1», «8», «9» and «10», and [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245) through «15» to «17». The strip leaves out the writers this page does not show and the drawn object's fields that carry events into the IRQ thread; the table names each with its site and the reason.

| left out | writer | site | reason |
|---|---|---|---|
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) | [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) | [`pciehp_ctrl.c:174`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L174) | event handling after a button press, which this page follows only to its hand-off |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) | [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) | [`pciehp_ctrl.c:226`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L226) | event handling in the IRQ thread |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) | [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) | [`pciehp_ctrl.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L246) | event handling in the IRQ thread, where hot-add and hot-remove begin |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) | [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) | [`pciehp_ctrl.c:355`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L355) | the end of a hot-add |
| [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) | [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) | [`pciehp_ctrl.c:387`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L387) | the end of a hot-remove |
| [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) | [`pciehp_configure_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L32) | [`pciehp_pci.c:76`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_pci.c#L76) | the hot-add path, after probe |
| [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) | [`pcie_poll_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L86) | [`pciehp_hpc.c:102`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L102) | the completion side of the command protocol, polled |
| [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) | [`pciehp_hpc.c:708`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L708) | the completion side of the command protocol, from the interrupt |
| [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) | [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) | [`pciehp_ctrl.c:143`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L143) | carries events into the IRQ thread; this page shows only the request side |
| [`power_fault_detected`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L106) | [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623), [`pciehp_power_on_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L534) | [`pciehp_hpc.c:677`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L677) | power fault handling, outside probe, sleep and remove |
| [`ist_running`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L116) | [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) | [`pciehp_hpc.c:735`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L735) | written only inside the IRQ thread |
| [`request_result`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L117) | the event handlers, [`pciehp_sysfs_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L393) | [`pciehp_ctrl.c:229`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L229) | the result of a request from sysfs |

Between «1» and «10» the controller belongs to probe alone, because neither an interrupt nor a user request can reach it yet. From «10» on, the IRQ thread and user space share it, which the locks of the groups above keep apart.

### to_ctrl and slot_name connect a controller and its slot

The hotplug core knows a slot only as a [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57), and it passes that pointer to every callback. Because pciehp embeds the structure in the controller, a callback recovers the controller by address arithmetic, and the slot's name comes back the other way, through the [`struct pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L85) the PCI core created. Read [`struct hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L57) and [`hotplug_slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L66) for the two links.

```c
/* include/linux/pci_hotplug.h:50 */
/**
 * struct hotplug_slot - used to register a physical slot with the hotplug pci core
 * @ops: pointer to the &struct hotplug_slot_ops to be used for this slot
 * @pci_slot: represents a physical slot
 * @owner: The module owner of this structure
 * @mod_name: The module name (KBUILD_MODNAME) of this structure
 */
struct hotplug_slot {
	const struct hotplug_slot_ops	*ops;

	/* Variables below this are for use only by the hotplug pci core. */
	struct pci_slot			*pci_slot;
	struct module			*owner;
	const char			*mod_name;
};

static inline const char *hotplug_slot_name(const struct hotplug_slot *slot)
{
	return pci_slot_name(slot->pci_slot);
}
```

[`ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L58) is the driver's callback table, and the core fills [`pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L61), [`owner`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L62) and [`mod_name`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L63) at registration, as the comment above them says. [`hotplug_slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L66) returns the name of the slot's kobject, so it works only after registration. pciehp wraps both directions in two inline helpers of pciehp.h, [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) and [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207).

```c
/* drivers/pci/hotplug/pciehp.h:202 */
static inline const char *slot_name(struct controller *ctrl)
{
	return hotplug_slot_name(&ctrl->hotplug_slot);
}

static inline struct controller *to_ctrl(struct hotplug_slot *hotplug_slot)
{
	return container_of(hotplug_slot, struct controller, hotplug_slot);
}
```

[`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) is `container_of()` over the member [`hotplug_slot`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L113), so it subtracts the member's offset from the pointer the core passes. [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) hands the embedded slot to [`hotplug_slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L66), which makes the Physical Slot Number that names the kobject the name of every pciehp message about the slot. At v7.2 each callback that [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installs starts with [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207); read [`get_power_status()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L118), which a read of the slot's power file reaches.

```c
/* drivers/pci/hotplug/pciehp_core.c:118 */
static int get_power_status(struct hotplug_slot *hotplug_slot, u8 *value)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl->pcie->port;

	pci_config_pm_runtime_get(pdev);
	pciehp_get_power_status(ctrl, value);
	pci_config_pm_runtime_put(pdev);
	return 0;
}
```

The callback converts the slot to its controller, takes a runtime power reference on the port so that the configuration read reaches it, and reads the power state. The figure draws the embedding and the two pointers that close the loop between the controller and the PCI core's slot.

```text
    Embedding lets to_ctrl step back from the slot to its controller
    ────────────────────────────────────────────────────────────────

                          struct controller
                     ┌──┬────────────────────────────────────────────────┐
    member offset    │  │ pcie, dsn, slot_cap, slot_ctrl, ...            │
    that to_ctrl     │  │ state, state_lock, button_work                 │
    subtracts        │  │                                                │
                     └──┼───────────────┬────────────────────────────┐   │           struct pci_slot
                        │ hotplug_slot  │ ops                        │   │           ┌────────────────────────────┐
                        │               │ pci_slot ──────────────────┼───┼──────────▶│ hotplug ─────────────────┐ │
                        │               │ owner, mod_name            │   │           │ number                   │ │
                        │               └────────────────────────────┘   │           │ kobj  named by PSN       │ │
                        │                             ▲                  │           └──────────────────────────┼─┘
                        │                             └──────────────────┼──────────────────────────────────────┘
                        │ reset_lock, depth, ... requester               │
                        └────────────────────────────────────────────────┘  slot_name(ctrl) returns the name of kobj
```

[`pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L61) leads from the embedded slot to the PCI core's slot, and [`hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L88) leads back, so either side reaches the other once registration has set both.

So far, the port has qualified for the hotplug service, portdrv has created a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) for it, and [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) binds pciehp to that device. The controller that probe builds holds the slot's state in groups with their own writers, and [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) and [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) connect it to the slot the hotplug core sees.

### pciehp_probe builds the controller in four nested steps

Binding hands [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) a hotplug service device, and probe turns it into a working slot through four steps, each of which the next one depends on. The slot is registered for in-kernel use before the interrupt is requested and published to user space only after that, an order that commit [774d446b0f92](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=774d446b0f9222f46772dde8770d7c1c169c0284) ("PCI: pciehp: Publish to user space last on probe") says lets the IRQ thread alone enable and disable the slot. The function is read in three pieces.

| piece | lines | stage |
|---|---|---|
| ❶ | pciehp_core.c:185-206 | refuses a foreign service or a port without a secondary bus, builds the controller and stores it |
| ❷ | pciehp_core.c:207-234 | registers the slot, enables events, publishes the slot and checks presence |
| ❸ | pciehp_core.c:235-243 | undoes the steps taken so far when one fails |

❶ The first piece of [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) checks the service device and its port, then builds the controller and stores it in the service device.

```c
/* drivers/pci/hotplug/pciehp_core.c:185 */
static int pciehp_probe(struct pcie_device *dev)
{
	int rc;
	struct controller *ctrl;

	/* If this is not a "hotplug" service, we have no business here. */
	if (dev->service != PCIE_PORT_SERVICE_HP)
		return -ENODEV;

	if (!dev->port->subordinate) {
		/* Can happen if we run out of bus numbers during probe */
		pci_err(dev->port,
			"Hotplug bridge without secondary bus, ignoring\n");
		return -ENODEV;
	}

	ctrl = pcie_init(dev);
	if (!ctrl) {
		pci_err(dev->port, "Controller initialization failed\n");
		return -ENODEV;
	}
	set_service_data(dev, ctrl);
```

A port without a [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus has nowhere to put a slot, and the comment names running out of bus numbers as the cause. [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) returns the new controller or NULL, and [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) stores it in [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63), where every later hook of [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) finds it.

❷ The second piece of [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) runs the registration, notification and publication steps and then the presence check, each failure jumping to a label of the third piece.

```c
/* drivers/pci/hotplug/pciehp_core.c:207 */

	/* Setup the slot information structures */
	rc = init_slot(ctrl);
	if (rc) {
		if (rc == -EBUSY)
			ctrl_warn(ctrl, "Slot already registered by another hotplug driver\n");
		else
			ctrl_err(ctrl, "Slot initialization failed (%d)\n", rc);
		goto err_out_release_ctlr;
	}

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
```

[`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) registers the slot for in-kernel use and fails with -EBUSY when another hotplug driver already claimed the slot, which probe reports as a warning. [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) requests the interrupt or starts the poll thread and enables the slot's events, [`pci_hp_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L424) creates the slot's files, and [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) brings the slot in line with what it holds.

❸ The third piece of [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) holds the error labels, in the reverse order of the steps.

```c
/* drivers/pci/hotplug/pciehp_core.c:235 */

err_out_shutdown_notification:
	pcie_shutdown_notification(ctrl);
err_out_free_ctrl_slot:
	cleanup_slot(ctrl);
err_out_release_ctlr:
	pciehp_release_ctrl(ctrl);
	return -ENODEV;
}
```

Each label undoes one step and falls through to the labels below it, so a failure undoes exactly the steps taken before it. Probe returns -ENODEV for every failure, whatever the failing step returned. The figure draws the four steps as nested spans, each closed by the function that remove and the labels share.

```text
    Probe opens four nested spans, and remove closes them in reverse
    ────────────────────────────────────────────────────────────────

    opened by probe                                                             closed by remove and by the
                                                                                error labels, innermost first

    time ──────────────────────────────────────────────────────────────────────▶

    pcie_init: controller     ├─────────────────────────────────────────────┤   pciehp_release_ctrl
    init_slot: slot registered   ├───────────────────────────────────────┤      cleanup_slot
    pcie_init_notification: IRQ     ├─────────────────────────────────┤         pcie_shutdown_notification
    pci_hp_add: slot files             ├───────────────────────────┤            pci_hp_del, remove only
                                          ╎
                                          ╎ pciehp_check_presence runs inside all four

    a failed step leaves through the label that closes every span opened before it
```

The presence check runs inside all four spans, so it can hand work to the IRQ thread and let user space see the slot. The subsections that follow open the spans in order, starting with the controller itself.

### pcie_init allocates the controller and caches Slot Capabilities

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) builds the controller before anything else can reach it, so it reads and writes the slot's registers without taking a lock. It works in four stages, which the outline names, and this subsection reads the first two: the allocation, and the copy of Slot Capabilities with the port adjustments.

| piece | lines | stage |
|---|---|---|
| Ⓐ | pciehp_hpc.c:1006-1019 | allocates the controller and records the service device and the hotplug depth |
| Ⓑ | pciehp_hpc.c:1020-1039 | reads and adjusts Slot Capabilities, initializes locks, wait queues and the button work |
| Ⓒ | pciehp_hpc.c:1040-1059 | seeds the state, disables in-band presence detection and clears stale events |
| Ⓓ | pciehp_hpc.c:1060-1094 | prints the capabilities, powers off an empty slot and caches the serial number |

Ⓐ The first piece of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) allocates the controller and records the port's service device and its depth among hot-plug ports.

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
	ctrl->depth = pcie_hotplug_depth(dev->port);
```

`kzalloc_obj()` returns zeroed memory, so every member starts at 0 or NULL until a later line sets it. [`pcie`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L92) points at the service device, and [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) receives from [`pcie_hotplug_depth()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L992) the number of hot-plug capable ports above this one, the lockdep subclass of the reset lock. `pdev`, the port, and `subordinate`, its secondary bus, are locals of this function.

Ⓑ The second piece of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) reads Slot Capabilities, applies two port adjustments and initializes the locks, the wait queues and the button work.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1020 */
	pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP, &slot_cap);

	if (pdev->hotplug_user_indicators)
		slot_cap &= ~(PCI_EXP_SLTCAP_AIP | PCI_EXP_SLTCAP_PIP);

	/*
	 * We assume no Thunderbolt controllers support Command Complete events,
	 * but some controllers falsely claim they do.
	 */
	if (pdev->is_thunderbolt)
		slot_cap |= PCI_EXP_SLTCAP_NCCS;

	ctrl->slot_cap = slot_cap;
	mutex_init(&ctrl->ctrl_lock);
	mutex_init(&ctrl->state_lock);
	init_rwsem(&ctrl->reset_lock);
	init_waitqueue_head(&ctrl->requester);
	init_waitqueue_head(&ctrl->queue);
	INIT_DELAYED_WORK(&ctrl->button_work, pciehp_queue_pushbutton_work);
	dbg_ctrl(ctrl);
```

On a port with [`hotplug_user_indicators`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L425) set, the copy drops Attention Indicator Present and Power Indicator Present, so pciehp leaves both indicators to user space; on x86 the flag is set at [`common.c:640`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/pci/common.c#L640) for the ports of one vendor-specific domain. The port flag tested at line 1029 marks one vendor's tunneling controllers, and the comment says they do not support Command Completed events although some claim to, so the copy sets No Command Completed Support. [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95) receives the adjusted copy, the three locks and two wait queues are initialized, [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111) is bound to the button work function, and [`dbg_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L978) prints the slot registers at the debug level. The figure compares the register as read with the copy.

```text
    pcie_init caches Slot Capabilities with three bits adjusted
    ───────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    read  │       PSN (31:19)       │N│E│LS │  SPLV (14:7)  │H│S│P│A│M│C│B│
          ├─────────────────────────┼─┼─┼───┼───────────────┼─┼─┼─┼─┼─┼─┼─┤
    copy  │       PSN (31:19)       │1│E│LS │  SPLV (14:7)  │H│S│0│0│M│C│B│
          └─────────────────────────┴─┴─┴───┴───────────────┴─┴─┴─┴─┴─┴─┴─┘

    read = PCI_EXP_SLTCAP as pcie_init reads it; copy = the value pcie_init stores in slot_cap
    N = PCI_EXP_SLTCAP_NCCS (No Command Completed Support), forced to 1 in the copy on ports pciehp_hpc.c:1029 selects
    P = PCI_EXP_SLTCAP_PIP (Power Indicator Present), A = PCI_EXP_SLTCAP_AIP (Attention Indicator Present),
        both cleared in the copy on a port with hotplug_user_indicators set
    B = PCI_EXP_SLTCAP_ABP (Attention Button Present), C = PCI_EXP_SLTCAP_PCP (Power Controller Present)
    M = PCI_EXP_SLTCAP_MRLSP (MRL Sensor Present), PSN = PCI_EXP_SLTCAP_PSN (Physical Slot Number, 31:19)
    H = PCI_EXP_SLTCAP_HPC (Hot-Plug Capable), S = PCI_EXP_SLTCAP_HPS (Hot-Plug Surprise)
    E = PCI_EXP_SLTCAP_EIP (Electromechanical Interlock Present), LS = PCI_EXP_SLTCAP_SPLS (16:15)
    SPLV = PCI_EXP_SLTCAP_SPLV (Slot Power Limit Value, 14:7)
    the copy is tested through ATTN_BUTTN (B), POWER_CTRL (C), MRL_SENS (M), ATTN_LED (A), PWR_LED (P),
    NO_CMD_CMPL (N) and PSN (PSN)
```

The capability tests of pciehp read the copy through macros of pciehp.h; read them for the bit each one tests.

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

Each macro masks one Slot Capabilities bit of [`slot_cap`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L95), and [`PSN`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162) shifts the Physical Slot Number down from bits 31:19. Because they read the copy, the two adjustments above change their answers for the life of the controller. At v7.2 [`PWR_LED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L160) has one user, [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513); read it for how the two indicator tests shape a Slot Control command.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:513 */
void pciehp_set_indicators(struct controller *ctrl, int pwr, int attn)
{
	u16 cmd = 0, mask = 0;

	if (PWR_LED(ctrl) && pwr != INDICATOR_NOOP) {
		cmd |= (pwr & PCI_EXP_SLTCTL_PIC);
		mask |= PCI_EXP_SLTCTL_PIC;
	}

	if (ATTN_LED(ctrl) && attn != INDICATOR_NOOP) {
		cmd |= (attn & PCI_EXP_SLTCTL_AIC);
		mask |= PCI_EXP_SLTCTL_AIC;
	}

	if (cmd) {
		pcie_write_cmd_nowait(ctrl, cmd, mask);
		ctrl_dbg(ctrl, "%s: SLOTCTRL %x write cmd %x\n", __func__,
			 pci_pcie_cap(ctrl->pcie->port) + PCI_EXP_SLTCTL, cmd);
	}
}
```

A field joins the command only when the copy says its indicator exists and the caller asked to change it, so [`pciehp_set_indicators()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L513) writes Power Indicator Control only on a port whose copy keeps Power Indicator Present. After the second piece the controller holds its port, its depth and its capability copy, and its locks are ready.

### pcie_init seeds the state and quiets the slot before an interrupt exists

A slot the firmware brought up already holds devices when pciehp probes, and a slot can also carry stale events or power left on with nothing inserted. The last two pieces of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) read the bus to seed the state, clear old events and power off an empty slot, all before the interrupt exists, so that nothing they do is reported as a hotplug event.

Ⓒ The third piece of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) seeds the state, disables in-band presence detection where the port supports it, and clears the event bits of Slot Status.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1040 */

	down_read(&pci_bus_sem);
	ctrl->state = list_empty(&subordinate->devices) ? OFF_STATE : ON_STATE;
	up_read(&pci_bus_sem);

	pcie_capability_read_dword(pdev, PCI_EXP_SLTCAP2, &slot_cap2);
	if (slot_cap2 & PCI_EXP_SLTCAP2_IBPD) {
		pcie_write_cmd_nowait(ctrl, PCI_EXP_SLTCTL_IBPD_DISABLE,
				      PCI_EXP_SLTCTL_IBPD_DISABLE);
		ctrl->inband_presence_disabled = 1;
	}

	if (dmi_first_match(inband_presence_disabled_dmi_table))
		ctrl->inband_presence_disabled = 1;

	/* Clear all remaining event bits in Slot Status register. */
	pcie_capability_write_word(pdev, PCI_EXP_SLTSTA,
		PCI_EXP_SLTSTA_ABP | PCI_EXP_SLTSTA_PFD |
		PCI_EXP_SLTSTA_MRLSC | PCI_EXP_SLTSTA_CC |
		PCI_EXP_SLTSTA_DLLSC | PCI_EXP_SLTSTA_PDC);
```

[`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109) becomes [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) when the secondary bus lists devices and [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) otherwise, read under `pci_bus_sem`. A port whose Slot Capabilities 2 sets In-band PD Disable Supported gets the disable written with [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219), the controller's first Slot Control command, and [`inband_presence_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L96) records it. [`inband_presence_disabled_dmi_table`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L31) at the top of the file sets the same flag on the systems it lists. With [`CONFIG_DMI`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/Kconfig#L944) set, as on x86-64 by default, [`dmi_first_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/firmware/dmi_scan.c#L935) searches the firmware's DMI data; unset, it is the stub of dmi.h below.

```c
/* include/linux/dmi.h:170 */
static inline const struct dmi_system_id *
	dmi_first_match(const struct dmi_system_id *list) { return NULL; }
```

The stub returns NULL, so without [`CONFIG_DMI`](https://elixir.bootlin.com/linux/v7.2/source/arch/x86/Kconfig#L944) only the capability bit sets the flag. The Slot Status write clears the six event bits of its mask, because those bits clear when written with 1, so no event older than the controller survives into the interrupt handler.

Ⓓ The fourth piece of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) prints the capabilities, powers off an empty slot whose power is on, and caches the serial number of the device in the slot.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1060 */

	ctrl_info(ctrl, "Slot #%d AttnBtn%c PwrCtrl%c MRL%c AttnInd%c PwrInd%c HotPlug%c Surprise%c Interlock%c NoCompl%c IbPresDis%c LLActRep%c%s\n",
		FIELD_GET(PCI_EXP_SLTCAP_PSN, slot_cap),
		FLAG(slot_cap, PCI_EXP_SLTCAP_ABP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_PCP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_MRLSP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_AIP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_PIP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_HPC),
		FLAG(slot_cap, PCI_EXP_SLTCAP_HPS),
		FLAG(slot_cap, PCI_EXP_SLTCAP_EIP),
		FLAG(slot_cap, PCI_EXP_SLTCAP_NCCS),
		FLAG(slot_cap2, PCI_EXP_SLTCAP2_IBPD),
		FLAG(pdev->link_active_reporting, true),
		pdev->broken_cmd_compl ? " (with Cmd Compl erratum)" : "");

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

	pdev = pci_get_slot(subordinate, PCI_DEVFN(0, 0));
	if (pdev)
		ctrl->dsn = pci_get_dsn(pdev);
	pci_dev_put(pdev);

	return ctrl;
}
```

The info line prints the Physical Slot Number and a sign for each capability. The signs come from a macro defined just above [`pcie_hotplug_depth()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L992).

```c
/* drivers/pci/hotplug/pciehp_hpc.c:990 */
#define FLAG(x, y)	(((x) & (y)) ? '+' : '-')
```

[`FLAG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L990) yields '+' for a set bit and '-' for a clear one, and the message also reports Link Active Reporting and the Command Completed erratum of the port. When the slot has a Power Controller, holds nothing and has power on, [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) first masks the slot's events with [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) and then powers the slot off. The masking keeps the power-off command from raising an interrupt, and commit [4e6a13356f1c](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=4e6a13356f1c1dc27ff48ff35576a478d73f8713) ("PCI: pciehp: Deduplicate presence check on probe & resume") added it when it moved this check into [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006). Read [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) for the mask it clears.

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

The command writes 0 under a mask of every event enable and both interrupt enables, and [`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) waits for it to complete before returning. The last lines of the fourth piece look up the function at devfn 00.0 with `pci_get_slot()`, store its Device Serial Number from [`pci_get_dsn()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L555) in [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93), and drop the lookup's reference; an empty slot leaves [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) at 0. The resume hooks compare that number to detect a device replaced during sleep. When [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) returns, the controller knows its slot's capabilities and state, and the slot raises no stale event.

### ctrl_lock serializes Slot Control commands and their completion

A Slot Control write is a command to the port, and the specification lets software issue the next one only after the port signals Command Completed or a second has passed, as the comment on [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) cites. Within pciehp at v7.2 a single line writes Slot Control, inside one function that holds [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99), and the third piece of [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) issued the first command through it. Read the two entry points, which differ only in whether they wait for the new command.

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

[`pcie_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L213) waits for the command it issues, and [`pcie_write_cmd_nowait()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L219) returns once the write is done. [`pcie_do_write_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L157) holds [`ctrl_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L99) across the wait for the previous command, the read-modify-write and the optional wait for the new one; read it for the order of those steps and for the members it sets.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:157 */
static void pcie_do_write_cmd(struct controller *ctrl, u16 cmd,
			      u16 mask, bool wait)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_ctrl_orig, slot_ctrl;

	mutex_lock(&ctrl->ctrl_lock);

	/*
	 * Always wait for any previous command that might still be in progress
	 */
	pcie_wait_cmd(ctrl);

	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &slot_ctrl);
	if (PCI_POSSIBLE_ERROR(slot_ctrl)) {
		ctrl_info(ctrl, "%s: no response from device\n", __func__);
		goto out;
	}

	slot_ctrl_orig = slot_ctrl;
	slot_ctrl &= ~mask;
	slot_ctrl |= (cmd & mask);
	ctrl->cmd_busy = 1;
	smp_mb();
	ctrl->slot_ctrl = slot_ctrl;
	pcie_capability_write_word(pdev, PCI_EXP_SLTCTL, slot_ctrl);
	ctrl->cmd_started = jiffies;

	/*
	 * Controllers with the Intel CF118 and similar errata advertise
	 * Command Completed support, but they only set Command Completed
	 * if we change the "Control" bits for power, power indicator,
	 * attention indicator, or interlock.  If we only change the
	 * "Enable" bits, they never set the Command Completed bit.
	 */
	if (pdev->broken_cmd_compl &&
	    (slot_ctrl_orig & CC_ERRATUM_MASK) == (slot_ctrl & CC_ERRATUM_MASK))
		ctrl->cmd_busy = 0;

	/*
	 * Optionally wait for the hardware to be ready for a new command,
	 * indicating completion of the above issued command.
	 */
	if (wait)
		pcie_wait_cmd(ctrl);

out:
	mutex_unlock(&ctrl->ctrl_lock);
}
```

The write takes the current register value, replaces the bits under `mask` with those of `cmd`, both parameters of the function, and keeps the result in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98). [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) is set before the write and [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) right after it, and the next writer waits on both. On a port with [`broken_cmd_compl`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L521) set, a command that changes none of the erratum fields clears the busy flag at once, because the comment says such ports never complete it. The erratum fields are those of a mask macro defined just above the function.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:152 */
#define CC_ERRATUM_MASK		(PCI_EXP_SLTCTL_PCC |	\
				 PCI_EXP_SLTCTL_PIC |	\
				 PCI_EXP_SLTCTL_AIC |	\
				 PCI_EXP_SLTCTL_EIC)
```

[`CC_ERRATUM_MASK`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L152) holds the Power Controller Control, both indicator controls and Electromechanical Interlock Control, the fields whose change does complete on such a port. [`pcie_wait_cmd()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L112) is the wait itself; read it for the deadline and the two ways of waiting.

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

A port whose copy has [`NO_CMD_CMPL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) set never waits, and neither does a writer that finds [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) clear. Otherwise the deadline is [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) plus 1000 ms, or 2500 ms with [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) set; the writer sleeps on [`queue`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L102) when Hot-Plug Interrupt Enable and Command Completed Interrupt Enable are both set in [`slot_ctrl`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L98), and polls Slot Status otherwise. A wait that ends without completion prints the timeout message, and the next write proceeds anyway. The figure puts both outcomes on one time axis.

```text
    A Slot Control write holds the next one until Command Completed or a deadline
    ─────────────────────────────────────────────────────────────────────────────

    (▼ = write A at cmd_started; the deadline is 1000 ms later, 2500 ms with pciehp_poll_mode)

                  ▼                                               ▼ cmd_started + 1000 ms
    Command Completed arrives                                     ╎
                  ┌───────────┐                                   ╎
    cmd_busy ─────┘           └────────────────────────────────────────────────────────────────
                  A           CC clears it    B writes at once    ╎
                                                                  ╎
    no Command Completed arrives                                  ╎
                  ┌────────────────────────────────────────────────────────────────────────────
    cmd_busy ─────┘                                               ╎
                  A               B waits in pcie_wait_cmd        B writes; the timeout
                                                                  message prints and cmd_busy
                                                                  is set again by B
```

Because the next writer reads [`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) and [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101), code that writes Slot Control outside this function must set both, which the resume hooks do after the PCI core's restore.

### init_slot registers one slot for the whole secondary bus

The hotplug core shows a slot through callbacks the driver supplies and through a [`struct pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L85) that the PCI core creates on the slot's bus. [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) fills the callback table from the capability copy and registers the slot for in-kernel use, without publishing it yet. Read it for which callbacks depend on which capability and for the slot number it registers.

```c
/* drivers/pci/hotplug/pciehp_core.c:51 */
static int init_slot(struct controller *ctrl)
{
	struct hotplug_slot_ops *ops;
	char name[SLOT_NAME_SIZE];
	int retval;

	/* Setup hotplug slot ops */
	ops = kzalloc_obj(*ops);
	if (!ops)
		return -ENOMEM;

	ops->enable_slot = pciehp_sysfs_enable_slot;
	ops->disable_slot = pciehp_sysfs_disable_slot;
	ops->get_power_status = get_power_status;
	ops->get_adapter_status = get_adapter_status;
	ops->reset_slot = pciehp_reset_slot;
	if (MRL_SENS(ctrl))
		ops->get_latch_status = get_latch_status;
	if (ATTN_LED(ctrl)) {
		ops->get_attention_status = pciehp_get_attention_status;
		ops->set_attention_status = set_attention_status;
	} else if (ctrl->pcie->port->hotplug_user_indicators) {
		ops->get_attention_status = pciehp_get_raw_indicator_status;
		ops->set_attention_status = pciehp_set_raw_indicator_status;
	}

	/* register this slot with the hotplug pci core */
	ctrl->hotplug_slot.ops = ops;
	snprintf(name, SLOT_NAME_SIZE, "%u", PSN(ctrl));

	retval = pci_hp_initialize(&ctrl->hotplug_slot,
				   ctrl->pcie->port->subordinate,
				   PCI_SLOT_ALL_DEVICES, name);
	if (retval) {
		ctrl_err(ctrl, "pci_hp_initialize failed: error %d\n", retval);
		kfree(ops);
	}
	return retval;
}
```

Enable, disable, power, adapter and reset callbacks are always installed. The latch callback needs [`MRL_SENS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L158), and the attention callbacks need [`ATTN_LED`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L159) or, on a port whose indicators belong to user space, use the raw indicator pair. [`ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L58) points at the table, the slot is named by the decimal [`PSN`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L162), at most [`SLOT_NAME_SIZE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L44) bytes, and [`pci_hp_initialize()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L86) registers it on the port's secondary bus with the number [`PCI_SLOT_ALL_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L82). A failure frees the table and returns the error, which probe reports. [`pci_hp_initialize()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L86) is a macro that adds the caller's module to the call.

```c
/* include/linux/pci_hotplug.h:86 */
#define pci_hp_initialize(slot, bus, nr, name) \
	__pci_hp_initialize(slot, bus, nr, name, THIS_MODULE, KBUILD_MODNAME)
```

The module and its name end up in the slot's [`owner`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L62) and [`mod_name`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L63), which the slot's module link uses later. [`__pci_hp_initialize()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L385) does the registration; read it for the two pointers it sets.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:385 */
int __pci_hp_initialize(struct hotplug_slot *slot, struct pci_bus *bus,
			int devnr, const char *name, struct module *owner,
			const char *mod_name)
{
	struct pci_slot *pci_slot;

	if (slot == NULL)
		return -ENODEV;
	if (slot->ops == NULL)
		return -EINVAL;

	slot->owner = owner;
	slot->mod_name = mod_name;

	/*
	 * No problems if we call this interface from both ACPI_PCI_SLOT
	 * driver and call it here again. If we've already created the
	 * pci_slot, the interface will simply bump the refcount.
	 */
	pci_slot = pci_create_slot(bus, devnr, name, slot);
	if (IS_ERR(pci_slot))
		return PTR_ERR(pci_slot);

	slot->pci_slot = pci_slot;
	pci_slot->hotplug = slot;
	return 0;
}
```

The function refuses a slot without callbacks, records the module, and asks [`pci_create_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L259) for the bus's slot of that number; [`pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L61) and [`hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L88) then point at each other. The number pciehp passes is defined beside [`struct pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L85), whose [`number`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L89) holds it.

```c
/* include/linux/pci.h:76 */
/*
 * PCI_SLOT_ALL_DEVICES indicates a slot that covers all devices on the bus.
 * Used for PCIe hotplug where the physical slot is the entire secondary bus,
 * and, if ARI Forwarding is enabled, functions may appear to be on multiple
 * devices.
 */
#define PCI_SLOT_ALL_DEVICES	0xfe

/* pci_slot represents a physical slot */
struct pci_slot {
	struct pci_bus		*bus;		/* Bus this slot is on */
	struct list_head	list;		/* Node in list of slots */
	struct hotplug_slot	*hotplug;	/* Hotplug info (move here) */
	unsigned char		number;		/* Device nr, or PCI_SLOT_ALL_DEVICES */
	struct kobject		kobj;
};
```

[`PCI_SLOT_ALL_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L82) is 0xfe, a value no device number reaches. The comment explains that the physical slot of a PCIe hotplug port is the whole secondary bus, and that with ARI Forwarding a device's functions appear under several device numbers. The change in commit [102c8b26b54e](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=102c8b26b54e363f85c4c86099ca049a0a76bb58) ("PCI: Allow all bus devices to use the same slot") introduced it for v7.1; before it, [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) registered device number 0. [`pci_create_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L259) gives the number its meaning when it links the bus's functions to a new slot; read the stage that does so.

```c
/* drivers/pci/slot.c:259 */
struct pci_slot *pci_create_slot(struct pci_bus *parent, int slot_nr,
				 const char *name,
				 struct hotplug_slot *hotplug)
{
	... /* 56 lines, to :319 */
	down_read(&pci_bus_sem);
	list_for_each_entry(dev, &parent->devices, bus_list)
		if (slot_nr == PCI_SLOT_ALL_DEVICES ||
		    PCI_SLOT(dev->devfn) == slot_nr)
			dev->slot = slot;
	up_read(&pci_bus_sem);

	dev_dbg(&parent->dev, "dev %02x, created physical slot %s\n",
		slot_nr, pci_slot_name(slot));
```

A function joins the slot when the slot is bus-wide or when its device number equals the slot's, and the loop stores the slot in each matching [`slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L359). Within drivers/pci at v7.2, [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) is the one caller that passes [`PCI_SLOT_ALL_DEVICES`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L82), and [`pci_dev_assign_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L184) and the slot's release apply the same test to functions that appear later. The figure shows the effect on an ARI device.

```text
    A slot numbered PCI_SLOT_ALL_DEVICES claims every function on the bus
    ─────────────────────────────────────────────────────────────────────

    (one ARI device behind the port: its function 8 has devfn 0x08, so PCI_SLOT() reads it as device 1)

    PCI_SLOT() of devfn
      0                 1                 2                 ...     31
    ┌─────────────────┬─────────────────┬─────────────────┬───────┬─────────────────┐
    │ 00.0  00.1      │ 01.0, fn 8      │ empty           │ ...   │ empty           │
    └─────┬───────────┴─────┬───────────┴─────────────────┴───────┴─────────────────┘
          │                 │
          │ dev->slot       │ dev->slot
          │                 │
          ▼                 ▼
    ┌──────────────────────────────────┐
    │ struct pci_slot of the port      │    with number 0, as before v7.1, the
    │ number  PCI_SLOT_ALL_DEVICES     │    function at 01.0 got no slot
    └──────────────────────────────────┘
```

The slot's address file keeps its old format for such a slot; read [`address_read_file()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L38) for the device number it prints.

```c
/* drivers/pci/slot.c:38 */
static ssize_t address_read_file(struct pci_slot *slot, char *buf)
{
	if (slot->number == 0xff)
		return sysfs_emit(buf, "%04x:%02x\n",
				  pci_domain_nr(slot->bus),
				  slot->bus->number);

	/*
	 * Preserve legacy ABI expectations that hotplug drivers that manage
	 * multiple devices per slot emit 0 for the device number.
	 */
	if (slot->number == PCI_SLOT_ALL_DEVICES)
		return sysfs_emit(buf, "%04x:%02x:00\n",
				  pci_domain_nr(slot->bus),
				  slot->bus->number);

	return sysfs_emit(buf, "%04x:%02x:%02x\n",
			  pci_domain_nr(slot->bus),
			  slot->bus->number,
			  slot->number);
}
```

A bus-wide slot prints device 00 in its address, as the comment says, to preserve the ABI that hotplug drivers with several devices per slot had before. After [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51), the slot exists in the PCI core and the hotplug core can reach pciehp's callbacks, but user space sees no file of it yet.

### Probe requests the interrupt before user space sees the slot

A request that user space makes through the slot's files is served by the IRQ thread, so that thread has to exist before the files do. Probe requests the interrupt and enables the slot's events between registering the slot and publishing it; read the part of [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) that orders the two.

```c
/* drivers/pci/hotplug/pciehp_core.c:185 */
static int pciehp_probe(struct pcie_device *dev)
{
	... /* 31 lines, to :218 */
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
```

The notification step comes first and the publication second, and a failed publication shuts notification down again. [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) does the notification step; read it for the flag it sets.

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

[`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) is set only after the interrupt or the poll thread exists and the events are enabled, so the shutdown path can tell whether there is anything to undo. [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) picks between the interrupt and the poll thread.

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

With [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) set, a kernel thread named after the slot by [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202) polls Slot Status, which is why the slot had to be registered first. Otherwise the service device's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) gets a threaded handler, [`pciehp_isr()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L623) in hard interrupt context and [`pciehp_ist()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L728) as its thread, shared with the port's other services. [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) then turns the slot's events on in Slot Control.

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

Link events are always enabled, so a link going down counts as an unplug. Presence Detect Changed is enabled only when the slot has no Attention Button, which [`ATTN_BUTTN`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L156) decides, and the two interrupt enables are left off in poll mode; Command Completed Interrupt Enable also needs [`NO_CMD_CMPL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L161) clear. Power Fault Detected stays masked, and the comment gives an interrupt storm on some machines as the reason. The command goes out without waiting, and a debug message records it. [`pci_hp_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L424) publishes the slot last; read it for what user space receives.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:414 */
/**
 * pci_hp_add - publish hotplug slot to user space
 * @slot: pointer to the &struct hotplug_slot to publish
 *
 * Make a hotplug slot's sysfs interface available and inform user space of its
 * addition by sending a uevent.  The hotplug driver must be prepared to handle
 * all &struct hotplug_slot_ops callbacks from this point on.
 *
 * Returns 0 on success or a negative int on error.
 */
int pci_hp_add(struct hotplug_slot *slot)
{
	struct pci_slot *pci_slot;
	int result;

	if (WARN_ON(!slot))
		return -EINVAL;

	pci_slot = slot->pci_slot;

	result = fs_add_slot(slot, pci_slot);
	if (result)
		return result;

	kobject_uevent(&pci_slot->kobj, KOBJ_ADD);
	return 0;
}
EXPORT_SYMBOL_GPL(pci_hp_add);
```

The kerneldoc says that from this point on the driver must handle every callback, which the order of probe guarantees. The swimlane shows the order across probe, the IRQ thread, the slot's sysfs directory and user space.

```text
    The IRQ thread exists before user space can reach the slot
    ──────────────────────────────────────────────────────────

    time ↓
    pciehp_probe              ╎ IRQ thread of the port    ╎ slot directory in sysfs ╎ user space
    ──────────────────────────┼───────────────────────────┼─────────────────────────┼──────────────────────────
    slot registered,          ╎                           ╎                         ╎
    no files yet              ╎                           ╎                         ╎
                              ╎                           ╎                         ╎
    IRQ requested ────────────▶ exists, idle              ╎                         ╎
    events enabled            ╎                           ╎                         ╎
                              ╎                           ╎                         ╎
    slot published ───────────────────────────────────────▶ power, adapter and the  ╎
                              ╎                           ╎ optional attention and  ╎
                              ╎                           ╎ latch files; a uevent   ╎
                              ╎                           ╎                         ╎
    presence check ───────────▶ brings an occupied        ╎                         ╎
                              ╎ slot up                   ╎                         ╎
                              ╎                           ╎ ◀───────────────────────╎ writes 1 to power
                              ╎ ◀─────────────────────────╎ enable request          ╎
                              ╎ handles it                ╎                         ╎
                              ╎                           ╎                         ╎
```

A write to the slot's power file can arrive only after publication, and by then the IRQ thread exists to serve it. So far, probe has built the controller, quieted the slot, registered a bus-wide slot, enabled its events and published it, and [`notification_enabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L105) is 1; the last step of probe is the presence check.

### pciehp_check_presence turns occupancy into a synthetic event

Probe cleared every stale event in Slot Status, so a card that was inserted before probe raises no interrupt. The kerneldoc of [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) adds that the specification makes an interrupt for events that happened while interrupts were disabled optional, so the driver compares occupancy with its state and synthesizes the event itself. The same check ends [`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318); read the function for the two locks it takes and for the comparison.

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

[`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) is taken for reading with [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) as the lockdep subclass, and [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110) inside it. The local `occupied` is positive for an occupied slot, 0 for an empty one and negative when the port is gone. An occupied slot whose state is [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134), or an empty one in [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135), gets a synthetic Presence Detect Changed. A negative result matches neither test, and a slot in a power transition is left to the handler that started it. The table lists the outcomes.

| state | occupied slot | empty slot |
|---|---|---|
| [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) | Presence Detect Changed requested | nothing |
| [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) or [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) | nothing | Presence Detect Changed requested |
| [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) or [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) | nothing | nothing |

The occupancy test is [`pciehp_card_present_or_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L463), which accepts either sign of a card.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:463 */
int pciehp_card_present_or_link_active(struct controller *ctrl)
{
	int ret;

	ret = pciehp_card_present(ctrl);
	if (ret)
		return ret;

	return pciehp_check_link_active(ctrl);
}
```

A set Presence Detect State answers at once, and a clear one falls back to the link; the helper's kerneldoc calls this a concession to ports that hardwire Presence Detect State to zero. [`pciehp_card_present()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L438) reads Presence Detect State through [`PCI_EXP_SLTSTA_PDS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L640).

```c
/* drivers/pci/hotplug/pciehp_hpc.c:438 */
int pciehp_card_present(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 slot_status;
	int ret;

	ret = pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &slot_status);
	if (ret == PCIBIOS_DEVICE_NOT_FOUND || PCI_POSSIBLE_ERROR(slot_status))
		return -ENODEV;

	return !!(slot_status & PCI_EXP_SLTSTA_PDS);
}
```

A failed read, or the all-ones value of a vanished port, returns -ENODEV. [`pciehp_check_link_active()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L235) reads Data Link Layer Link Active the same way and logs the raw Link Status at the debug level.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:235 */
int pciehp_check_link_active(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl_dev(ctrl);
	u16 lnk_status;
	int ret;

	ret = pcie_capability_read_word(pdev, PCI_EXP_LNKSTA, &lnk_status);
	if (ret == PCIBIOS_DEVICE_NOT_FOUND || PCI_POSSIBLE_ERROR(lnk_status))
		return -ENODEV;

	ret = !!(lnk_status & PCI_EXP_LNKSTA_DLLLA);
	ctrl_dbg(ctrl, "%s: lnk_status = %x\n", __func__, lnk_status);

	return ret;
}
```

Both reads can see a flap while a slot reset retrains the link, which is why the check holds [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) across them. The request itself is [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), which hands the event to the IRQ thread.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:141 */
void pciehp_request(struct controller *ctrl, int action)
{
	atomic_or(action, &ctrl->pending_events);
	if (!pciehp_poll_mode)
		irq_wake_thread(ctrl->pcie->irq, ctrl);
}
```

The event joins [`pending_events`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L104) by an atomic OR, and outside poll mode `irq_wake_thread()` wakes the IRQ thread of the service device's interrupt; in poll mode the poll thread finds the bit on its next pass. The handling itself runs later in that thread, which starts hot-add or hot-remove. The figure draws the two locks as brackets around the read and the request.

```text
    The presence check compares occupancy with state inside two locks
    ─────────────────────────────────────────────────────────────────

    time ────────────────────────────────────────────────────────────────────────────────▶

    reset_lock held to read           ├───────────────────────────────────────────────┤
    state_lock held                      ├─────────────────────────────────────────┤
    occupancy read                          ├──────────────┤
    compared; PDC if they differ                              ├───────┬───────┤
                                      ╎                               │               ╎
    slot reset, the lock's writer     ╎ cannot start, so no flap      │               ╎
    event handlers, under state_lock  ╎ wait, so no state change      │               ╎
                                                                      │
    IRQ thread of the port                                            ▼ woken unless polling;
                                                                        handles the PDC after
                                                                        both locks are dropped
```

Inside both brackets the slot can neither flap under a reset nor change state under an event handler, so the request matches what the slot held at the moment of the read. The decision rests on the state values, which the next subsection reads.

### The state values tell each path what the slot is doing

The slot state, [`state`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L109), records where the slot stands between the button, the presence and link events, and the requests from user space, so that each path can tell whether its action applies. pciehp.h defines the six values as plain macros, with a comment that says what each means; read them together.

```c
/* drivers/pci/hotplug/pciehp.h:121 */
/**
 * DOC: Slot state
 *
 * @OFF_STATE: slot is powered off, no subordinate devices are enumerated
 * @BLINKINGON_STATE: slot will be powered on after the 5 second delay,
 *	Power Indicator is blinking
 * @BLINKINGOFF_STATE: slot will be powered off after the 5 second delay,
 *	Power Indicator is blinking
 * @POWERON_STATE: slot is currently powering on
 * @POWEROFF_STATE: slot is currently powering off
 * @ON_STATE: slot is powered on, subordinate devices have been enumerated
 */
#define OFF_STATE			0
#define BLINKINGON_STATE		1
#define BLINKINGOFF_STATE		2
#define POWERON_STATE			3
#define POWEROFF_STATE			4
#define ON_STATE			5
```

| value | meaning | defining construct |
|---|---|---|
| 0 | powered off, nothing below enumerated | [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) |
| 1 | will power on after the 5 second delay, Power Indicator blinking | [`BLINKINGON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L134) |
| 2 | will power off after the 5 second delay, Power Indicator blinking | [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) |
| 3 | powering on | [`POWERON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L136) |
| 4 | powering off | [`POWEROFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L137) |
| 5 | powered on, devices enumerated | [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) |

[`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) seeds the value with [`OFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L133) or [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138), and the event handlers of [`pciehp_ctrl.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c) move it, always under [`state_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L110). The graph draws the transitions and the events that drive them.

```text
    The slot state moves between six values
    ───────────────────────────────────────

                        5 s or up
            ┌───────────────────────────────────────────┐
            │                                           ▼
    ┌───────┴──────┐ btn   ┌──────────────┐ up    ┌──────────────┐ ok    ┌──────────────┐ btn   ┌──────────────┐
    │              │◀──────│              │──────▶│              │──────▶│              │──────▶│              │
    │ BLINKINGON   │       │ OFF          │       │ POWERON      │       │ ON           │       │ BLINKINGOFF  │
    │              │──────▶│              │◀──────│              │       │              │◀──────│              │
    └──────────────┘ agn   └──────────────┘ fail  └──────────────┘       └─────┬────────┘ agn   └─────┬────────┘
                                  ▲                                            │                      │
                                  │                                            │                      │
                                  │                                            │                      │
                                  │                                            │                      │
                                  │               ┌──────────────┐  down       │                      │
                                  │ done          │              │◀────────────┘                      │
                                  └───────────────┤ POWEROFF     │                                    │
                                                  │              │◀───────────────────────────────────┘
                                                  └──────────────┘                5 s or down

    btn    an Attention Button press
    agn    a second press within the 5 s; from BLINKINGON also a slot found empty with its link down
    up     presence or link up, handled by the IRQ thread; an enable request from sysfs arrives this way
    5 s    the button work running after the delay
    ok     enabling the slot succeeded; fail: it failed
    down   a presence or link change, or a disable request
    done   the slot disabled, its devices removed
```

The transitions start from three handlers and two slot functions, and the table gives the line that writes each target value; the event handling itself is read with the IRQ thread.

| transition | handler | site |
|---|---|---|
| OFF to BLINKINGON, ON to BLINKINGOFF | [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) | [`pciehp_ctrl.c:173-180`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L173) |
| BLINKINGOFF to ON, BLINKINGON to OFF | [`pciehp_handle_button_press()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L167) | [`pciehp_ctrl.c:195-206`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L195) |
| any state to POWEROFF on a disable request | [`pciehp_handle_disable_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L217) | [`pciehp_ctrl.c:226`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L226) |
| ON or BLINKINGOFF to POWEROFF, BLINKINGON to OFF, OFF or BLINKINGON to POWERON | [`pciehp_handle_presence_or_link_change()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L232) | [`pciehp_ctrl.c:241-294`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L241) |
| POWERON to ON or OFF | [`pciehp_enable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L342) | [`pciehp_ctrl.c:355`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L355) |
| POWEROFF to OFF | [`pciehp_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L378) | [`pciehp_ctrl.c:387`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L387) |

A path that only reads the state shows how the values steer decisions. [`pciehp_sysfs_disable_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L432), the disable callback that [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installed, tests every value; read it for which values let a request through.

```c
/* drivers/pci/hotplug/pciehp_ctrl.c:432 */
int pciehp_sysfs_disable_slot(struct hotplug_slot *hotplug_slot)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);

	mutex_lock(&ctrl->state_lock);
	switch (ctrl->state) {
	case BLINKINGOFF_STATE:
	case ON_STATE:
		mutex_unlock(&ctrl->state_lock);
		pciehp_request(ctrl, DISABLE_SLOT);
		wait_event(ctrl->requester,
			   !atomic_read(&ctrl->pending_events) &&
			   !ctrl->ist_running);
		return ctrl->request_result;
	case POWEROFF_STATE:
		ctrl_info(ctrl, "Slot(%s): Already in powering off state\n",
			  slot_name(ctrl));
		break;
	case BLINKINGON_STATE:
	case OFF_STATE:
	case POWERON_STATE:
		ctrl_info(ctrl, "Slot(%s): Already disabled\n",
			  slot_name(ctrl));
		break;
	default:
		ctrl_err(ctrl, "Slot(%s): Invalid state %#x\n",
			 slot_name(ctrl), ctrl->state);
		break;
	}
	mutex_unlock(&ctrl->state_lock);

	return -ENODEV;
}
```

Only [`ON_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L138) and [`BLINKINGOFF_STATE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L135) pass the request to the IRQ thread, as [`DISABLE_SLOT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L153) through [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), and the caller sleeps on [`requester`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L118) until the thread is idle again. The four other values print why nothing happens, and a value outside the six reports an invalid state. The callback converts its argument with [`to_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L207) and names the slot with [`slot_name()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L202), the two helpers read earlier.

### reset_lock nests by the number of hot-plug ports above

A slot reset makes the link drop and retrain, and the presence and link bits flap while it does. [`reset_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L114) is a read-write semaphore that lets any number of readers of those bits run together and keeps them out while a reset holds it for writing. Read [`pciehp_reset_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L939), the reset callback, for the writer side.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:931 */
/*
 * pciehp has a 1:1 bus:slot relationship so we ultimately want a secondary
 * bus reset of the bridge, but at the same time we want to ensure that it is
 * not seen as a hot-unplug, followed by the hot-plug of the device. Thus,
 * disable link state notification and presence detection change notification
 * momentarily, if we see that they could interfere. Also, clear any spurious
 * events after.
 */
int pciehp_reset_slot(struct hotplug_slot *hotplug_slot, bool probe)
{
	struct controller *ctrl = to_ctrl(hotplug_slot);
	struct pci_dev *pdev = ctrl_dev(ctrl);
	int rc;

	if (probe)
		return 0;

	down_write_nested(&ctrl->reset_lock, ctrl->depth);

	pci_hp_ignore_link_change(pdev);

	rc = pci_bridge_secondary_bus_reset(ctrl->pcie->port);

	pci_hp_unignore_link_change(pdev);

	up_write(&ctrl->reset_lock);
	return rc;
}
```

The secondary bus reset runs with the lock held for writing, between the calls that tell the link-change handling to ignore the flap. Both sides pass [`depth`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L115) as the lockdep subclass, which [`pcie_hotplug_depth()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L992) computes at probe; read it for what it counts.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:992 */
static inline int pcie_hotplug_depth(struct pci_dev *dev)
{
	struct pci_bus *bus = dev->bus;
	int depth = 0;

	while (bus->parent) {
		bus = bus->parent;
		if (bus->self && bus->self->is_pciehp)
			depth++;
	}

	return depth;
}
```

The loop climbs from the port's bus to the root bus and counts each bus whose bridge has [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) set, so a Root Port has depth 0 and a hot-plug port behind it depth 1. All controllers' reset locks share one lock class. Lockdep reported a possible recursion when the IRQ thread of one port held its lock while the presence check of a port below took its own, as commit [085a9f43433f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=085a9f43433f30cbe8a1ade62d9d7827c3217f4d) ("PCI: pciehp: Use down_read/write_nested(reset_lock) to fix lockdep errors") records. The change in commit [f5eff5591b8f](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=f5eff5591b8f9c5effd25c92c758a127765f74c1) ("PCI: pciehp: Fix AB-BA deadlock between reset_lock and device_lock") later made the IRQ thread drop its lock around driver binding and unbinding. The figure shows how depth separates nested ports.

```text
    Hotplug depth gives each nested port's reset_lock its own subclass
    ──────────────────────────────────────────────────────────────────

    depth

            ┌───────────────────────────────────┐
    0       │ Root Port, hot-plug capable       │    reset_lock taken with subclass 0
            └───────────┬───────────────────────┘    zero hot-plug ports above it
                        │ slot
                        │
            ┌───────────┴───────────────────────┐
            │ Upstream Port of a Switch         │    no controller: not counted
            └───────────┬───────────────────────┘
                        │
                        │
            ┌───────────┴───────────────────────┐
    1       │ Downstream Port, hot-plug capable │    reset_lock taken with subclass 1
            └───────────┬───────────────────────┘    one hot-plug port above it
                        │ slot
                        │
            ┌───────────┴───────────────────────┐
    2       │ another hot-plug port below       │    reset_lock taken with subclass 2
            └───────────────────────────────────┘    two hot-plug ports above it
```

Each nested port takes its own lock at its own subclass, so a hold at one depth and an acquisition at another are distinct to lockdep.

### Suspend masks the slot interrupt when the OS owns PME

When a port goes to D3hot for system sleep, the link below it goes down, and an enabled hotplug interrupt would fire at once and wake the system. pciehp therefore masks the interrupt across sleep when PME can wake the system instead, which commit [eb34da60edee](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=eb34da60edee8cf7bac691a406a1ddaa4175e5bc) ("PCI: pciehp: Disable hotplug interrupt during suspend") introduced. The port's power management callbacks reach the hook through portdrv; read [`pcie_portdrv_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L656) for which callbacks of the port lead to which member.

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

Suspend, freeze and poweroff all call the same function, and so do the three resume and the two noirq restore callbacks, under [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217). Each of them calls one member of every bound service driver through [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385); read it with [`pcie_port_device_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L405), one of its users.

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
```

The iterator visits the port's children, skips any that is not a bound service device, and calls the member at the offset the caller chose, so [`pciehp_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L275) runs for the hotplug child alongside the other services' hooks. Whether pciehp masks anything depends on [`pme_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256), which only [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) builds.

```c
/* drivers/pci/hotplug/pciehp_core.c:255 */
#ifdef CONFIG_PM
static bool pme_is_native(struct pcie_device *dev)
{
	const struct pci_host_bridge *host;

	host = pci_find_host_bridge(dev->port->bus);
	return pcie_ports_native || host->native_pme;
}
```

The test is the same one that gates the hotplug service: [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) set by the boot parameter, or [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) kept by the host bridge. On x86 that flag is cleared when _OSC withholds PME control, in the lines of [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) shown again here.

```c
/* drivers/acpi/pci_root.c:995 */
struct pci_bus *acpi_pci_root_create(struct acpi_pci_root *root,
				     struct acpi_pci_root_ops *ops,
				     struct acpi_pci_root_info *info,
				     void *sysdata)
{
	... /* 34 lines, to :1034 */
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_AER_CONTROL))
		host_bridge->native_aer = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_PME_CONTROL))
		host_bridge->native_pme = 0;
```

When the firmware keeps PME, it owns the wake path, and the hotplug interrupt stays enabled across sleep. [`pciehp_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L264) wraps the test around the mask.

```c
/* drivers/pci/hotplug/pciehp_core.c:264 */
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

The comment states the purpose, keeping the interrupt from triggering as the downstream link goes down. [`pcie_disable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L890) clears two enables in one waiting command.

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

Hot-Plug Interrupt Enable and Data Link Layer State Changed Enable go to 0, while the event enables stay set, and the comment explains that the port still sends PME for an enabled event. [`pciehp_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L275), built only with [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140), calls the mask unless the port stays runtime suspended.

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

`dev_pm_skip_suspend()` reports a port that the PM core leaves runtime suspended through system suspend, and such a port already masked its interrupt when it was runtime suspended, so the hook skips a second Slot Control write. The change in commit [75fcc0ce72e5](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=75fcc0ce72e5cea2e357cdde858216c5bad40442) ("PCI: pciehp: Do not disable interrupt twice on suspend") added the skip after the second write found no response from the suspended port. The runtime hook masks without that test.

```c
/* drivers/pci/hotplug/pciehp_core.c:330 */
static int pciehp_runtime_suspend(struct pcie_device *dev)
{
	pciehp_disable_interrupt(dev);
	return 0;
}
```

[`pciehp_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L330) runs from the port's runtime suspend, which portdrv allows only for a port the PCI core marked able to enter D3; read [`pcie_port_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L638) for the gate.

```c
/* drivers/pci/pcie/portdrv.c:638 */
static int pcie_port_runtime_suspend(struct device *dev)
{
	if (!to_pci_dev(dev)->bridge_d3)
		return -EBUSY;

	return pcie_port_device_runtime_suspend(dev);
}
```

A port without [`bridge_d3`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L418) refuses runtime suspend with -EBUSY, and its hooks never run. The figure follows the enable bits of Slot Control from probe through suspend and back.

```text
    Suspend clears two Slot Control enables that resume sets again
    ──────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    bits  │·│I│L│D│E│W│PIC│AIC│H│C│P│M│F│B│
          ├─┼─┼─┼─┼─┼─┼───┼───┼─┼─┼─┼─┼─┼─┤
    probe │·│·│·│1│·│·│ · │ · │1│1│1│·│0│0│
          ├─┼─┼─┼─┼─┼─┼───┼───┼─┼─┼─┼─┼─┼─┤
    sleep │·│·│·│0│·│·│ · │ · │0│·│·│·│·│·│
          ├─┼─┼─┼─┼─┼─┼───┼───┼─┼─┼─┼─┼─┼─┤
    wake  │·│·│·│1│·│·│ · │ · │1│·│·│·│·│·│
          └─┴─┴─┴─┴─┴─┴───┴───┴─┴─┴─┴─┴─┴─┘

    bits: D = PCI_EXP_SLTCTL_DLLSCE (Data Link Layer State Changed Enable), H = PCI_EXP_SLTCTL_HPIE
    (Hot-Plug Interrupt Enable), C = PCI_EXP_SLTCTL_CCIE (Command Completed Interrupt Enable),
    P = PCI_EXP_SLTCTL_PDCE (Presence Detect Changed Enable), M = PCI_EXP_SLTCTL_MRLSCE (MRL Sensor Changed
    Enable), F = PCI_EXP_SLTCTL_PFDE (Power Fault Detected Enable), B = PCI_EXP_SLTCTL_ABPE (Attention Button
    Pressed Enable), I = PCI_EXP_SLTCTL_IBPD_DISABLE, L = PCI_EXP_SLTCTL_ASPL_DISABLE, E = PCI_EXP_SLTCTL_EIC,
    W = PCI_EXP_SLTCTL_PCC, PIC = PCI_EXP_SLTCTL_PIC, AIC = PCI_EXP_SLTCTL_AIC; bit 15 has no macro
    probe: the bits pcie_enable_notification writes on a port with no Attention Button, outside poll mode,
           with Command Completed support (a port with a button gets B = 1 and P = 0)
    sleep: the bits pcie_disable_interrupt clears when pme_is_native, from suspend or runtime suspend
    wake:  the bits pcie_enable_interrupt sets again when pme_is_native, H only outside poll mode
    · = not written by that step; the last value written is cached in slot_ctrl
```

The suspend hooks change two bits and leave the event enables, which is why a slot event during sleep still produces PME, while the hotplug interrupt waits for resume.

### pciehp_resume_noirq accounts for the restore's Slot Control write

On resume, the PCI core restores the port's saved configuration before any driver hook runs, and that restore writes Slot Control behind pciehp's back. A write is a command, so the next pciehp command must wait for it, and stale events from the rediscovered card must not be mistaken for a hot-plug. Read [`pci_pm_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L979) for the order of the restore and the driver's noirq hook.

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

The restore runs first, unless a suspend-to-idle left the port in D0, and the driver's noirq callback runs after it, which for the port is portdrv's iterator over [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288) and the other services' hooks. The restore of the PCIe capability writes Slot Control among the other control registers; read the stage of [`pci_restore_pcie_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1672) that does so.

```c
/* drivers/pci/pci.c:1672 */
static void pci_restore_pcie_state(struct pci_dev *dev)
{
	int i = 0;
	struct pci_cap_saved_state *save_state;
	u16 *cap;
	... /* 19 lines, to :1696 */
	cap = (u16 *)&save_state->cap.data[0];
	pcie_capability_write_word(dev, PCI_EXP_DEVCTL, cap[i++]);
	pcie_capability_write_word(dev, PCI_EXP_LNKCTL, cap[i++]);
	pcie_capability_write_word(dev, PCI_EXP_SLTCTL, cap[i++]);
```

The saved Slot Control value goes back to the register with no regard for pciehp's command protocol. [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288), built with [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140), makes the protocol account for it.

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

[`cmd_started`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L100) and [`cmd_busy`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L101) now describe the restore's write as a command in flight, so the first pciehp command after resume waits for its completion or its deadline; commit [469e764c4a3c](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=469e764c4a3c7260b353b7bc1bd56c283cb001da) ("PCI: pciehp: Obey compulsory command delay after resume") added these two lines. A slot that was on, or about to power off, has its rediscovery events cleared, and is checked for a replaced device. [`pcie_clear_hotplug_events()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L874) clears the two events.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:874 */
void pcie_clear_hotplug_events(struct controller *ctrl)
{
	pcie_capability_write_word(ctrl_dev(ctrl), PCI_EXP_SLTSTA,
				   PCI_EXP_SLTSTA_PDC | PCI_EXP_SLTSTA_DLLSC);
}
```

Presence Detect Changed and Data Link Layer State Changed are written with 1, which clears them. [`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) compares the device in the slot with the one probe or the last hot-add saw.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:567 */
bool pciehp_device_replaced(struct controller *ctrl)
{
	struct pci_dev *pdev __free(pci_dev_put) = NULL;
	u32 reg;

	if (pci_dev_is_disconnected(ctrl->pcie->port))
		return false;

	pdev = pci_get_slot(ctrl->pcie->port->subordinate, PCI_DEVFN(0, 0));
	if (!pdev)
		return true;

	if (pci_read_config_dword(pdev, PCI_VENDOR_ID, &reg) ||
	    reg != (pdev->vendor | (pdev->device << 16)) ||
	    pci_read_config_dword(pdev, PCI_CLASS_REVISION, &reg) ||
	    reg != (pdev->revision | (pdev->class << 8)))
		return true;

	if (pdev->hdr_type == PCI_HEADER_TYPE_NORMAL &&
	    (pci_read_config_dword(pdev, PCI_SUBSYSTEM_VENDOR_ID, &reg) ||
	     reg != (pdev->subsystem_vendor | (pdev->subsystem_device << 16))))
		return true;

	if (pci_get_dsn(pdev) != ctrl->dsn)
		return true;

	return false;
}
```

A disconnected port reports no replacement, and an empty slot, a changed vendor, device, revision or class, a changed subsystem ID of a normal header, or a Device Serial Number different from [`dsn`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L93) reports one. Back in [`pciehp_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L288), a replacement marks every function below the port disconnected, so their drivers stop touching the new device. It also requests a Presence Detect Changed, which removes the old functions and adds the new ones; commit [9d573d19547b](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=9d573d19547b3fae0c1d4e5fce52bdad3fda3664) ("PCI: pciehp: Detect device replacement during system sleep") introduced the check. The swimlane shows the order across the PCI core, pciehp and the port's Slot Control.

```text
    Resume accounts for the restore's Slot Control write before unmasking
    ─────────────────────────────────────────────────────────────────────

    time ↓
    PCI core and portdrv        ╎ pciehp                                    ╎ the port's Slot Control
    ────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────
    noirq phase:                ╎                                           ╎
    port powered up,            ╎                                           ╎
    saved state restored ───────────────────────────────────────────────────▶ saved value written;
                                ╎                                           ╎ a command in flight
                                ╎                                           ╎
    resume_noirq hook ──────────▶ cmd_busy 1, cmd_started now               ╎
                                ╎ slot ON or BLINKINGOFF: PDC and           ╎
                                ╎ DLLSC cleared; a replaced device          ╎
                                ╎ marked disconnected, PDC requested        ╎
                                ╎                                           ╎
    resume phase:               ╎                                           ╎
    resume hook ────────────────▶ PME native: waits for Command             ╎
                                ╎ Completed or the deadline,                ╎
                                ╎ then writes ──────────────────────────────▶ HPIE and DLLSCE set
                                ╎                                           ╎
                                ╎ presence check runs                       ╎
                                ╎                                           ╎
                                ╎                                           ╎
```

After the noirq hook, the controller treats the restore as an outstanding command and has no stale event pending. So far, the controller has been built, published and checked for presence, and it is carried across sleep with its interrupt masked and its command protocol aware of the restore.

### pciehp_resume unmasks the interrupt and repeats the presence check

The last resume hook undoes the suspend mask and repeats the check that ends probe, because the slot may have gained or lost a card during sleep. [`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318) does both; read it for the order.

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
```

The interrupt is unmasked only when [`pme_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256) says suspend masked it, and [`pciehp_check_presence()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L167) then compares occupancy with the state as it did at the end of probe. [`pcie_enable_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L880) sets the two enables again.

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

Data Link Layer State Changed Enable is always set again, and Hot-Plug Interrupt Enable outside poll mode, with a waiting command that the restore's outstanding command delays. Runtime resume combines the noirq work and the resume in one hook; read [`pciehp_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L336).

```c
/* drivers/pci/hotplug/pciehp_core.c:336 */
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

The hook's comment says that the PCI core's restore has just written Slot Control here too, so it records the same command in flight. It clears the rediscovery events only when PME is native, because only then did the runtime suspend mask the interrupt, and it ends in [`pciehp_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L318), which unmasks and checks presence. After either resume, the slot raises its interrupt again and the controller's state matches what the slot holds.

### pciehp_remove takes the controller apart in reverse

When the port's driver unbinds, portdrv unregisters the port's service devices, and the driver core calls the bus remove for each bound one. [`remove_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L448) unregisters every child on the port bus; read it with [`pcie_port_bus_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L562), which calls the hook.

```c
/* drivers/pci/pcie/portdrv.c:448 */
static int remove_iter(struct device *dev, void *data)
{
	if (dev->bus == &pcie_port_bus_type)
		device_unregister(dev);
	return 0;
}
```

Unregistering a bound service device unbinds it, which reaches the bus's remove callback.

```c
/* drivers/pci/pcie/portdrv.c:562 */
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

The callback calls [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245) and drops the reference the bus probe took. [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245) closes the spans of probe from the innermost out; read it for the order.

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

The slot's files go first, so no new request from user space can arrive, then the interrupt, then the slot, then the controller. [`pci_hp_del()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L463) removes the files.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:457 */
/**
 * pci_hp_del - unpublish hotplug slot from user space
 * @slot: pointer to the &struct hotplug_slot to unpublish
 *
 * Remove a hotplug slot's sysfs interface.
 */
void pci_hp_del(struct hotplug_slot *slot)
{
	if (WARN_ON(!slot))
		return;

	fs_remove_slot(slot, slot->pci_slot);
}
EXPORT_SYMBOL_GPL(pci_hp_del);
```

[`pcie_shutdown_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L969) masks the slot's events and releases the interrupt or the poll thread, if probe got that far.

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

The flag set at the end of [`pcie_init_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L960) decides whether there is anything to undo, and it is cleared after the interrupt is gone. [`pciehp_free_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L78) is the inverse of the request.

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

In poll mode the poll thread is stopped, otherwise the threaded handler is freed, which waits for a running handler to finish. [`cleanup_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L91) then destroys the slot and frees the callback table that [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) allocated.

```c
/* drivers/pci/hotplug/pciehp_core.c:91 */
static void cleanup_slot(struct controller *ctrl)
{
	struct hotplug_slot *hotplug_slot = &ctrl->hotplug_slot;

	pci_hp_destroy(hotplug_slot);
	kfree(hotplug_slot->ops);
}
```

At v7.2 [`cleanup_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L91) has two callers, the second label of probe and [`pciehp_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L245). [`pci_hp_destroy()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L481) breaks the links that registration made.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:472 */
/**
 * pci_hp_destroy - remove hotplug slot from in-kernel use
 * @slot: pointer to the &struct hotplug_slot to destroy
 *
 * Destroy a PCI slot used by a hotplug driver.  Once this has been called,
 * the driver may no longer invoke hotplug_slot_name() to get the slot's
 * unique name.  The driver no longer needs to handle a ->reset_slot callback
 * from this point on.
 */
void pci_hp_destroy(struct hotplug_slot *slot)
{
	struct pci_slot *pci_slot = slot->pci_slot;

	slot->pci_slot = NULL;
	pci_slot->hotplug = NULL;
	pci_destroy_slot(pci_slot);
}
EXPORT_SYMBOL_GPL(pci_hp_destroy);
```

[`pci_slot`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L61) and [`hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L88) go back to NULL before [`pci_destroy_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L350) drops the reference that registration took; read it for the put and its debug line.

```c
/* drivers/pci/slot.c:342 */
/**
 * pci_destroy_slot - decrement refcount for physical PCI slot
 * @slot: struct pci_slot to decrement
 *
 * %struct pci_slot is refcounted, so destroying them is really easy; we
 * just call kobject_put on its kobj and let our release methods do the
 * rest.
 */
void pci_destroy_slot(struct pci_slot *slot)
{
	dev_dbg(&slot->bus->dev, "dev %02x, dec refcount to %d\n",
		slot->number, kref_read(&slot->kobj.kref) - 1);

	mutex_lock(&pci_slot_mutex);
	kobject_put(&slot->kobj);
	mutex_unlock(&pci_slot_mutex);
}
```

The put frees the slot through its release once no other holder keeps a reference, and the comment in [`__pci_hp_initialize()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L385) names the ACPI slot driver as one such holder. [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096) ends the controller.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:1096 */
void pciehp_release_ctrl(struct controller *ctrl)
{
	cancel_delayed_work_sync(&ctrl->button_work);
	kfree(ctrl);
}
```

`cancel_delayed_work_sync()` waits for a running button work and cancels a pending one, so no work item touches the controller after `kfree()`. The figure compares the objects before and after the hook.

```text
    Remove detaches the controller from the service device and the slot
    ───────────────────────────────────────────────────────────────────

    before pciehp_remove                                    ╎   after pciehp_remove
    ┌──────────────────────┐                                ╎   ┌──────────────────────┐
    │ struct pcie_device   │                                ╎   │ struct pcie_device   │
    │ priv_data ─────┐     │                                ╎   │ priv_data stale      │
    └────────────────┼─────┘                                ╎   └──────────────────────┘
                     │                                      ╎
                     ▼                                      ╎
    ┌────────────────────────────┐                          ╎
    │ struct controller          │     ┌───────────────┐    ╎   controller freed, button           ┌───────────────────┐
    │ IRQ or poll thread on      │     │ pci_slot      │    ╎   work cancelled, IRQ freed          │ pci_slot          │
    │ hotplug_slot.pci_slot ─────┼────▶│ slot files    │    ╎   or poll thread stopped             │ no slot files,    │
    │                            │     │ in sysfs      │    ╎                                      │ one reference put │
    └────────────────────────────┘     └───────────────┘    ╎                                      └───────────────────┘

    priv_data keeps the freed pointer; the device is unbound, and portdrv's PM and error callbacks
    skip a service device that has no driver
```

The service device keeps the freed pointer in [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63), but it is unbound by then, and [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) skips a child without a driver. The controller's life ends here, in the reverse of the order probe built it.

### Messages, tracepoints and hand-offs expose these paths

The paths of this page print a few lines, hand work to two threads and a work item, and fire no tracepoint of their own. pciehp prints through macros of pciehp.h that name the port, with a comment on how to turn the debug lines on; read them.

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

Each macro prints through the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), so a line carries the port's name, and both [`pciehp_core.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c) and [`pciehp_hpc.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c) define a message prefix of "pciehp: ". With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, each [`ctrl_dbg`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L35) line is a dynamic-debug site that the comment's dyndbg setting, or a write to /sys/kernel/debug/dynamic_debug/control, turns on. With [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) set, drivers/pci/Makefile compiles the directory with -DDEBUG and prints them unconditionally; the page assumes it unset. [`dbg_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L978) is the first debug site probe reaches.

```c
/* drivers/pci/hotplug/pciehp_hpc.c:978 */
static inline void dbg_ctrl(struct controller *ctrl)
{
	struct pci_dev *pdev = ctrl->pcie->port;
	u16 reg16;

	ctrl_dbg(ctrl, "Slot Capabilities      : 0x%08x\n", ctrl->slot_cap);
	pcie_capability_read_word(pdev, PCI_EXP_SLTSTA, &reg16);
	ctrl_dbg(ctrl, "Slot Status            : 0x%04x\n", reg16);
	pcie_capability_read_word(pdev, PCI_EXP_SLTCTL, &reg16);
	ctrl_dbg(ctrl, "Slot Control           : 0x%04x\n", reg16);
}
```

It prints the cached Slot Capabilities and the current Slot Status and Slot Control, the state of the slot before [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) changes it. The table lists the message sites of the paths this page reads.

| site | level | message | what it reports |
|---|---|---|---|
| [`pciehp_core.c:379`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L379) | dynamic debug | "pcie_port_service_register = %d" | the result of registering [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) |
| [`pciehp_core.c:381`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L381) | dynamic debug | "Failure to register service" | a failed registration |
| [`pciehp_core.c:196`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L196) | error | "Hotplug bridge without secondary bus, ignoring" | a port with no [`subordinate`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L355) bus |
| [`pciehp_core.c:203`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L203) | error | "Controller initialization failed" | [`pcie_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1006) returned NULL |
| [`pciehp_hpc.c:983`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L983) | dynamic debug | "Slot Capabilities : 0x%08x" and the two lines after it | the slot registers at probe, through [`dbg_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L978) |
| [`pciehp_hpc.c:1061`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1061) | info | "Slot #%d AttnBtn%c PwrCtrl%c ..." | the Physical Slot Number and the capability signs |
| [`pciehp_hpc.c:870`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L870) | dynamic debug | "%s: SLOTCTRL %x write cmd %x" | the masking command of [`pcie_disable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L861) |
| [`pciehp_core.c:85`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L85) | error | "pci_hp_initialize failed: error %d" | a failed slot registration in [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) |
| [`pciehp_core.c:212`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L212) | warning | "Slot already registered by another hotplug driver" | -EBUSY from slot registration |
| [`pciehp_core.c:214`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L214) | error | "Slot initialization failed (%d)" | another slot registration error |
| [`pciehp_hpc.c:73`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L73) | error | "Cannot get irq %d for the hotplug controller" | a failed `request_threaded_irq()` |
| [`pciehp_core.c:221`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L221) | error | "Notification initialization failed (%d)" | the interrupt or poll thread could not start |
| [`pciehp_hpc.c:857`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L857) | dynamic debug | "%s: SLOTCTRL %x write cmd %x" | the enable command of [`pcie_enable_notification()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L821) |
| [`pciehp_core.c:228`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L228) | error | "Publication to user space failed (%d)" | a failed [`pci_hp_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L424) |
| [`pciehp_hpc.c:246`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L246) | dynamic debug | "%s: lnk_status = %x" | the Link Status read of the presence check |
| [`pciehp_hpc.c:147`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L147) | info | "Timeout on hotplug command %#06x (issued %u msec ago)" | a Slot Control command that did not complete, after resume among others |
| [`pciehp_hpc.c:172`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L172) | info | "%s: no response from device" | a Slot Control read of a port that has gone |
| [`pciehp_core.c:307`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L307) | dynamic debug | "device replaced during system sleep" | [`pciehp_device_replaced()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L567) found another device |
| [`slot.c:326`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L326) | dynamic debug | "dev %02x, created physical slot %s" | the slot [`pci_create_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L259) made, number fe for a bus-wide slot |
| [`slot.c:352`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L352) | dynamic debug | "dev %02x, dec refcount to %d" | the reference [`pci_destroy_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L350) drops at remove |
| [`slot.c:80`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/slot.c#L80) | dynamic debug | "dev %02x, released physical slot %s" | the slot's release after the last reference |

The hand-offs are three. The presence check hands a synthetic event to the IRQ thread through [`pciehp_request()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L141), or to the poll thread that [`pciehp_request_irq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L58) starts with [`pciehp_poll_mode`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L34) set. [`pci_hp_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L424) sends a `KOBJ_ADD` uevent for the slot. [`button_work`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp.h#L111), the delayed work a button press schedules, is cancelled by [`pciehp_release_ctrl()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L1096). Probe, suspend, resume and remove fire no PCI tracepoint of their own at v7.2. The tracepoint that follows the hand-off is `pci:pci_hp_event`, which the IRQ thread fires when it handles the synthetic event; read its definition for what a record carries.

```c
/* include/trace/events/pci.h:43 */
TRACE_EVENT(pci_hp_event,

	TP_PROTO(const char *port_name,
		 const char *slot,
		 const int event),

	TP_ARGS(port_name, slot, event),

	TP_STRUCT__entry(
		__string(	port_name,	port_name	)
		__string(	slot,		slot		)
		__field(	int,		event	)
	),

	TP_fast_assign(
		__assign_str(port_name);
		__assign_str(slot);
		__entry->event = event;
	),

	TP_printk("%s slot:%s, event:%s\n",
		__get_str(port_name),
		__get_str(slot),
		__print_symbolic(__entry->event, PCI_HOTPLUG_EVENT)
	)
);
```

A record names the port by [`pci_name()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2354), the slot by its name and the event as one of the hotplug event values, so enabling `pci:pci_hp_event` under /sys/kernel/tracing/events/pci shows each card or link change that a presence check passed on. The IRQ thread fires it at [`pciehp_ctrl.c:251`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_ctrl.c#L251) and at four more sites in that file.

### The slot directory and parameters expose the controller

User space sees the controller through the slot's directory under /sys/bus/pci/slots, named by the Physical Slot Number, and steers it through two module parameters and a boot parameter. [`fs_add_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L242) creates the files when [`pci_hp_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pci_hotplug_core.c#L424) publishes the slot; read the stage that picks them.

```c
/* drivers/pci/hotplug/pci_hotplug_core.c:242 */
static int fs_add_slot(struct hotplug_slot *slot, struct pci_slot *pci_slot)
{
	struct kobject *kobj;
	int retval = 0;

	/* Create symbolic link to the hotplug driver module */
	kobj = kset_find_obj(module_kset, slot->mod_name);
	if (kobj) {
		retval = sysfs_create_link(&pci_slot->kobj, kobj, "module");
		if (retval)
			dev_err(&pci_slot->bus->dev,
				"Error creating sysfs link (%d)\n", retval);
		kobject_put(kobj);
	}

	if (has_power_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_power.attr);
		if (retval)
			goto exit_power;
	}

	if (has_attention_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_attention.attr);
		if (retval)
			goto exit_attention;
	}

	if (has_latch_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_latch.attr);
		if (retval)
			goto exit_latch;
	}

	if (has_adapter_file(slot)) {
		retval = sysfs_create_file(&pci_slot->kobj,
					   &hotplug_slot_attr_presence.attr);
		if (retval)
			goto exit_adapter;
	}
```

The module link points at the driver that registered the slot, which [`mod_name`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_hotplug.h#L63) names. The power file appears because pciehp installs the enable, disable and power callbacks, and the adapter file because it installs the adapter callback. The attention and latch files appear only when [`init_slot()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L51) installed their callbacks, and no test file appears, since pciehp leaves the hardware test empty. The directory also holds the PCI core's "address", "max_bus_speed" and "cur_bus_speed" files. The two module parameters choose polling.

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

Because pciehp is built in, as [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) is a bool option, the parameters are set on the kernel command line as `pciehp.pciehp_poll_mode=1` and `pciehp.pciehp_poll_time=`, and they are also writable under /sys/module/pciehp/parameters. The `pcie_ports=` boot parameter sets the two portdrv flags this page tests; read [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622).

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

`pcie_ports=compat` sets [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1889), which stops [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) and so pciehp, and `pcie_ports=native` sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614), which makes [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) and [`pme_is_native()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L256) ignore what _OSC granted. No debugfs file and no fault-injection point covers the controller's probe, power management or remove at v7.2.
