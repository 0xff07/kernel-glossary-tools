# PCIe port service framework

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A PCIe port can carry several capabilities that each need a driver of their own, among them native hotplug, Advanced Error Reporting (AER), Downstream Port Containment (DPC), PME signaling and link bandwidth notification. The driver model binds one driver to a device, so the PCI core binds one port driver, [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791), to the [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) of each Root Port, Switch Port and Root Complex Event Collector. Each capability the port may use gets a child [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) on a bus of its own, and a service driver, a [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78), binds to that child. This page traces how a port gets its services, how their devices are created, named and bound, how power management and error recovery reach them, and how they are torn down.

```text
    One Root Port as the parent of its service instances, each bound to a service driver
    ────────────────────────────────────────────────────────────────────────────────────

                        ┌────────────────────────────────────────────────┐            ┌────────────────────────────┐
                        │ struct pci_dev 0000:00:1c.0, a Root Port       │  bound     │ struct pci_driver          │
                        │ on the pci bus type                            ├───────────▶│ pcie_portdriver            │
                        │ dev    its embedded struct device              │            │ name "pcieport"            │
                        └────────────────────────┬───────────────────────┘            └────────────────────────────┘
                                                 │ children of dev: device.parent is &dev,
                                                 │ port is the struct pci_dev
                                                 │
              ┌─────────────────────┬────────────┴────────┬─────────────────────┬─────────────────────┐
              ▼                     ▼                     ▼                     ▼                     ▼
    ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
    │ struct pcie_device│ │ struct pcie_device│ │ struct pcie_device│ │ struct pcie_device│ │ struct pcie_device│
    │ service PME       │ │ service AER       │ │ service HP        │ │ service DPC       │ │ service BWCTRL    │
    │ name ...:pcie001  │ │ name ...:pcie002  │ │ name ...:pcie004  │ │ name ...:pcie008  │ │ name ...:pcie010  │
    │ irq  a vector     │ │ irq  a vector     │ │ irq  a vector     │ │ irq  a vector     │ │ irq  a vector     │
    └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
              │                     │                     │                     │                     │
              │ bound               │ bound               │ bound               │ bound               │ bound
              │                     │                     │                     │                     │
              ▼                     ▼                     ▼                     ▼                     ▼
    ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
    │ "pcie_pme"        │ │ "aer"             │ │ "pciehp"          │ │ "dpc"             │ │ "pcie_bwctrl"     │
    └───────────────────┘ └───────────────────┘ └───────────────────┘ └───────────────────┘ └───────────────────┘

    the struct pcie_port_service_driver of each service, matched by equal service bits

    the port is a device of the pci bus type; the five service instances are devices of pcie_port_bus_type,
    the bus named "pci_express"; a service instance is a child device in the driver model and no PCIe function
    a port gets an instance only for the services its type, its hardware and the platform allow
```

## SUMMARY

The framework splits one port into a parent device and its service instances, and the table settles the terms the rest of the page uses.

| Term | Kernel representation | Role on this page |
|---|---|---|
| Port, one of a Root Port, a Switch Upstream Port, a Switch Downstream Port and a Root Complex Event Collector (RCEC) | a [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) whose [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) returns one of those four Device/Port Types | the parent, bound to [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791), the port driver named "pcieport" |
| Port service, one of PME, AER, native hotplug (HP), DPC and bandwidth notification (BWCTRL) | one bit of the mask [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) returns, [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) through [`PCIE_PORT_SERVICE_BWCTRL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L24) | decides which instances a port gets |
| Service instance | a [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), a child of the port's embedded device on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575), the bus named "pci_express" | the device a service driver binds to |
| Service driver | a [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78) holding one service bit | bound to the instance whose service bit equals its own |
| Permission to use a service | the [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654), [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) and [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) bits of the port's [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628), set from the _OSC result | gates the HP, AER and PME bits |

A port's probe enables the port, computes its mask, allocates the interrupt vectors once and registers one instance per set bit, and each instance then binds to its service driver. Power management and error recovery reach the services through the port driver, whose callbacks call one callback slot of every bound service driver. Removal unregisters the instances before the port's vectors are freed, and each instance is freed at its last reference.

## SPECIFICATIONS

The port service framework is a kernel construction that no specification defines, read here from [`portdrv.c`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c) and [`portdrv.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h). The registers its predicates and its interrupt setup read are defined by the PCIe specifications that the source comments name by revision and section, without titles.

- PCI Express Base Specification 1.0a, sections 7.8.2, 7.8.9 and 7.9 - 7.11, named by the kerneldoc of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) at [`portdrv.c:212-214`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L212) for the port registers it reads.
- PCIe r3.1, sec 7.8.2, and PCI r3.0, sec 6.8.3.1, named by the comment at [`portdrv.c:25-29`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L25) for the Interrupt Message Number and the limit of 32 MSI vectors behind [`PCIE_PORT_MAX_MSI_ENTRIES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L30).
- PCIe r6.0, sec 7.5.3.18, and PCIe r3.0, sec 7.8.18, named by the kerneldoc of [`pcie_get_supported_speeds()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6020) at [`pci.c:6005-6009`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6005) for the Supported Link Speeds Vector of Link Capabilities 2.

## COVERAGE

### The service instance and its driver (drivers/pci/pcie/portdrv.h)

