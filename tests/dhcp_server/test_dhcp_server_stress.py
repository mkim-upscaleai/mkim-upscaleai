import logging
import ipaddress
import pytest
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from dhcp_server_test_common import apply_dhcp_server_config_gcu, empty_config_patch, append_common_config_patch


pytestmark = [
    pytest.mark.topology('t0', 'mx'),
]


DHCP_PACKAGES_PATH = "/tmp/dhcp_packages"
DHCP_PACKAGES = [
    "isc-dhcp-common_4.4.3-P1-2_amd64.deb",
    "isc-dhcp-client_4.4.3-P1-2_amd64.deb",
]
DHCP_PACKAGES_SRC_DIR = "../ansible/roles/test/files/dhcp_packages"


@pytest.fixture(scope="module", autouse=True)
def dhcp_client_setup_teardown_on_ptf(ptfhost, creds):
    # Try installing from local .deb packages first to avoid relying on apt mirrors
    ptfhost.shell("mkdir -p {}".format(DHCP_PACKAGES_PATH))
    local_install_ok = True
    for pkg in DHCP_PACKAGES:
        src = "{}/{}".format(DHCP_PACKAGES_SRC_DIR, pkg)
        dst = "{}/{}".format(DHCP_PACKAGES_PATH, pkg)
        try:
            ptfhost.copy(src=src, dest=dst)
        except Exception:
            local_install_ok = False
            break

    if local_install_ok:
        ptfhost.shell("dpkg -i {}/*.deb".format(DHCP_PACKAGES_PATH), module_ignore_errors=True)
        result = ptfhost.shell("which dhclient", module_ignore_errors=True)
        local_install_ok = result["rc"] == 0

    if not local_install_ok:
        http_proxy = creds.get("proxy_env", {}).get("http_proxy", "")
        http_param = "-o Acquire::http::proxy='{}'".format(http_proxy) if http_proxy != "" else ""
        ptfhost.shell("apt-get {} update".format(http_param), module_ignore_errors=True)
        ptfhost.shell("apt-get {} install isc-dhcp-client -y".format(http_param))

    yield

    ptfhost.shell("apt-get remove isc-dhcp-client -y", module_ignore_errors=True)
    ptfhost.shell("rm -rf {}".format(DHCP_PACKAGES_PATH), module_ignore_errors=True)


@pytest.fixture(scope="module")
def parse_vlan_setting_from_running_config(duthost, tbinfo):
    vlan_brief = duthost.get_vlan_brief()
    first_vlan_name = list(vlan_brief.keys())[0]
    first_vlan_info = list(vlan_brief.values())[0]
    first_vlan_prefix = first_vlan_info['interface_ipv4'][0]
    disabled_host_interfaces = tbinfo['topo']['properties']['topology'].get('disabled_host_interfaces', [])
    connected_ptf_ports_idx = [interface for interface in
                               tbinfo['topo']['properties']['topology'].get('host_interfaces', [])
                               if interface not in disabled_host_interfaces]
    dut_intf_to_ptf_index = duthost.get_extended_minigraph_facts(tbinfo)['minigraph_ptf_indices']
    connected_dut_intf_to_ptf_index = {k: v for k, v in dut_intf_to_ptf_index.items() if v in connected_ptf_ports_idx}
    vlan_members = first_vlan_info['members']
    vlan_member_with_ptf_idx = [(member, connected_dut_intf_to_ptf_index[member])
                                for member in vlan_members if member in connected_dut_intf_to_ptf_index]
    pytest_assert(len(vlan_member_with_ptf_idx) >= 2, 'Vlan members is too little for testing')
    vlan_net = ipaddress.ip_network(address=first_vlan_prefix, strict=False)
    vlan_gateway = first_vlan_prefix.split('/')[0]
    vlan_hosts = [str(host) for host in vlan_net.hosts()]
    # to avoid configurate an range contains gateway ip, simply ignore all ip before gateway and gateway itself
    vlan_hosts_after_gateway = vlan_hosts[vlan_hosts.index(vlan_gateway) + 1:]
    pytest_assert(len(vlan_hosts_after_gateway) >= 2, 'Vlan size is too small for testing')
    vlan_setting = {
        'vlan_name': first_vlan_name,
        'vlan_gateway': vlan_gateway,
        'vlan_subnet_mask': str(vlan_net.netmask),
        'vlan_hosts': vlan_hosts_after_gateway,
        'vlan_member_with_ptf_idx': vlan_member_with_ptf_idx,
    }

    logging.info("The vlan_setting before test is %s" % vlan_setting)
    return vlan_setting['vlan_name'], \
        vlan_setting['vlan_gateway'], \
        vlan_setting['vlan_subnet_mask'], \
        vlan_setting['vlan_hosts'], \
        vlan_setting['vlan_member_with_ptf_idx']


def test_dhcp_server_with_multiple_dhcp_clients(
    duthost,
    ptfhost,
    parse_vlan_setting_from_running_config
):
    """
        Make sure all ports can get assigend ip when all ports request ip at same time
    """
    vlan_name, gateway, net_mask, vlan_hosts, vlan_members_with_ptf_idx = parse_vlan_setting_from_running_config
    start_command = " && ".join(["dhclient -nw eth%s" % ptf_index for _, ptf_index in vlan_members_with_ptf_idx])
    end_command = " ; ".join(["dhclient -r eth%s" % ptf_index for _, ptf_index in vlan_members_with_ptf_idx])
    try:
        config_to_apply = empty_config_patch()
        dut_ports, _ = zip(*vlan_members_with_ptf_idx)
        exp_assigned_ip_ranges = [[ip] for ip in vlan_hosts[:len(vlan_members_with_ptf_idx)]]
        append_common_config_patch(
            config_to_apply,
            vlan_name,
            gateway,
            net_mask,
            dut_ports,
            exp_assigned_ip_ranges
        )
        apply_dhcp_server_config_gcu(duthost, config_to_apply)
        ptfhost.shell(start_command)

        def all_ip_shown_up(ptfhost, expected_assigned_ips):
            ip_addr_output = ptfhost.shell("ip addr")['stdout']
            for expected_ip in expected_assigned_ips:
                if expected_ip not in ip_addr_output:
                    return False
            return True
        expected_assigned_ips = [range[0] for range in exp_assigned_ip_ranges]
        pytest_assert(
            wait_until(20, 1, 1,
                       all_ip_shown_up,
                       ptfhost,
                       expected_assigned_ips),
            'Not all configurated IP shown up on ptf interfaces'
        )
    finally:
        ptfhost.shell(end_command, module_ignore_errors=True)
        ptfhost.shell("killall dhclient", module_ignore_errors=True)
