"""
Vega 6540 transceiver tests (CMIS / OSFP via xcvrd + sonic_platform).

Replaces mellanox/test_check_sfp_presence.py and test_check_sfp_eeprom.py.
"""
import pytest

from tests.common.fixtures.conn_graph_facts import conn_graph_facts  # noqa F401
from .check_transceiver import (
    check_service_sfpp_presence,
    check_transceiver_eeprom,
    check_transceiver_presence,
    connected_test_interfaces,
    SHOW_EEPROM_CMDS,
)

pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
]


@pytest.fixture(scope="module")
def vega_connected_intfs(duthosts, rand_one_dut_hostname, conn_graph_facts, xcvr_skip_list):  # noqa F811
    duthost = duthosts[rand_one_dut_hostname]
    interfaces = connected_test_interfaces(duthost, conn_graph_facts, xcvr_skip_list)
    if not interfaces:
        pytest.skip("No cabled interfaces in conn_graph for transceiver tests")
    return interfaces


def test_service_sfpp_presence(duthosts, rand_one_dut_hostname):
    """On-board service SFPP ports Ethernet512/Ethernet520."""
    duthost = duthosts[rand_one_dut_hostname]
    check_service_sfpp_presence(duthost)


def test_transceiver_presence_connected_ports(duthosts, rand_one_dut_hostname, vega_connected_intfs):
    """Cabled OSFP ports report Present."""
    duthost = duthosts[rand_one_dut_hostname]
    check_transceiver_presence(duthost, vega_connected_intfs)


@pytest.mark.parametrize("show_eeprom_cmd", SHOW_EEPROM_CMDS)
def test_transceiver_eeprom_connected_ports(
    duthosts, rand_one_dut_hostname, vega_connected_intfs, show_eeprom_cmd,
):
    """CMIS EEPROM fields on cabled ports (replaces mellanox SFP EEPROM check)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_transceiver_eeprom(duthost, vega_connected_intfs, show_eeprom_cmd)
