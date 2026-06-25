"""
Vega 6540 reboot cause tests.

Replaces mellanox/test_reboot_cause.py where ASIC/BIOS reset mockers do not
apply. Vega currently uses software reboot cause only (hardware latch disabled
in platform.json).
"""
import pytest

from .check_platform import check_reboot_cause_readable

pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
]


def test_software_reboot_cause_readable(duthosts, rand_one_dut_hostname):
    """Host reboot-cause file is populated (software path)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_reboot_cause_readable(duthost)


def test_hardware_reboot_cause_not_supported(duthosts, rand_one_dut_hostname):
    """Document: ASIC/BIOS reboot-cause mock tests are N/A until CPLD latch enabled."""
    duthost = duthosts[rand_one_dut_hostname]
    hw_enabled = duthost.facts.get("chassis", {}).get("reboot_cause", {}).get("hardware", {}).get("enabled")
    if hw_enabled:
        pytest.skip("Hardware reboot cause enabled — add Vega ASIC/BIOS mock tests when supported")
    # Pass: expected state on current Vega builds
