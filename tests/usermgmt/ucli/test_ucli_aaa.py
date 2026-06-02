
import shlex
import pytest
import logging
import random # noqa F401
import re # noqa F401
import json # noqa F401
import time

from tests.common.reboot import reboot # noqa F401
from tests.common.config_reload import config_reload # noqa F401
from tests.common.fixtures.duthost_utils import backup_and_restore_config_db  # noqa F401
from tests.common.helpers.assertions import pytest_assert # noqa F401
from tests.common.utilities import wait, wait_until # noqa F401
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.platform.interface_utils import check_interface_status_of_up_ports # noqa F401

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.skip_check_dut_health,
    pytest.mark.disable_loganalyzer,
]

logger = logging.getLogger(__name__)
allure.logger = logger

def dut_run_retry(duthost, cmd, attempts: int = 5, wait_time_sec: int = 2):
    attempts = 1 if attempts < 1 else attempts
    while attempts > 0:
        result = duthost.shell(cmd, module_ignore_errors=True)
        if result['rc'] == 0:
            return result
        time.sleep(wait_time_sec)
        attempts = attempts - 1
    return result

# Requires: sudo apt install sshpass in HOST/TEST SERVER
def ssh_run_retry(localhost, remote_ip, username, password, cmd, attempts: int = 5, wait_time_sec: int = 2):
    attempts = 1 if attempts < 1 else attempts
    while attempts > 0:
        ssh_cmd = (
            f"sshpass -p {shlex.quote(password)} ssh "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"{shlex.quote(username)}@{shlex.quote(remote_ip)} {shlex.quote(cmd)}"
        )
        res = localhost.shell(
            ssh_cmd,
            module_ignore_errors=True,
        )
        if res['rc'] == 0:
            return res
        time.sleep(wait_time_sec)
        attempts = attempts - 1
    return res

