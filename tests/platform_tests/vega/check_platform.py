"""
Reusable checks for Vega 6540 platform bring-up.

These mirror the *intent* of tests/platform_tests/mellanox/check_sysfs.py but
validate FPGA-backed sonic_platform paths instead of /var/run/hw-management/*.
"""
import logging
import re

from . import vega_data as vd

logger = logging.getLogger(__name__)

_TEMP_LINE = re.compile(
    r"^(?P<name>\S+)\s+(?P<temp>-?\d+(?:\.\d+)?|N/A)\s+",
    re.MULTILINE,
)


def _parse_show_platform_temperature(output):
    """Return {sensor_name: temp_celsius_or_None}."""
    readings = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("Thermal"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        try:
            readings[name] = float(parts[1])
        except ValueError:
            readings[name] = None
    return readings


def _parse_show_platform_fan(output):
    """Return list of dicts with fan drawer/fan fields from CLI table."""
    fans = []
    header_seen = False
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        if "Drawer" in line and "Fan" in line:
            header_seen = True
            continue
        if not header_seen:
            continue
        parts = line.split()
        if len(parts) >= 4:
            fans.append({
                "drawer": parts[0],
                "fan": parts[1],
                "speed": parts[2],
                "direction": parts[3] if len(parts) > 3 else "",
                "presence": parts[4] if len(parts) > 4 else "",
                "status": parts[5] if len(parts) > 5 else "",
            })
    return fans


def _parse_show_platform_psustatus(output):
    """Return list of PSU status rows (name, model, serial, ...)."""
    psus = []
    header_seen = False
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        if line.lower().startswith("psu"):
            header_seen = True
            continue
        if not header_seen:
            continue
        parts = line.split()
        if parts:
            psus.append(parts[0])
    return psus


def check_sonic_platform_import(dut):
    """Verify sonic_platform is importable inside pmon."""
    cmd = (
        "docker exec pmon python3 -c "
        "\"from sonic_platform.chassis import Chassis; "
        "c=Chassis(); "
        "print(len(c.get_all_thermals()), len(c.get_all_psus()), len(c.get_all_fan_drawers()))\""
    )
    result = dut.command(cmd)
    assert result["rc"] == 0, "sonic_platform import failed in pmon: {}".format(result)
    parts = result["stdout"].strip().split()
    assert len(parts) == 3, "Unexpected sonic_platform summary: {}".format(result["stdout"])
    thermals, psus, drawers = map(int, parts)
    assert thermals >= len(vd.BOARD_THERMAL_NAMES), \
        "Expected >= {} thermals, got {}".format(len(vd.BOARD_THERMAL_NAMES), thermals)
    assert psus == vd.PSU_COUNT, "Expected {} PSUs, got {}".format(vd.PSU_COUNT, psus)
    assert drawers == vd.FAN_DRAWER_COUNT, \
        "Expected {} fan drawers, got {}".format(vd.FAN_DRAWER_COUNT, drawers)


def check_board_thermals(dut):
    """Board TMP1075 sensors via show platform temperature / sonic_platform."""
    output = dut.command("show platform temperature")["stdout"]
    readings = _parse_show_platform_temperature(output)
    assert readings, "show platform temperature returned no data: {}".format(output)

    missing = []
    bad = []
    for name in vd.BOARD_THERMAL_NAMES:
        if name not in readings:
            missing.append(name)
            continue
        temp = readings[name]
        if temp is None:
            bad.append("{}=N/A".format(name))
        elif not (vd.MIN_BOARD_TEMP_C <= temp <= vd.MAX_BOARD_TEMP_C):
            bad.append("{}={}".format(name, temp))

    assert not missing, "Missing board thermal sensors: {}".format(missing)
    assert not bad, "Board thermal out of range: {}".format(bad)
    logger.info("Board thermals OK: %s", {k: readings[k] for k in vd.BOARD_THERMAL_NAMES})


def check_cpu_thermals(dut):
    """Host coretemp sensors (CPU Package / CPU Core N)."""
    output = dut.command("show platform temperature")["stdout"]
    readings = _parse_show_platform_temperature(output)

    cpu_sensors = {
        name: temp for name, temp in readings.items()
        if name.startswith(vd.CPU_THERMAL_PREFIXES)
    }
    assert cpu_sensors, "No CPU thermal sensors in show platform temperature"

    bad = []
    for name, temp in cpu_sensors.items():
        if temp is None:
            bad.append("{}=N/A".format(name))
        elif not (vd.MIN_CPU_TEMP_C <= temp <= vd.MAX_CPU_TEMP_C):
            bad.append("{}={}".format(name, temp))
    assert not bad, "CPU thermal out of range: {}".format(bad)
    logger.info("CPU thermals OK: %s", cpu_sensors)


def check_fan_drawers(dut):
    """Fan trays via show platform fan (ADT7476 behind FPGA)."""
    output = dut.command("show platform fan")["stdout"]
    fans = _parse_show_platform_fan(output)
    assert len(fans) >= vd.FAN_COUNT, \
        "Expected >= {} fans, parsed {} from:\n{}".format(vd.FAN_COUNT, len(fans), output)

    not_present = [f for f in fans if f.get("presence", "").lower() == "false"]
    not_ok = [f for f in fans if f.get("status", "").lower() not in ("", "ok", "true")]
    assert not not_present, "Fans not present: {}".format(not_present)
    assert not not_ok, "Fans not OK: {}".format(not_ok)
    logger.info("Fan status OK (%d fans reported)", len(fans))


def check_fan_tray_hwmon_rpm(dut):
    """ADT7476 fan RPM via direct hwmon on FPGA fan-tray buses (32-35)."""
    bad = []
    for bus in vd.FAN_TRAY_BUSES:
        for fan_attr in ("fan1_input", "fan2_input"):
            glob_path = "/sys/bus/i2c/devices/{}-002c/hwmon/hwmon*/{}".format(bus, fan_attr)
            result = dut.command(
                "sh -c 'for f in {}; do cat \"$f\"; done'".format(glob_path),
                module_ignore_errors=True,
            )
            if result["rc"] != 0 or not result["stdout"].strip():
                bad.append("bus{} {}".format(bus, fan_attr))
                continue
            try:
                rpm = int(result["stdout"].strip().splitlines()[0])
            except ValueError:
                bad.append("bus{} {} invalid: {}".format(bus, fan_attr, result["stdout"].strip()))
                continue
            if not (vd.MIN_FAN_RPM <= rpm <= vd.MAX_FAN_RPM):
                bad.append("bus{} {} rpm={}".format(bus, fan_attr, rpm))
    assert not bad, "Fan tray hwmon RPM check failed: {}".format(bad)


def check_psu_status(dut):
    """PSU telemetry via show platform psustatus."""
    output = dut.command("show platform psustatus")["stdout"]
    psus = _parse_show_platform_psustatus(output)
    assert len(psus) >= vd.PSU_COUNT, \
        "Expected >= {} PSUs, got {} from:\n{}".format(vd.PSU_COUNT, len(psus), output)
    logger.info("PSU status OK: %s", psus)


def check_psu_pmbus_hwmon(dut):
    """PMBus hwmon nodes for lower/upper PSU (buses 36-37 @ 0x58)."""
    bad = []
    for bus in vd.PSU_PMBUS_BUSES:
        base = "/sys/bus/i2c/devices/{}-0058/hwmon/hwmon*".format(bus)
        for attr in ("in1_input", "curr1_input", "power1_input"):
            result = dut.command(
                "sh -c 'for f in {}/{}; do test -f \"$f\" && cat \"$f\"; done'".format(base, attr),
                module_ignore_errors=True,
            )
            if result["rc"] != 0 or not result["stdout"].strip():
                bad.append("bus{} missing {}".format(bus, attr))
                continue
            try:
                value = int(result["stdout"].strip().splitlines()[0])
            except ValueError:
                bad.append("bus{} {} invalid".format(bus, attr))
                continue
            if value < 0:
                bad.append("bus{} {} negative".format(bus, attr))
    assert not bad, "PSU PMBus hwmon check failed: {}".format(bad)


def _pmon_eval(dut, python_expr):
    """Run a one-liner against sonic_platform.Chassis inside pmon."""
    cmd = (
        "docker exec pmon python3 -c "
        "\"from sonic_platform.chassis import Chassis; "
        "c=Chassis(); {}\""
    ).format(python_expr)
    return dut.command(cmd)


def check_psu_platform_api(dut):
    """PSU presence and telemetry via sonic_platform (replaces hw-management PSU sysfs)."""
    result = _pmon_eval(
        dut,
        "psus=[(p.get_name(), p.get_presence(), p.get_voltage(), p.get_current(), p.get_power()) "
        "for p in c.get_all_psus()]; print(psus)",
    )
    assert result["rc"] == 0, "PSU platform API query failed: {}".format(result)
    assert "True" in result["stdout"] or "1" in result["stdout"], \
        "No PSU reports present: {}".format(result["stdout"])
    logger.info("PSU platform API: %s", result["stdout"].strip())


def check_thermal_platform_api(dut):
    """All board + CPU thermals return valid readings via sonic_platform."""
    result = _pmon_eval(
        dut,
        "temps=[(t.get_name(), t.get_temperature()) for t in c.get_all_thermals() "
        "if t.get_temperature() is not None]; print(len(temps), temps[:5])",
    )
    assert result["rc"] == 0, "Thermal platform API query failed: {}".format(result)
    parts = result["stdout"].strip().split(None, 1)
    assert parts and int(parts[0]) >= len(vd.BOARD_THERMAL_NAMES), \
        "Too few valid thermals from platform API: {}".format(result["stdout"])


def check_fpga_thermal_hwmon(dut):
    """Direct sysfs: TMP1075 hwmon nodes on FPGA bus 30."""
    missing = []
    for addr in vd.FPGA_THERMAL_ADDRS:
        glob_path = "/sys/bus/i2c/devices/{}-{}/hwmon/hwmon*/temp1_input".format(
            vd.FPGA_THERMAL_BUS, addr)
        result = dut.command("ls {}".format(glob_path), module_ignore_errors=True)
        if result["rc"] != 0 or not result["stdout"].strip():
            missing.append("{}-{}".format(vd.FPGA_THERMAL_BUS, addr))
    assert not missing, "Missing TMP1075 hwmon under bus {}: {}".format(
        vd.FPGA_THERMAL_BUS, missing)


def check_pmon_platform_daemons(dut, daemon_names):
    """Verify listed PMON supervisor programs are RUNNING."""
    not_running = []
    for daemon in daemon_names:
        status = dut.command(
            "docker exec pmon supervisorctl status {}".format(daemon),
            module_ignore_errors=True,
        )
        if "RUNNING" not in status["stdout"]:
            not_running.append((daemon, status["stdout"].strip()))
    assert not not_running, "PMON daemons not running: {}".format(not_running)


def check_reboot_cause_readable(dut):
    """Software reboot cause file exists (hardware latch not enabled on Vega yet)."""
    result = dut.command("test -f {} && cat {}".format(
        vd.REBOOT_CAUSE_HOST_FILE, vd.REBOOT_CAUSE_HOST_FILE), module_ignore_errors=True)
    assert result["rc"] == 0, "Reboot cause file missing: {}".format(vd.REBOOT_CAUSE_HOST_FILE)
    assert result["stdout"].strip(), "Reboot cause file is empty"
    logger.info("Reboot cause: %s", result["stdout"].strip()[:200])
