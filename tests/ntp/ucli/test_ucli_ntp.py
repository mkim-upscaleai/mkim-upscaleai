import pytest
import logging
import re
import time
import ast

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure


pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.skip_check_dut_health,
    pytest.mark.disable_loganalyzer
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

def time_check_retry(duthost, ptfhost, attempts: int = 5, wait_time_sec: int = 180):
    attempts = 1 if attempts < 1 else attempts
    while attempts > 0:
        duttime = int(duthost.shell(r"date +%s")['stdout'])
        ptftime = int(ptfhost.shell(r"date +%s")['stdout'])
        if abs(duttime - ptftime) < 2:
            return True
        time.sleep(wait_time_sec)
        attempts = attempts - 1
    return False

def test_ntp_manual_clock_set(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "NTP|global"')
    old = {}
    try:
        old = ast.literal_eval(result['stdout'])
    except Exception as exc:
        raise AssertionError('Failed to parse CONFIG_DB NTP|global') from exc
    result = duthost.shell('date +"%Y-%m-%d %H:%M:%S"')
    now = result['stdout'].strip()

    try:
        with allure.step("NTP-REQ-01: Manual Clock Set"):
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
            # Not an industry standard CLI
            result = dut_run_retry(duthost, 'ucli -c "configure terminal" -c "clock set 12:34:56 01 Jan 2026"')
            assert result['rc'] == 0, 'UCLI command failed to set clock'

        with allure.step("NTP-REQ-19: NTP show clock"):
            result = dut_run_retry(duthost, 'ucli -c "show clock" | grep -E "Thu Jan 01 12:[0-9]{2}:[0-9]{2} 2026"')
            assert result['rc'] == 0, 'UCLI show clock did not show the correct time'

    finally:
        duthost.shell(f"sudo timedatectl set-time '{now}'", module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB DEL "NTP|global"', module_ignore_errors=True)
        for k, v in old.items():
            duthost.shell(f'sonic-db-cli CONFIG_DB HSET "NTP|global" "{k}" "{v}"', module_ignore_errors=True)

def test_ntp_timezone(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
    old_timezone = ast.literal_eval(result['stdout'])['timezone']
    try:
        with allure.step("NTP-REQ-02: Timezone Configuration"):
            duthost.shell('ucli -c "configure terminal" -c "clock timezone America Los_Angeles"')
            result = dut_run_retry(duthost, 'timedatectl status | grep "Time zone: America/Los_Angeles"')
            assert result['rc'] == 0, 'Time zone not set correctly from timedatectl status'
            result = dut_run_retry(duthost, 'ucli -c "show clock" | grep "Timezone: America/Los_Angeles"')
            assert result['rc'] == 0, 'Timezone not set correctly from UCLI'

            duthost.shell('ucli -c "configure terminal" -c "no clock timezone"')
            result = dut_run_retry(duthost, 'timedatectl status | grep "Time zone: UTC"')
            assert result['rc'] == 0, 'Time zone not set correctly from timedatectl status'
            result = dut_run_retry(duthost, 'ucli -c "show clock" | grep "Timezone: UTC"')
            assert result['rc'] == 0, 'Timezone not set correctly from UCLI'
    finally:
        duthost.shell(f'sonic-db-cli CONFIG_DB HSET "DEVICE_METADATA|localhost" timezone "{old_timezone}"', module_ignore_errors=True)

def test_ntp_disable_enable(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "NTP|global"')
    old = ast.literal_eval(result['stdout'])

    try:
        with allure.step("NTP-REQ-03: Disable and Enable NTP"):
            duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
            result = dut_run_retry(duthost, 'timedatectl status | grep "NTP service: inactive"')
            assert result['rc'] == 0, "NTP service active when it should not be"

            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "NTP|global"')
            d = ast.literal_eval(result['stdout'])
            assert d['admin_state'] == 'disabled', 'CONFIG_DB did not show correct admin_state'

            result = duthost.shell('ucli -c "show ntp configured"')
            pattern = r"State\s*:\s*Disabled"
            assert re.search(pattern, result['stdout']), 'UCLI shows ntp is not disabled when it should be'

            duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
            result = dut_run_retry(duthost, 'timedatectl status | grep "NTP service: active"')
            assert result['rc'] == 0, "NTP service active when it should not be"

            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "NTP|global"')
            d = ast.literal_eval(result['stdout'])
            assert d['admin_state'] == 'enabled', 'CONFIG_DB did not show correct admin_state'

            result = duthost.shell('ucli -c "show ntp configured"')
            pattern = r"State\s*:\s*Enabled"
            assert re.search(pattern, result['stdout']), 'UCLI shows ntp is not disabled when it should be'

    finally:
        duthost.shell('sonic-db-cli CONFIG_DB DEL "NTP|global"', module_ignore_errors=True)
        for k, v in old.items():
            duthost.shell(f'sonic-db-cli CONFIG_DB HSET "NTP|global" "{k}" "{v}"')

@pytest.mark.device_type('vs') # VRFs are dangerous
def test_ntp_vrf(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        duthost.shell('sudo config vrf add mgmt')
        result = dut_run_retry(duthost, 'show mgmt-vrf | grep "vrf table 5000"')
        assert result['rc'] == 0, 'MGMT VRF did not come up for NTP'

        with allure.step("NTP-REQ-04: NTP VRF"):
            duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ip}"')
            duthost.shell('ucli -c "configure terminal" -c "ntp vrf mgmt enable"')
            duthost.shell('sudo systemctl restart chrony')
            result = dut_run_retry(duthost, 'sudo ip vrf mgmt chronyc sources')
            assert result['rc'] == 0, 'NTP was not moved into VRF'

            duthost.shell('ucli -c "configure terminal" -c "ntp vrf default enable"')
            duthost.shell('sudo systemctl restart chrony')
            result = dut_run_retry(duthost, 'chronyc sources')
            assert result['rc'] == 0, 'NTP was not moved backed to default'

    finally:
        duthost.shell(f'sudo config ntp del {ptfhost.mgmt_ip}', module_ignore_errors=True)
        duthost.shell('sudo config vrf del mgmt', module_ignore_errors=True)

def test_ntp_server_config(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("NTP-REQ-05: NTP Server Configuration IPv4"):
            duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ip}"')
            result = dut_run_retry(duthost, f'cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "IPv4 NTP server configuration failed"
            duthost.shell(f'ucli -c "configure terminal" -c "no ntp server {ptfhost.mgmt_ip}"')
            result = dut_run_retry(duthost, f'! cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "IPv4 no NTP server configuration failed"

        with allure.step("NTP-REQ-24: NTP Server Configuration IPv6"):
            duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ipv6} iburst"')
            result = dut_run_retry(duthost, f'cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ipv6}"')
            assert result['rc'] == 0, "IPv6 NTP server configuration failed"
            duthost.shell(f'ucli -c "configure terminal" -c "no ntp server {ptfhost.mgmt_ipv6}"')
            result = dut_run_retry(duthost, f'! cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ipv6}"')
            assert result['rc'] == 0, "IPv6 no NTP server configuration failed"

        with allure.step("NTP-REQ-23: NTP Server Configuration Hostname"):
            duthost.shell('ucli -c "configure terminal" -c "ntp server time.windows.com"')
            result = dut_run_retry(duthost, 'cat /etc/chrony/chrony.conf | grep "time.windows.com"')
            assert result['rc'] == 0, "Hostname NTP server configuration failed"
            duthost.shell('ucli -c "configure terminal" -c "no ntp server time.windows.com"')
            result = dut_run_retry(duthost, '! cat /etc/chrony/chrony.conf | grep "time.windows.com"')
            assert result['rc'] == 0, "Hostname no NTP server configuration failed"

        with allure.step("NTP-REQ-07: NTP Server disable temporarily"):
            duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ip}"')
            result = dut_run_retry(duthost, f'cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "NTP server configuration failed before temporary disable"
            duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ip} disable"')
            result = dut_run_retry(duthost, f'! cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "NTP server configuration failed after temporary disable"
            duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ip} enable"')
            result = dut_run_retry(duthost, f'cat /etc/chrony/chrony.conf | grep "server {ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "NTP server configuration failed after temporary re-enable"

            # Sanity check
            duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
            result = dut_run_retry(duthost, fr'chronyc sources | grep -E "\^.* {ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "Could not use NTP server after temporary disable/enable"

    finally:
        # SONiC
        duthost.shell(f'sudo config ntp del {ptfhost.mgmt_ip}', module_ignore_errors=True)
        duthost.shell(f'sudo config ntp del {ptfhost.mgmt_ipv6}', module_ignore_errors=True)
        duthost.shell('sudo config ntp del time.windows.com', module_ignore_errors=True)

def test_ntp_one_time_sync(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    result = duthost.shell('date +"%Y-%m-%d %H:%M:%S"')
    now = result['stdout'].strip()

    try:
        with allure.step("NTP-REQ-11: NTP one time sync"):
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
            # Not an industry standard CLI
            result = dut_run_retry(duthost, 'ucli -c "configure terminal" -c "clock set 12:34:56 2026 Jan 01"')
            assert result['rc'] == 0, 'UCLI command failed to set clock'
            result = dut_run_retry(duthost, 'ucli -c "show clock" | grep -E "Thu Jan 01 12:[0-9]{2}:[0-9]{2} 2026"')
            assert result['rc'] == 0, 'UCLI show clock did not show the correct time after clock set'
            duthost.shell(f'ucli -c "configure terminal" -c "ntp sync {ptfhost.mgmt_ip}"')
            result = dut_run_retry(duthost, '! ucli -c "show clock" | grep -E "Thu Jan 01 12:[0-9]{2}:[0-9]{2} 2026"')
            assert result['rc'] == 0, 'UCLI show clock did not show the correct time after one time sync'

    finally:
        duthost.shell(f"sudo timedatectl set-time '{now}'", module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB HSET "NTP|global" "admin_state" "enabled"', module_ignore_errors=True)

def test_ntp_show_all(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
        duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ip}"')
        duthost.shell(f'ucli -c "configure terminal" -c "ntp server {ptfhost.mgmt_ipv6}"')

        with allure.step("NTP-REQ-21: NTP show ntp configured"):
            result = dut_run_retry(duthost, 'ucli -c "show ntp configured" | grep -E "State.*Enabled"')
            assert result['rc'] == 0, "UCLI show ntp configured failed: state"
            result = dut_run_retry(duthost, f'ucli -c "show ntp configured" | grep -E "{ptfhost.mgmt_ip}.*enabled"')
            assert result['rc'] == 0, "UCLI show ntp configured failed: ipv4"
            result = dut_run_retry(duthost, f'ucli -c "show ntp configured" | grep -E "{ptfhost.mgmt_ipv6}.*enabled"')
            assert result['rc'] == 0, "UCLI show ntp configured failed: ipv6"
            result = dut_run_retry(duthost, 'ucli -c "show ntp configured" | grep -E "VRF.*default"')
            assert result['rc'] == 0, "UCLI show ntp configured failed: ipv6"

        with allure.step("NTP-REQ-20: NTP show ntp"):
            result = dut_run_retry(duthost, 'ucli -c "show ntp" | grep "Reference ID"')
            assert result['rc'] == 0, "UCLI show ntp failed"
            result = dut_run_retry(duthost, f'ucli -c "show ntp" | grep "{ptfhost.mgmt_ip}"')
            assert result['rc'] == 0, "UCLI show ntp failed ipv4"
            result = dut_run_retry(duthost, f'ucli -c "show ntp" | grep "{ptfhost.mgmt_ipv6}"')
            assert result['rc'] == 0, "UCLI show ntp failed ipv6"

    finally:
        duthost.shell(f'sudo config ntp del {ptfhost.mgmt_ip}', module_ignore_errors=True)
        duthost.shell(f'sudo config ntp del {ptfhost.mgmt_ipv6}', module_ignore_errors=True)

def test_ntp_time_changes(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
        result = ptfhost.shell('date +%s')
        ptftime = int(result['stdout'].strip())
        duthost.shell(f'ucli -c "configure terminal" -c "clock set $(date -d @{ptftime - 10} +\'%H:%M:%S %Y %b %d\')"')
        duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
        assert time_check_retry(duthost, ptfhost), "Time is closely behind failed to sync"

        duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
        result = ptfhost.shell('date +%s')
        ptftime = int(result['stdout'].strip())
        duthost.shell(f'ucli -c "configure terminal" -c "clock set $(date -d @{ptftime + 10} +\'%H:%M:%S %Y %b %d\')"')
        duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
        assert time_check_retry(duthost, ptfhost), "Time is closely ahead failed to sync"

        duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
        result = ptfhost.shell('date +%s')
        ptftime = int(result['stdout'].strip())
        duthost.shell(f'ucli -c "configure terminal" -c "clock set $(date -d @{ptftime + 50} +\'%H:%M:%S %Y %b %d\')"')
        duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
        assert time_check_retry(duthost, ptfhost), "Time is further ahead failed to sync"

        duthost.shell('ucli -c "configure terminal" -c "no ntp enable"')
        result = ptfhost.shell('date +%s')
        ptftime = int(result['stdout'].strip())
        duthost.shell(f'ucli -c "configure terminal" -c "clock set $(date -d @{ptftime - 50} +\'%H:%M:%S %Y %b %d\')"')
        duthost.shell('ucli -c "configure terminal" -c "ntp enable"')
        assert time_check_retry(duthost, ptfhost), "Time is further behind failed to sync"

    finally:
        pass

@pytest.mark.skip(reason="NTP peer/auth/key requirements are not supported")
def test_ntp_nothing_burger(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("NTP-REQ-09: NTP Server Protocol Version"):
        pass
    with allure.step("NTP-REQ-06: NTP Peer Configuration"):
        pass
    with allure.step("NTP-REQ-08: NTP Peer disable temporarily"):
        pass
    with allure.step("NTP-REQ-10: NTP Peer version"):
        pass
    with allure.step("NTP-REQ-16: NTP Peer key assignment"):
        pass
    with allure.step("NTP-REQ-12: NTP authentication global"):
        pass
    with allure.step("NTP-REQ-13: NTP authentication key management"):
        pass
    with allure.step("NTP-REQ-14: NTP trusted key marking"):
        pass
    with allure.step("NTP-REQ-15: NTP key assignment"):
        pass
    with allure.step("NTP-REQ-17: NTP trusted server marking"):
        pass
    with allure.step("NTP-REQ-18: NTP server role"):
        pass
    with allure.step("NTP-REQ-22: NTP show ntp keys"):
        pass
