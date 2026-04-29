import pytest
import random
import logging
from tests.common.snappi_tests.common_helpers import enable_packet_aging, start_pfcwd, \
    get_bgp_redistribute_connected_hosts
from tests.conftest import generate_priority_lists

logger = logging.getLogger(__name__)


def _apply_redistribute_connected(duthost, apply=True):
    """Apply or remove 'redistribute connected' in BGP on a DUT via vtysh."""
    bgp_asn = duthost.shell(
        "redis-cli -n 4 hget 'DEVICE_METADATA|localhost' bgp_asn"
    )["stdout"].strip()
    if not bgp_asn:
        logger.warning("{}: could not read bgp_asn, skipping redistribute connected".format(
            duthost.hostname))
        return
    action = "redistribute connected" if apply else "no redistribute connected"
    duthost.shell(
        "docker exec bgp vtysh "
        "-c 'configure terminal' "
        "-c 'router bgp {}' "
        "-c 'address-family ipv4 unicast' "
        "-c '{}' "
        "-c 'end'".format(bgp_asn, action),
        module_ignore_errors=True
    )
    logger.info("{}: BGP {} in ASN {}".format(duthost.hostname, action, bgp_asn))


@pytest.fixture(autouse=True, scope="module")
def bgp_redistribute_connected(duthosts):
    """
    Ensure BGP 'redistribute connected' is applied on DUTs listed under
    bgp_redistribute_connected_hosts in variables.override.yml, and explicitly
    removed from all other DUTs. Runs once per test module.

    This is needed so that traffic-generator subnets attached to the egress DUT
    are reachable by the ingress DUT after any config_reload that wipes the FRR
    running configuration.
    """
    redistribute_hosts = set(get_bgp_redistribute_connected_hosts())
    if not redistribute_hosts:
        yield
        return

    for duthost in duthosts:
        if duthost.hostname in redistribute_hosts:
            _apply_redistribute_connected(duthost, apply=True)
        else:
            _apply_redistribute_connected(duthost, apply=False)

    yield

    # Teardown: remove redistribute connected from all DUTs we added it to
    for duthost in duthosts:
        if duthost.hostname in redistribute_hosts:
            _apply_redistribute_connected(duthost, apply=False)


@pytest.fixture(autouse=True, scope="module")
def rand_lossless_prio(request):
    """
    Fixture that randomly selects a lossless priority

    Args:
        request (object): pytest request object

    Yields:
        lossless priority (str): string containing 'hostname|lossless priority'

    """
    lossless_prios = generate_priority_lists(request, "lossless")
    if lossless_prios:
        yield random.sample(lossless_prios, 1)[0]
    else:
        yield 'unknown|unknown'


@pytest.fixture(autouse=True, scope="module")
def rand_lossy_prio(request):
    """
    Fixture that randomly selects a lossy priority

    Args:
        request (object): pytest request object

    Yields:
        lossy priority (str): string containing 'hostname|lossy priority'

    """
    lossy_prios = generate_priority_lists(request, "lossy")
    if lossy_prios:
        yield random.sample(lossy_prios, 1)[0]
    else:
        yield 'unknown|unknown'


@pytest.fixture(autouse=True, scope="module")
def start_pfcwd_after_test(duthosts, rand_one_dut_hostname):
    """
    Ensure that PFC watchdog is enabled with default setting after tests

    Args:
        duthosts (pytest fixture) : list of DUTs
        rand_one_dut_hostname (pytest fixture): DUT hostname

    Yields:
        N/A
    """
    yield

    duthost = duthosts[rand_one_dut_hostname]
    start_pfcwd(duthost)


@pytest.fixture(autouse=True, scope="module")
def enable_packet_aging_after_test(duthosts, rand_one_dut_hostname):
    """
    Ensure that packet aging is enabled after tests

    Args:
        duthosts (pytest fixture) : list of DUTs
        rand_one_dut_hostname (pytest fixture): DUT hostname

    Yields:
        N/A
    """
    yield

    duthost = duthosts[rand_one_dut_hostname]
    enable_packet_aging(duthost)
