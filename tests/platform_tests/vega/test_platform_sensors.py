"""
Vega 6540 platform sensor tests.

Functional equivalents of mellanox/check_sysfs.py checks, adapted for the
FPGA sonic_platform stack (see UPSW-5952 / SONiC-6540-PORTING-NOTES.md).
"""
import logging
import pytest

from .check_platform import (
    check_board_thermals,
    check_cpu_thermals,
    check_fan_drawers,
    check_fan_tray_hwmon_rpm,
    check_fpga_thermal_hwmon,
    check_psu_pmbus_hwmon,
    check_psu_platform_api,
    check_psu_status,
    check_sonic_platform_import,
    check_thermal_platform_api,
)

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
]


def test_sonic_platform_import(duthosts, rand_one_dut_hostname):
    """sonic_platform wheel loads in pmon and reports expected device counts."""
    duthost = duthosts[rand_one_dut_hostname]
    check_sonic_platform_import(duthost)


def test_board_thermal_sensors(duthosts, rand_one_dut_hostname):
    """TMP1075 board sensors (replaces hw-management thermal/asic check)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_board_thermals(duthost)


def test_cpu_thermal_sensors(duthosts, rand_one_dut_hostname):
    """COMX coretemp via host_hwmon (replaces hw-management CPU thermal sysfs)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_cpu_thermals(duthost)


def test_fan_drawers(duthosts, rand_one_dut_hostname):
    """4 fan trays x 2 fans via ADT7476 (replaces hw-management fan sysfs)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_fan_drawers(duthost)


def test_fan_tray_hwmon_rpm(duthosts, rand_one_dut_hostname):
    """Fan RPM in range via ADT7476 hwmon (replaces hw-management fan speed check)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_fan_tray_hwmon_rpm(duthost)


def test_psu_status(duthosts, rand_one_dut_hostname):
    """Lower/Upper PSU via PMBus + OOB (replaces hw-management PSU sysfs)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_psu_status(duthost)


def test_psu_pmbus_hwmon(duthosts, rand_one_dut_hostname):
    """PSU PMBus hwmon on FPGA buses 36-37."""
    duthost = duthosts[rand_one_dut_hostname]
    check_psu_pmbus_hwmon(duthost)


def test_psu_platform_api(duthosts, rand_one_dut_hostname):
    """PSU voltage/current/power via sonic_platform API."""
    duthost = duthosts[rand_one_dut_hostname]
    check_psu_platform_api(duthost)


def test_thermal_platform_api(duthosts, rand_one_dut_hostname):
    """Thermal readings via sonic_platform API."""
    duthost = duthosts[rand_one_dut_hostname]
    check_thermal_platform_api(duthost)


def test_fpga_thermal_hwmon_sysfs(duthosts, rand_one_dut_hostname):
    """Direct I2C hwmon nodes for TMP1075 on FPGA bus 30."""
    duthost = duthosts[rand_one_dut_hostname]
    check_fpga_thermal_hwmon(duthost)
