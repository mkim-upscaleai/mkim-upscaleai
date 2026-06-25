"""
Vega 6540 PMON / platform daemon smoke tests.

Replaces mellanox/test_hw_management_service.py for Vega: we validate the
daemons that consume sonic_platform, not hw-management.
"""
import logging
import pytest

from tests.common.platform.daemon_utils import check_pmon_daemon_enable_status
from . import vega_data as vd
from .check_platform import check_pmon_platform_daemons

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
]


@pytest.fixture(scope="module", autouse=True)
def skip_disabled_daemons(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    enabled = [d for d in vd.VEGA_PMON_DAEMONS if check_pmon_daemon_enable_status(duthost, d)]
    if not enabled:
        pytest.skip("No Vega platform PMON daemons enabled on this SKU")
    yield enabled


def test_pmon_platform_daemons_running(duthosts, rand_one_dut_hostname, skip_disabled_daemons):
    """thermalctld, psud, xcvrd running in pmon (Vega platform stack)."""
    duthost = duthosts[rand_one_dut_hostname]
    check_pmon_platform_daemons(duthost, skip_disabled_daemons)
