import pytest
import logging
import secrets

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.skip_check_dut_health,
    pytest.mark.disable_loganalyzer
]

logger = logging.getLogger(__name__)
allure.logger = logger

def test_attest_pcr_quote(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        duthost.shell('sudo mkdir -p /tmp/att')
        with allure.step("SB-REQ-07: Measured Boot (TPM PCR Extension)"):
            result = duthost.shell('sudo tpm2_createek -c /tmp/att/ek.ctx -G ecc384 -u /tmp/att/ek.pub')
            assert result['rc'] == 0, "Could not create EK"
            result = duthost.shell('sudo tpm2_createak -C /tmp/att/ek.ctx -c /tmp/att/ak.ctx -u /tmp/att/ak.pub -n /tmp/att/ak.name -G ecc384')
            assert result['rc'] == 0, "Could not create AK"
            result = duthost.shell('sudo cp /sys/kernel/security/tpm0/binary_bios_measurements /tmp/att/eventlog')
            assert result['rc'] == 0, "Could not materialize event log"
            result = duthost.shell('sudo tpm2_readpublic -c /tmp/att/ak.ctx -o /tmp/att/ak.pem -f pem')
            assert result['rc'] == 0, "Could not materialize AK public key"
            nonce = secrets.token_hex(32)
            result = duthost.shell(f'sudo tpm2_quote -c /tmp/att/ak.ctx -l \'sha256:0,1,2,3,4,5,6,7,8,9\' -m /tmp/att/quote.msg -s /tmp/att/quote.sig -o /tmp/att/quote.pcrs -g sha256 -q {nonce}')
            assert result['rc'] == 0, "Could not create TPM quote"
            result = duthost.shell(f'sudo tpm2_checkquote -u /tmp/att/ak.pem -m /tmp/att/quote.msg -s /tmp/att/quote.sig -f /tmp/att/quote.pcrs -g sha256 -q {nonce} -e /tmp/att/eventlog')
            assert result['rc'] == 0, "Could not verify TPM quote"
    finally:
        duthost.shell('sudo rm -rf /tmp/att')
