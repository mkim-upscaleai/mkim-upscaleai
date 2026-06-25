"""
Vega 6540 PSU detail tests.

Lightweight replacement for mellanox/test_psu_power_threshold.py — validates
telemetry via sonic_platform without hw-management threshold mockers.
"""
import pytest

from .check_platform import check_psu_platform_api, check_psu_pmbus_hwmon, check_psu_status

pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
]


def test_psu_cli_and_hwmon(duthosts, rand_one_dut_hostname):
    """PSU status CLI matches PMBus hwmon presence."""
    duthost = duthosts[rand_one_dut_hostname]
    check_psu_status(duthost)
    check_psu_pmbus_hwmon(duthost)


def test_psu_telemetry_platform_api(duthosts, rand_one_dut_hostname):
    """PSU voltage/current/power readable via sonic_platform."""
    duthost = duthosts[rand_one_dut_hostname]
    check_psu_platform_api(duthost)