def test_aaa_enable_radius(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-01: Enable AAA"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model"')
            assert result['rc'] == 0, 'AAA new model enable command failed'
            result = duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')
            assert result['rc'] == 0, 'AAA new model disable command failed'
            result = dut_run_retry(duthost, '! ucli -c "configure terminal" -c "aaa authentication login default group radius local"')
            assert result['rc'] == 0, 'AAA radius should not be allowed with no aaa new-model'

        with allure.step("AAA-02: Authentication using RADIUS with local fallback"):
            # Also covered by USER-MGMT-04
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authentication login default group radius local"')
            assert result['rc'] == 0, 'AAA could not set authentication radius'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')


def test_aaa_radius_authz(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-03: Radius Authorization (exec mode)"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authorization exec default group radius local"')
            assert result['rc'] == 0, 'AAA radius authz exec mode command failed'
        with allure.step("AAA-04: Radius Authorization (commands)"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authorization commands all default group radius local"')
            assert result['rc'] == 0, 'AAA radius authz all command failed'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')

def test_aaa_radius_acct(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-05: Radius Accounting for command logging"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa accounting commands all default start-stop group radius"')
            assert result['rc'] == 0, 'AAA radius acct all command failed'
        with allure.step("AAA-06: Radius Accounting for exec sessions"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa accounting exec default start-stop group radius"')
            assert result['rc'] == 0, 'AAA radius acct exec mode command failed'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')

def test_aaa_radius_server(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-07: RADIUS servers (with VRF)"):
            # This first one is also allowed
            result = duthost.shell(f'ucli -c "radius-server host {ptfhost.mgmt_ip} key 0 testing123"')
            assert result['rc'] == 0, 'radius server host setting command failed'
            # result = duthost.shell(f'ucli -c "radius-server host {ptfhost.mgmt_ip} key testing123"')
            # assert result['rc'] == 0, 'radius server host setting command failed'
            # result = duthost.shell(f'ucli -c "radius-server host {ptfhost.mgmt_ip} key testing123 vrf mgmt"')
            # assert result['rc'] == 0, 'radius server host setting with vrf command failed'
        with allure.step("AAA-08: Source interface for RADIUS packets"):
            result = duthost.shell('ucli -c "radius-server source-interface eth0"')
            assert result['rc'] == 0, 'radius server source interface setting command failed'
        with allure.step("AAA-09: Radius Timeout (seconds)"):
            result = duthost.shell('ucli -c "radius-server timeout 5"')
            assert result['rc'] == 0, 'radius server time out setting command failed'
        with allure.step("AAA-10: Radius Retransmit attempts"):
            result = duthost.shell('ucli -c "radius-server retransmit 3"')
            assert result['rc'] == 0, 'radius server retransmit setting command failed'
        with allure.step("AAA-11: Deadtime (minutes)"):
            result = duthost.shell('ucli -c "radius-server deadtime 1"')
            assert result['rc'] == 0, 'radius server deadtime setting command failed'

        result = duthost.shell('ucli -c "show radius"')
        # TODO: Check results to see all settings are displayed and/or some radius conf file
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')
        duthost.shell(f'ucli -c "configure terminal" -c "no radius-server host {ptfhost.mgmt_ip}"')

def test_aaa_enable_tacacs(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-13: Enable AAA Tacacs+"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model"')
            assert result['rc'] == 0, 'AAA new model enable command failed'

        with allure.step("AAA-14: Authentication using TACACS+ with local fallback"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authentication login default group tacacs+ local"')
            assert result['rc'] == 0, 'AAA could not set authentication tacacs'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')


def test_aaa_tacacs_authz(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-15: TACACS Authorization (exec and commands)"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authorization exec default group tacacs+ local"')
            assert result['rc'] == 0, 'AAA tacacs authz exec mode command failed'
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authorization commands all default group tacacs+ local"')
            assert result['rc'] == 0, 'AAA radius authz all command failed'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')

def test_aaa_tacacs_acct(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-16: TACACS Accounting"):
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa accounting commands all default start-stop group tacacs+"')
            assert result['rc'] == 0, 'AAA tacacs acct all command failed'
            result = duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa accounting exec default start-stop group tacacs+"')
            assert result['rc'] == 0, 'AAA tacacs acct exec mode command failed'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no aaa new-model"')

def test_aaa_tacacs_server(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-17: TACACS Multi Servers"):
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "tacacs-server host 172.17.0.101 key testing123"')
            result = dut_run_retry(duthost, f'ucli -c "show tacacs" | grep {ptfhost.mgmt_ip}')
            assert result['rc'] == 0, 'Issue with configuring multiple TACACS servers did not get configured'
            result = dut_run_retry(duthost, 'ucli -c "show tacacs" | grep 172.17.0.101')
            assert result['rc'] == 0, 'Issue with configuring multiple TACACS servers did not get configured'
    finally:
        duthost.shell(f'ucli -c "configure terminal" -c "no tacacs-server host {ptfhost.mgmt_ip}"')
        duthost.shell('ucli -c "configure terminal" -c "no tacacs-server host 172.17.0.101"')


def test_aaa_tacacs_server_vrf(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    if duthost.facts.get('asic_type') != 'vs':
        pytest.skip("test_aaa_tacacs_server_vrf is vs-only; adding the mgmt VRF can disconnect a physical DUT")

    try:
        with allure.step("AAA-18: TACACS VRF"):
            duthost.shell('sudo config vrf add mgmt')
            result = duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123 vrf mgmt"')
            assert result['rc'] == 0, 'AAA tacacs acct all command failed'
    finally:
        duthost.shell('sudo config vrf del mgmt', module_ignore_errors=True)

def test_aaa_reco_settings(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("AAA-19: TACACS Recommended Settings"):
            result = duthost.shell('ucli -c "configure terminal" -c "tacacs-server timeout 5"')
            assert result['rc'] == 0, 'tacacs-server timeout setting failed'
            result = duthost.shell('ucli -c "configure terminal" -c "tacacs-server source-interface eth0"')
            assert result['rc'] == 0, 'tacacs-server source-interface setting failed'
            result = duthost.shell('ucli -c "configure terminal" -c "tacacs-server directed-request"')
            assert result['rc'] == 0, 'tacacs-server directed-request setting failed'
            result = duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} single-connection"')
            assert result['rc'] == 0, 'tacacs-server single-connection setting failed for primary server'
            result = duthost.shell('ucli -c "configure terminal" -c "tacacs-server host 172.17.0.102 single-connection"')
            assert result['rc'] == 0, 'tacacs-server single-connection setting failed for secondary server'
            # TODO: Check /etc/tacplus_nss.conf or /etc/tacacs to make sure effect was done
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no tacacs-server host 172.17.0.102"')
        duthost.shell(f'ucli -c "configure terminal" -c "no tacacs-server host {ptfhost.mgmt_ip}"')

def test_aaa_non_spec_radius(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {ptfhost.mgmt_ip}" -c "radius-server key 0 testing123"')
        duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authentication login default group radius local"')
        result = ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", "show version")
        assert result['rc'] == 0, "RADIUS user cannot login"
    finally:
        duthost.shell(f'ucli -c "configure terminal" -c "no radius-server host {ptfhost.mgmt_ip}" -c "no aaa new-model"')

def test_aaa_non_spec_tacacs(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} port 49 auth-type login priority 1" -c "tacacs-server key 0 testing123"')
        duthost.shell('ucli -c "configure terminal" -c "aaa new-model" -c "aaa authentication login default group tacacs+ local"')
        result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva1", "tacshiva1pw", "show version")
        assert result['rc'] == 0, "TACACS user cannot login"
    finally:
        duthost.shell(f'ucli -c "configure terminal" -c "no tacacs-server host {ptfhost.mgmt_ip}" -c "no aaa new-model"')