- [`'\<struct pcie_device\>':'drivers/pci/pcie/portdrv.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59): portdrv's service instance, one service of one port, a child device on the pci_express bus.
- [`'to_pcie_device'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66): converts the embedded device back to its service instance.
- [`'\<set_service_data\>':'drivers/pci/pcie/portdrv.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68): stores a service driver's data in the instance at bind.
- [`'\<get_service_data\>':'drivers/pci/pcie/portdrv.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73): reads that data back in the service driver's callbacks.
- [`'\<struct pcie_port_service_driver\>':'drivers/pci/pcie/portdrv.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78): a service driver, its callbacks, its service bit and its accepted port type.
- [`'to_service_driver'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L95): converts an embedded device driver back to its service driver.
- [`'PCIE_PORT_SERVICE_PME'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16): the PME service bit, bit 0.
- [`'PCIE_PORT_SERVICE_AER'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18): the AER service bit, bit 1.
- [`'PCIE_PORT_SERVICE_HP'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20): the native hotplug service bit, bit 2.
- [`'PCIE_PORT_SERVICE_DPC'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L22): the DPC service bit, bit 3.
- [`'PCIE_PORT_SERVICE_BWCTRL'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L24): the bandwidth notification service bit, bit 4.
- [`'PCIE_PORT_DEVICE_MAXSERVICES'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L26): the number of service bits, which bounds the loops over them.
- [`'PCIE_ANY_PORT'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57): the port type a service driver gives to accept every port type.

### The bus, binding and lookup (drivers/pci/pcie/portdrv.c)

- [`'\<pcie_port_bus_type\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575): the "pci_express" bus type of the service instances and service drivers.
- [`'\<pcie_port_bus_match\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511): pairs an instance with a driver of the same service bit and an accepted port type.
- [`'\<pcie_port_bus_probe\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534): calls the service driver's probe and takes a reference on the bound instance.
- [`'\<pcie_port_bus_remove\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L562): calls the service driver's remove and drops that reference.
- [`'\<pcie_port_service_register\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586): puts a service driver on the pci_express bus unless port services are disabled.
- [`'\<struct portdrv_service_data\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L34): the search record of a lookup by service bit.
- [`'\<pcie_port_find_device\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L483): returns the bound instance of one service under a port.
- [`'\<find_service_iter\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L455): tests one child of the port for the service a lookup asks for.

### The port driver (drivers/pci/pcie/portdrv.c)

- [`'\<port_pci_ids\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L775): the class codes the port driver binds to.
- [`'\<pcie_portdriver\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791): the PCI driver "pcieport" with its probe, remove, shutdown, error handlers and PM callbacks.
- [`'\<pcie_portdrv_probe\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685): accepts a port by Device/Port Type, registers its services and sets up its runtime PM.
- [`'\<pcie_port_device_register\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331): enables the port, computes the mask, sets up the vectors and creates one instance per set bit.
- [`'\<get_port_device_capability\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218): computes the service mask from the port's type, hardware and permissions.
- [`'get_descriptor_id'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L32): packs the port type and the service bit into the digits of an instance name.
- [`'\<pcie_device_init\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290): allocates, names, parents and registers one service instance.
- [`'\<release_pcie_device\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L47): frees an instance at its last reference.
- [`'\<pcie_init_services\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L830): registers the five service drivers.
- [`'\<pcie_portdrv_init\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839): the initcall that registers the service drivers and then the port driver.
- [`'\<pcie_ports_disabled\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607): set by pcie_ports=compat, keeps the framework from registering anything.
- [`'\<pcie_portdrv_remove\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L726): tears the services down and disables the port when the driver unbinds.
- [`'\<pcie_portdrv_shutdown\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L739): tears the services down at system shutdown.
- [`'\<pcie_port_device_remove\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L505): unregisters every instance of a port and frees its vectors.
- [`'\<remove_iter\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L448): unregisters one child of the port when it is a service instance.

### Power management and error handlers (drivers/pci/pcie/portdrv.c)

- [`'\<pcie_port_device_iter\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385): calls the callback at a given offset of a bound instance's service driver.
- [`'\<pcie_port_device_suspend\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L405): calls every bound service's suspend.
- [`'\<pcie_port_device_resume_noirq\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L411): calls every bound service's resume_noirq.
- [`'\<pcie_port_device_resume\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L421): calls every bound service's resume.
- [`'\<pcie_port_device_runtime_suspend\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L431): calls every bound service's runtime_suspend.
- [`'\<pcie_port_device_runtime_resume\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L441): calls every bound service's runtime_resume.
- [`'\<pcie_port_runtime_suspend\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L638): refuses runtime suspend until the core allows D3 for the port.
- [`'\<pcie_port_runtime_idle\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L646): answers an idle check from the same bit.
- [`'\<pcie_portdrv_pm_ops\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L656): the port driver's PM callbacks, each a fan-out to the services.
- [`'PCIE_PORTDRV_PM_OPS'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L670): the PM callbacks the driver installs, NULL without CONFIG_PM.
- [`'\<pcie_portdrv_err_handler\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L785): the port driver's error recovery callbacks.
- [`'\<pcie_portdrv_error_detected\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L750): asks for a reset when the channel is frozen.
- [`'\<pcie_portdrv_slot_reset\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758): calls every bound service's slot_reset and restores the port's saved state.
- [`'\<pcie_portdrv_mmio_enabled\>':'drivers/pci/pcie/portdrv.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L767): reports the port recovered.

## DOCUMENTATION

- [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst): the guide to the port bus driver, why one driver binds the port and hands each service to a service driver of its own, and how a service driver registers.
- [`Documentation/admin-guide/kernel-parameters.txt`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/admin-guide/kernel-parameters.txt): the pcie_ports=, pcie_port_pm= and pcie_pme= boot parameters and pci=noaer.
- [`Documentation/PCI/pci-error-recovery.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pci-error-recovery.rst): the error_detected, mmio_enabled and slot_reset callbacks of [`struct pci_error_handlers`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L941) that the port driver implements.

## OTHER SOURCES

- [PCI Express Port Bus Driver Guide HOWTO](https://docs.kernel.org/PCI/pciebus-howto.html): the rendered form of the in-tree guide, with the service driver registration walkthrough.
- [PCI-SIG specifications](https://pcisig.com/specifications): the source for the PCI Express Base and PCI Firmware specifications whose capabilities the framework manages.

### Added by Claude Opus 5.5

- [PCI/portdrv: Use bus-type functions (commit cba202aa355d)](https://patch.msgid.link/83d1edc7d619423331fa6802f0e7da3919a308a9.1764688034.git.u.kleine-koenig@baylibre.com)
- [PCI/portdrv: Don't check for valid device and driver in bus callbacks (commit 9d29a9c06f3e)](https://patch.msgid.link/2cc2e15e05318b9f0d7b6a2b69b3169d2a6f0bd3.1764688034.git.u.kleine-koenig@baylibre.com)
- [PCI/portdrv: Move pcie_port_bus_type to pcie source file (commit 61df4929a74b)](https://patch.msgid.link/420d771f0091dea7cf18f445b94301576dcee4c8.1764688034.git.u.kleine-koenig@baylibre.com)
- [PCI/portdrv: Drop empty shutdown callback (commit 15fff3b799ff)](https://patch.msgid.link/283fef06ac51efbb7df25f347d6f3a2967f96429.1764688034.git.u.kleine-koenig@baylibre.com)
- [PCI/portdrv: Fix potential resource leak (commit 01464a3fdf91)](https://patch.msgid.link/e1c68c3b3f1af8427e98ca5e2c79f8bf0ebe2ce4.1764688034.git.u.kleine-koenig@baylibre.com)
- [PCI/portdrv: Use is_pciehp instead of is_hotplug_bridge (commit 1d60796a62f3)](https://patch.msgid.link/40d5a5fe8d40595d505949c620a067fa110ee85e.1752390102.git.lukas@wunner.de)
- [PCI/portdrv: Only disable pciehp interrupts early when needed (commit 9d7db4db1982)](https://lore.kernel.org/r/20250303023630.78397-1-feng.tang@linux.alibaba.com)
- [PCI/bwctrl: Enable only if more than one speed is supported (commit 774c71c52aa4)](https://lore.kernel.org/r/3564908a9c99fc0d2a292473af7a94ebfc8f5820.1734428762.git.lukas@wunner.de)
- [PCI/bwctrl: Re-add BW notification portdrv as PCIe BW controller (commit 665745f27487)](https://lore.kernel.org/r/20241018144755.7875-7-ilpo.jarvinen@linux.intel.com)
- [PCI/portdrv: Allow AER service only for Root Ports & RCECs (commit d8d2b65a940b)](https://lore.kernel.org/r/20221207084105.84947-1-mika.westerberg@linux.intel.com)
- [PCI/portdrv: Set PCIE_PORT_SERVICE_HP for Root and Downstream Ports only (commit 05f5747414c6)](https://lore.kernel.org/r/4786090.31r3eYUQgx@kreacher)
- [PCI/portdrv: Squash into portdrv.c (commit a1ccd3d91138)](https://lore.kernel.org/r/20221019204127.44463-2-helgaas@kernel.org)
- [PCI: portdrv: Set driver_managed_dma (commit c7d469849747)](https://lore.kernel.org/r/20220418005000.897664-7-baolu.lu@linux.intel.com)
- [PCI/portdrv: Remove unused resume err_handler (commit 80dcd36c388a)](https://lore.kernel.org/r/25334149b604e005058aeb0fdf51e01f991d5d74.1627638184.git.lukas@wunner.de)
- [PCI: pciehp: Ignore Link Down/Up caused by error-induced Hot Reset (commit ea401499e943)](https://lore.kernel.org/r/251f4edcc04c14f873ff1c967bc686169cd07d2d.1627638184.git.lukas@wunner.de)
- [PCI/portdrv: Report reset for frozen channel (commit ba952824e6c1)](https://lore.kernel.org/r/20210104230300.1277180-6-kbusch@kernel.org)
- [PCI/ERR: Bind RCEC devices to the Root Port driver (commit c9d659b60770)](https://lore.kernel.org/r/20201121001036.8560-3-sean.v.kelley@intel.com)
- [PCI/DPC: Add "pcie_ports=dpc-native" to allow DPC without AER control (commit 35a0b2378c19)](https://lore.kernel.org/r/20191023192205.97024-1-olof@lixom.net)

## REGISTERS

The framework reads a few configuration registers of a port, most of them through copies the PCI core made at enumeration, and writes two enable bits. Each drawing below names the field the paths of this page touch, with the macro that names it and the member of [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) that caches it.

The Device/Port Type field of the PCIe Capabilities register decides whether the port driver keeps a function, which predicates can grant it a service and which digits name its service instances. [`set_pcie_port_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L1620) caches the whole register in [`pcie_flags_reg`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L385) at enumeration, and [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) extracts [`PCI_EXP_FLAGS_TYPE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L485) from the cache, so neither the probe nor the predicates read configuration space for it.

```text
    PCI Express Capabilities register, offset 0x02 of the PCIe capability
    ────────────────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x02  │F│·│   IRQ   │S│  type │  vers │
          │ │ │  (13:9) │ │ (7:4) │ (3:0) │
          └─┴─┴─────────┴─┴───────┴───────┘

    type = PCI_EXP_FLAGS_TYPE (0x00f0, Device/Port Type, cached in pci_dev.pcie_flags_reg, read by pci_pcie_type()):
           PCI_EXP_TYPE_ROOT_PORT (0x4), PCI_EXP_TYPE_UPSTREAM (0x5), PCI_EXP_TYPE_DOWNSTREAM (0x6),
           PCI_EXP_TYPE_PCI_BRIDGE (0x7, refused by the probe), PCI_EXP_TYPE_RC_EC (0xa)
    IRQ  = PCI_EXP_FLAGS_IRQ (0x3e00, Interrupt Message Number, read by the vector distribution)
    vers = PCI_EXP_FLAGS_VERS (0x000f)   S = PCI_EXP_FLAGS_SLOT (0x0100)   F = PCI_EXP_FLAGS_FLIT (0x8000)
    ·    = bit 14, which pci_regs.h does not name; vers, S and F are unread on these paths
```

Slot Capabilities says whether a port has a slot that supports native hotplug. [`set_pcie_hotplug_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L1688) copies its Hot-Plug Capable bit, [`PCI_EXP_SLTCAP_HPC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L604), into [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) when setup reads a bridge header, and the hotplug predicate tests the copy.

```text
    Slot Capabilities register, offset 0x14 of the PCIe capability
    ─────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x14  │·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│H│·│·│·│·│·│·│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴┬┴─┴─┴─┴─┴─┴─┘
                                                             │
                                                             └──────────────── HPC

    HPC = PCI_EXP_SLTCAP_HPC (0x00000040, Hot-Plug Capable, copied into pci_dev.is_pciehp)
    ·   = the other fields of Slot Capabilities, unread on these paths
```

Slot Control holds the enables of the hotplug interrupts. The hotplug predicate clears [`PCI_EXP_SLTCTL_CCIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L615) and [`PCI_EXP_SLTCTL_HPIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L616) only in a kernel built without [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16), where no driver would handle an interrupt that firmware left enabled. With the option set, as this page assumes, the branch is never taken.

```text
    Slot Control register, offset 0x18 of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x18  │·│·│·│·│·│·│·│·│·│·│H│C│·│·│·│·│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴┬┴┬┴─┴─┴─┴─┘
                               │ │
                               │ └──────────── CCIE
                               └────────────── HPIE

    CCIE = PCI_EXP_SLTCTL_CCIE (0x0010, Command Completed Interrupt Enable)
    HPIE = PCI_EXP_SLTCTL_HPIE (0x0020, Hot-Plug Interrupt Enable)
    both cleared by get_port_device_capability() only when CONFIG_HOTPLUG_PCI_PCIE is unset
    ·    = the other fields of Slot Control, untouched on these paths
```

Root Control holds the PME Interrupt Enable of a Root Port or RCEC. The PME predicate clears [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) through [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54) for each port that gets the PME service, and the PME service driver sets it again once its interrupt handler is installed.

```text
    Root Control register, offset 0x1c of the PCIe capability
    ────────────────────────────────────────────────────────

    bit    1 1 1 1 1 1
           5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x1c  │·│·│·│·│·│·│·│·│·│·│·│·│P│·│·│·│
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴┬┴─┴─┴─┘
                                   │
                                   └────────── PMEIE

    PMEIE = PCI_EXP_RTCTL_PMEIE (0x0008, PME Interrupt Enable), cleared through pcie_pme_interrupt_enable()
    ·     = the other fields of Root Control, untouched on these paths
```

Link Capabilities says whether the port can signal bandwidth changes. The bandwidth predicate reads [`PCI_EXP_LNKCAP_LBNC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L562) from the register itself, and [`pcie_get_supported_speeds()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6020) uses Max Link Speed, [`PCI_EXP_LNKCAP_SLS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L546), to cut the speed vector it records.

```text
    Link Capabilities register, offset 0x0c of the PCIe capability
    ─────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x0c  │·│·│·│·│·│·│·│·│·│·│L│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│  SLS  │
          │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ (3:0) │
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴┬┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴───────┘
                               │
    LBNC ──────────────────────┘

    LBNC = PCI_EXP_LNKCAP_LBNC (0x00200000, Link Bandwidth Notification Capability)
    SLS  = PCI_EXP_LNKCAP_SLS (0x0000000f, Max Link Speed, which caps the vector of Link Capabilities 2)
    ·    = the other fields of Link Capabilities, unread on these paths
```

Link Capabilities 2 lists every speed the port supports, one bit per speed. [`pcie_get_supported_speeds()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6020) keeps the vector, [`PCI_EXP_LNKCAP2_SLS`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L694), in [`supported_speeds`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L582), and the bandwidth predicate grants its service only when more than one bit of that copy is set.

```text
    Link Capabilities 2 register, offset 0x2c of the PCIe capability
    ───────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x2c  │·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│·│  SLS vector │·│
          │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │    (7:1)    │ │
          └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─────────────┴─┘

    SLS vector = PCI_EXP_LNKCAP2_SLS (0x000000fe, Supported Link Speeds Vector, kept with its bit 0 as
                 pci_dev.supported_speeds): 0x02 2.5 GT/s, 0x04 5 GT/s, 0x08 8 GT/s, 0x10 16 GT/s,
                 0x20 32 GT/s, 0x40 64 GT/s
    ·          = the other fields of Link Capabilities 2, unread on these paths
```

The class code is what the PCI core matches the port driver against. Each entry of [`port_pci_ids`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L775) gives a class and a class mask of `~0`, and [`pci_match_one_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L453) compares all 24 bits of [`class`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L366) with it. A function therefore matches when its class is a PCI-to-PCI bridge, a subtractive decode bridge or an RCEC, whatever its vendor.

```text
    Class Code and Revision ID, offset 0x08 of every configuration header
    ────────────────────────────────────────────────────────────────────

    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    0x08  │   Base Class  │   Sub Class   │    Prog IF    │  Revision ID  │
          │    (31:24)    │    (23:16)    │     (15:8)    │     (7:0)     │
          └───────────────┴───────────────┴───────────────┴───────────────┘

    Base Class, Sub Class, Prog IF = PCI_CLASS_REVISION bits 31:8 (0x08, cached in pci_dev.class as 24 bits)
    port_pci_ids compares all 24 bits with:
      PCI_CLASS_BRIDGE_PCI_NORMAL      (0x060400, a PCI-to-PCI bridge)
      PCI_CLASS_BRIDGE_PCI_SUBTRACTIVE (0x060401, a subtractive decode PCI-to-PCI bridge)
      PCI_CLASS_SYSTEM_RCEC << 8       (0x080700, a Root Complex Event Collector)
    Revision ID = PCI_REVISION_ID (0x08, unread on these paths)
```

## DETAILS

The first subsections build the model, the service instance a port parents, the service driver that binds to it and the bus that pairs the two. They then show how the service drivers are registered before any port binds and how a boot parameter can stop it all. The journey follows one port from the probe that accepts it, through the predicates that pick its services and their inputs, to the loop that creates one instance per service and the binding of each instance. Two searches over a port's instances follow, and the later subsections carry the port through system sleep, runtime suspend, removal, the release of its instances and error recovery. The page ends with the messages, hand-offs and files that make these paths visible.

### Kconfig assumptions

The page documents an x86-64 kernel built from the defconfig resolved at v7.2 with the options of this documentation campaign added, among them [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121), [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) and [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120). Its host bridges come from ACPI, so the permissions the predicates read are the results of the _OSC negotiation.

| Option | Value assumed | What it decides on these paths |
|---|---|---|
| [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) | y | builds portdrv.c and bwctrl.c and registers the pci_express bus type; without it [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) is the constant true |
| [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) | y | compiles the fan-out callbacks and [`pcie_portdrv_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L656); without it [`PCIE_PORTDRV_PM_OPS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L670) is NULL |
| [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) | y | compiles the suspend, resume_noirq and resume slots of the hotplug service driver |
| [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) | y, from CONFIG_PCIEPORTBUS and CONFIG_PM | builds pme.c, whose init registers the PME service driver |
| [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) | y | compiles the AER predicate and builds aer.c, whose init registers the AER service driver |
| [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) | y | builds dpc.c, whose init registers the DPC service driver |
| [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) | y | registers the hotplug service driver and leaves Slot Control alone in the hotplug predicate |
| [`CONFIG_PCI_MSI`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L44) | y | lets [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) report MSI on, which the AER and DPC predicates need |
| [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37) | not set | leaves out aer_inject.c, the one caller of [`pcie_port_find_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L483) |
| [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) | y | makes the dev_dbg(), pci_dbg() and pr_debug() sites of these paths dynamic-debug sites |
| [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70) | not set | would print the same PCI sites unconditionally through -DDEBUG |

The table indexes the prose and is no source of its own: each option's effect is stated again where it applies in the subsections below.

### A service instance stands for one service of one port

A PCIe port can host several capabilities at once, and each needs a driver that requests its interrupt, handles its events and saves its state. The driver model binds one driver to a device, so the framework binds [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) to the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). Each capability the port may use gets a device of its own, a child of the port's embedded device. The guide [`Documentation/PCI/pciebus-howto.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/PCI/pciebus-howto.rst) states the reason, that without the split "several service drivers will compete for a single PCI-PCI Bridge device".

[`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59) is portdrv's service instance, a device of the driver model that stands for one service of one port and is no PCIe function of its own. Its definition in [`portdrv.h`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h) holds the link back to the port, the service bit, the interrupt and the service driver's data, and [`to_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) after it maps the embedded device back to the instance. Read it for what each member points at.

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

[`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) points at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), so a service driver reaches the port's configuration space through it. [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) holds one service bit, and [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) holds the interrupt vector the port's interrupt setup chose for that service. [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) holds whatever the service driver stores at bind. [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is the embedded [`struct device`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L703) that the bus, the driver core and sysfs handle, and [`to_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) subtracts its offset with `container_of()` to recover the instance from it.

The bits that [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) holds are defined at the top of the same header, one per service, with [`PCIE_PORT_DEVICE_MAXSERVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L26) giving their number. Read them for the bit each service owns, because the bit number later indexes the interrupt array and appears in the instance's name.

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

PME owns bit 0, AER bit 1, native hotplug bit 2, DPC bit 3 and bandwidth notification bit 4. Each `_SHIFT` macro gives the bit number and the plain macro its mask, from [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) to [`PCIE_PORT_SERVICE_BWCTRL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L24). [`PCIE_PORT_DEVICE_MAXSERVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L26) is 5, one past the highest bit. In portdrv.c it bounds the three loops over the services and sizes the interrupt array that registration fills.

An instance's fields are written at a few points of its life, by the registration that creates it, by the service driver that binds to it and by the release that frees it. The strip follows one instance from its allocation to its free, and the subsections after this one show the line of each mark in the order of the marks.

```text
    One struct pcie_device from allocation to free, and the writes to its fields
    ────────────────────────────────────────────────────────────────────────────
    fields: the object, port, irq, service, device.bus, device.release, device.parent, priv_data

    time ──────────────────────────────────────────────────────────────────────────────────────────────▶
    event            alloc       fill        register      bind          unbind          last put
                     ▼           ▼           ▼             ▼             ▼               ▼
                     ┌───────────┬───────────────────────────────────────────────────────┬─────────────┐
    object           │① zeroed   │allocated: filled, registered, bound, unbound in turn  │⑨ freed      │
                     └───────────┴───────────────────────────────────────────────────────┴─────────────┘
                     ┌───────────┬─────────────────────────────────────────────────────────────────────┐
    port             │NULL       │② the port's struct pci_dev                                          │
                     └───────────┴─────────────────────────────────────────────────────────────────────┘
                     ┌───────────┬─────────────────────────────────────────────────────────────────────┐
    irq              │0          │③ irqs[i], the vector found for the service                          │
                     └───────────┴─────────────────────────────────────────────────────────────────────┘
                     ┌───────────┬─────────────────────────────────────────────────────────────────────┐
    service          │0          │④ one PCIE_PORT_SERVICE_* bit                                        │
                     └───────────┴─────────────────────────────────────────────────────────────────────┘
                     ┌───────────┬─────────────────────────────────────────────────────────────────────┐
    device.bus       │NULL       │⑤ &pcie_port_bus_type                                                │
                     └───────────┴─────────────────────────────────────────────────────────────────────┘
                     ┌───────────┬─────────────────────────────────────────────────────────────────────┐
    device.release   │NULL       │⑥ release_pcie_device                                                │
                     └───────────┴─────────────────────────────────────────────────────────────────────┘
                     ┌───────────┬─────────────────────────────────────────────────────────────────────┐
    device.parent    │NULL       │⑦ &port->dev, the port's embedded device                             │
                     └───────────┴─────────────────────────────────────────────────────────────────────┘
                     ┌─────────────────────────────────────┬───────────────────────────────────────────┐
    priv_data        │NULL                                 │⑧ the service driver's data, left as it is │
                     └─────────────────────────────────────┴───────────────────────────────────────────┘

    ① pcie_device_init portdrv.c:296  allocates the instance zeroed through kzalloc_obj
    ② pcie_device_init :299  points port at the port's struct pci_dev
    ③ pcie_device_init :300  stores the vector that irqs[] holds for the service
    ④ pcie_device_init :301  stores the one service bit the instance stands for
    ⑤ pcie_device_init :305  puts the embedded device on pcie_port_bus_type
    ⑥ pcie_device_init :306  installs the callback that frees the instance
    ⑦ pcie_device_init :310  makes the port's embedded device the parent
    ⑧ set_service_data portdrv.h:70  stores the service driver's data at bind
    ⑨ release_pcie_device portdrv.c:49  frees the instance at the last put
```

① [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) allocates the instance zeroed through `kzalloc_obj()`. ② `pcie_device_init()` points [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61) at the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352). ③ `pcie_device_init()` stores the vector the interrupt array holds for the service in [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60). ④ `pcie_device_init()` stores the service bit in [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62). ⑤ `pcie_device_init()` puts the embedded device on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575). ⑥ `pcie_device_init()` installs the release callback in the embedded device. ⑦ `pcie_device_init()` makes the port's embedded device the parent. ⑧ [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) stores the service driver's data in [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) when that driver binds. ⑨ [`release_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L47) frees the instance when the last reference to its embedded device is dropped.

At v7.2 every assignment to [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61), [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60), [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62) and [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) in the tree lies in portdrv.c and portdrv.h, and the strip shows them all. The driver core's [`device_move()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4667) in drivers/base/core.c also writes the parent of a device it moves, and the strip leaves it out because no code of this framework moves a service instance. Between ⑧ and ⑨ the instance keeps the pointer its driver stored, since no remove path clears [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63).

### A service driver declares the one service it drives

An instance waits for a driver that knows its service, and the framework defines its own driver type for that. [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78) carries the callbacks a service implements, the service bit it drives and the port type it accepts, and it embeds the [`struct device_driver`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/driver.h#L100) the driver core registers. Read the definition for the groups of members and for [`to_service_driver()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L95), which maps the embedded driver back to the service driver.

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

[`name`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L79) becomes the name of the embedded driver. [`probe`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L80) and [`remove`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L81) bind and unbind one instance, the five power-management slots from [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L82) to [`runtime_resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L86) follow the port through sleep and runtime suspend, and [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88) runs after a reset above the port. [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) are what the bus matches against an instance, and [`driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L93) is the embedded driver. Every callback takes the [`struct pcie_device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L59), so a service never handles the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352) without its instance.

The tree defines five service drivers at v7.2, each in the file of its service. The table lists, for each, the service bit it declares and the slots it fills besides probe and remove, read from their initializers.

| Service driver | Service bit | Slots filled besides probe and remove | Registered by |
|---|---|---|---|
| [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456) "pcie_pme" | [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) | suspend, resume | [`pcie_pme_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470) |
| [`aerdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1719) "aer" | [`PCIE_PORT_SERVICE_AER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18) | suspend, resume | [`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735) |
| [`hpdriver_portdrv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L353) "pciehp" | [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20) | suspend, resume_noirq and resume with [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140), runtime_suspend and runtime_resume with [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217), slot_reset | [`pcie_hp_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374) |
| [`dpcdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L523) "dpc" | [`PCIE_PORT_SERVICE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L22) | suspend, resume | [`pcie_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L533) |
| [`pcie_bwctrl_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L319) "pcie_bwctrl" | [`PCIE_PORT_SERVICE_BWCTRL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L24) | suspend, resume | [`pcie_bwctrl_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L329) |

The hotplug driver is the one that fills resume_noirq, the two runtime slots and slot_reset, so every later fan-out through those slots reaches pciehp alone at v7.2. The PME driver shows the shape all five share; read [`pcie_pme_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L456) and [`pcie_pme_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470) for the fields an initializer sets and for the registration call.

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

/**
 * pcie_pme_init - Register the PCIe PME service driver.
 */
int __init pcie_pme_init(void)
{
	return pcie_port_service_register(&pcie_pme_driver);
}
```

The initializer names the driver, accepts [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57), claims [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) and fills four callbacks, leaving the other slots NULL. [`pcie_pme_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470) hands the structure to [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586), which completes the embedded driver before it reaches the driver core. The service is decided by [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) alone, and the side-by-side drawing in the next subsection sets this definition against the instance it is matched with.

### The pci_express bus pairs instances with drivers by service bit

Instances and service drivers meet on a bus type of their own, which keeps them apart from the PCI functions and drivers of [`pci_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1726). The PCI core registers both bus types in [`pci_driver_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1745) at the postcore initcall level; read it for the [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) guard around the second registration.

```c
/* drivers/pci/pci-driver.c:1745 */
static int __init pci_driver_init(void)
{
	int ret;

	pci_probe_wq = alloc_workqueue("sync_wq", WQ_PERCPU, 0);
	if (!pci_probe_wq)
		return -ENOMEM;

	ret = bus_register(&pci_bus_type);
	if (ret)
		return ret;

#ifdef CONFIG_PCIEPORTBUS
	ret = bus_register(&pcie_port_bus_type);
	if (ret)
		return ret;
#endif
	dma_debug_add_bus(&pci_bus_type);
	return 0;
}
postcore_initcall(pci_driver_init);
```

With [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) set, [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) is registered right after [`pci_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1726), before any device initcall runs, so a service driver or an instance can be added to it from then on. A failure of either [`bus_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/bus.c#L941) call stops the function before the DMA debug hook. The bus type itself names three callbacks and nothing else; read [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) for them.

```c
/* drivers/pci/pcie/portdrv.c:575 */
const struct bus_type pcie_port_bus_type = {
	.name = "pci_express",
	.match = pcie_port_bus_match,
	.probe = pcie_port_bus_probe,
	.remove = pcie_port_bus_remove,
};
```

The bus is named "pci_express", which is the directory it gets under /sys/bus. [`match`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/bus.h#L90) pairs an instance with a driver, [`probe`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/bus.h#L92) binds them and [`remove`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device/bus.h#L94) unbinds them, and the bus has no power-management callbacks. The driver core calls the match through [`driver_match_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/base.h#L169); read it for what happens when a bus has no match callback.

```c
/* drivers/base/base.h:169 */
static inline int driver_match_device(const struct device_driver *drv,
				      struct device *dev)
{
	return drv->bus->match ? drv->bus->match(dev, drv) : 1;
}
```

A bus without a match callback accepts every pairing, so the pci_express bus would hand any instance to the first registered service driver without [`pcie_port_bus_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511). The match also reads the wildcard a service driver gives as its port type, [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57), defined in the header beside the instance.

```c
/* drivers/pci/pcie/portdrv.h:56 */
/* Port Type */
#define PCIE_ANY_PORT			(~0)
```

[`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) is all bits set, a value no Device/Port Type can take. The figure sets the two structures beside each other and shows which members the match compares.

```text
    A service instance and a service driver meet at the bus match
    ─────────────────────────────────────────────────────────────

    struct pcie_device                                struct pcie_port_service_driver
    ┌──────────────────────────────────────────┐      ┌────────────────────────────────────────────────────────┐
    │ irq        the service's vector          │      │ name             the driver's name                     │
    │ port       the port's struct pci_dev     │      │ probe, remove    bind and unbind an instance           │
    │ service    one service bit               │      │ suspend, resume_noirq, resume                          │
    │ priv_data  the service driver's data     │      │ runtime_suspend, runtime_resume                        │
    │ device     the embedded struct device,   │      │ slot_reset       after a reset above the port          │
    │            to_pcie_device() maps it back │      │ port_type        PCIE_ANY_PORT or one port type        │
    └─────────┬───────────────────┬────────────┘      │ service          one service bit                       │
              │                   │                   │ driver           the embedded struct device_driver,    │
              │ service           │ port              │                  to_service_driver() maps it back      │
              │                   │                   └─────────────┬───────────────────────┬──────────────────┘
              │                   │                                 │                       │
              │                   ▼                                 │ service               │ port_type
              │           pci_pcie_type(port)                       │                       │
              │                   │                                 │                       │
              ▼                   ▼                                 ▼                       ▼
    ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
    │ pcie_port_bus_match(): a match when the two service bits are equal                                       │
    │ and port_type is PCIE_ANY_PORT or equals the Device/Port Type of port;                                   │
    │ every service driver at v7.2 sets PCIE_ANY_PORT, so the service bits decide                              │
    └──────────────────────────────────────────────────────────────────────────────────────────────────────────┘

    on a match the bus probe calls the driver's probe with the instance
```

[`pcie_port_bus_match()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L511) converts both arguments back to their containers and compares them twice. Read it for the order of the two tests.

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

The first test rejects a driver whose [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) differs from the instance's [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62). The second rejects a driver whose [`port_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L90) is neither [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57) nor the Device/Port Type of the instance's port. At v7.2 all five service drivers in drivers/pci set [`PCIE_ANY_PORT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L57), so the second test never rejects and the service bit alone decides. A service meant for some port types checks the type in its own probe, as [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326) does.

### The service drivers register before the port driver

A port's probe registers instances, and an instance binds at once when its service driver is already on the bus. The framework arranges that order in one initcall, which registers the service drivers before the port driver. Every service driver comes in through [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586), defined with [`pcie_port_service_unregister()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L601) after it; read them for the gate and for the two fields they fill in the embedded driver.

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

/**
 * pcie_port_service_unregister - unregister PCI Express port service driver
 * @drv: PCI Express port service driver to unregister
 */
void pcie_port_service_unregister(struct pcie_port_service_driver *drv)
{
	driver_unregister(&drv->driver);
}
```

[`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) refuses with -ENODEV when [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) is set. Otherwise it copies [`name`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L79) into the embedded driver, puts the driver on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) and calls [`driver_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/driver.c#L150). [`pcie_port_service_unregister()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L601) has no caller at v7.2, because every service driver is built in and stays registered. The driver core offers a newly registered driver the devices already on its bus in [`bus_add_driver()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/bus.c#L732); read the stage that prints the debug line and attaches.

```c
/* drivers/base/bus.c:732 */
int bus_add_driver(struct device_driver *drv)
{
	struct subsys_private *sp = bus_to_subsys(drv->bus);
	struct driver_private *priv;
	int error = 0;

	if (!sp)
		return -EINVAL;

	/*
	 * Reference in sp is now incremented and will be dropped when
	 * the driver is removed from the bus
	 */
	pr_debug("bus: '%s': add driver %s\n", sp->bus->name, drv->name);

	... /* 14 lines, to :761 */
	klist_add_tail(&priv->knode_bus, &sp->klist_drivers);
	if (sp->drivers_autoprobe) {
		error = driver_attach(drv);
		if (error)
			goto out_del_list;
	}
```

The pr_debug() line names the bus and the driver, and when the bus's drivers_autoprobe flag is set, [`driver_attach()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L1307) tries the driver on every device already on the bus. For a service driver those are the instances registered so far, and for the port driver the ports that enumeration has already added. The service drivers' init functions are declared in portdrv.h with stubs for the services a build leaves out; read the block for the option that guards each.

```c
/* drivers/pci/pcie/portdrv.h:28 */
extern bool pcie_ports_dpc_native;

#ifdef CONFIG_PCIEAER
int pcie_aer_init(void);
#else
static inline int pcie_aer_init(void) { return 0; }
#endif

#ifdef CONFIG_HOTPLUG_PCI_PCIE
int pcie_hp_init(void);
#else
static inline int pcie_hp_init(void) { return 0; }
#endif

#ifdef CONFIG_PCIE_PME
int pcie_pme_init(void);
#else
static inline int pcie_pme_init(void) { return 0; }
#endif

#ifdef CONFIG_PCIE_DPC
int pcie_dpc_init(void);
#else
static inline int pcie_dpc_init(void) { return 0; }
#endif

int pcie_bwctrl_init(void);
```

[`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735), [`pcie_hp_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374), [`pcie_pme_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L470) and [`pcie_dpc_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/dpc.c#L533) become stubs returning 0 when [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28), [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16), [`CONFIG_PCIE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L117) or [`CONFIG_PCIE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L121) is not set, while [`pcie_bwctrl_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/bwctrl.c#L329) is always declared because bwctrl.c is built with the port driver. The AER init adds a condition of its own; read [`pcie_aer_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1735).

```c
/* drivers/pci/pcie/aer.c:1730 */
/**
 * pcie_aer_init - register AER service driver
 *
 * Invoked when AER service driver is loaded.
 */
int __init pcie_aer_init(void)
{
	if (!pci_aer_available())
		return -ENXIO;
	return pcie_port_service_register(&aerdriver);
}
```

The AER service driver is not registered at all when [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is false, which the AER predicate tests as well. [`pcie_init_services()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L830) calls the five init functions in a fixed order; read it for that order.

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

The order is AER, PME, DPC, bandwidth notification and hotplug, and the return values are dropped, so a service driver that fails to register leaves the others registered. [`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) wraps the call between the global switch and the registration of the port driver; read it for the order of the three steps.

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
```

[`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) returns -EACCES before registering anything when [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) is set. Otherwise it registers the service drivers, runs the DMI quirk table and registers [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) through [`pci_register_driver()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1683) last, so the service drivers are on the bus before the first port probe creates an instance. The quirk table is the file's own; read [`pcie_portdrv_dmi_table`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L814) with its callback.

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

At v7.2 the table holds one entry, for one listed system, and its callback prints the system's name with pr_notice() and calls [`pcie_pme_disable_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L108). That makes [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) true for the whole boot, which sends every port that gets the PME service to INTx for all its services, as the interrupt setup in the registration subsection shows. The initcall level of the function is fixed by the line after it.

```c
/* drivers/pci/pcie/portdrv.c:849 */
device_initcall(pcie_portdrv_init);
```

[`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) is a device initcall, while [`pci_driver_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1745) is a postcore initcall. The macros in [`init.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/init.h) give each name its level number; read the two for the numbers.

```c
/* include/linux/init.h:293 */
#define pure_initcall(fn)		__define_initcall(fn, 0)

#define core_initcall(fn)		__define_initcall(fn, 1)
#define core_initcall_sync(fn)		__define_initcall(fn, 1s)
#define postcore_initcall(fn)		__define_initcall(fn, 2)
#define postcore_initcall_sync(fn)	__define_initcall(fn, 2s)
#define arch_initcall(fn)		__define_initcall(fn, 3)
#define arch_initcall_sync(fn)		__define_initcall(fn, 3s)
#define subsys_initcall(fn)		__define_initcall(fn, 4)
#define subsys_initcall_sync(fn)	__define_initcall(fn, 4s)
#define fs_initcall(fn)			__define_initcall(fn, 5)
#define fs_initcall_sync(fn)		__define_initcall(fn, 5s)
#define rootfs_initcall(fn)		__define_initcall(fn, rootfs)
#define device_initcall(fn)		__define_initcall(fn, 6)
#define device_initcall_sync(fn)	__define_initcall(fn, 6s)
#define late_initcall(fn)		__define_initcall(fn, 7)
#define late_initcall_sync(fn)		__define_initcall(fn, 7s)

```

A postcore initcall is level 2 and a device initcall level 6. [`do_initcalls()`](https://elixir.bootlin.com/linux/v7.2/source/init/main.c#L1412) runs the levels one after the other in ascending order; read the loop.

```c
/* init/main.c:1412 */
static void __init do_initcalls(void)
{
	int level;
	size_t len = saved_command_line_len + 1;
	char *command_line;

	command_line = kzalloc(len, GFP_KERNEL);
	if (!command_line)
		panic("%s: Failed to allocate %zu bytes\n", __func__, len);

	for (level = 0; level < ARRAY_SIZE(initcall_levels) - 1; level++) {
		/* Parser modifies command_line, restore it each time */
		strcpy(command_line, saved_command_line);
		do_initcall_level(level, command_line);
	}

	kfree(command_line);
}
```

Every level-2 initcall has returned before the first level-6 initcall starts, so [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) exists when the first service driver registers. The figure places the pieces this subsection created against the ports that enumeration adds before the initcall and after it.

```text
    The order in which the framework's pieces come into existence
    ─────────────────────────────────────────────────────────────

    time ──────────────────────────────────────────────────────────────────────────────────────────────────────────▶
    initcall              postcore                device                                          later
    event                 pci_driver_init         pcie_portdrv_init                               a port
                                                  disabled?  services  DMI  pcieport              is added
                          ╎                       ╎          ╎         ╎    ╎                     ╎
    bus types             ├─ pci and pci_express registered ───────────────────────────────────────────────────────▶
    existing ports              ├─ enumerated, no driver ──────────────────┤├─ bound to pcieport ──────────────────▶
    service drivers                                          ├─ on pci_express, waiting ───────────────────────────▶
    port driver                                                             ├─ pcieport on pci ────────────────────▶
    service instances                                                       ├─ one per bit, per port ──────────────▶
    a hot-added port                                                                              ├─ probed ───────▶

    with pcie_ports=compat, pcie_portdrv_init returns -EACCES at its first column and the rows
    below "bus types" stay empty; the pci_express bus type is registered either way
```

Ports enumerated before the initcall bind when [`pci_register_driver()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1683) attaches the port driver to them, and a port that appears later binds when the PCI core adds its device. Either way the service drivers are registered first, and each instance a port's probe creates finds its driver on the bus.

### The pcie_ports= parameter can switch the framework off

Firmware and the kernel can disagree over who handles AER, PME, DPC and hotplug, and the pcie_ports= boot parameter lets the administrator settle it either way. [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) parses the parameter into three flags of portdrv.c; read it with the flags.

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

pcie_ports=compat sets [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607), pcie_ports=native sets [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) and pcie_ports=dpc-native sets [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620). The comparisons use strncmp() on 6 and 10 characters, so a value that starts with one of the words also counts, and any other value sets nothing. The table lists what each flag changes on the paths of this page.

| Value | Flag set | Effect on these paths |
|---|---|---|
| compat | [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) | [`pcie_portdrv_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L839) and [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) refuse, and the ACPI host bridge requests no _OSC control |
| native | [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) | the HP, AER and PME predicates of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) grant their bits without the host bridge's native bits |
| dpc-native | [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620) | the DPC predicate grants its bit without the AER bit |

Two of the flags are read outside the framework, and [`pci.h`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h) declares them for a build with [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5) and replaces them with constants for a build without it. Read the block for both cases.

```c
/* include/linux/pci.h:1882 */
#ifdef CONFIG_PCIEPORTBUS
extern bool pcie_ports_disabled;
extern bool pcie_ports_native;

int pcie_set_target_speed(struct pci_dev *port, enum pci_bus_speed speed_req,
			  bool use_lt);
#else
#define pcie_ports_disabled	true
#define pcie_ports_native	false

static inline int pcie_set_target_speed(struct pci_dev *port,
					enum pci_bus_speed speed_req,
					bool use_lt)
{
	return -EOPNOTSUPP;
}
#endif
```

Without [`CONFIG_PCIEPORTBUS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L5), [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) is the constant true and [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) the constant false, so code that tests them compiles either way and sees port services off. One such reader is the ACPI host bridge code, which asks firmware for control of the PCIe features only after [`os_control_query_checks()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L539) approves; read the check.

```c
/* drivers/acpi/pci_root.c:539 */
static bool os_control_query_checks(struct acpi_pci_root *root, u32 support)
{
	struct acpi_device *device = root->device;

	if (pcie_ports_disabled) {
		dev_info(&device->dev, "PCIe port services disabled; not requesting _OSC control\n");
		return false;
	}

	if ((support & ACPI_PCIE_REQ_SUPPORT) != ACPI_PCIE_REQ_SUPPORT) {
		decode_osc_support(root, "not requesting OS control; OS requires",
				   ACPI_PCIE_REQ_SUPPORT);
		return false;
	}

	return true;
}
```

With [`pcie_ports_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L607) set, the host bridge prints that port services are disabled and requests no _OSC control, so the native bits of its [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) end up clear. The switch thus holds on both sides, since the framework registers neither its service drivers nor its port driver.

So far, [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) is registered, the five service drivers wait on it and [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) is registered on [`pci_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1726), unless pcie_ports=compat stopped the initcall. No port has been probed yet, and the next subsection follows the probe that accepts one.

### The probe accepts a port by its Device/Port Type

Binding starts on [`pci_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1726), where the port driver must pick out the ports among all PCIe functions. It does so in two steps, a class match in its ID table and a type check in its probe. [`port_pci_ids`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L775) holds the classes; read it for the three entries and the mask each one carries.

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

Each entry is built by [`PCI_DEVICE_CLASS()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1108), which leaves vendor and device open; read the macro.

```c
/* include/linux/pci.h:1108 */
#define PCI_DEVICE_CLASS(dev_class,dev_class_mask) \
	.class = (dev_class), .class_mask = (dev_class_mask), \
	.vendor = PCI_ANY_ID, .device = PCI_ANY_ID, \
	.subvendor = PCI_ANY_ID, .subdevice = PCI_ANY_ID
```

The entries ask for class [`PCI_CLASS_BRIDGE_PCI_NORMAL`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_ids.h#L63), [`PCI_CLASS_BRIDGE_PCI_SUBTRACTIVE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_ids.h#L64) and [`PCI_CLASS_SYSTEM_RCEC`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci_ids.h#L90) shifted by 8 with programming interface 0, each with a mask of `~0`, and set every ID field to [`PCI_ANY_ID`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device-id/pci.h#L10). [`pci_match_one_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.h#L453) applies an entry to a function; read its last test for what the mask does.

```c
/* drivers/pci/pci.h:452 */
static inline const struct pci_device_id *
pci_match_one_device(const struct pci_device_id *id, const struct pci_dev *dev)
{
	if ((id->vendor == PCI_ANY_ID || id->vendor == dev->vendor) &&
	    (id->device == PCI_ANY_ID || id->device == dev->device) &&
	    (id->subvendor == PCI_ANY_ID || id->subvendor == dev->subsystem_vendor) &&
	    (id->subdevice == PCI_ANY_ID || id->subdevice == dev->subsystem_device) &&
	    !((id->class ^ dev->class) & id->class_mask))
		return id;
	return NULL;
}

```

The class test XORs the entry's class with the function's 24-bit [`class`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L366) and masks the difference, so with a mask of `~0` every bit must agree. A Root Port, a Switch Port and a PCIe-to-PCI bridge all report a PCI-to-PCI bridge class and pass, as does a conventional PCI-to-PCI bridge, and an Endpoint does not. The probe sorts the bridges out, and the driver that names it is [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791); read it for the callbacks and flags it hands the PCI core.

```c
/* drivers/pci/pcie/portdrv.c:791 */
static struct pci_driver pcie_portdriver = {
	.name		= "pcieport",
	.id_table	= port_pci_ids,

	.probe		= pcie_portdrv_probe,
	.remove		= pcie_portdrv_remove,
	.shutdown	= pcie_portdrv_shutdown,

	.err_handler	= &pcie_portdrv_err_handler,

	.driver_managed_dma = true,

	.driver.pm	= PCIE_PORTDRV_PM_OPS,
};
```

[`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) is named "pcieport", binds through [`port_pci_ids`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L775) and gives the PCI core a probe, a remove and a shutdown callback, the error handlers of [`pcie_portdrv_err_handler`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L785) and the PM callbacks of [`PCIE_PORTDRV_PM_OPS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L670). [`driver_managed_dma`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L1037) is set, and [`pci_dma_configure()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1668) reads it when a driver binds; read the stage where it does.

```c
/* drivers/pci/pci-driver.c:1668 */
static int pci_dma_configure(struct device *dev)
{
	const struct device_driver *drv = READ_ONCE(dev->driver);
	... /* 24 lines, to :1695 */
	/* @drv may not be valid when we're called from the IOMMU layer */
	if (!ret && drv && !to_pci_driver(drv)->driver_managed_dma) {
		ret = iommu_device_use_default_domain(dev);
		if (ret)
			arch_teardown_dma_ops(dev);
	}
```

With the flag set, [`pci_dma_configure()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1668) skips [`iommu_device_use_default_domain()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/iommu/iommu.c#L3316) for a port, and the IOMMU core beneath that call is outside this page. According to commit [c7d469849747](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=c7d469849747ce380785536173d08b30a820a83c) ("PCI: portdrv: Set driver_managed_dma"), the flag lets the port driver stay bound to a switch port. The devices below the switch, which share its IOMMU group, can then be assigned to user space through VFIO. The type check in the probe uses two inline helpers of include/linux/pci.h; read [`pci_is_pcie()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2660) and [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) for the cached values they read.

```c
/* include/linux/pci.h:2655 */
 * pci_is_pcie - check if the PCI device is PCI Express capable
 * @dev: PCI device
 *
 * Returns: true if the PCI device is PCI Express capable, false otherwise.
 */
static inline bool pci_is_pcie(struct pci_dev *dev)
{
	return pci_pcie_cap(dev);
}

/**
 * pcie_caps_reg - get the PCIe Capabilities Register
 * @dev: PCI device
 */
static inline u16 pcie_caps_reg(const struct pci_dev *dev)
{
	return dev->pcie_flags_reg;
}

/**
 * pci_pcie_type - get the PCIe device/port type
 * @dev: PCI device
 */
static inline int pci_pcie_type(const struct pci_dev *dev)
{
	return (pcie_caps_reg(dev) & PCI_EXP_FLAGS_TYPE) >> 4;
}
```

[`pci_is_pcie()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2660) is true when the function has a PCIe capability offset, and [`pci_pcie_type()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L2678) takes the Device/Port Type field out of [`pcie_flags_reg`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L385). Enumeration fills both in [`set_pcie_port_type()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L1620); read the stage that caches them.

```c
/* drivers/pci/probe.c:1620 */
void set_pcie_port_type(struct pci_dev *pdev)
{
	int pos;
	u16 reg16;
	u32 reg32;
	int type;
	struct pci_dev *parent;

	pos = pci_find_capability(pdev, PCI_CAP_ID_EXP);
	if (!pos)
		return;

	pdev->pcie_cap = pos;
	pci_read_config_word(pdev, pos + PCI_EXP_FLAGS, &reg16);
	pdev->pcie_flags_reg = reg16;
```

[`pcie_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L379) gets the offset of the PCIe capability and [`pcie_flags_reg`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L385) the PCIe Capabilities register at that offset, so a function without the capability keeps both at 0. With both helpers known, [`pcie_portdrv_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685) reads as one sequence of decisions; read it whole.

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

	pci_save_state(dev);

	dev_pm_set_driver_flags(&dev->dev, DPM_FLAG_NO_DIRECT_COMPLETE |
					   DPM_FLAG_SMART_SUSPEND);

	if (pci_bridge_d3_possible(dev)) {
		/*
		 * Keep the port resumed 100ms to make sure things like
		 * config space accesses from userspace (lspci) will not
		 * cause the port to repeatedly suspend and resume.
		 */
		pm_runtime_set_autosuspend_delay(&dev->dev, 100);
		pm_runtime_use_autosuspend(&dev->dev);
		pm_runtime_mark_last_busy(&dev->dev);
		pm_runtime_put_autosuspend(&dev->dev);
		pm_runtime_allow(&dev->dev);
	}

	return 0;
}
```

The probe returns -ENODEV for a function without a PCIe capability and for any type other than [`PCI_EXP_TYPE_ROOT_PORT`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L488), [`PCI_EXP_TYPE_UPSTREAM`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L489), [`PCI_EXP_TYPE_DOWNSTREAM`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L490) and [`PCI_EXP_TYPE_RC_EC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L494). That turns away the PCIe-to-PCI bridge and the conventional bridge the class match let through. For an RCEC it first calls [`pcie_link_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L110), then [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331), whose failure fails the probe. After a successful registration it saves the port's configuration with [`pci_save_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1747), sets [`DPM_FLAG_NO_DIRECT_COMPLETE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L661) and [`DPM_FLAG_SMART_SUSPEND`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L663), and enables runtime PM with a 100 ms autosuspend delay when [`pci_bridge_d3_possible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2988) allows D3 for the port. The RCEC step records which integrated Endpoints the RCEC serves; read [`pcie_link_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L110).

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

[`pcie_link_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L110) returns at once for an RCEC without Endpoint Association data, [`rcec_ea`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L374), and otherwise hands the RCEC to [`walk_rcec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/rcec.c#L68), which its kerneldoc says links the RCEC to each integrated Endpoint found. The links serve the error and PME paths of the RCEC, and the probe sets them up before the services start. The figure shows which functions of a hierarchy end up bound.

```text
    Which functions of a hierarchy the port driver binds
    ────────────────────────────────────────────────────

             ┌────────────────────────────────────────────────────────────────────┐
    tier 0   │ host bridge, root bus 00                                           │
             └───┬────────────────────────┬────────────────────────┬──────────────┘
                 │                        │                        │
             ┌───┴────────────┐       ┌───┴────────────┐       ┌───┴────────────┐
    tier 1   │ Root Port      │       │ Root Port      │       │ RCEC           │
             │ bound          │       │ bound          │       │ bound          │
             └───┬────────────┘       └───┬────────────┘       └────────────────┘
                 │                        │
             ┌───┴──────────────┐     ┌───┴────────────────┐
    tier 2   │ Endpoint         │     │ Switch Upstream    │
             │ no bridge class: │     │ Port: bound        │
             │ no ID match      │     └───┬────────────────┘
             └──────────────────┘         │
                                      ┌───┴────────────────┐
    tier 3                            │ Switch Downstream  │
                                      │ Port: bound        │
                                      └───┬────────────────┘
                                          │
                                      ┌───┴────────────────┐
    tier 4                            │ PCIe-to-PCI        │  class matches, Device/Port Type 0x7:
                                      │ bridge             │  pcie_portdrv_probe() returns -ENODEV
                                      └───┬────────────────┘
                                          │
    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   conventional PCI below this line
                                      ┌───┴────────────────┐
    tier 5                            │ PCI-to-PCI         │  class matches, no PCIe capability:
                                      │ bridge             │  pci_is_pcie() is false, -ENODEV
                                      └────────────────────┘
```

A port is bound when its class matches and its type is one of the four, whatever its position in the hierarchy. The functions below a PCIe-to-PCI bridge get no port driver, since the bridge itself fails the type check and conventional PCI bridges have no PCIe capability.

### Port type, hardware and permission decide each service bit

A port should get a service when its Device/Port Type can host the service, when its hardware implements it and when the platform lets the kernel drive it. [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) applies those three tests to each service and returns the service mask, one PCIE_PORT_SERVICE_* bit per granted service, which the registration loop then turns into instances. The figure shows the objects that hold its inputs.

```text
    What the service mask of one port is computed from
    ──────────────────────────────────────────────────

    the port's struct pci_dev        its host bridge's                kernel-wide switches
    ┌───────────────────────────┐    struct pci_host_bridge           ┌─────────────────────────────┐
    │ Device/Port Type          │    ┌────────────────────────┐       │ pcie_ports_native           │
    │ is_pciehp                 │    │ native_pcie_hotplug    │       │ pcie_ports_dpc_native       │
    │ aer_cap                   │    │ native_aer             │       │ pci_aer_available(): no     │
    │ DPC extended capability   │    │ native_pme             │       │ pci=noaer and MSI enabled   │
    │ LBNC, Link Capabilities   │    └────────────┬───────────┘       └──────────────┬──────────────┘
    │ supported_speeds          │                 │                                  │
    └─────────────┬─────────────┘                 │                                  │
                  │                               │                                  │
                  └───────────────────────────────┼──────────────────────────────────┘
                                                  │ get_port_device_capability()
                                                  ▼
                      ┌────────────────────────────────────────────────────────┐
                      │ services: bit 0 PME, bit 1 AER, bit 2 HP,              │
                      │           bit 3 DPC, bit 4 BWCTRL                      │
                      └────────────────────────────────────────────────────────┘

    the hotplug, AER and PME bits each need their native_* bit or pcie_ports_native; native_dpc is no input:
    the DPC bit needs the AER bit already computed, or pcie_ports_dpc_native
```

The port's own fields record what the hardware offers and the native bits of its host bridge what firmware granted through _OSC. The kernel-wide switches record what the command line and the AER code decided. The table sets out the tests of each predicate, with the AER predicate compiled only under [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28).

| Service bit | Port types | Hardware test | Permission test |
|---|---|---|---|
| [`PCIE_PORT_SERVICE_HP`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L20) | Root Port, Downstream Port | [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) set | [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654) |
| [`PCIE_PORT_SERVICE_AER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18) | Root Port, RCEC | [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370) nonzero and [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) true | [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653) |
| [`PCIE_PORT_SERVICE_PME`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L16) | Root Port, RCEC | none | [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) |
| [`PCIE_PORT_SERVICE_DPC`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L22) | any type the probe accepts | a DPC Extended Capability, [`PCI_EXT_CAP_ID_DPC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L753), and [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) true | [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620) or [`PCIE_PORT_SERVICE_AER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L18) already granted |
| [`PCIE_PORT_SERVICE_BWCTRL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L24) | Root Port, Downstream Port | [`PCI_EXP_LNKCAP_LBNC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L562) set and more than one bit of [`supported_speeds`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L582) | none |

The function is read in three pieces, one per pair of predicates, and the outline gives the lines of each.

| Piece | Lines | Stage |
|---|---|---|
| ❶ | portdrv.c:218-238 | the host bridge lookup and the hotplug predicate |
| ❷ | portdrv.c:239-260 | the AER and PME predicates |
| ❸ | portdrv.c:261-282 | the DPC and bandwidth predicates and the return |

❶ The first piece of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) finds the port's host bridge and decides the hotplug bit; read it for the three conditions and for the Slot Control branch inside.

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

[`pci_find_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L20) returns the [`struct pci_host_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L628) above the port, whose native bits record what firmware granted. The hotplug bit needs [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484), a Root Port or a Downstream Port, and [`pcie_ports_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L614) or [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654). In a build without [`CONFIG_HOTPLUG_PCI_PCIE`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L16) the branch also clears the two hotplug interrupt enables of Slot Control, since no hotplug driver would handle them. With the option set, as here, `IS_ENABLED()` makes the test false and the write never runs.

❷ The second piece of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) decides the AER bit under [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) and the PME bit; read it for the port types and for the side effect of the PME branch.

```c
/* drivers/pci/pcie/portdrv.c:239 */
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

The AER bit needs a Root Port or an RCEC, an AER capability offset in [`aer_cap`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L370), a true [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) and a permission, and without [`CONFIG_PCIEAER`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L28) the block is compiled out and no port gets AER. The PME bit needs only the port type and a permission. Its branch clears the port's PME Interrupt Enable through [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54), so an enable that firmware left set stays off until the PME service driver binds.

❸ The third piece of [`get_port_device_capability()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L218) decides the DPC and bandwidth bits and returns the mask; read it for the DPC predicate's use of the AER bit computed in the second piece.

```c
/* drivers/pci/pcie/portdrv.c:261 */
	/*
	 * With dpc-native, allow Linux to use DPC even if it doesn't have
	 * permission to use AER.
	 */
	if (pci_find_ext_capability(dev, PCI_EXT_CAP_ID_DPC) &&
	    pci_aer_available() &&
	    (pcie_ports_dpc_native || (services & PCIE_PORT_SERVICE_AER)))
		services |= PCIE_PORT_SERVICE_DPC;

	/* Enable bandwidth control if more than one speed is supported. */
	if (pci_pcie_type(dev) == PCI_EXP_TYPE_DOWNSTREAM ||
	    pci_pcie_type(dev) == PCI_EXP_TYPE_ROOT_PORT) {
		u32 linkcap;

		pcie_capability_read_dword(dev, PCI_EXP_LNKCAP, &linkcap);
		if (linkcap & PCI_EXP_LNKCAP_LBNC &&
		    hweight8(dev->supported_speeds) > 1)
			services |= PCIE_PORT_SERVICE_BWCTRL;
	}

	return services;
}
```

The DPC bit needs the DPC Extended Capability, a true [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138), and [`pcie_ports_dpc_native`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L620) or the AER bit granted above, so DPC follows AER ownership and the host bridge's [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658) is no input of this predicate. The bandwidth bit needs a Root Port or a Downstream Port whose Link Capabilities report bandwidth notification and whose [`supported_speeds`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L582) holds more than one speed, as the comment says. The mask returns to the caller with one bit per granted service, and 0 when a port gets none.

### Enumeration caches the hardware facts the predicates test

Each hardware test of the predicates reads a value that enumeration stored in the port's [`struct pci_dev`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L352), or a bit a helper reads from the host bridge. The writers of those values decide what a port can get. The host bridge comes first, through [`pci_find_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L20) and the static helper before it; read both.

```c
/* drivers/pci/host-bridge.c:12 */
static struct pci_bus *find_pci_root_bus(struct pci_bus *bus)
{
	while (bus->parent)
		bus = bus->parent;

	return bus;
}

struct pci_host_bridge *pci_find_host_bridge(struct pci_bus *bus)
{
	struct pci_bus *root_bus = find_pci_root_bus(bus);

	return to_pci_host_bridge(root_bus->bridge);
}
```

[`find_pci_root_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L12) follows [`parent`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L704) up to the root bus, and [`pci_find_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L20) converts that bus's [`bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L730) device to its host bridge, so every port under one host bridge reads the same native bits. Hotplug capability comes from Slot Capabilities, and [`set_pcie_hotplug_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L1688) copies it; read it.

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

The function sets [`is_hotplug_bridge`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L483) and [`is_pciehp`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L484) together when [`PCI_EXP_SLTCAP_HPC`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L604) is set in Slot Capabilities. Setup calls it for every function with a bridge header and records the supported speeds before that; read [`pci_setup_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L2016) at those two stages.

```c
/* drivers/pci/probe.c:2016 */
int pci_setup_device(struct pci_dev *dev)
{
	... /* 57 lines, to :2075 */
	set_pcie_untrusted(dev);

	if (pci_is_pcie(dev))
		dev->supported_speeds = pcie_get_supported_speeds(dev);
	... /* 81 lines, to :2160 */
	case PCI_HEADER_TYPE_BRIDGE:		    /* bridge header */
		/*
		 * The PCI-to-PCI bridge spec requires that subtractive
		 * decoding (i.e. transparent) bridge must have programming
		 * interface code of 0x01.
		 */
		pci_read_irq(dev);
		dev->transparent = ((dev->class & 0xff) == 1);
		pci_read_bases(dev, 2, PCI_ROM_ADDRESS1);
		pci_read_bridge_windows(dev);
		set_pcie_hotplug_bridge(dev);
```

For a PCIe function, setup stores the result of [`pcie_get_supported_speeds()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6020) in [`supported_speeds`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L582), and the bridge branch of the header switch calls [`set_pcie_hotplug_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L1688) after it reads the bridge windows. Read [`pcie_get_supported_speeds()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6020) for the vector it builds.

```c
/* drivers/pci/pci.c:6020 */
u8 pcie_get_supported_speeds(struct pci_dev *dev)
{
	u32 lnkcap2, lnkcap;
	u8 speeds;

	/*
	 * Speeds retain the reserved 0 at LSB before PCIe Supported Link
	 * Speeds Vector to allow using SLS Vector bit defines directly.
	 */
	pcie_capability_read_dword(dev, PCI_EXP_LNKCAP2, &lnkcap2);
	speeds = lnkcap2 & PCI_EXP_LNKCAP2_SLS;

	/* Ignore speeds higher than Max Link Speed */
	pcie_capability_read_dword(dev, PCI_EXP_LNKCAP, &lnkcap);
	speeds &= GENMASK(lnkcap & PCI_EXP_LNKCAP_SLS, 0);

	/* PCIe r3.0-compliant */
	if (speeds)
		return speeds;

	/* Synthesize from the Max Link Speed field */
	if ((lnkcap & PCI_EXP_LNKCAP_SLS) == PCI_EXP_LNKCAP_SLS_5_0GB)
		speeds = PCI_EXP_LNKCAP2_SLS_5_0GB | PCI_EXP_LNKCAP2_SLS_2_5GB;
	else if ((lnkcap & PCI_EXP_LNKCAP_SLS) == PCI_EXP_LNKCAP_SLS_2_5GB)
		speeds = PCI_EXP_LNKCAP2_SLS_2_5GB;

	return speeds;
}
```

The vector is the Supported Link Speeds Vector of Link Capabilities 2 cut at Max Link Speed, or for a port without that vector a set built from Max Link Speed. Either way bit 0 stays clear, so `hweight8()` of the vector counts the speeds, and a port limited to one speed gets no bandwidth service. The AER and DPC tests depend on [`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138), which reads a flag of aer.c; read it with [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133), the flag's setter.

```c
/* drivers/pci/pcie/aer.c:130 */
static bool pcie_aer_disable;
static pci_ers_result_t aer_root_reset(struct pci_dev *dev);

void pci_no_aer(void)
{
	pcie_aer_disable = true;
}

bool pci_aer_available(void)
{
	return !pcie_aer_disable && pci_msi_enabled();
}
```

[`pci_aer_available()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L138) is true unless [`pci_no_aer()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L133) has run, and only while [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) reports MSI on. The PCI command-line parser calls the setter for pci=noaer, next to the handling of pci=nomsi; read the stage of [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743).

```c
/* drivers/pci/pci.c:6743 */
static int __init pci_setup(char *str)
{
	while (str) {
		char *k = strchr(str, ',');
		if (k)
			*k++ = 0;
		if (*str && (str = pcibios_setup(str)) && *str) {
			if (!pci_setup_cardbus(str)) {
				/* Function handled the parameters */
			} else if (!strcmp(str, "nomsi")) {
				pci_no_msi();
			} else if (!strncmp(str, "noats", 5)) {
				pr_info("PCIe: ATS is disabled\n");
				pcie_ats_disabled = true;
			} else if (!strcmp(str, "noaer")) {
				pci_no_aer();
```

pci=noaer takes the AER and the DPC bits away from every port, and pci=nomsi does the same through the MSI test. Read [`pci_msi_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L407) for what else switches MSI off.

```c
/* drivers/pci/msi/api.c:401 */
/**
 * pci_msi_enabled() - Are MSI(-X) interrupts enabled system-wide?
 *
 * Return: true if MSI has not been globally disabled through ACPI FADT,
 * PCI bridge quirks, or the "pci=nomsi" kernel command-line option.
 */
bool pci_msi_enabled(void)
{
	return pci_msi_enable;
}
EXPORT_SYMBOL(pci_msi_enabled);
```

According to its kerneldoc, MSI is off system-wide after the ACPI FADT, a PCI bridge quirk or pci=nomsi disabled it. The PME branch of the predicates calls [`pcie_pme_interrupt_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L54); read it for the register bit.

```c
/* drivers/pci/pcie/pme.c:54 */
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

Called with `false`, the helper clears [`PCI_EXP_RTCTL_PMEIE`](https://elixir.bootlin.com/linux/v7.2/source/include/uapi/linux/pci_regs.h#L647) in Root Control, and the PME service driver calls it with `true` once its interrupt handler is installed.

### The host bridge's native bits record the _OSC grant

The native bits decide whether the kernel may drive a service at all, and two writers set them, the generic host bridge setup and the ACPI host bridge code. [`pci_init_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/probe.c#L659) sets them first; read the stage.

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
	bridge->native_ltr = 1;
	bridge->native_dpc = 1;
```

Every host bridge starts with its native bits set, the comment saying the kernel assumes it can manage the features until firmware says otherwise. On x86 with ACPI, [`acpi_pci_root_create()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L995) clears each bit whose control the _OSC negotiation did not obtain; read the stage after the root bus is created.

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
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_PME_CONTROL))
		host_bridge->native_pme = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_LTR_CONTROL))
		host_bridge->native_ltr = 0;
	if (!(root->osc_control_set & OSC_PCI_EXPRESS_DPC_CONTROL))
		host_bridge->native_dpc = 0;
```

[`osc_control_set`](https://elixir.bootlin.com/linux/v7.2/source/include/acpi/acpi_bus.h#L739) holds the controls the negotiation obtained, and each missing control clears its bit, among them [`native_pcie_hotplug`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L654), [`native_aer`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L653), [`native_pme`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L656) and [`native_dpc`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L658). The negotiation itself is outside this page, and the predicates read its result through [`pci_find_host_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/host-bridge.c#L20) for every port below the root.

### Registration enables the port and creates one instance per bit

With the mask known, the port needs interrupt vectors for its services and an instance for each set bit. [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) does both, in an order that lets a port without usable interrupts keep its hotplug service, and it is read in three pieces.

| Piece | Lines | Stage |
|---|---|---|
| Ⓐ | portdrv.c:331-345 | enabling the port and computing the mask |
| Ⓑ | portdrv.c:346-359 | bus mastering and the interrupt vectors |
| Ⓒ | portdrv.c:360-381 | the loop over the bits and the unwinding |

Ⓐ The first piece of [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) enables the port and asks for the mask; read it for the early return.

```c
/* drivers/pci/pcie/portdrv.c:324 */
/**
 * pcie_port_device_register - register PCI Express port
 * @dev: PCI Express port to register
 *
 * Allocate the port extension structure and register services associated with
 * the port.
 */
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

```

[`pci_enable_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2120) must succeed first, and its error fails the probe. An empty mask returns 0 with the port enabled and no instance. A Switch Upstream Port ends there, since only the DPC predicate can grant it a bit, and only when it has a DPC capability.

Ⓑ The second piece of [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) turns on bus mastering and sets up the vectors; read it for what happens when no interrupt can be had.

```c
/* drivers/pci/pcie/portdrv.c:346 */
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

[`pci_set_master()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L4172) enables bus mastering on the port before its interrupts are set up. When [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177) fails, the mask shrinks to the hotplug bit, because the comment says such a driver may poll, and a mask left empty disables the port and fails the probe. The vectors come from [`pcie_init_service_irqs()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L177), which fills the caller's array, one entry per service bit; read it for the starting value and the INTx fallback.

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

Every entry starts at -1. When the mask holds PME and [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) is true, or when the MSI-X and MSI setup fails, one INTx vector serves every service and every entry gets it. With no INTx either, the function returns -ENODEV. Otherwise [`pcie_port_enable_irq_vec()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L113) has filled the entries; read its last stage, where it does.

```c
/* drivers/pci/pcie/portdrv.c:113 */
static int pcie_port_enable_irq_vec(struct pci_dev *dev, int *irqs, int mask)
{
	int nr_entries, nvec, pcie_irq;
	... /* 35 lines, to :151 */
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

The entries are indexed by each service's `_SHIFT` value, the bit number of its service bit. PME, hotplug and bandwidth notification share the vector of the PME Interrupt Message Number whenever the mask holds any of them. AER and DPC get the vectors of their own message numbers when the mask holds them. How the message numbers are read and the vectors counted is the interrupt setup's own mechanism, and this page leaves it out.

Ⓒ The third piece of [`pcie_port_device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L331) creates the instances; read it for the index that ties a bit to its vector and for the count that decides success.

```c
/* drivers/pci/pcie/portdrv.c:360 */

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

The loop visits bits 0 to [`PCIE_PORT_DEVICE_MAXSERVICES`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L26) minus 1, skips each clear bit and calls [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) with the bit and `irqs[i]`, the vector of the same index. `nr_service`, a local of the function, counts the instances registered. With none registered the function frees the vectors, disables the port and returns -ENODEV, the value `status` received before the loop. One instance is enough for success, and an instance that failed is left out. The figure follows the loop for a Root Port granted PME, AER and hotplug, with the vectors the MSI path stores.

```text
    The registration loop leaves an instance at each set bit of the mask
    ────────────────────────────────────────────────────────────────────

    bit i                0          1          2          3          4
                    ┌──────────┬──────────┬──────────┬──────────┬──────────┐
    capabilities    │ PME   ██ │ AER   ██ │ HP    ██ │ DPC      │ BWCTRL   │
                    └──────────┴──────────┴──────────┴──────────┴──────────┘
                    ┌──────────┬──────────┬──────────┬──────────┬──────────┐
    irqs[i]         │ vector a │ vector b │ vector a │ -1       │ vector a │
                    └──────────┴──────────┴──────────┴──────────┴──────────┘

    cursor i             ▼          ▼          ▼       skipped    skipped
                     ┌────────┐ ┌────────┐ ┌────────┐
    instance         │ pcie001│ │ pcie002│ │ pcie004│
                     └────────┘ └────────┘ └────────┘

    nr_service           1          2          3       loop ends: 3 instances, return 0

    a Root Port whose mask holds PME, AER and HP, with MSI or MSI-X vectors: vector a is the one PME, HP and
    BWCTRL share, vector b the AER vector; DPC keeps the -1 that pcie_init_service_irqs() stores first
```

Each set bit leaves one registered instance whose [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) is the entry of the same index, and a clear bit leaves nothing, even where its entry holds a shared vector.

### Each instance is allocated, named, parented and registered

An instance must be a complete device before the driver core sees it, because registration offers it to the service drivers at once. [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) fills it and registers it, and its name carries the port type and the service bit through [`get_descriptor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L32); read the macro first.

```c
/* drivers/pci/pcie/portdrv.c:32 */
#define get_descriptor_id(type, service) (((type - 4) << 8) | service)
```

[`get_descriptor_id()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L32) subtracts 4 from the Device/Port Type, so a Root Port, type 4, contributes 0, and shifts the difference above the service bit. Read [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) whole for the order of its writes, which the strip at the start of DETAILS marks ① to ⑦.

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

The function allocates the instance zeroed and fills [`port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L61), [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L62). It puts the embedded device on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) with [`release_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L47) as its release callback, names it, parents it under the port's device and marks it for asynchronous suspend. After [`device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3851) it tells the PM core that the instance has no runtime PM callbacks of its own, and a failed registration ends in [`put_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3876). The figure lays out the twelve bits behind the name's last three digits.

```text
    The descriptor that ends a service instance's name
    ──────────────────────────────────────────────────

    bit    1 1
           1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    id    │ type-4│  service bit  │
          │ (11:8)│     (7:0)     │
          └───────┴───────────────┘

    type-4  = pci_pcie_type(port) - 4 in get_descriptor_id(): 0 Root Port, 1 Upstream Port,
              2 Downstream Port, 6 RCEC
    service = the PCIE_PORT_SERVICE_* bit: 0x01 PME, 0x02 AER, 0x04 HP, 0x08 DPC, 0x10 BWCTRL
    name    = pci_name(port), ":pcie", then the 12 bits as three hex digits by "%03x":
              0000:00:1c.0:pcie002 is a Root Port's AER, 0000:02:01.0:pcie204 a Downstream Port's HP
```

A Root Port's instances are named pcie001 to pcie010, a Downstream Port's begin with pcie2 and an RCEC's with pcie6, so the name alone tells the service and the port type. [`device_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3851) is two steps; read it with the warning in its kerneldoc.

```c
/* drivers/base/core.c:3847 */
 * NOTE: _Never_ directly free @dev after calling this function, even
 * if it returned an error! Always use put_device() to give up the
 * reference initialized in this function instead.
 */
int device_register(struct device *dev)
{
	device_initialize(dev);
	return device_add(dev);
}
EXPORT_SYMBOL_GPL(device_register);
```

[`device_initialize()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3227) creates the reference that the comment tells callers to give up with [`put_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3876), which is why the failure path of [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) frees the instance through [`put_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3876). [`device_add()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3639) makes the instance visible; read it at the stage that offers the new device to the drivers of its bus.

```c
/* drivers/base/core.c:3639 */
int device_add(struct device *dev)
{
	 ... /* 118 lines, to :3759 */
	 * bus_add_device() then it's possible that probe could have been
	 * attempted in a different thread via userspace loading a driver
	 * matching the device. "ready_to_probe" being unset would have
	 * blocked those attempts. Now that all of the above initialization has
	 * happened, unblock probe. If probe happens through another thread
	 * after this point but before bus_probe_device() runs then it's fine.
	 * bus_probe_device() -> device_initial_probe() -> __device_attach()
	 * will notice (under device_lock) that the device is already bound.
	 */
	device_lock(dev);
	dev_set_ready_to_probe(dev);
	device_unlock(dev);

	bus_probe_device(dev);
```

[`bus_probe_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/bus.c#L612) starts the matching of the instance against the service drivers of [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575), the comment naming the chain down to [`__device_attach()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L1068), so an instance whose service driver is registered can be bound before [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) returns. The two PM calls of [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) set flags of the embedded device; read [`device_enable_async_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L1019) first.

```c
/* include/linux/device.h:1019 */
static inline void device_enable_async_suspend(struct device *dev)
{
	if (!dev->power.is_prepared)
		dev->power.async_suspend = true;
}
```

[`device_enable_async_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L1019) sets [`async_suspend`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L669) unless a system transition is already preparing the device, which marks the instance for asynchronous suspend and resume by the PM core. [`pm_runtime_no_callbacks()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1719) marks the runtime side; read it with its kerneldoc.

```c
/* drivers/base/power/runtime.c:1712 */
 * pm_runtime_no_callbacks - Ignore runtime PM callbacks for a device.
 * @dev: Device to handle.
 *
 * Set the power.no_callbacks flag, which tells the PM core that this
 * device is power-managed through its parent and has no runtime PM
 * callbacks of its own.  The runtime sysfs attributes will be removed.
 */
void pm_runtime_no_callbacks(struct device *dev)
{
	spin_lock_irq(&dev->power.lock);
	dev->power.no_callbacks = 1;
	spin_unlock_irq(&dev->power.lock);
	if (device_is_registered(dev))
		rpm_sysfs_remove(dev);
}
EXPORT_SYMBOL_GPL(pm_runtime_no_callbacks);
```

With [`no_callbacks`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L711) set, the kerneldoc says the device is power-managed through its parent and loses its runtime sysfs attributes, so an instance's power directory shows no runtime state. The instance is now registered, named and parented, and bound when its service driver is on the bus.

### The bus probe hands the instance to its service driver

Once the match has paired an instance with a service driver, the driver core binds them through the bus's probe callback, which on pci_express adapts the generic device to the service driver's callback. The driver core prefers a bus probe over the driver's own; read [`call_driver_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L621).

```c
/* drivers/base/dd.c:621 */
static int call_driver_probe(struct device *dev, const struct device_driver *drv)
{
	int ret = 0;

	if (dev->bus->probe)
		ret = dev->bus->probe(dev);
	else if (drv->probe)
		ret = drv->probe(dev);

	switch (ret) {
	case 0:
		break;
	case -EPROBE_DEFER:
		/* Driver requested deferred probing */
		dev_dbg(dev, "Driver %s requests probe deferral\n", drv->name);
		break;
	case -ENODEV:
	case -ENXIO:
		dev_dbg(dev, "probe with driver %s rejects match %d\n",
			drv->name, ret);
		break;
	default:
		/* driver matched but the probe failed */
		dev_err(dev, "probe with driver %s failed with error %d\n",
			drv->name, ret);
		break;
	}

	return ret;
}
```

A bus with a probe callback gets the call, and the returned error decides the message. -ENODEV and -ENXIO are a quiet refusal at the debug level, -EPROBE_DEFER a deferral, and any other error an error line naming the driver. [`pcie_port_bus_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534) is that callback for pci_express; read it.

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

The callback converts the device and its driver back to the instance and the service driver, returns -ENODEV when the driver has no probe and calls [`probe`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L80) with the instance. On success it takes a reference on the instance with [`get_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3866), held while the driver stays bound and dropped by [`pcie_port_bus_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L562). The PME service driver shows what a service probe does with the instance; read [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326).

```c
/* drivers/pci/pcie/pme.c:326 */
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

The probe refuses ports other than Root Ports and RCECs, allocates its data and stores it with [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68). It requests the instance's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) as a shared interrupt with the instance as the cookie, and it enables the PME interrupt that the predicate disabled once the handler is in place. The two accessors it relies on are in portdrv.h; read them.

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

[`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) writes [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) and [`get_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73) reads it, which is how a service's callbacks find their state from the instance alone. At v7.2 [`set_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L68) has three callers, [`pcie_pme_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L326), [`aer_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1607) at [`aer.c:1630`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer.c#L1630) and [`pciehp_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L185) at [`pciehp_core.c:206`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L206), so the DPC and bandwidth probes store no data in the instance. The figure lays the binding of one instance across the three parties that take part.

```text
    Binding one service instance: driver core, bus callbacks, service driver
    ────────────────────────────────────────────────────────────────────────

    time ↓
    driver core                    ╎ pci_express bus callbacks          ╎ service driver
    ───────────────────────────────┼────────────────────────────────────┼─────────────────────────────────
    an instance added, or a        ╎                                    ╎
    service driver registered ───▶ ╎ match: service bits equal and      ╎
                                   ╎ port type accepted, returns 1      ╎
    pairing found: probe ────────▶ ╎ bus probe calls driver->probe ───▶ ╎ allocates its data, stores it
                                   ╎                                    ╎ in priv_data, requests irq
                                   ╎ ◀── 0 ──────────────────────────── ╎ instance in use
                                   ╎ get_device(): one more reference   ╎
                                   ╎ for the bound driver               ╎
    ◀── 0 ──────────────────────── ╎                                    ╎
    instance listed under its      ╎                                    ╎
    driver: bound                  ╎                                    ╎

    a probe that fails returns its error through the bus probe; no reference is taken and the instance stays
    registered without a driver
```

A bound instance holds two references, its registration's and the one the bus probe took, and its driver's data is in [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63).

So far, a port has been probed and its mask computed from its type, its hardware and its host bridge's permissions. Each set bit has become a registered instance bound to the service driver of the same bit. The next subsections search the instances of a port, once for one service and once for all of them.

### A lookup finds the bound instance of one service

Code outside the framework sometimes holds a port and needs the instance of one of its services, for example to raise that service's interrupt. [`pcie_port_find_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L483) answers by searching the port's children, and it keeps the state of the search in [`struct portdrv_service_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L34); read the record first.

```c
/* drivers/pci/pcie/portdrv.c:34 */
struct portdrv_service_data {
	struct pcie_port_service_driver *drv;
	struct device *dev;
	u32 service;
};
```

[`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L37) holds the service bit asked for, [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L36) the instance found and [`drv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L35) its service driver. The record is a local of the lookup and reaches each child test as an opaque pointer. Read [`pcie_port_find_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L483) for how it fills the record and what it returns.

```c
/* drivers/pci/pcie/portdrv.c:476 */
/**
 * pcie_port_find_device - find the struct device
 * @dev: PCI Express port the service is associated with
 * @service: For the service to find
 *
 * Find the struct device associated with given service on a pci_dev
 */
struct device *pcie_port_find_device(struct pci_dev *dev,
				      u32 service)
{
	struct device *device;
	struct portdrv_service_data pdrvs;

	pdrvs.dev = NULL;
	pdrvs.service = service;
	device_for_each_child(&dev->dev, &pdrvs, find_service_iter);

	device = pdrvs.dev;
	return device;
}
EXPORT_SYMBOL_GPL(pcie_port_find_device);
```

The lookup sets [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L36) to NULL and [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L37) to the requested bit, lets [`device_for_each_child()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4089) call [`find_service_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L455) on each child of the port, and returns whatever [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L36) holds then. It takes no reference on the instance it returns, and it is exported to GPL modules. Read [`find_service_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L455) for the test a child must pass.

```c
/* drivers/pci/pcie/portdrv.c:455 */
static int find_service_iter(struct device *device, void *data)
{
	struct pcie_port_service_driver *service_driver;
	struct portdrv_service_data *pdrvs;
	u32 service;

	pdrvs = (struct portdrv_service_data *) data;
	service = pdrvs->service;

	if (device->bus == &pcie_port_bus_type && device->driver) {
		service_driver = to_service_driver(device->driver);
		if (service_driver->service == service) {
			pdrvs->drv = service_driver;
			pdrvs->dev = device;
			return 1;
		}
	}

	return 0;
}
```

A child passes when it is on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575), has a driver bound and that driver's [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L91) is the bit asked for, so an instance whose service driver has not bound is not found. The test then records the driver and the child and returns 1, which ends the iteration at the first match, as [`device_for_each_child()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4089) shows; read it.

```c
/* drivers/base/core.c:4077 */
/**
 * device_for_each_child - device child iterator.
 * @parent: parent struct device.
 * @data: data for the callback.
 * @fn: function to be called for each device.
 *
 * Iterate over @parent's child devices, and call @fn for each,
 * passing it @data.
 *
 * We check the return of @fn each time. If it returns anything
 * other than 0, we break out and return that value.
 */
int device_for_each_child(struct device *parent, void *data,
			  device_iter_t fn)
{
	struct klist_iter i;
	struct device *child;
	int error = 0;

	if (!parent || !parent->p)
		return 0;

	klist_iter_init(&parent->p->klist_children, &i);
	while (!error && (child = next_device(&i)))
		error = fn(child, data);
	klist_iter_exit(&i);
	return error;
}
EXPORT_SYMBOL_GPL(device_for_each_child);
```

The iterator stops at the first callback that returns anything but 0 and returns that value, which serves the lookup's early exit and, later, the fan-outs' error reporting. The strip shows the writes to the record during one lookup.

```text
    One struct portdrv_service_data during a lookup, and the writes to its fields
    ─────────────────────────────────────────────────────────────────────────────
    fields: service, dev, drv

    time ───────────────────────────────────────────────────────────────────────────────▶
    event            init          child, no match       matching child      return
                     ▼             ▼                     ▼                   ▼
                     ┌──────────────────────────────────────────────────────────────────┐
    service          │➋ the service bit asked for                                       │
                     └──────────────────────────────────────────────────────────────────┘
                     ┌───────────────────────────────────┬──────────────────────────────┐
    dev              │➊ NULL                             │➍ that child                  │
                     └───────────────────────────────────┴──────────────────────────────┘
                     ┌───────────────────────────────────┬──────────────────────────────┐
    drv              │ never initialized                 │➌ its driver                  │
                     └───────────────────────────────────┴──────────────────────────────┘

    ➊ pcie_port_find_device portdrv.c:489  sets dev to NULL before the search starts
    ➋ pcie_port_find_device :490  stores the service bit the caller asked for
    ➌ find_service_iter :467  records the service driver of the matching child
    ➍ find_service_iter :468  records the matching child itself, ending the search
```

➊ [`pcie_port_find_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L483) sets [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L36) to NULL before the search. ➋ `pcie_port_find_device()` stores the requested bit in [`service`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L37). ➌ [`find_service_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L455) records the matching child's service driver in [`drv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L35). ➍ `find_service_iter()` records the matching child itself in [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L36), which ends the search.

At v7.2 the record is defined and used in portdrv.c alone, so these four lines are its only writers. [`drv`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L35) stays uninitialized when nothing matches, and nothing reads it, since the lookup returns [`dev`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L36) alone. The one caller of the lookup at v7.2 is the AER error injector, built with [`CONFIG_PCIEAER_INJECT`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/Kconfig#L37), which this page's build leaves unset; read the stage of [`aer_inject()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/aer_inject.c#L319) where it finds the Root Port's AER instance.

```c
/* drivers/pci/pcie/aer_inject.c:319 */
static int aer_inject(struct aer_error_inj *einj)
{
	struct aer_error *err, *rperr;
	struct aer_error *err_alloc = NULL, *rperr_alloc = NULL;
	struct pci_dev *dev, *rpdev;
	struct pcie_device *edev;
	struct device *device;
	... /* 138 lines, to :464 */
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

The injector looks the AER instance up from the Root Port, converts it with [`to_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) and refuses it while its [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) is NULL. It then raises the instance's [`irq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L60) with [`irq_inject_interrupt()`](https://elixir.bootlin.com/linux/v7.2/source/kernel/irq/resend.c#L171), so the AER service handles the injected error as if the port had signaled it. A Root Port whose AER bit was refused has no instance to find, and the injector reports "AER device not found".

### One iterator calls a chosen callback of every bound service

The port driver has to pass one event, a suspend or a slot reset, to every service of the port, and the services fill different subsets of the callback slots. [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) does that for any slot of [`struct pcie_port_service_driver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L78), given the slot's byte offset; read it with the callback type before it.

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

The iterator receives each child of the port from [`device_for_each_child()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4089) and the offset through `data`, its second parameter. It skips children that are not on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) or have no driver, reads the function pointer at the offset into the bound service driver, and calls it with the instance when it is not NULL. A nonzero return ends the iteration and becomes the caller's result. The figure shows the slots an offset can select on x86-64, where each pointer takes 8 bytes.

```text
    The offset a fan-out passes selects one callback slot of each service driver
    ────────────────────────────────────────────────────────────────────────────

    offset  member of struct pcie_port_service_driver (x86-64)   read by
           ┌──────┬─────────────────────┐
           │ 0x00 │ name                │
           │ 0x08 │ probe               │◀── the bus probe, directly
           │ 0x10 │ remove              │◀── the bus remove, directly
           │ 0x18 │ suspend             │◀── «1» through the iterator
           │ 0x20 │ resume_noirq        │◀── «2» through the iterator
           │ 0x28 │ resume              │◀── «3» through the iterator
           │ 0x30 │ runtime_suspend     │◀── «4» through the iterator
           │ 0x38 │ runtime_resume      │◀── «5» through the iterator
           │ 0x40 │ slot_reset          │◀── «6» through the iterator
           │ 0x48 │ port_type           │◀── the bus match
           │ 0x4c │ service             │◀── the bus match and the lookup
           │ 0x50 │ driver              │◀── dev->driver of a bound instance points here
           └──────┴─────────────────────┘

    the iterator, for each child of the port that is on pcie_port_bus_type and has a driver bound:
    to_service_driver(dev->driver) steps back 0x50 to offset 0x00, the pointer at the passed offset is
    the callback, and a NULL slot is skipped

    «1» pcie_port_device_suspend portdrv.c:407  passes the offset of the suspend slot
    «2» pcie_port_device_resume_noirq :413  passes the offset of the resume_noirq slot
    «3» pcie_port_device_resume :423  passes the offset of the resume slot
    «4» pcie_port_device_runtime_suspend :433  passes the offset of the runtime_suspend slot
    «5» pcie_port_device_runtime_resume :443  passes the offset of the runtime_resume slot
    «6» pcie_portdrv_slot_reset :760  passes the offset of the slot_reset slot
```

«1» [`pcie_port_device_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L405) passes the offset of [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L82). «2» [`pcie_port_device_resume_noirq()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L411) passes the offset of [`resume_noirq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L83). «3» [`pcie_port_device_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L421) passes the offset of [`resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L84). «4» [`pcie_port_device_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L431) passes the offset of [`runtime_suspend`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L85). «5» [`pcie_port_device_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L441) passes the offset of [`runtime_resume`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L86). «6» [`pcie_portdrv_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758) passes the offset of [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88).

Those six are the only callers of the iterator at v7.2, and the offsets of [`probe`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L80) and [`remove`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L81) never reach it, since the bus callbacks call those two slots directly. Because a nonzero return stops the iteration, a service whose callback fails keeps the services after it in the port's child list from seeing the event.

### System sleep reaches the services through the port's callbacks

During system sleep the PM core calls each device's callbacks, and an instance has none of its own, since neither [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) nor any service driver's embedded driver carries a [`struct dev_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L288). The services are reached through the port's callbacks instead, [`pcie_portdrv_pm_ops`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L656), which the port driver installs through [`PCIE_PORTDRV_PM_OPS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L670); read the table.

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

Suspend, freeze and poweroff share one fan-out, resume, thaw and restore a second, and resume_noirq and restore_noirq a third. The two runtime callbacks and the idle callback belong to the next subsection. The table is compiled with [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) only, and the macro the driver uses follows it; read the two definitions.

```c
/* drivers/pci/pcie/portdrv.c:670 */
#define PCIE_PORTDRV_PM_OPS	(&pcie_portdrv_pm_ops)

#else /* !PM */

#define PCIE_PORTDRV_PM_OPS	NULL
#endif /* !PM */
```

With [`CONFIG_PM`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L217) set, as here, [`PCIE_PORTDRV_PM_OPS`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L670) points at the table, and without it the port driver installs no PM callbacks at all. The three system-sleep fan-outs are one statement each; read them.

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

Each passes the offset of its slot to [`pcie_port_device_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L385) through [`device_for_each_child()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4089) on `dev`, the port's embedded device that each receives as its parameter. The figure maps the members of the table onto the slots they reach and names the services that fill each slot.

```text
    Each callback of the port's dev_pm_ops reaches one slot of every service driver
    ───────────────────────────────────────────────────────────────────────────────

    pcie_portdrv_pm_ops member                      slot of struct pcie_port_service_driver   filled by
    ──────────────────────────                      ───────────────────────────────────────   ─────────
                                                    ┌──────────────────┐
    .suspend         ──┐                            │                  │
    .freeze          ──┼──────────────────────────▶ │ suspend          │   PME, AER, DPC, BWCTRL, HP
    .poweroff        ──┘                            │                  │
                                                    ├──────────────────┤
    .resume_noirq    ──┐                            │                  │
    .restore_noirq   ──┴──────────────────────────▶ │ resume_noirq     │   HP
                                                    ├──────────────────┤
    .resume          ──┐                            │                  │
    .thaw            ──┼──────────────────────────▶ │ resume           │   PME, AER, DPC, BWCTRL, HP
    .restore         ──┘                            │                  │
                                                    ├──────────────────┤
    .runtime_suspend ──── only with bridge_d3 ────▶ │ runtime_suspend  │   HP
                                                    ├──────────────────┤
    .runtime_resume  ─────────────────────────────▶ │ runtime_resume   │   HP
                                                    └──────────────────┘
    .runtime_idle       no slot: answers from bridge_d3 alone

    HP's suspend, resume_noirq and resume exist with CONFIG_PM_SLEEP, its runtime slots with CONFIG_PM
```

A system suspend reaches the suspend slot of every bound service, and the noirq phase of a resume reaches the hotplug service alone, both with [`CONFIG_PM_SLEEP`](https://elixir.bootlin.com/linux/v7.2/source/kernel/power/Kconfig#L140) set. The PCI core calls the port driver's [`suspend`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L291) from [`pci_pm_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L812); read the stages around the call.

```c
/* drivers/pci/pci-driver.c:812 */
static int pci_pm_suspend(struct device *dev)
{
	struct pci_dev *pci_dev = to_pci_dev(dev);
	const struct dev_pm_ops *pm = dev->driver ? dev->driver->pm : NULL;
	... /* 30 lines, to :846 */
	if (!dev_pm_smart_suspend(dev) || pci_dev_need_resume(pci_dev)) {
		pm_runtime_resume(dev);
		pci_dev->state_saved = false;
	} else {
		pci_dev_adjust_pme(pci_dev);
	}

	if (pm->suspend) {
		pci_power_t prev = pci_dev->current_state;
		int error;

		error = pm->suspend(dev);
		suspend_report_result(dev, pm->suspend, error);
		if (error)
			return error;

		if (!pci_dev->state_saved && pci_dev->current_state != PCI_D0
		    && pci_dev->current_state != PCI_UNKNOWN) {
			pci_WARN_ONCE(pci_dev, pci_dev->current_state != prev,
				      "PCI PM: State of device not saved by %pS\n",
				      pm->suspend);
		}
	}
```

A port carrying [`DPM_FLAG_SMART_SUSPEND`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L663), which the probe set, stays runtime-suspended through system suspend unless [`pci_dev_need_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2785) asks for a resume, and the fan-out then runs on the suspended port. Without the flag the core resumes the port first. The probe's other flag concerns the direct-complete optimization; read the comment that describes both flags.

```c
/* include/linux/pm.h:648 */
/*
 * Driver flags to control system suspend/resume behavior.
 *
 * These flags can be set by device drivers at the probe time.  They need not be
 * cleared by the drivers as the driver core will take care of that.
 *
 * NO_DIRECT_COMPLETE: Do not apply direct-complete optimization to the device.
 * SMART_PREPARE: Take the driver ->prepare callback return value into account.
 * SMART_SUSPEND: Avoid resuming the device from runtime suspend.
 * MAY_SKIP_RESUME: Allow driver "noirq" and "early" callbacks to be skipped.
 *
 * See Documentation/driver-api/pm/devices.rst for details.
 */
#define DPM_FLAG_NO_DIRECT_COMPLETE	BIT(0)
#define DPM_FLAG_SMART_PREPARE		BIT(1)
#define DPM_FLAG_SMART_SUSPEND		BIT(2)
#define DPM_FLAG_MAY_SKIP_RESUME	BIT(3)
```

[`DPM_FLAG_NO_DIRECT_COMPLETE`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L661) keeps the PM core from applying the direct-complete optimization to the port, in the comment's words, and the comment sends the reader to Documentation/driver-api/pm/devices.rst for what the optimization skips. Both flags are set once in the probe and stay set while the port driver is bound.

### Runtime suspend of a port waits for the core's D3 decision

A port that the PCI core lets into D3 can runtime suspend once nothing below it is busy, and its services must be told when it does. The probe turned runtime PM on only for such a port; read those lines of [`pcie_portdrv_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685) again.

```c
/* drivers/pci/pcie/portdrv.c:685 */
static int pcie_portdrv_probe(struct pci_dev *dev,
					const struct pci_device_id *id)
{
	... /* 22 lines, to :710 */
	if (pci_bridge_d3_possible(dev)) {
		/*
		 * Keep the port resumed 100ms to make sure things like
		 * config space accesses from userspace (lspci) will not
		 * cause the port to repeatedly suspend and resume.
		 */
		pm_runtime_set_autosuspend_delay(&dev->dev, 100);
		pm_runtime_use_autosuspend(&dev->dev);
		pm_runtime_mark_last_busy(&dev->dev);
		pm_runtime_put_autosuspend(&dev->dev);
		pm_runtime_allow(&dev->dev);
	}
```

The 100 ms autosuspend delay keeps the port awake between bursts of configuration accesses, as the comment says. [`pm_runtime_put_autosuspend()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L599) gives back the usage count the PCI core took around the probe, and [`pm_runtime_allow()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1691) lifts the ban the core set at enumeration. The count is taken in [`local_pci_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L314); read it.

```c
/* drivers/pci/pci-driver.c:314 */
static int local_pci_probe(struct drv_dev_and_id *ddi)
{
	struct pci_dev *pci_dev = ddi->dev;
	struct pci_driver *pci_drv = ddi->drv;
	struct device *dev = &pci_dev->dev;
	int rc;

	/*
	 * Unbound PCI devices are always put in D0, regardless of
	 * runtime PM status.  During probe, the device is set to
	 * active and the usage count is incremented.  If the driver
	 * supports runtime PM, it should call pm_runtime_put_noidle(),
	 * or any other runtime PM helper function decrementing the usage
	 * count, in its probe routine and pm_runtime_get_noresume() in
	 * its remove routine.
	 */
	pm_runtime_get_sync(dev);
	pci_dev->driver = pci_drv;
	rc = pci_drv->probe(pci_dev, ddi->id);
	if (!rc)
		return rc;
	if (rc < 0) {
		pci_dev->driver = NULL;
		pm_runtime_put_sync(dev);
		return rc;
	}
	/*
	 * Probe function should return < 0 for failure, 0 for success
	 * Treat values > 0 as success, but warn.
	 */
	pci_warn(pci_dev, "Driver probe function unexpectedly returned %d\n",
		 rc);
	return 0;
}
```

The comment states the rule the port driver follows, that a driver supporting runtime PM drops the usage count in its probe and takes it again in its remove. The core takes the count with [`pm_runtime_get_sync()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L511) before calling the probe and gives it back itself only when the probe fails. The ban comes from [`pci_pm_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L3161); read its stages.

```c
/* drivers/pci/pci.c:3161 */
void pci_pm_init(struct pci_dev *dev)
{
	int pm;
	u16 pmc;

	device_enable_async_suspend(&dev->dev);
... /* 57 lines, to :3224 */
poweron:
	pci_pm_power_up_and_verify_state(dev);
	pm_runtime_forbid(&dev->dev);

	/*
	 * Runtime PM will be enabled for the device when it has been fully
	 * configured, but since its parent and suppliers may suspend in
	 * the meantime, prevent them from doing so by changing the
	 * device's runtime PM status to "active".
	 */
	pm_runtime_set_active(&dev->dev);
}
```

Every PCI function starts with runtime PM forbidden and its runtime status active. [`pm_runtime_forbid()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1664) expresses the ban as one count of the same usage counter; read it.

```c
/* drivers/base/power/runtime.c:1664 */
void pm_runtime_forbid(struct device *dev)
{
	spin_lock_irq(&dev->power.lock);
	if (!dev->power.runtime_auto)
		goto out;

	dev->power.runtime_auto = false;
	atomic_inc(&dev->power.usage_count);
	rpm_resume(dev, 0);

 out:
	spin_unlock_irq(&dev->power.lock);
}
```

[`pm_runtime_forbid()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1664) clears [`runtime_auto`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L709), increments the usage count and resumes the device, unless runtime PM is already forbidden. [`pm_runtime_allow()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1691) undoes it; read it.

```c
/* drivers/base/power/runtime.c:1691 */
void pm_runtime_allow(struct device *dev)
{
	int ret;

	spin_lock_irq(&dev->power.lock);
	if (dev->power.runtime_auto)
		goto out;

	dev->power.runtime_auto = true;
	ret = rpm_drop_usage_count(dev);
	if (ret == 0)
		rpm_idle(dev, RPM_AUTO | RPM_ASYNC);
	else if (ret > 0)
		trace_rpm_usage(dev, RPM_AUTO | RPM_ASYNC);

 out:
	spin_unlock_irq(&dev->power.lock);
}
```

[`pm_runtime_allow()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1691) sets [`runtime_auto`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L709) again and drops the count, starting an asynchronous idle check when the count reaches 0. The figure follows the port's usage count from enumeration to unbind, with the remove path of the next subsection included.

```text
    The port's runtime PM usage count from enumeration to unbind
    ────────────────────────────────────────────────────────────

    time ───────────────────────────────────────────────────────────────────────────────────────────────────────▶
    event          pci_pm_init  local_pci_  port      pci_device_   port          put_noidle   put_sync
                                probe       probe     remove: get   remove        in pci_device_remove
                   ╎            ╎           ╎         ╎             ╎             ╎            ╎
    forbid         ├────────────────────────┤                       ├───────────────────────────────────────────▶
    probe ref                   ├───────────┤                       ├──────────────────────────┤
    remove ref                                        ├───────────────────────────┤
    may suspend                             ├─────────┤
                   ╎            ╎           ╎         ╎             ╎             ╎            ╎
    usage count    1            2           0         1             3             2            1

    the bars assume pci_bridge_d3_possible() is true; without it the probe drops neither holder, the count
    stays at 2 while the driver is bound, and it is back at 1 after the remove path
    forbid      runtime PM forbidden, which holds one count until pm_runtime_allow()
    probe ref   the count local_pci_probe() takes, dropped at the end of the port's probe and taken
                back by its remove for the final put of pci_device_remove()
    remove ref  the count pci_device_remove() holds around the driver's remove
```

Between the end of the probe and the start of the removal the count is 0, and the port can runtime suspend once its autosuspend delay has passed. Whether the probe drops its holders at all depends on [`pci_bridge_d3_possible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2988); read the stage that sorts ports.

```c
/* drivers/pci/pci.c:2988 */
bool pci_bridge_d3_possible(struct pci_dev *bridge)
{
	if (!pci_is_pcie(bridge))
		return false;

	switch (pci_pcie_type(bridge)) {
	case PCI_EXP_TYPE_ROOT_PORT:
	case PCI_EXP_TYPE_UPSTREAM:
	case PCI_EXP_TYPE_DOWNSTREAM:
		if (pci_bridge_d3_disable)
			return false;

		/*
		 * Hotplug ports handled by platform firmware may not be put
		 * into D3 by the OS, e.g. ACPI slots ...
		 */
		if (bridge->is_hotplug_bridge && !bridge->is_pciehp)
			return false;

		/* ... or PCIe hotplug ports not handled natively by the OS. */
		if (bridge->is_pciehp && !pciehp_is_native(bridge))
			return false;

		if (pci_bridge_d3_force)
			return true;
	... /* 27 lines, to :3040 */
	}

	return false;
}
```

Root Ports and Switch Ports pass the type switch and an RCEC does not, so an RCEC never drops its holders. A port is refused when bridge D3 is disabled or when firmware handles its hotplug, and pcie_port_pm=force allows it at that point. When the count reaches 0 and the delay expires, the PCI core's [`pci_pm_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1314) calls the port driver's [`runtime_suspend`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm.h#L309); read the call and its error handling.

```c
/* drivers/pci/pci-driver.c:1314 */
static int pci_pm_runtime_suspend(struct device *dev)
{
	struct pci_dev *pci_dev = to_pci_dev(dev);
	const struct dev_pm_ops *pm = dev->driver ? dev->driver->pm : NULL;
	pci_power_t prev = pci_dev->current_state;
	int error;

	pci_suspend_ptm(pci_dev);

	/*
	 * If pci_dev->driver is not set (unbound), we leave the device in D0,
	 * but it may go to D3cold when the bridge above it runtime suspends.
	 * Save its config space in case that happens.
	 */
	if (!pci_dev->driver) {
		pci_save_state(pci_dev);
		return 0;
	}

	pci_dev->state_saved = false;
	if (pm && pm->runtime_suspend) {
		error = pm->runtime_suspend(dev);
		/*
		 * -EBUSY and -EAGAIN is used to request the runtime PM core
		 * to schedule a new suspend, so log the event only with debug
		 * log level.
		 */
		if (error == -EBUSY || error == -EAGAIN) {
			pci_dbg(pci_dev, "can't suspend now (%ps returned %d)\n",
				pm->runtime_suspend, error);
			return error;
		} else if (error) {
			pci_err(pci_dev, "can't suspend (%ps returned %d)\n",
				pm->runtime_suspend, error);
			return error;
		}
	}
```

-EBUSY or -EAGAIN from the driver asks the runtime PM core to try again later and prints a debug line, and any other error prints an error line naming the callback. The port driver's callback is [`pcie_port_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L638), with [`pcie_port_runtime_idle()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L646) beside it; read both.

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

Both answer -EBUSY while [`bridge_d3`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L418) is clear, and the comment states the assumption that the PCI core sets that bit whenever it thinks the port may go to D3. With the bit set, the idle check lets the suspend go ahead and [`pcie_port_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L638) passes on to the fan-out; read it with the resume side.

```c
/* drivers/pci/pcie/portdrv.c:427 */
/**
 * pcie_port_device_runtime_suspend - runtime suspend port services
 * @dev: PCI Express port to handle
 */
static int pcie_port_device_runtime_suspend(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, runtime_suspend);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}

/**
 * pcie_port_device_runtime_resume - runtime resume port services
 * @dev: PCI Express port to handle
 */
static int pcie_port_device_runtime_resume(struct device *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, runtime_resume);
	return device_for_each_child(dev, &off, pcie_port_device_iter);
}
#endif /* PM */
```

[`pcie_port_device_runtime_suspend()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L431) and [`pcie_port_device_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L441) pass the offsets of the two runtime slots, which at v7.2 the hotplug service alone fills. A port with only PME, AER, DPC or bandwidth instances runtime suspends with no service callback run, and the resume side, [`pcie_port_device_runtime_resume()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L441), is installed in the table directly, with no test of the bit.

### Removal and shutdown unregister every service instance

When the port driver unbinds, or the system shuts down, the services must stop before the port loses its interrupt vectors. [`pcie_portdrv_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L726) and [`pcie_portdrv_shutdown()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L739) share that work and differ in one call; read them.

```c
/* drivers/pci/pcie/portdrv.c:726 */
static void pcie_portdrv_remove(struct pci_dev *dev)
{
	if (pci_bridge_d3_possible(dev)) {
		pm_runtime_forbid(&dev->dev);
		pm_runtime_get_noresume(&dev->dev);
		pm_runtime_dont_use_autosuspend(&dev->dev);
	}

	pcie_port_device_remove(dev);

	pci_disable_device(dev);
}

static void pcie_portdrv_shutdown(struct pci_dev *dev)
{
	if (pci_bridge_d3_possible(dev)) {
		pm_runtime_forbid(&dev->dev);
		pm_runtime_get_noresume(&dev->dev);
		pm_runtime_dont_use_autosuspend(&dev->dev);
	}

	pcie_port_device_remove(dev);
}
```

Both forbid runtime PM, take back the usage count the probe gave away and stop autosuspend when D3 is possible, then call [`pcie_port_device_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L505). Removal also disables the port with [`pci_disable_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2196), while shutdown leaves it enabled. The PCI core calls the remove from [`pci_device_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L498); read it for the runtime PM calls around it.

```c
/* drivers/pci/pci-driver.c:498 */
static void pci_device_remove(struct device *dev)
{
	struct pci_dev *pci_dev = to_pci_dev(dev);
	struct pci_driver *drv = pci_dev->driver;

	if (drv->remove) {
		pm_runtime_get_sync(dev);
		/*
		 * If the driver provides a .runtime_idle() callback and it has
		 * started to run already, it may continue to run in parallel
		 * with the code below, so wait until all of the runtime PM
		 * activity has completed.
		 */
		pm_runtime_barrier(dev);
		drv->remove(pci_dev);
		pm_runtime_put_noidle(dev);
	}
	pcibios_free_irq(pci_dev);
	pci_dev->driver = NULL;
	pci_iov_remove(pci_dev);

	/* Undo the runtime PM settings in local_pci_probe() */
	pm_runtime_put_sync(dev);

	/*
	 * We would love to complain here if pci_dev->is_enabled is set, that
	 * the driver should have called pci_disable_device(), but the
	 * unfortunate fact is there are too many odd BIOS and bridge setups
	 * that don't like drivers doing that all of the time.
	 * Oh well, we can dream of sane hardware when we sleep, no matter how
	 * horrible the crap we have to deal with is when we are awake...
	 */

	pci_dev_put(pci_dev);
}
```

The core resumes the port and waits for runtime PM activity before the driver's remove, then drops its own count with [`pm_runtime_put_noidle()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L131). After the remove it puts the count the driver took back, through [`pm_runtime_put_sync()`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pm_runtime.h#L677), which leaves the port with the ban's count alone, as the figure of the previous subsection shows. Shutdown takes another path; read [`pci_device_shutdown()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L534).

```c
/* drivers/pci/pci-driver.c:534 */
static void pci_device_shutdown(struct device *dev)
{
	struct pci_dev *pci_dev = to_pci_dev(dev);
	struct pci_driver *drv = pci_dev->driver;

	pm_runtime_resume(dev);

	if (drv && drv->shutdown)
		drv->shutdown(pci_dev);

	/*
	 * If this is a kexec reboot, turn off Bus Master bit on the
	 * device to tell it to not continue to do DMA. Don't touch
	 * devices in D3cold or unknown states.
	 * If it is not a kexec reboot, firmware will hit the PCI
	 * devices with big hammer and stop their DMA any way.
	 */
	if (kexec_in_progress && (pci_dev->current_state <= PCI_D3hot))
		pci_clear_master(pci_dev);
}
```

The core resumes the port and calls the shutdown callback without unbinding the driver, and for a kexec reboot it then clears bus mastering on a port in D3hot or a higher-power state. Both driver callbacks come to [`pcie_port_device_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L505); read it.

```c
/* drivers/pci/pcie/portdrv.c:498 */
/**
 * pcie_port_device_remove - unregister PCI Express port service devices
 * @dev: PCI Express port the service devices to unregister are associated with
 *
 * Remove PCI Express port service devices associated with given port and
 * disable MSI-X or MSI for the port.
 */
static void pcie_port_device_remove(struct pci_dev *dev)
{
	device_for_each_child(&dev->dev, NULL, remove_iter);
	pci_free_irq_vectors(dev);
}
```

[`pcie_port_device_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L505) lets [`device_for_each_child()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4089) call [`remove_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L448) on every child of the port and frees the port's vectors with [`pci_free_irq_vectors()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/msi/api.c#L379) afterwards, so the services' remove callbacks run before the vectors go. Read [`remove_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L448).

```c
/* drivers/pci/pcie/portdrv.c:448 */
static int remove_iter(struct device *dev, void *data)
{
	if (dev->bus == &pcie_port_bus_type)
		device_unregister(dev);
	return 0;
}
```

[`remove_iter()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L448) unregisters each child on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) and leaves any other child alone, and it returns 0, so the iteration covers every child. The figure shows the port before and after the two paths.

```text
    A port before and after its service instances are torn down
    ───────────────────────────────────────────────────────────

    before                                            after pcie_portdrv_remove(), then unbound
    ┌────────────────────────────────────┐            ┌──────────────────────────────────────┐
    │ port bound to pcieport             │            │ port about to be unbound             │
    │ pci_enable_device() done           │            │ pci_disable_device() done            │
    │ vectors allocated                  ├────┬─────▶ │ vectors freed                        │
    │ children on pci_express:           │    │       │ children: none                       │
    │   pcie001  pcie002  pcie004        │    │       │                                      │
    └────────────────────────────────────┘    │       └──────────────────────────────────────┘
                                              │       after pcie_portdrv_shutdown()
                                              │       ┌──────────────────────────────────────┐
                                              │       │ port still bound                     │
                                              └─────▶ │ left enabled                         │
                                                      │ vectors freed                        │
                                                      │ children: none                       │
                                                      └──────────────────────────────────────┘

    both paths unregister every child on pci_express and free the vectors; only removal disables the port
```

So far, the port's instances have been created, bound, looked up and called through the PM callbacks, and removal or shutdown has unregistered them all and freed the port's vectors. What remains is the release of each instance, which waits for its last reference.

### The last reference frees the instance through its release

Unregistering an instance does not free it at once, because the registration and the bound driver each hold a reference. [`device_unregister()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3999) drops the registration's; read it with its comment.

```c
/* drivers/base/core.c:3992 */
 * We do this in two parts, like we do device_register(). First,
 * we remove it from all the subsystems with device_del(), then
 * we decrement the reference count via put_device(). If that
 * is the final reference count, the device will be cleaned up
 * via device_release() above. Otherwise, the structure will
 * stick around until the final reference to the device is dropped.
 */
void device_unregister(struct device *dev)
{
	pr_debug("device: '%s': %s\n", dev_name(dev), __func__);
	device_del(dev);
	put_device(dev);
}
EXPORT_SYMBOL_GPL(device_unregister);
```

The comment says [`device_del()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3915) removes the device from all the subsystems, which for a bound instance includes unbinding its driver. The [`put_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3876) after it drops the registration's reference, so the structure stays until the last reference goes. The unbind reaches the bus's remove callback through [`device_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L610); read it.

```c
/* drivers/base/dd.c:610 */
static void device_remove(struct device *dev)
{
	device_remove_file(dev, &dev_attr_state_synced);
	device_remove_groups(dev, dev->driver->dev_groups);

	if (dev->bus && dev->bus->remove)
		dev->bus->remove(dev);
	else if (dev->driver->remove)
		dev->driver->remove(dev);
}
```

The pci_express bus has a remove callback, so the driver core calls it, and the service driver's remove runs from inside it. Read [`pcie_port_bus_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L562).

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

The callback calls [`remove`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L81) when the service driver has one, then drops the reference [`pcie_port_bus_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L534) took. The PME service's remove shows what that callback undoes; read [`pcie_pme_remove()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L446).

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

The remove reads its data through [`get_service_data()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L73), disables the port's PME interrupt, frees the instance's interrupt, waits for its work item and frees the data, which leaves [`priv_data`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L63) pointing at freed memory. The lookup and the iterator skip an instance without a driver, so neither reaches that pointer again. The last [`put_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3876) runs the release callback; read [`release_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L47).

```c
/* drivers/pci/pcie/portdrv.c:40 */
/**
 * release_pcie_device - free PCI Express port service device structure
 * @dev: Port service device to release
 *
 * Invoked automatically when device is being removed in response to
 * device_unregister(dev).  Release all resources being claimed.
 */
static void release_pcie_device(struct device *dev)
{
	kfree(to_pcie_device(dev));
}
```

[`release_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L47) frees the whole instance with `kfree()` after [`to_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L66) steps back from the embedded device to the start of the instance, since [`device`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L64) is its last member. The figure counts the references from registration to release.

```text
    The references on one service instance and the release they lead to
    ───────────────────────────────────────────────────────────────────

    time ───────────────────────────────────────────────────────────────────────────────────────────▶
    event            device_register   bus probe     device_unregister:   bus remove    put_device
                                       returns 0     device_del           returns       after it
                     ╎                 ╎             ╎                    ╎             ╎
    registration     ├──────────────────────────────────────────────────────────────────┤
    bound driver                       ├──────────────────────────────────┤
                     ╎                 ╎             ╎                    ╎             ╎
    count            1                 2             2                    1             0 release_pcie_device()
                                                                                          frees the instance

    a service probe that fails takes no reference, so the bound-driver bar is absent and device_unregister's
    put_device drops the count from 1 to 0; a device_register that fails is followed by put_device at once
```

With a bound driver the count runs 1, 2, 2, 1 and 0 across registration, binding, unregistration, the bus remove and the final put, and [`release_pcie_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L47) runs at that last [`put_device()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3876).

### Error recovery reaches services through the port's error handlers

When AER or DPC reports an error, the recovery code calls the error handlers of the drivers below the bridge it recovers. A port below that point is bound to the port driver, so the port driver needs handlers too. The port driver provides three, in [`pcie_portdrv_err_handler`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L785); read the table.

```c
/* drivers/pci/pcie/portdrv.c:785 */
static const struct pci_error_handlers pcie_portdrv_err_handler = {
	.error_detected = pcie_portdrv_error_detected,
	.slot_reset = pcie_portdrv_slot_reset,
	.mmio_enabled = pcie_portdrv_mmio_enabled,
};
```

[`error_detected`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L943), [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) and [`mmio_enabled`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L947) are filled, and [`resume`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L957) stays NULL since commit [80dcd36c388a](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=80dcd36c388a34d5c2d0b9c8c171887903dbefbb) ("PCI/portdrv: Remove unused resume err_handler"). Read the three handlers together.

```c
/* drivers/pci/pcie/portdrv.c:750 */
static pci_ers_result_t pcie_portdrv_error_detected(struct pci_dev *dev,
					pci_channel_state_t error)
{
	if (error == pci_channel_io_frozen)
		return PCI_ERS_RESULT_NEED_RESET;
	return PCI_ERS_RESULT_CAN_RECOVER;
}

static pci_ers_result_t pcie_portdrv_slot_reset(struct pci_dev *dev)
{
	size_t off = offsetof(struct pcie_port_service_driver, slot_reset);
	device_for_each_child(&dev->dev, &off, pcie_port_device_iter);

	pci_restore_state(dev);
	return PCI_ERS_RESULT_RECOVERED;
}

static pci_ers_result_t pcie_portdrv_mmio_enabled(struct pci_dev *dev)
{
	return PCI_ERS_RESULT_RECOVERED;
}
```

[`pcie_portdrv_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L750) asks for a reset when the channel is frozen and answers that it can recover otherwise, and [`pcie_portdrv_mmio_enabled()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L767) reports the port recovered. [`pcie_portdrv_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758) passes the offset of [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L88) to the iterator, restores the configuration the probe saved with [`pci_restore_state()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L1826) and reports the port recovered. The recovery code reaches these handlers through [`pci_walk_bridge()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L200); read it for the devices it visits.

```c
/* drivers/pci/pcie/err.c:187 */
/**
 * pci_walk_bridge - walk bridges potentially AER affected
 * @bridge:	bridge which may be a Port, an RCEC, or an RCiEP
 * @cb:		callback to be called for each device found
 * @userdata:	arbitrary pointer to be passed to callback
 *
 * If the device provided is a bridge, walk the subordinate bus, including
 * any bridged devices on buses under this bus.  Call the provided callback
 * on each device found.
 *
 * If the device provided has no subordinate bus, e.g., an RCEC or RCiEP,
 * call the callback on the device itself.
 */
static void pci_walk_bridge(struct pci_dev *bridge,
			    int (*cb)(struct pci_dev *, void *),
			    void *userdata)
{
	if (bridge->subordinate)
		pci_walk_bus(bridge->subordinate, cb, userdata);
	else
		cb(bridge, userdata);
}
```

A bridge with a secondary bus has the callback run on the devices below it through [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461), and the bridge itself is skipped. A bridge without one, an RCEC or an integrated Endpoint, gets the callback itself. Read [`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) for the lock it takes.

```c
/* drivers/pci/bus.c:461 */
void pci_walk_bus(struct pci_bus *top, int (*cb)(struct pci_dev *, void *), void *userdata)
{
	down_read(&pci_bus_sem);
	__pci_walk_bus(top, cb, userdata);
	up_read(&pci_bus_sem);
}
```

[`pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L461) holds [`pci_bus_sem`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/search.c#L17) for reading around [`__pci_walk_bus()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/bus.c#L408); read the recursion.

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

Each device on the bus gets the callback, and a device with a secondary bus has its subtree visited right after it. The visit goes down the hierarchy depth first and stops at the first nonzero return. A switch below the recovering Root Port therefore has its Upstream Port and its Downstream Ports visited, and their handlers are the port driver's. [`pcie_do_recovery()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L210) picks the bridge the visit starts from and the messages it sends; read the stages that do.

```c
/* drivers/pci/pcie/err.c:210 */
pci_ers_result_t pcie_do_recovery(struct pci_dev *dev,
		pci_channel_state_t state,
		pci_ers_result_t (*reset_subordinates)(struct pci_dev *pdev))
{
	... /* 14 lines, to :228 */
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
	... /* 15 lines, to :258 */
	if (status == PCI_ERS_RESULT_NEED_RESET) {
		/*
		 * TODO: Should call platform-specific
		 * functions to reset slot before calling
		 * drivers' slot_reset callbacks?
		 */
		status = PCI_ERS_RESULT_RECOVERED;
		pci_dbg(bridge, "broadcast slot_reset message\n");
		pci_walk_bridge(bridge, report_slot_reset, &status);
	}
```

Recovery starts from the reporting device when it is a Root Port, a Downstream Port, an RCEC or an integrated Endpoint, and from the bridge above it otherwise. A frozen channel makes every port driver below vote for a reset through [`pcie_portdrv_error_detected()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L750), and when the merged result asks for a reset, the slot_reset message goes to every device below. Read [`report_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L148) for how the message reaches a port's handler.

```c
/* drivers/pci/pcie/err.c:148 */
static int report_slot_reset(struct pci_dev *dev, void *data)
{
	struct pci_driver *pdrv;
	pci_ers_result_t vote, *result = data;
	const struct pci_error_handlers *err_handler;

	device_lock(&dev->dev);
	pdrv = dev->driver;
	if (!pci_dev_set_io_state(dev, pci_channel_io_normal) ||
	    !pdrv || !pdrv->err_handler || !pdrv->err_handler->slot_reset)
		goto out;

	err_handler = pdrv->err_handler;
	vote = err_handler->slot_reset(dev);
	*result = merge_result(*result, vote);
out:
	device_unlock(&dev->dev);
	return 0;
}
```

Under the device lock, the message goes to the bound driver's [`slot_reset`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L950) when the device's I/O state can return to normal, and the vote is merged into the result. For a port that handler is [`pcie_portdrv_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L758), which passes the reset on to the services, and at v7.2 pciehp is the one service with a slot_reset slot filled; read [`pciehp_slot_reset()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_hpc.c#L915).

```c
/* drivers/pci/hotplug/pciehp_hpc.c:905 */
/**
 * pciehp_slot_reset() - ignore link event caused by error-induced hot reset
 * @dev: PCI Express port service device
 *
 * Called from pcie_portdrv_slot_reset() after AER or DPC initiated a reset
 * further up in the hierarchy to recover from an error.  The reset was
 * propagated down to this hotplug port.  Ignore the resulting link flap.
 * If the link failed to retrain successfully, synthesize the ignored event.
 * Surprise removal during reset is detected through Presence Detect Changed.
 */
int pciehp_slot_reset(struct pcie_device *dev)
{
	struct controller *ctrl = get_service_data(dev);

	if (ctrl->state != ON_STATE)
		return 0;

	pcie_capability_write_word(dev->port, PCI_EXP_SLTSTA,
				   PCI_EXP_SLTSTA_DLLSC);

	if (!pciehp_check_link_active(ctrl))
		pciehp_request(ctrl, PCI_EXP_SLTSTA_DLLSC);

	return 0;
}
```

According to its kerneldoc, the hotplug service ignores the link flap that the reset caused, clearing the Data Link Layer State Changed event, and synthesizes the event when the link did not come back. The figure shows where in a hierarchy the port driver's handlers run.

```text
    Where recovery calls the port driver's error handlers
    ─────────────────────────────────────────────────────

             ┌──────────────────────────────────────────┐
    tier 0   │ Root Port: the bridge recovery runs on   │   no pcieport handler of its own runs:
             │ after its AER or DPC service reported    │   the walk covers its subordinate bus
             └────────────────┬─────────────────────────┘
                              │
    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   the walk starts below this line
             ┌────────────────┴─────────────────────────┐
    tier 1   │ Switch Upstream Port                     │   its error_detected, mmio_enabled and
             │ bound to pcieport                        │   slot_reset are the port driver's
             └────────────────┬─────────────────────────┘
             ┌────────────────┴─────────────────────────┐
    tier 2   │ Switch Downstream Port                   │   the same handlers; its slot_reset calls
             │ bound to pcieport, with pciehp           │   pciehp's slot_reset through the iterator
             └────────────────┬─────────────────────────┘
             ┌────────────────┴─────────────────────────┐
    tier 3   │ Endpoint                                 │   the handlers of its own driver
             └──────────────────────────────────────────┘

    an RCEC has no subordinate bus, so recovery that runs on an RCEC calls the RCEC's own pcieport handlers
```

A port's handlers run when the port lies below the bridge recovery starts from, or when the port is the RCEC recovery starts from. The handlers of a starting bridge with a secondary bus do not run. The port driver's part is to forward the reset to its services and to restore the configuration saved in its probe, the restore coming from commit [874b3251113a](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=874b3251113a1e2cbe79c24994dc03fe4fe4b99b) ("PCI: portdrv: Restore PCI config state on slot reset").

### The framework's paths print little and fire no tracepoints

Watching these paths means knowing which events leave a trace. Neither portdrv.c nor portdrv.h defines a tracepoint, and portdrv.c prints a single message; the table lists, class by class, what the flows of this page produce.

| Class | On these paths | Sites |
|---|---|---|
| tracepoints | none of the framework's own; the PM core's power:device_pm_callback_start and power:device_pm_callback_end fire around the port's sleep callbacks, and the runtime PM core's rpm:rpm_suspend, rpm:rpm_resume, rpm:rpm_idle and rpm:rpm_usage events fire for the port | [`drivers/base/power/main.c:509-511`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/main.c#L509), [`runtime.c:593`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L593), [`runtime.c:793`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L793), [`runtime.c:496`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L496), [`runtime.c:1704`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1704) |
| messages always printed | the DMI quirk's notice, the host bridge's notice under pcie_ports=compat, a failed service probe's error, a refused runtime suspend's error, and recovery's final line | [`portdrv.c:808`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L808), [`pci_root.c:544`](https://elixir.bootlin.com/linux/v7.2/source/drivers/acpi/pci_root.c#L544), [`dd.c:644`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L644), [`pci-driver.c:1346`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1346), [`err.c:288`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L288) |
| dynamic-debug sites | each driver added to the bus, each instance added and unregistered, each bind attempt and its outcome, a quiet probe refusal, a runtime suspend refused with -EBUSY, recovery's broadcasts, and the hotplug driver's registration | [`drivers/base/bus.c:745`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/bus.c#L745), [`core.c:3678`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L3678), [`core.c:4001`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/core.c#L4001), [`dd.c:672`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L672), [`dd.c:453`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L453), [`dd.c:639`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/dd.c#L639), [`pci-driver.c:1342`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L1342), [`err.c:238`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/err.c#L238), [`pciehp_core.c:379`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L379) |
| asynchronous hand-offs | the port's probe on a worker of its NUMA node, the asynchronous suspend of instances, the autosuspend timer of the port; recovery runs in the thread of the AER or DPC service that started it | [`pci-driver.c:415`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L415), [`device.h:1022`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/device.h#L1022), [`portdrv.c:716`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L716) |
| notifier chains | none registered on [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) at v7.2 | none |
| debugging surfaces | sysfs and boot parameters, no debugfs file and no fault injection of the framework's own | the next subsection |

The debug sites are dev_dbg(), pci_dbg() and pr_debug() calls, and what they compile to depends on two options; read the dev_dbg() definitions.

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

With [`CONFIG_DYNAMIC_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/lib/Kconfig.debug#L120) set, as here, every dev_dbg() is a dynamic-debug site, off until a reader enables it through /sys/kernel/debug/dynamic_debug/control, and with `DEBUG` defined instead it always prints. pci_dbg() is dev_dbg() on the function's embedded device; read its definition.

```c
/* include/linux/pci.h:2896 */
#define pci_dbg(pdev, fmt, arg...)	dev_dbg(&(pdev)->dev, fmt, ##arg)
```

The PCI directories get `DEBUG` from their Makefile only with [`CONFIG_PCI_DEBUG`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/Kconfig#L70), which this build leaves unset.

```c
/* drivers/pci/Makefile:50 */
subdir-ccflags-$(CONFIG_PCI_DEBUG) := -DDEBUG
```

Enabling the sites of drivers/base/dd.c shows each bind attempt on pci_express with the service driver's name and its result, which tells a reader which services bound on which port. The sites of drivers/base/bus.c and drivers/base/core.c add each service driver and each instance by name as they register, and the site of pci-driver.c shows a port refusing runtime suspend while [`bridge_d3`](https://elixir.bootlin.com/linux/v7.2/source/include/linux/pci.h#L418) is clear. The hotplug driver's init adds two lines of its own; read [`pcie_hp_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/hotplug/pciehp_core.c#L374).

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

The first line reports the registration's return value and the second appears only on failure. The PM core fires its callback tracepoints in [`dpm_run_callback()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/main.c#L497); read the stage.

```c
/* drivers/base/power/main.c:497 */
static int dpm_run_callback(pm_callback_t cb, struct device *dev,
			    pm_message_t state, const char *info)
{
	ktime_t calltime;
	int error;

	if (!cb)
		return 0;

	calltime = initcall_debug_start(dev, cb);

	pm_dev_dbg(dev, state, info);
	trace_device_pm_callback_start(dev, info, state.event);
	error = cb(dev);
	trace_device_pm_callback_end(dev, error);
	suspend_report_result(dev, cb, error);
```

The pair brackets the callback with the device and the phase, after the PM core's own debug line from [`pm_dev_dbg()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/main.c#L463), and a NULL callback returns before either fires, which is the case of every instance. The one asynchronous hand-off on the port's own probe path is in [`pci_call_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L373); read the stage.

```c
/* drivers/pci/pci-driver.c:373 */
static int pci_call_probe(struct pci_driver *drv, struct pci_dev *dev,
			  const struct pci_device_id *id)
{
	int error, node, cpu;
	struct drv_dev_and_id ddi = { drv, dev, id };
	... /* 14 lines, to :392 */
	if (node < 0 || node >= MAX_NUMNODES || !node_online(node) ||
	    pci_physfn_is_probed(dev)) {
		error = local_pci_probe(&ddi);
	} else {
		struct pci_probe_arg arg = { .ddi = &ddi };

		INIT_WORK_ONSTACK(&arg.work, local_pci_probe_callback);
		/*
		 * The target election and the enqueue of the work must be within
		 * the same RCU read side section so that when the workqueue pool
		 * is flushed after a housekeeping cpumask update, further readers
		 * are guaranteed to queue the probing work to the appropriate
		 * targets.
		 */
		rcu_read_lock();
		cpu = cpumask_any_and(cpumask_of_node(node),
				      housekeeping_cpumask(HK_TYPE_DOMAIN));

		if (cpu < nr_cpu_ids) {
			struct workqueue_struct *wq = pci_probe_wq;

			if (WARN_ON_ONCE(!wq))
				wq = system_percpu_wq;
			queue_work_on(cpu, wq, &arg.work);
			rcu_read_unlock();
			flush_work(&arg.work);
			error = arg.ret;
		} else {
			rcu_read_unlock();
			error = local_pci_probe(&ddi);
		}

		destroy_work_on_stack(&arg.work);
	}
```

When the port's node is online and is not the current one, the probe runs as a work item on [`pci_probe_wq`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci-driver.c#L349) on a CPU of that node. The caller waits for it with flush_work(), so the instances the probe registers are created in that worker. Otherwise the probe runs in the caller's thread.

### sysfs and boot parameters expose the services

User space sees the framework through the sysfs tree of the driver model and steers it through boot parameters. The framework adds no debugfs file, and the one fault-injection user of its lookup, the AER error injector, is not built here. The table lists the surfaces with the code behind each.

| Surface | What it shows or sets | Code behind it |
|---|---|---|
| /sys/bus/pci_express/devices/ | one link per instance, named like 0000:00:1c.0:pcie002 | the bus name in [`pcie_port_bus_type`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L575) and the name [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) sets |
| /sys/bus/pci_express/drivers/ | one directory per registered service driver, aer, dpc, pcie_bwctrl, pcie_pme and pciehp | the name [`pcie_port_service_register()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L586) copies |
| the port's sysfs directory | one subdirectory per instance, the port's device being the instance's parent | [`pcie_device_init()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L290) |
| /sys/bus/pci/drivers/pcieport/ | one link per bound port | [`pcie_portdriver`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L791) |
| the port's power/control and power/autosuspend_delay_ms | auto or on, through [`pm_runtime_allow()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1691) and [`pm_runtime_forbid()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1664), and the 100 ms delay | [`control_store()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/sysfs.c#L107), [`pcie_portdrv_probe()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L685) |
| pcie_ports=compat, native or dpc-native | switches the framework off, ignores the native bits, or allows DPC without AER | [`pcie_port_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.c#L622) |
| pcie_port_pm=off or force | refuses or forces D3 for ports, which decides whether the probe enables runtime PM | [`pcie_port_pm_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L161) |
| pci=noaer, pci=nomsi | takes the AER and DPC bits away from every port | [`pci_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L6743) |
| pcie_pme=nomsi | puts every port with the PME service on INTx | [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33) |

The power/control file of the port writes the same state the probe and the remove change; read [`control_store()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/sysfs.c#L107).

```c
/* drivers/base/power/sysfs.c:107 */
static ssize_t control_store(struct device * dev, struct device_attribute *attr,
			     const char * buf, size_t n)
{
	device_lock(dev);
	if (sysfs_streq(buf, ctrl_auto))
		pm_runtime_allow(dev);
	else if (sysfs_streq(buf, ctrl_on))
		pm_runtime_forbid(dev);
	else
		n = -EINVAL;
	device_unlock(dev);
	return n;
}
```

Writing on forbids runtime PM and writing auto allows it again, so a reader can keep a port with services awake without unbinding anything. An instance has no such file, since [`pm_runtime_no_callbacks()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/base/power/runtime.c#L1719) removed its runtime attributes. The pcie_port_pm= parameter sets the two flags [`pci_bridge_d3_possible()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L2988) tests; read [`pcie_port_pm_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L161).

```c
/* drivers/pci/pci.c:161 */
static int __init pcie_port_pm_setup(char *str)
{
	if (!strcmp(str, "off"))
		pci_bridge_d3_disable = true;
	else if (!strcmp(str, "force"))
		pci_bridge_d3_force = true;
	return 1;
}
__setup("pcie_port_pm=", pcie_port_pm_setup);
```

pcie_port_pm=off sets [`pci_bridge_d3_disable`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L157), which keeps every port's usage count up after its probe, and pcie_port_pm=force sets [`pci_bridge_d3_force`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pci.c#L159), which lets a Root Port or Switch Port suspend unless firmware handles its hotplug. pcie_pme=nomsi has the same effect as the DMI quirk; read [`pcie_pme_setup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L33).

```c
/* drivers/pci/pcie/pme.c:33 */
static int __init pcie_pme_setup(char *str)
{
	if (!strncmp(str, "nomsi", 5))
		pcie_pme_msi_disabled = true;

	return 1;
}
__setup("pcie_pme=", pcie_pme_setup);
```

The parameter sets [`pcie_pme_msi_disabled`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/pme.c#L31), the flag [`pcie_pme_no_msi()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/pci/pcie/portdrv.h#L113) returns, so every port granted the PME bit sets up INTx for all its services. Through these files and parameters a reader can tell which services each port got, which drivers bound to them and whether the port may runtime suspend, which is the state the earlier subsections built.
