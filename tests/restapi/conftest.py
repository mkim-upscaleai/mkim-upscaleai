import logging
import os
import pytest
import urllib3
import ipaddress
from six.moves.urllib.parse import urlunparse

from tests.common import config_reload
from tests.common.helpers.assertions import pytest_require as pyrequire
from tests.common.helpers.dut_utils import check_container_state

from helper import apply_cert_config

RESTAPI_CONTAINER_NAME = 'restapi'

# Use the directory where this conftest.py is located for all certificate files
# This ensures localhost.shell() and duthost.copy() use the same paths
CERT_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="module", autouse=True)
def setup_restapi_server(duthosts, rand_one_dut_hostname, localhost):
    '''
    Create RESTAPI client certificates and copy the subject names to the config DB
    '''
    duthost = duthosts[rand_one_dut_hostname]

    # Check if RESTAPI is enabled on the device
    pyrequire(check_container_state(duthost, RESTAPI_CONTAINER_NAME, should_be_running=True),
              "Test was not supported on devices which do not support RESTAPI!")

    # Check for clock skew between test host and DUT
    test_host_time = int(localhost.shell("date '+%s'")['stdout'].strip())
    dut_time = int(duthost.shell("date '+%s'")['stdout'].strip())
    clock_skew = test_host_time - dut_time

    # Define absolute paths for all certificate files
    ca_key = os.path.join(CERT_DIR, 'restapiCA.key')
    ca_pem = os.path.join(CERT_DIR, 'restapiCA.pem')
    ca_srl = os.path.join(CERT_DIR, 'restapiCA.srl')
    server_key = os.path.join(CERT_DIR, 'restapiserver.key')
    server_csr = os.path.join(CERT_DIR, 'restapiserver.csr')
    server_crt = os.path.join(CERT_DIR, 'restapiserver.crt')
    client_key = os.path.join(CERT_DIR, 'restapiclient.key')
    client_csr = os.path.join(CERT_DIR, 'restapiclient.csr')
    client_crt = os.path.join(CERT_DIR, 'restapiclient.crt')

    # Create Root key
    local_command = f"openssl genrsa -out {ca_key} 2048"
    localhost.shell(local_command)

    # Create Root cert
    local_command = f"openssl req -x509 -new -nodes -key {ca_key} -sha256 -days 1825 -subj '/CN=test.restapi.sonic' -out {ca_pem}"
    localhost.shell(local_command)

    # Create server key
    local_command = f"openssl genrsa -out {server_key} 2048"
    localhost.shell(local_command)

    # Create server CSR
    local_command = f"openssl req -new -key {server_key} -subj '/CN=test.server.restapi.sonic' -out {server_csr}"
    localhost.shell(local_command)

    # Sign server certificate
    local_command = f"openssl x509 -req -in {server_csr} -CA {ca_pem} -CAkey {ca_key} -CAcreateserial -out {server_crt} -days 825 -sha256"
    localhost.shell(local_command)

    # Create client key
    local_command = f"openssl genrsa -out {client_key} 2048"
    localhost.shell(local_command)

    # Create client CSR
    local_command = f"openssl req -new -key {client_key} -subj '/CN=test.client.restapi.sonic' -out {client_csr}"
    localhost.shell(local_command)

    # Sign client certificate
    local_command = f"openssl x509 -req -in {client_csr} -CA {ca_pem} -CAkey {ca_key} -CAcreateserial -out {client_crt} -days 825 -sha256"
    localhost.shell(local_command)

    # If DUT clock is behind, wait for it to catch up to certificate creation time
    if clock_skew > 10:
        import time
        wait_time = clock_skew + 10
        logging.info(f"DUT clock is {clock_skew}s behind test host. Waiting {wait_time}s for DUT to catch up to certificate validity time...")
        time.sleep(wait_time)

    # Copy CA certificate and server certificate over to the DUT
    duthost.copy(src=ca_pem, dest='/etc/sonic/credentials/restapiCA.pem')
    duthost.copy(src=server_crt, dest='/etc/sonic/credentials/testrestapiserver.crt')
    duthost.copy(src=server_key, dest='/etc/sonic/credentials/testrestapiserver.key')

    apply_cert_config(duthost)
    urllib3.disable_warnings()

    yield
    # Perform a config load_minigraph to ensure config_db is not corrupted
    config_reload(duthost, config_source='minigraph')

    # Delete all created certs
    for cert_file in [ca_key, ca_pem, ca_srl, server_key, server_csr, server_crt, client_key, client_csr, client_crt]:
        if os.path.exists(cert_file):
            os.remove(cert_file)


@pytest.fixture
def construct_url(duthosts, rand_one_dut_hostname):
    def get_endpoint(path):
        duthost = duthosts[rand_one_dut_hostname]
        RESTAPI_PORT = "8081"

        # Handle IPv6 addresses by wrapping them in square brackets
        try:
            ip_obj = ipaddress.ip_address(duthost.mgmt_ip)
            if ip_obj.version == 6:
                netloc = "[{}]:{}".format(duthost.mgmt_ip, RESTAPI_PORT)
            else:
                netloc = "{}:{}".format(duthost.mgmt_ip, RESTAPI_PORT)
        except ValueError:
            # If it's not a valid IP address, treat it as hostname and use as-is
            netloc = "{}:{}".format(duthost.mgmt_ip, RESTAPI_PORT)

        try:
            tup = ('https', netloc, path, '', '', '')
            endpoint = urlunparse(tup)
        except Exception:
            logging.error("Invalid URL: "+endpoint)
            return None
        return endpoint
    return get_endpoint


@pytest.fixture
def vlan_members(duthosts, rand_one_dut_hostname, tbinfo):
    duthost = duthosts[rand_one_dut_hostname]
    VLAN_INDEX = 0
    mg_facts = duthost.get_extended_minigraph_facts(tbinfo)
    if mg_facts["minigraph_vlans"] != {}:
        vlan_interfaces = list(mg_facts["minigraph_vlans"].values())[
            VLAN_INDEX]["members"]
        if vlan_interfaces is not None:
            return vlan_interfaces
    return []


@pytest.fixture
def is_support_warm_fast_reboot(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    support_warm_fast_reboot = True
    if 'isolated' in duthosts.tbinfo['topo']['name'] or \
            duthost.dut_basic_facts()['ansible_facts']['dut_basic_facts'].get("is_smartswitch"):
        support_warm_fast_reboot = False
        logging.info("Skipping warm and fast reboot tests for isolated topology or smartswitch")
        logging.info("Applying cert config")
        apply_cert_config(duthost)

    yield support_warm_fast_reboot
