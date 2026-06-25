"""
Transceiver checks for Vega 6540 (CMIS / OSFP via xcvrd + sonic_platform).

Replaces mellanox/test_check_sfp_presence.py and test_check_sfp_eeprom.py for
platforms that do not use mlxlink / hw-management module sysfs.
"""
import logging

from tests.common.platform.transceiver_utils import parse_sfp_eeprom_infos
from . import vega_data as vd

logger = logging.getLogger(__name__)

SHOW_PRESENCE_CMD = "show interface transceiver presence {}"
SHOW_EEPROM_CMDS = [
    "show interface transceiver eeprom -d",
    "sudo sfputil show eeprom -d",
]


def connected_test_interfaces(duthost, conn_graph_facts, xcvr_skip_list):
    """Front-panel interfaces cabled in the testbed topology."""
    skip = set(xcvr_skip_list.get(duthost.hostname, []))
    device_conn = conn_graph_facts.get("device_conn", {}).get(duthost.hostname, {})
    return [intf for intf in device_conn if intf not in skip]


def check_transceiver_presence(duthost, interfaces):
    """Connected ports report Present via show interface transceiver presence."""
    assert interfaces, "No connected interfaces from conn_graph_facts to check"

    missing = []
    for intf in interfaces:
        output = duthost.command(SHOW_PRESENCE_CMD.format(intf), module_ignore_errors=True)
        if output["rc"] != 0:
            missing.append("{}: cmd failed".format(intf))
            continue
        lines = [ln.strip() for ln in output["stdout_lines"] if ln.strip()]
        body = " ".join(lines[2:]) if len(lines) > 2 else output["stdout"]
        if "Present" not in body:
            missing.append("{}: {}".format(intf, body))
    assert not missing, "Transceiver not present on connected ports: {}".format(missing)
    logger.info("Transceiver presence OK on %d connected ports", len(interfaces))


def check_service_sfpp_presence(duthost):
    """On-board service SFPP ports (Ethernet512/520) are always present."""
    missing = []
    for intf in vd.SERVICE_SFPP_PORTS:
        output = duthost.command(SHOW_PRESENCE_CMD.format(intf), module_ignore_errors=True)
        if output["rc"] != 0 or "Present" not in output["stdout"]:
            missing.append(intf)
    assert not missing, "Service SFPP not present: {}".format(missing)


def _cmis_eeprom_has_required_keys(eeprom_info):
    if not isinstance(eeprom_info, dict):
        return False, "eeprom is not a dict"
    if eeprom_info in ("SFP EEPROM Not detected", "Not detected"):
        return False, "not detected"
    found = [k for k in vd.CMIS_EEPROM_KEYS if k in eeprom_info]
    if len(found) < 2:
        return False, "expected >=2 of {} found {}".format(vd.CMIS_EEPROM_KEYS, found)
    return True, found


def check_transceiver_eeprom(duthost, interfaces, show_eeprom_cmd):
    """Parse transceiver EEPROM output; validate CMIS fields on connected ports."""
    output = duthost.command(show_eeprom_cmd, module_ignore_errors=True)
    assert output["rc"] == 0, "Failed to read EEPROM via {}: {}".format(show_eeprom_cmd, output)

    eeprom_map = parse_sfp_eeprom_infos(output["stdout"])
    assert eeprom_map, "No transceiver EEPROM entries parsed from {}".format(show_eeprom_cmd)

    bad = []
    checked = 0
    for intf in interfaces:
        if intf not in eeprom_map:
            bad.append("{}: missing from eeprom dump".format(intf))
            continue
        ok, detail = _cmis_eeprom_has_required_keys(eeprom_map[intf])
        if not ok:
            if detail == "not detected":
                bad.append("{}: EEPROM not detected".format(intf))
            else:
                bad.append("{}: {}".format(intf, detail))
        else:
            checked += 1
            logger.info("%s EEPROM keys: %s", intf, detail)

    assert checked > 0, "No connected port passed EEPROM validation: {}".format(bad)
    assert not bad, "EEPROM validation failures: {}".format(bad)
