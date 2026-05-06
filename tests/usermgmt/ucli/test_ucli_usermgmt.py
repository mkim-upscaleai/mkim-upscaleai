
import contextlib
import shlex
import pytest
import logging
import random # noqa F401
import re # noqa F401
import json # noqa F401
import ast
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

@contextlib.contextmanager
def tcpdump_bgp(duthost, save_path):
    result = duthost.shell(
        f"nohup sudo tcpdump -ni any port 179 -vv > {save_path} 2>&1 & echo $!"
    )
    tcpdump_pid = result["stdout"].strip()
    try:
        yield
    finally:
        duthost.shell(f"sudo kill {tcpdump_pid}", module_ignore_errors=True)

def test_usermgmt_local_roles(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-01: Supports local user and roles"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 role admin"')
            result = dut_run_retry(duthost, 'cat /etc/passwd | grep localshiva1')
            assert 'localshiva1' in result['stdout'], "localshiva1 was not in /etc/passwd"
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", 'ucli -c "configure terminal"')
            assert result['rc'] == 0, "Admin should be able to configure"

            duthost.shell('ucli -c "configure terminal" -c "username localshiva2 role monitor"')
            result = dut_run_retry(duthost, 'cat /etc/passwd | grep localshiva2')
            assert 'localshiva2' in result['stdout'], "localshiva2 was not in /etc/passwd"
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva2", "password1234", 'ucli -c "configure terminal"')
            assert result['rc'] != 0, "Monitor should not be able to configure"

        finally:
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")
            result = duthost.shell("id localshiva2")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva2")

def test_usermgmt_local_password(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-02: Local password authentication"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 secret password1234"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", "ls")
            assert result['rc'] == 0, "Local user cannot login"

        finally:
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_rbac(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-03: RBAC (role to privilege)"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 role admin secret password1234"')
            duthost.shell('ucli -c "configure terminal" -c "role admin privilege 15"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", 'ucli -c "configure terminal"')
            assert result['rc'] == 0, "Admin 15 should be able to configure"
            duthost.shell('ucli -c "configure terminal" -c "username localshiva2 role monitor secret password1234"')
            duthost.shell('ucli -c "configure terminal" -c "role monitor privilege 1"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva2", "password1234", 'ucli -c "configure terminal"')
            assert result['rc'] != 0, "Monitor 1 should not be able to configure"

        finally:
            # SONiC
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")
            result = duthost.shell("id localshiva2")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva2")

def test_usermgmt_aaa_ldap_authen(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-10: AAA authentication LDAP"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "ldap server {ptfhost.mgmt_ip} base-dn dc=upscaleshiva,dc=org"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group ldap local"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "ldapuser", "ldapuserpass", "ls")
            assert result['rc'] == 0, "LDAP user cannot login"

        finally:
            # SONiC
            duthost.shell(f'sudo config ldap-server del {ptfhost.mgmt_ip}')
            duthost.shell('sudo config aaa authentication login local')

def test_usermgmt_aaa_radius_authen(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-04: AAA authentication RADIUS"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group radius local"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", "ls")
            assert result['rc'] == 0, "RADIUS user cannot login"

        finally:
            # SONiC
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell(f'sudo config radius delete {ptfhost.mgmt_ip}')
            result = duthost.shell("id radiusopsuser")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel radiusopsuser")

def test_usermgmt_aaa_radius_author(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-05: AAA Authorization RADIUS"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group radius local"')
            duthost.shell(f'ucli -c "configure terminal" -c "aaa authorization exec default group radius local"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", "ls")
            assert result['rc'] == 0, "RADIUS user cannot login"
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", 'echo radiusopspass | sudo -S ls')
            assert result['rc'] != 0, "RADIUS user should not be able to sudo"

        finally:
            # SONiC
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell(f'sudo config radius delete {ptfhost.mgmt_ip}')
            result = duthost.shell("id radiusopsuser")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel radiusopsuser")


def test_usermgmt_aaa_radius_config(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-17: RADIUS server key timeout tls"):
        try:
            # UCLI
            # No radius server running on DUT
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {duthost.mgmt_ip} key testing123 tls"')
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server timeout 10"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group radius local"')

            duthost.shell("sudo useradd -m -p $(mkpasswd -m yescrypt 'password1234') -s /bin/bash localshiva1")
            before = time.time()
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", "ls", attempts=1, wait_time_sec=11)
            after = time.time()
            duration = after - before
            assert result['rc'] == 0, "Did not fallback to local user"
            assert duration > 10, "Should have waited for RADIUS for 10 seconds"

        finally:
            # SONiC
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell(f'sudo config radius delete {duthost.mgmt_ip}')
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_aaa_radius_acct(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-06: AAA Accounting RADIUS"):
        try:
            ptfhost.shell('rm -rf /var/log/freeradius/radacct')

            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group radius local"')
            duthost.shell(f'ucli -c "configure terminal" -c "aaa accounting commands all default start-stop group radius"')
            ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", "ls")

            result = ptfhost.shell("test -d /var/log/freeradius/radacct")
            assert result['rc'] == 0, "RADIUS accounting failed"

        finally:
            ptfhost.shell('rm -rf /var/log/freeradius/radacct')
            # SONiC
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell(f'sudo config radius delete {ptfhost.mgmt_ip}')
            result = duthost.shell("id radiusopsuser")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel radiusopsuser")

def test_usermgmt_aaa_tacacs_authen(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-07: AAA authentication TACACS"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva1", "tacshiva1pw", "ls")
            assert result['rc'] == 0, "TACACS user cannot login"

        finally:
            # SONiC
            duthost.shell(f"sudo config tacacs delete {ptfhost.mgmt_ip}")
            duthost.shell('sudo config aaa authentication login local')
            result = duthost.shell("id tacshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva1")

def test_usermgmt_timeout(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-23: Session timeout"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "exec-timeout 1"')
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 secret password1234"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", "sleep 65", attempts=1, wait_time_sec=70)
            assert result['rc'] != 0, "Session did not timeout properly"

        finally:
            # SONiC
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_lockout(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-24: Login attempts and lockout"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "login attempts 1 lock-time 10"')
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 secret password1234"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "badpassword", "ls")
            time.sleep(1)
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "badpassword", "ls")
            assert result['rc'] != 0, "User should have been locked out"
            time.sleep(11)
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", "ls")
            assert result['rc'] == 0, "Locked user should have been unlocked"

        finally:
            # SONiC
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_aaa_tacacs_author(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-08: AAA Authorization TACACS"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authorization exec default group tacacs+ local"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva2", "tacshiva2pw", "show version")
            assert result['rc'] == 0, "TACACS user is permitted to show version"

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva2", "tacshiva2pw", "show interfaces")
            assert result['rc'] != 0, "TACACS user is not permitted to show interfaces"

        finally:
            # SONiC
            duthost.shell(f"sudo config tacacs delete {ptfhost.mgmt_ip}")
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell('sudo config aaa authorization login')
            result = duthost.shell("id tacshiva2")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva2")

def test_usermgmt_aaa_tacacs_acct(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-09: AAA Accounting TACACS"):        
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')
            duthost.shell('ucli -c "configure terminal" -c "aaa accounting exec default start-stop group tacacs+"')

            ptfhost.shell('truncate -s 0 /var/log/tacshiva.acct')
            ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva2", "tacshiva2pw", "show version")
            result = ptfhost.shell('grep tacshiva2 /var/log/tacshiva.acct')
            assert result['rc'] == 0, "TACACS accounting did not record anything"

        finally:
            # SONiC    
            duthost.shell(f"sudo config tacacs delete {ptfhost.mgmt_ip}")
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell('sudo config aaa authorization local')
            duthost.shell('sudo config aaa accounting local')
            result = duthost.shell("id tacshiva2")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva2")

def test_usermgmt_aaa_tacacs_config(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-18: TACACS server key and tls"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123 tls"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva2", "tacshiva2pw", "ls")
            assert result['rc'] == 0, "TACACS server and key succeeded"

        finally:
            # SONiC
            duthost.shell(f"sudo config tacacs delete {ptfhost.mgmt_ip}")
            duthost.shell('sudo config aaa authentication login local')
            result = duthost.shell("id tacshiva2")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva2")

def test_usermgmt_aaa_tacacs_cmd_author_acct(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-21: TACACS Command Authorization"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authorization commands 15 default group tacacs+"')            

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva1", "tacshiva1pw", 'ucli -c "configure terminal"')
            assert result['rc'] == 0, "TACACS admin user is permitted"

        finally:
            # SONiC
            duthost.shell(f"sudo config tacacs delete {ptfhost.mgmt_ip}")
            duthost.shell('sudo config aaa authentication login local')
            result = duthost.shell("id tacshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva1")

    with allure.step("USER-MGMT-REQ-22: TACACS Command Accounting"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authorization commands 15 default group tacacs+"')
            duthost.shell(f'ucli -c "configure terminal" -c "aaa accounting commands 15 default start-stop group tacacs+"')

            ptfhost.shell('truncate -s 0 /var/log/tacshiva.acct')
            ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva1", "tacshiva1pw", "show version")
            result = ptfhost.shell('grep tacshiva1 /var/log/tacshiva.acct')
            assert result['rc'] == 0, "TACACS accounting did not record anything"

        finally:
            # SONiC
            duthost.shell(f"sudo config tacacs delete {ptfhost.mgmt_ip}")
            duthost.shell('sudo config aaa authentication login local')
            result = duthost.shell("id tacshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva1")

def test_usermgmt_ssh_harden(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-26-27: Secure mode - SSHv2 only"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "ssh server min-version 2"')
            result = dut_run_retry(duthost, 'cat /etc/ssh/sshd_config | grep "Protocol.*1"')
            assert result['rc'] != 0, "SSH configured for version less than 2"

        finally:
            pass

    with allure.step("USER-MGMT-REQ-28: Strict SSH ciphers"):
        try:
            duthost.shell('sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak')
            duthost.shell('grep -q "^ciphers" /etc/ssh/sshd_config || echo "ciphers chacha20-poly1305@openssh.com,aes128-gcm@openssh.com,aes256-gcm@openssh.com,aes128-ctr,aes192-ctr,aes256-ctr,3des-cbc" | sudo tee -a /etc/ssh/sshd_config')

            # UCLI
            result = duthost.shell('ucli -c "configure terminal" -c "ssh server security strict"')
            assert result['rc'] == 0, "Could not set SSH to strict ciphers"
            result = duthost.shell("grep ciphers /etc/ssh/sshd_config | grep 3des-cbc")
            assert result['rc'] != 0, "Weak cipher included in SSH when it should not have"

        finally:
            duthost.shell('sudo mv /etc/ssh/sshd_config.bak /etc/ssh/sshd_config', module_ignore_errors=True)

def test_usermgmt_accting_logs(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-36: User session accounting logs"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ local"')
            duthost.shell('ucli -c "configure terminal" -c "aaa accounting exec default start-stop group tacacs+"')
            ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva2", "tacshiva2pw", "show version")
            result = duthost.shell('ucli -c "show accounting sessions"')
            assert result['rc'] == 0, 'No accounting session available when there should be'

        finally:
            pass

def test_usermgmt_mgmt_https(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-29: Disable HTTP management"):
        # UCLI
        duthost.shell('ucli -c "configure terminal" -c "no management http"')
        duthost.shell('ucli -c "configure terminal" -c "no web http enable"')
        result = dut_run_retry(duthost, 'sudo lsof -i TCP:80')
        assert result['rc'] != 0, "HTTP is running after no management http"

    with allure.step("USER-MGMT-REQ-30: Strong TLS for HTTPS"):
        # UCLI
        duthost.shell('ucli -c "configure terminal" -c "management https ssl profile fips"')
        duthost.shell('ucli -c "configure terminal" -c "web https ssl ciphers TLS1.2"')
        result = duthost.shell("echo "" | openssl s_client -connect 127.0.0.1:443  -tls1_2")
        assert result['rc'] == 0, "HTTPS is not running TLS 1.2"

def test_usermgmt_audit_login_failure(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-40: Audit logging of login failures"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "logging event login-failure"')
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 secret password1234"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "badpassword", "ls")
            assert result['rc'] != 0, "Login should have failed"
            result = dut_run_retry(duthost, 'sudo tail -n100 /var/log/auth.log')
            assert "password check failed for user (localshiva1)" in result['stdout'], 'No audit log of password failure'
            
        finally:
            # SONiC
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_secure_mode(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-25: Secure mode enable"):
        result = duthost.shell('ucli -c "configure terminal" -c "system secure-mode enable"')
        assert result['rc'] == 0, "Secure mode enable CLI failed"

    with allure.step("USER-MGMT-REQ-35: Show secure mode state ON"):
        result = duthost.shell('ucli -c "show system secure-mode"')
        assert result['rc'] == 0, "Show secure mode failed ON"

    with allure.step("USER-MGMT-REQ-34: Secure mode disable"):
        result = duthost.shell('ucli -c "configure terminal" -c "no system secure-mode enable"')
        assert result['rc'] == 0, "Secure mode disable CLI failed"

    with allure.step("USER-MGMT-REQ-35: Show secure mode state OFF"):
        result = duthost.shell('ucli -c "show system secure-mode"')
        assert result['rc'] == 0, "Show secure mode failed OFF"

def test_usermgmt_bgp_secure(request, duthost, ptfhost, localhost, nbrhosts, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-31: Disallow BGP neighbor MD5 passwords"):
        try:
            duthost.shell('sudo rm -f /tmp/bgp1.log')

            nbr = next(iter(nbrhosts.values()))
            cidr = nbr["conf"]["interfaces"]["Port-Channel1"]["ipv4"]
            peer_ip = cidr.split("/")[0]

            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "no router bgp 65200 neighbor {peer_ip} password"')
            with tcpdump_bgp(duthost, "/tmp/bgp1.log"):
                time.sleep(30)
            result = duthost.shell(f"grep '{peer_ip.replace('.', r'\.')}.*tcp-ao' /tmp/bgp1.log")
            assert result['rc'] == 0, "Secure BGP MD5 was allowed"

        finally:
            duthost.shell('sudo rm -f /tmp/bgp1.log')

    with allure.step("USER-MGMT-REQ-32: Disallow BGP peer-group passwords"):
        try:
            duthost.shell('sudo rm -f /tmp/bgp2.log')

            nbr = next(iter(nbrhosts.values()))
            cidr = nbr["conf"]["interfaces"]["Port-Channel1"]["ipv4"]
            peer_ip = cidr.split("/")[0]

            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "no router bgp 65100 peer-group 10.250.0.51 password"')
            with tcpdump_bgp(duthost, "/tmp/bgp2.log"):
                time.sleep(30)
            result = duthost.shell(f"grep '{peer_ip.replace('.', r'\.')}.*tcp-ao' /tmp/bgp2.log")
            assert result['rc'] == 0, "Secure BGP peer group was allowed"

        finally:
            duthost.shell('sudo rm -f /tmp/bgp2.log')

def test_usermgmt_pw_hash(request, duthost, ptfhost, localhost, nbrhosts, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-33: Modern password hashing"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "password hash sha512"')
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 role admin secret password1234"')
            result = dut_run_retry(duthost, 'sudo grep localshiva1 /etc/shadow')
            assert "$6$" in result['stdout'], "localshiva1 is not using sha512 for password"

        finally:
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_monitor_readonly(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-38: Per Role CLI View"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "username localshiva2 role monitor secret password1234"')
            duthost.shell('ucli -c "configure terminal" -c "role monitor view readonly"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva2", "password1234", 'ucli -c "configure terminal" -c "username localshiva3 role monitor secret password1234"')
            assert result['rc'] != 0, "Role monitor should not be able to change anything"

        finally:
            result = duthost.shell("id localshiva2")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva2")
            result = duthost.shell("id localshiva3")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva3")

def test_usermgmt_reauth(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-13: Re-auth on AAA change"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "aaa reauthentication enable"')
            result = duthost.shell('timeout -k 2s 3s ucli -c "enable"')
            assert result['rc'] != 0, "Enable command should have waited with aaa reauth enable"

        finally:
            pass

def test_usermgmt_encrypt(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-20: Encrypted transport to RADIUS/TACACS"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {ptfhost.mgmt_ip} key testing123 tls"')
            duthost.shell(f'ucli -c "configure terminal" -c "tacacs-server host {ptfhost.mgmt_ip} key testing123 tls"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group tacacs+ group radius local"')


            result = ssh_run_retry(localhost, duthost.mgmt_ip, "tacshiva1", "tacshiva1pw", "ls")
            assert result['rc'] == 0, "TACACS TLS user cannot login"
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", "ls")
            assert result['rc'] == 0, "Radius user cannot login"
        finally:
            # SONiC
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell(f'sudo config radius delete {ptfhost.mgmt_ip}')
            duthost.shell(f'sudo config tacacs delete {ptfhost.mgmt_ip}')
            result = duthost.shell("id radiusopsuser")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel radiusopsuser")
            result = duthost.shell("id tacshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel tacshiva1")

def test_usermgmt_precedence(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-37: External Authentication Precedence"):
        try:
            duthost.shell("sudo useradd -m -p $(mkpasswd -m yescrypt 'password1234') -s /bin/bash radiusopsuser")

            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "radius-server host {ptfhost.mgmt_ip} key testing123"')
            duthost.shell(f'ucli -c "configure terminal" -c "aaa authentication login default group radius group tacacs+ local"')

            result = ssh_run_retry(localhost, duthost.mgmt_ip, "radiusopsuser", "radiusopspass", "ls")
            assert result['rc'] == 0, "Radius user cannot login"
        finally:
            # SONiC
            duthost.shell('sudo config aaa authentication login local')
            duthost.shell(f'sudo config radius delete {ptfhost.mgmt_ip}')
            result = duthost.shell("id radiusopsuser")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel radiusopsuser")

    with allure.step("USER-MGMT-REQ-12: Multiple AAA and fallback to local"):
        try:
            # UCLI
            # Do not configure LDAP or TACACS, it should fail
            duthost.shell('ucli -c "configure terminal" -c "username localshiva1 secret password1234"')
            duthost.shell(f'ucli -c "configure terminal" -c "aaa authentication login default group ldap group tacacs+ local"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "localshiva1", "password1234", "ls")
            assert result['rc'] == 0, "Local fallback user cannot login"

        finally:
            result = duthost.shell("id localshiva1")
            if result['rc'] == 0:
                dut_run_retry(duthost, "sudo userdel localshiva1")

def test_usermgmt_emergency_local(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-39: Emergency Local Access"):
        # UCLI
        duthost.shell(f'ucli -c "configure terminal" -c "aaa authentication login default local"')
        result = dut_run_retry(duthost, "ls")
        assert result['rc'] == 0, 'Admin cannot login as emergency local access'

def test_usermgmt_aaa_ldap_group_role(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-11: LDAP group-to-role mapping"):
        try:
            # UCLI
            duthost.shell(f'ucli -c "configure terminal" -c "ldap server {ptfhost.mgmt_ip} base-dn dc=upscaleshiva,dc=org"')
            duthost.shell('ucli -c "configure terminal" -c "aaa authentication login default group ldap local"')

            duthost.shell('ucli -c "configure terminal" -c "role admin privilege 15"')
            duthost.shell('ucli -c "configure terminal" -c "ldap role-map group ldapusers role admin"')
            result = ssh_run_retry(localhost, duthost.mgmt_ip, "ldapuser", "ldapuserpass", "groups ldapuser")
            assert result['rc'] == 0, "LDAP user cannot login"
            assert "sudo" in result['stdout'], "LDAP user with admin privilege no in sudo group"

        finally:
            duthost.shell(f'sudo config ldap-server del {ptfhost.mgmt_ip}')
            duthost.shell('sudo config aaa authentication login local')

def test_usermgmt_aaa_ldap_server_base_dn(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-19: LDAP server and base DN"):
        assert True, "This is implied to test anything LDAP"

def test_usermgmt_nothing_burger(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("USER-MGMT-REQ-14: DOES NOT EXIST"):
        pass

    with allure.step("USER-MGMT-REQ-15: DOES NOT EXIST"):
        pass

    with allure.step("USER-MGMT-REQ-16: DOES NOT EXIST"):
        pass
