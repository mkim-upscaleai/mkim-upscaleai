# Vega 6540 platform tests (`x86_64-upscaleai_6540-r0`)

## Why this exists

**Jira:** [UPSW-5952](https://bugatti-asic.atlassian.net/browse/UPSW-5952)

Standard mellanox platform tests fail on Vega because they read
`/var/run/hw-management/*` (NVIDIA hw-management sysfs). Vega uses **Upscale FPGA +
`sonic_platform`**, not the Mellanox platform stack — even though the switch ASIC is
Spectrum-4.

This folder is the **Vega-specific replacement** for `tests/platform_tests/mellanox/`
on `x86_64-upscaleai_6540-r0`.

## What we are doing (this PR)

| Action | Detail |
|--------|--------|
| **Add** | `tests/platform_tests/vega/` — platform checks via `show platform *`, I2C hwmon, and `sonic_platform` inside pmon |
| **Skip on Vega** | Mellanox hw-management, SFP, PSU threshold, and reboot-cause tests that assume NVIDIA board integration |
| **Validate** | Thermals, fans, PSUs, PMON daemons, transceivers, software reboot cause |

### Architecture (one line)

```
Classic Mellanox:  ASIC → hw-management → /var/run/hw-management/* → tests
Vega 6540:         ASIC + FPGA → sonic_platform → show platform / hwmon → tests
```

See `caspian-sonic-buildimage` → `SONiC-6540-PORTING-NOTES.md` and
`SAI_INDEPENDENT_MODULE_MODE=2` in `sai.profile`.

---

## Mellanox → Vega mapping (full status)

| Mellanox source | Vega test | Status |
|-----------------|-----------|--------|
| `check_sysfs` — ASIC thermal (`thermal/asic`) | `test_platform_sensors::test_board_thermal_sensors` | ✅ Done |
| `check_sysfs` — CPU pack/core temps | `test_platform_sensors::test_cpu_thermal_sensors` | ✅ Done |
| `check_sysfs` — CPU max/crit threshold compare | — | ⚠️ Partial (range only, no crit compare) |
| `check_sysfs` — fan status/fault | `test_platform_sensors::test_fan_drawers` | ✅ Done |
| `check_sysfs` — fan speed min/max/set/get | `test_platform_sensors::test_fan_tray_hwmon_rpm` | ✅ Done (hwmon RPM) |
| `check_sysfs` — PSU temp/fan/capability sysfs | `test_platform_sensors::test_psu_*`, `test_platform_psu_detail.py` | ✅ Done (PMBus + API) |
| `check_sysfs` — SFP/module thermal sysfs | — | ❌ **Missing** — needs CMIS DOM / xcvrd path |
| `check_sysfs` — broken hw-management symlinks | — | ➖ N/A (no hw-management tree) |
| `test_check_sysfs::test_hw_mgmt_sysfs_mapped_to_pmon` | — | ➖ N/A |
| `test_hw_management_service.py` | `test_platform_pmon::test_pmon_platform_daemons_running` | ✅ Done |
| `test_check_sfp_presence.py` | `test_platform_transceiver::test_transceiver_presence_connected_ports` | ✅ Done |
| `test_check_sfp_presence.py` (on-board ports) | `test_platform_transceiver::test_service_sfpp_presence` | ✅ Done |
| `test_check_sfp_eeprom.py` | `test_platform_transceiver::test_transceiver_eeprom_connected_ports` | ✅ Done |
| `test_check_sfp_using_ethtool.py` | — | ➖ N/A (deprecated; Vega uses CMIS) |
| `test_psu_power_threshold.py` (mockers) | `test_platform_psu_detail.py` | ⚠️ Partial (telemetry only) |
| `test_reboot_cause.py` (ASIC/BIOS mock) | `test_platform_reboot_cause.py` | ⚠️ Partial (software file only) |

**Legend:** ✅ Done · ⚠️ Partial · ❌ Missing · ➖ Not applicable on Vega

---

## What is still missing (out of scope or follow-up)

| Item | Owner / track | Notes |
|------|---------------|-------|
| **`pcie.yaml` / `pcied` / PCIE_DEVICES table** | UPSW-5953 / buildimage (Suku) | Not in this PR; add `pcied` to suite when `device/.../pcie.yaml` lands |
| **Module thermal (OSFP temp fault)** | Future vega test | Mellanox `check_sysfs` SFP loop; needs CMIS monitor data via xcvrd |
| **PSU power threshold mockers** | Future / optional | Mellanox `PsuPowerThresholdMocker` is hw-management specific |
| **ASIC/BIOS reboot cause mock** | Future buildimage | `platform.json` has `reboot_cause.hardware.enabled: false` today |
| **CPU crit/max threshold compare** | Future vega test | Could add via platform API high/critical thresholds |
| **Full mellanox EEPROM key parity** | Optional | Vega uses CMIS keys, not mellanox `util.check_sfp_eeprom_info` |
| **`mellanox_data.py` entry for Vega** | Optional | Platform counts hardcoded in `vega_data.py` instead |

---

## Test files in this folder

| File | What it checks |
|------|----------------|
| `test_platform_sensors.py` | Import, board/CPU thermals, fans CLI+hwmon, PSU CLI+hwmon, platform API |
| `test_platform_pmon.py` | `thermalctld`, `psud`, `xcvrd` RUNNING in pmon |
| `test_platform_transceiver.py` | Service SFPP + cabled OSFP presence/EEPROM |
| `test_platform_psu_detail.py` | PSU PMBus sysfs + platform API voltage/current/power |
| `test_platform_reboot_cause.py` | `/host/reboot-cause/reboot-cause.txt` readable |

Helpers: `check_platform.py`, `check_transceiver.py`, `vega_data.py`

---

## How to run (Minbo / lab)

```bash
git fetch origin vega-platform-tests
git checkout vega-platform-tests

# Full suite
pytest tests/platform_tests/vega/ \
  --inventory=<lab> \
  --host-pattern=upscalelab2-spine6-800 \
  -v

# By area
pytest tests/platform_tests/vega/test_platform_sensors.py -v --inventory=... --host-pattern=...
pytest tests/platform_tests/vega/test_platform_pmon.py -v --inventory=... --host-pattern=...
pytest tests/platform_tests/vega/test_platform_transceiver.py -v --inventory=... --host-pattern=...
pytest tests/platform_tests/vega/test_platform_psu_detail.py -v --inventory=... --host-pattern=...
pytest tests/platform_tests/vega/test_platform_reboot_cause.py -v --inventory=... --host-pattern=...

# Confirm mellanox hw-mgmt tests SKIP on Vega (not fail)
pytest tests/platform_tests/mellanox/test_check_sysfs.py \
  --inventory=... --host-pattern=upscalelab2-spine6-800 -v
```

### Prerequisites

- Platform: `x86_64-upscaleai_6540-r0`
- Image: `caspian-sonic-buildimage` branch `upscaleai/vega-test-rc-eth0` (or newer with `sonic_platform` wheel)
- PMON: `thermalctld`, `psud`, `xcvrd` running
- Transceiver tests: cabled OSFP in `conn_graph_facts`; `Ethernet512`/`520` always tested

---

## Related work

| Ticket / repo | Topic |
|---------------|-------|
| UPSW-5952 | hw-management sysfs failure — **this PR** |
| UPSW-5953 | `pcie.yaml` for `pcied` — **buildimage, separate** |
| `caspian-sonic-buildimage` | `6540/specs/DUT-VALIDATION.md` manual bring-up checklist |
