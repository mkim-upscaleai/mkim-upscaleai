
import pytest
import logging
import re
import json # noqa F401
import ast
import time

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

def test_dns_hostname(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    CLI_SHOW_TEMPLATE = """Hostname: switchshiva
FQDN:     switchshiva
"""

    with allure.step("DNS-REQ-01: Set DNS hostname"):
        old_hostname = duthost.shell("hostname")['stdout'].strip()

        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "hostname switchshiva"')
            result = dut_run_retry(duthost, "cat /etc/hostname")
            assert 'switchshiva' in result['stdout'], '/etc/hostname does not have new hostname'

            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
            d = ast.literal_eval(result['stdout'])
            assert 'switchshiva' in d['hostname'], 'CONFIG_DB did not show correct hostname'

            with allure.step("DNS-REQ-10: show hostname"):
                result = duthost.shell('ucli -c "show hostname"')
                assert 'switchshiva' in result['stdout'], 'UCLI show hostname did not show the right hostname'
                assert result['stdout'].strip() == CLI_SHOW_TEMPLATE.strip(), 'UCLI show hostname does not match industry standard'
        finally:
            # SONiC
            duthost.shell(f"sudo config hostname {old_hostname}", module_ignore_errors=True)

def test_dns_domain(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("DNS-REQ-02: Set DNS domain"):
        result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
        d = ast.literal_eval(result['stdout'])
        old = None
        if 'dns_domain' in d:
            old = d['dns_domain']

        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "dns domain domainshiva1.org"')

            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
            d = ast.literal_eval(result['stdout'])
            assert 'domainshiva1.org' in d['dns_domain'], 'CONFIG_DB did not show correct domain'
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search domainshiva1.org"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain'

            with allure.step("DNS-REQ-11: show dns domain"):
                result = duthost.shell('ucli -c "show dns domain"')
                assert 'domainshiva1.org' in result['stdout'].strip(), 'UCLI show dns domain did not show the right domain'

            duthost.shell('ucli -c "configure terminal" -c "no dns domain"')
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "search domainshiva1.org"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain'
            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
            d = ast.literal_eval(result['stdout'])
            assert 'dns_domain' not in d, 'CONFIG_DB had a dns_domain when it should not'
            result = duthost.shell('ucli -c "show dns domain"')
            assert 'domainshiva1.org' not in result['stdout'].strip(), 'UCLI show dns domain did not show the right domain'

            # Deprecated but supported
            duthost.shell('ucli -c "configure terminal" -c "ip domain-name domainshiva2.org"')
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search domainshiva2.org"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain'
            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
            d = ast.literal_eval(result['stdout'])
            assert 'domainshiva2.org' in d['dns_domain'], 'CONFIG_DB did not show correct domain'
            with allure.step("DNS-REQ-11: show ip domain-name"):
                result = duthost.shell('ucli -c "show ip domain-name"')
                assert 'domainshiva2.org' in result['stdout'], 'UCLI show dns domain did not show the right domain'

            duthost.shell('ucli -c "configure terminal" -c "no ip domain-name"')
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "search domainshiva2.org"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain'
            result = duthost.shell('sonic-db-cli CONFIG_DB HGETALL "DEVICE_METADATA|localhost"')
            d = ast.literal_eval(result['stdout'])
            assert 'dns_domain' not in d, 'CONFIG_DB had a dns_domain when it should not'
            result = duthost.shell('ucli -c "show dns domain"')
            assert 'domainshiva2.org' not in result['stdout'].strip(), 'UCLI show dns domain did not show the right domain'

        finally:
            if old:
                duthost.shell(f'sonic-db-cli CONFIG_DB HSET "DEVICE_METADATA|localhost" dns_domain "{old}"', module_ignore_errors=True)
            else:
                duthost.shell('sonic-db-cli CONFIG_DB HDEL "DEVICE_METADATA|localhost" dns_domain', module_ignore_errors=True)

            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep domainshiva')
            assert result['rc'] == 0, '/etc/resolv.conf did not clean up properly'

def test_dns_domain_list(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("DNS-REQ-03: Set DNS domain search list"):
        result = duthost.shell('sonic-db-cli CONFIG_DB KEYS "IP_DOMAIN_LIST*"')
        old_domains = [line.strip() for line in result['stdout_lines']]

        try:
            duthost.shell('ucli -c "configure terminal" -c "ip domain-list domainlistshiva2.org" -c "ip domain-list domainlistshiva1.org"')
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search.*domainlistshiva2.org.*domainlistshiva1.org"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct input order search order for qualified hostnames'

            duthost.shell('ucli -c "configure terminal" -c "ip domain-list def" -c "ip domain-list abc"')
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search.*domainlist.*def.*abc"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct alphabetical search order for unqualified hostnames'

            with allure.step("DNS-REQ-12: show ip domain-list"):
                # Not an industry standard command
                result = dut_run_retry(duthost, 'ucli -c "show ip domain-list" | grep "domainlistshiva2.org"')
                assert result['rc'] == 0, "show ip domain-list is not showing correct domain list"
                result = dut_run_retry(duthost, 'ucli -c "show ip domain-list" | grep "domainlistshiva1.org"')
                assert result['rc'] == 0, "show ip domain-list is not showing correct domain list"
                result = dut_run_retry(duthost, 'ucli -c "show ip domain-list" | grep "abc"')
                assert result['rc'] == 0, "show ip domain-list is not showing correct domain list"
                result = dut_run_retry(duthost, 'ucli -c "show ip domain-list" | grep "def"')
                assert result['rc'] == 0, "show ip domain-list is not showing correct domain list"

            duthost.shell('ucli -c "configure terminal" -c "no ip domain-list domainlistshiva2.org"')
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search.*domainlistshiva1.org"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain list'

            duthost.shell('ucli -c "configure terminal" -c "no ip domain-list def"')
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "search.*def"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain list'

            duthost.shell('ucli -c "configure terminal" -c "no ip domain-list abc" -c "no ip domain-list domainlistshiva1.org"')
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "search"')
            assert result['rc'] == 0, '/etc/resolv.conf should be empty'

        finally:
            duthost.shell('sonic-db-cli CONFIG_DB DEL "IP_DOMAIN_LIST|domainlistshiva2.org"', module_ignore_errors=True)
            duthost.shell('sonic-db-cli CONFIG_DB DEL "IP_DOMAIN_LIST|domainlistshiva1.org"', module_ignore_errors=True)
            duthost.shell('sonic-db-cli CONFIG_DB DEL "IP_DOMAIN_LIST|abc"', module_ignore_errors=True)
            duthost.shell('sonic-db-cli CONFIG_DB DEL "IP_DOMAIN_LIST|def"', module_ignore_errors=True)
            for line in old_domains:
                duthost.shell(f'sonic-db-cli CONFIG_DB HSET "{line}" "NULL" "NULL"')

def test_dns_disable_enable(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("DNS-REQ-04: DNS disable enable"):
        result = duthost.shell('sonic-db-cli CONFIG_DB KEYS "IP_DOMAIN_LIST*"')
        old_domains = [line.strip() for line in result['stdout_lines']]

        try:
            with allure.step("DNS-REQ-16: show dns domain-lookup"):
                duthost.shell('ucli -c "configure terminal" -c "ip name-server 2001:4860:4860::8888"')
                duthost.shell('ucli -c "configure terminal" -c "ip domain-list domainlistshiva1.org"')
                result = dut_run_retry(duthost, 'ucli -c "show ip domain-lookup" | grep "domainlistshiva1.org"')
                assert result['rc'] == 0, "show ip domain-list is not showing correct domain list"
                result = dut_run_retry(duthost, 'ucli -c "show ip domain-lookup" | grep "DNS lookup is enabled"')
                assert result['rc'] == 0, "dns lookup enabled is missing from show ip domain-list"
                result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search.*domainlistshiva1.org"')
                assert result['rc'] == 0, '/etc/resolv.conf does not have correct domain list'

            duthost.shell('ucli -c "configure terminal" -c "no ip domain-lookup"')
            result = dut_run_retry(duthost, 'ucli -c "show ip domain-lookup" | grep "DNS lookup is disabled"')
            assert result['rc'] == 0, "dns lookup disabled is missing from show ip domain-list"
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "search.*domainlistshiva"')
            assert result['rc'] == 0, "/etc/resolv.conf should not have search domain"
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "nameserver"')
            assert result['rc'] == 0, "/etc/resolv.conf should not have nameserver"

            duthost.shell('ucli -c "configure terminal" -c "ip domain-lookup"')
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "search.*domainlistshiva"')
            assert result['rc'] == 0, "/etc/resolv.conf should have search domain"
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "nameserver 2001:4860:4860::8888"')
            assert result['rc'] == 0, "/etc/resolv.conf should have nameserver"

        finally:
            duthost.shell('sonic-db-cli CONFIG_DB DEL "DNS_NAMESERVER|2001:4860:4860::8888"', module_ignore_errors=True)
            duthost.shell('sonic-db-cli CONFIG_DB DEL "IP_DOMAIN_LIST|domainlistshiva1.org"', module_ignore_errors=True)
            for line in old_domains:
                duthost.shell(f'sonic-db-cli CONFIG_DB HSET "{line}" "NULL" "NULL"')

def test_dns_static_host(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    result = duthost.shell('sonic-db-cli CONFIG_DB KEYS "STATIC_HOST*"') # 4 and 6
    old_statics = {}
    for line in result['stdout_lines']:
        k = line.strip()
        r2 = duthost.shell(f'sonic-db-cli CONFIG_DB HGETALL "{k}"')
        r3 = ast.literal_eval(r2['stdout'])
        old_statics[k] = r3

    try:
        with allure.step("DNS-REQ-08: Set static host4"):
            duthost.shell('ucli -c "configure terminal" -c "ip host staticshiva4 192.168.1.100"')
            duthost.shell('ucli -c "configure terminal" -c "ip host staticshiva4a 192.168.1.100 192.168.1.101"')
            result = dut_run_retry(duthost, 'cat /etc/hosts | grep "192.168.1.100 staticshiva4"')
            assert result['rc'] == 0, "/etc/hosts missing static ipv4 host 1"
            result = dut_run_retry(duthost, 'cat /etc/hosts | grep "192.168.1.100 staticshiva4a"')
            assert result['rc'] == 0, "/etc/hosts missing static ipv4 host 2"
            result = dut_run_retry(duthost, 'cat /etc/hosts | grep "192.168.1.101 staticshiva4a"')
            assert result['rc'] == 0, "/etc/hosts missing static ipv4 host 3"

            with allure.step("DNS-REQ-14: show ip host"):
                # Not an industry standard command
                result = duthost.shell('ucli -c "show ip host" | grep "staticshiva4.*192.168.1.100"')
                assert result['rc'] == 0, "show ip host missing information host 1"
                result = duthost.shell('ucli -c "show ip host" | grep "staticshiva4a.*192.168.1.100.*192.168.1.101"')
                assert result['rc'] == 0, "show ip host missing information host 2 3"

            duthost.shell('ucli -c "configure terminal" -c "no ip host staticshiva4a"')
            result = dut_run_retry(duthost, '! cat /etc/hosts | grep "192.168.1.100 staticshiva4a"')
            assert result['rc'] == 0, "/etc/hosts should have removed static ipv4 host 1"
            result = dut_run_retry(duthost, '! cat /etc/hosts | grep "192.168.1.101 staticshiva4a"')
            assert result['rc'] == 0, "/etc/hosts should have removed static ipv4 host 2"

        with allure.step("DNS-REQ-09: Set static host6"):
            duthost.shell('ucli -c "configure terminal" -c "ipv6 host staticshiva6 2001:db8::100"')
            duthost.shell('ucli -c "configure terminal" -c "ipv6 host staticshiva6a 2001:db8::100 2001:db8::102"')
            result = dut_run_retry(duthost, 'cat /etc/hosts | grep "2001:db8::100 staticshiva6"')
            assert result['rc'] == 0, "/etc/hosts missing static ipv6 host 1"
            result = dut_run_retry(duthost, 'cat /etc/hosts | grep "2001:db8::100 staticshiva6a"')
            assert result['rc'] == 0, "/etc/hosts missing static ipv6 host 2"
            result = dut_run_retry(duthost, 'cat /etc/hosts | grep "2001:db8::102 staticshiva6a"')
            assert result['rc'] == 0, "/etc/hosts missing static ipv6 host 3"

            with allure.step("DNS-REQ-15: show ipv6 host"):
                # Not an industry standard command
                result = duthost.shell('ucli -c "show ipv6 host" | grep "staticshiva6.*2001:db8::100"')
                assert result['rc'] == 0, "show ipv6 host missing information host 1"
                result = duthost.shell('ucli -c "show ipv6 host" | grep "staticshiva6a.*2001:db8::100.*2001:db8::102"')
                assert result['rc'] == 0, "show ipv6 host missing information host 2 3"

            duthost.shell('ucli -c "configure terminal" -c "no ipv6 host staticshiva6a"')
            result = dut_run_retry(duthost, '! cat /etc/hosts | grep "2001:db8::100 staticshiva6a"')
            assert result['rc'] == 0, "/etc/hosts should have removed static ipv6 host 1"
            result = dut_run_retry(duthost, '! cat /etc/hosts | grep "2001:db8::102 staticshiva6a"')
            assert result['rc'] == 0, "/etc/hosts should have removed static ipv6 host 2"

    finally:
        duthost.shell('sonic-db-cli CONFIG_DB DEL "STATIC_HOST|staticshiva4"', module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB DEL "STATIC_HOST|staticshiva4a"', module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB DEL "STATIC_HOST_V6|staticshiva6"', module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB DEL "STATIC_HOST_V6|staticshiva6a"', module_ignore_errors=True)
        for static_host in old_statics:
            for k, v  in old_statics[static_host].items():
                duthost.shell(f'sonic-db-cli CONFIG_DB HSET "{static_host}" "{k}" "{v}"')

def test_dns_nameserver(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    result = duthost.shell('sonic-db-cli CONFIG_DB KEYS "DNS_NAMESERVER*"')
    old_nameservers = {}
    for line in result['stdout_lines']:
        k = line.strip()
        r2 = duthost.shell(f'sonic-db-cli CONFIG_DB HGETALL "{k}"')
        r3 = ast.literal_eval(r2['stdout'])
        old_nameservers[k] = r3

    try:
        with allure.step("DNS-REQ-05: DNS set nameserver"):
            duthost.shell('ucli -c "configure terminal" -c "ip name-server 8.8.8.8" -c "ip name-server 1.1.1.1"')
            duthost.shell('ucli -c "configure terminal" -c "ip name-server 2001:4860:4860::8888"')
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "nameserver 8.8.8.8"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct nameserver 8.8.8.8'
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "nameserver 1.1.1.1"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct nameserver 1.1.1.1'
            result = dut_run_retry(duthost, 'cat /etc/resolv.conf | grep "nameserver 2001:4860:4860::8888"')
            assert result['rc'] == 0, '/etc/resolv.conf does not have correct nameserver 2001:4860:4860::8888'

            with allure.step("DNS-REQ-13: show ip name-server"):
                result = duthost.shell('ucli -c "show ip name-server"')
                assert re.search(r"IP Address\s+VRF", result['stdout']), "Incorrect header for show ip name-server"
                assert re.search(r"8.8.8.8", result['stdout']), "Incorrect 8.8.8.8 output for show ip name-server"
                assert re.search(r"1.1.1.1", result['stdout']), "Incorrect 1.1.1.1 output for show ip name-server"
                assert re.search(r"2001:4860:4860::8888", result['stdout']), "Incorrect 2001:4860:4860::8888 output for show ip name-server"

            duthost.shell('ucli -c "configure terminal" -c "no ip name-server 1.1.1.1"')
            result = dut_run_retry(duthost, '! cat /etc/resolv.conf | grep "nameserver 1.1.1.1"')
            assert result['rc'] == 0, "/etc/resolv.conf did not remove 1.1.1.1"

    finally:
        duthost.shell('sonic-db-cli CONFIG_DB DEL "DNS_NAMESERVER|8.8.8.8"', module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB DEL "DNS_NAMESERVER|1.1.1.1"', module_ignore_errors=True)
        duthost.shell('sonic-db-cli CONFIG_DB DEL "DNS_NAMESERVER|2001:4860:4860::8888"', module_ignore_errors=True)
        for nameserver in old_nameservers:
            for k, v  in old_nameservers[nameserver].items():
                duthost.shell(f'sonic-db-cli CONFIG_DB HSET "{nameserver}" "{k}" "{v}"')

@pytest.mark.device_type('vs') # VRFs are dangerous
def test_dns_mgmt_vrf(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    # The device_type('vs') marker is only enforced when --device_type is passed on the
    # pytest CLI (see tests/common/plugins/custom_markers/__init__.py). Guard at runtime
    # so this test cannot brick a physical DUT: 'config vrf add mgmt' moves eth0 into the
    # mgmt VRF and cuts off the Ansible/SSH session, leaving the box unreachable until
    # someone clears the VRF over console.
    if duthost.facts.get('asic_type') != 'vs':
        pytest.skip("test_dns_mgmt_vrf is vs-only; adding the mgmt VRF can disconnect a physical DUT")
    try:
        duthost.shell('sudo config vrf add mgmt')
        with allure.step("DNS-REQ-06: DNS MGMT VRF"):
            duthost.shell('ucli -c "configure terminal" -c "ip name-server 8.8.8.8"')
            result = dut_run_retry(duthost, 'ping -c 1 google.com')
            assert result['rc'] != 0, 'DNS should not work without VRF'
            result = dut_run_retry(duthost, 'sudo ip vrf exec mgmt ping -c 1 google.com')
            assert result['rc'] == 0, 'DNS should work inside VRF'

    finally:
        duthost.shell('sonic-db-cli CONFIG_DB DEL "DNS_NAMESERVER|8.8.8.8"', module_ignore_errors=True)
        duthost.shell('sudo config vrf del mgmt', module_ignore_errors=True)

def test_dns_source_interface(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        with allure.step("DNS-REQ-07: DNS Source Interface"):
            duthost.shell('ucli -c "configure terminal" -c "ip domain-lookup source-interface eth0"')
            result = dut_run_retry(duthost, 'ucli -c "show ip domain-lookup" | grep "Source interface: eth0"')
            assert result['rc'] == 0, 'DNS source interface does not appear in show ip domain-lookup'

            duthost.shell('ucli -c "configure terminal" -c "no ip domain-lookup source-interface"')
            result = dut_run_retry(duthost, '! ucli -c "show ip domain-lookup" | grep "Source interface: eth0"')
            assert result['rc'] == 0, 'DNS source interface should not appear in show ip domain-lookup'

    finally:
        duthost.shell('sonic-db-cli CONFIG_DB HDEL "DEVICE_METADATA|localhost" dns_source_interface', module_ignore_errors=True)
