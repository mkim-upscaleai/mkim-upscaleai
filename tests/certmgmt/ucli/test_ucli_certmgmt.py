
import pytest
import logging
import re
import json # noqa F401
import ast
import time
import uuid

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

def test_certmgmt_show_crypto(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("X509-REQ-03: System must display encryption status and cipher in show commands"):
        try:
            # UCLI
            result = duthost.shell('ucli -c "show crypto encrypt-data"')
            assert result['rc'] == 0, "UCLI should show crypto information"
        finally:
            pass

def test_certmgmt_named_certs(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    with allure.step("X509-REQ-06: System must support certificate database with named cert objects"):
        try:
            # UCLI
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivacert generate self-signed"')
            result = dut_run_retry(duthost, 'ucli -c "show crypto certificate" | grep -i shivacert')
            assert result['rc'] == 0, 'UCLI show should show created certificate'
            result = dut_run_retry(duthost, 'test -f /etc/sonic/credentials/certs/shivacert.pem')
            assert result['rc'] == 0, "Certificate file missing for shivacert"
            result = dut_run_retry(duthost, 'test -f /etc/sonic/credentials/keys/shivacert.pem')
            assert result['rc'] == 0, "Key file missing for shivacert"

            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name ShivaCert generate self-signed"')
            result = dut_run_retry(duthost, 'ucli -c "show crypto certificate" | grep -i ShivaCert')
            assert result['rc'] == 0, 'UCLI show should show created certificate'
            result = dut_run_retry(duthost, 'test -f /etc/sonic/credentials/certs/ShivaCert.pem')
            assert result['rc'] == 0, "Certificate file missing for ShivaCert"
            result = dut_run_retry(duthost, 'test -f /etc/sonic/credentials/keys/ShivaCert.pem')
            assert result['rc'] == 0, "Key file missing for ShivaCert"
        finally:
            duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivacert"')
            duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name ShivaCert"')
            result = dut_run_retry(duthost, '! test -f /etc/sonic/credentials/keys/shivacert.pem')
            assert result['rc'] == 0, "Key file for shivacert was not removed"
            result = dut_run_retry(duthost, '! test -f /etc/sonic/credentials/keys/ShivaCert.pem')
            assert result['rc'] == 0, "Key file for ShivaCert was not removed"
            result = dut_run_retry(duthost, '! test -f /etc/sonic/credentials/certs/shivacert.pem')
            assert result['rc'] == 0, "Cert file for shivacert was not removed"
            result = dut_run_retry(duthost, '! test -f /etc/sonic/credentials/certs/ShivaCert.pem')
            assert result['rc'] == 0, "Cert file for ShivaCert was not removed"

def test_certmgmt_config(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    TMP_FILENAME = f'/tmp/foo_{uuid.uuid4().hex}.crt'
    try:
        # UCLI
        with allure.step("X509-REQ-07: System must generate self-signed certificates with configurable attributes"):
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivacert1 generate self-signed hash-algorithm sha256 key-size-bits 2048"')
            result = dut_run_retry(duthost, 'openssl x509 -in /etc/sonic/credentials/certs/shivacert1.pem -text -noout | awk -v RS="" \'/2048 bit/ && /rsaEncryption/ && /sha256/ && /CA:FALSE/\'')
            assert result['rc'] == 0, 'Did not generate certificate with correct attributes'
        with allure.step("X509-REQ-18: System must support certificate inspection with full attributes"):
            result = dut_run_retry(duthost, 'ucli -c "show crypto certificate name shivacert1 detail" | awk -v RS="" \'/2048 bit/ && /rsaEncryption/ && /sha256/ && /CA:FALSE/\'')
            assert result['rc'] == 0, 'show crypto command did not show the correct information'
        with allure.step("X509-REQ-19: System must support exporting PEM public cert"):
            duthost.shell(f'ucli -c "show crypto certificate name shivacert1 public-pem" > {TMP_FILENAME}')
            result = dut_run_retry(duthost, f'openssl x509 -in {TMP_FILENAME} -text -noout')
            assert result['rc'] == 0, 'export of certificate did not complete successfully'
        with allure.step("X509-REQ-17: System must support CA Basic Constraints flag control"):
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivacert2 generate self-signed key-type ecdsa hash-algorithm sha512 key-curve secp384r1 san upscaleshivacert.org ca-valid true"')
            result = dut_run_retry(duthost, 'openssl x509 -in /etc/sonic/credentials/certs/shivacert2.pem -text -noout | awk -v RS="" \'/384 bit/ && /ecPublicKey/ && /SHA512/ && /CA:TRUE/\'')
            assert result['rc'] == 0, 'Did not generate certificate with correct attributes'
            result = dut_run_retry(duthost, 'ucli -c "show crypto certificate name shivacert2 detail" | awk -v RS="" \'/384 bit/ && /ecPublicKey/ && /SHA512/ && /CA:TRUE/\'')
            assert result['rc'] == 0, 'show crypto command did not show the correct information'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivacert1"', module_ignore_errors=True)
        duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivacert2"', module_ignore_errors=True)
        duthost.shell(f'rm -f {TMP_FILENAME}', module_ignore_errors=True)

def test_certmgmt_imports(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step("X509-REQ-08: System must support importing private keys in PEM format"):
            duthost.shell('openssl req -x509 -newkey rsa:4096 -keyout /tmp/shivakey.pem -out /tmp/shivacert.pem -sha256 -days 365 -nodes -subj "/CN=localhost"')
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shiva1 private-key pem /tmp/shivakey.pem"')
            result = dut_run_retry(duthost, 'ucli -c "show running-config | include private-key" | ! grep -E "modulus|coefficient|exponent"')
            assert result['rc'] == 0, 'show running-config private key information was disclosed when it should not have'
            result = dut_run_retry(duthost, 'ucli -c "show crypto certificate name shiva1 detail" | ! grep -E "modulus|coefficient|exponent"')
            assert result['rc'] == 0, 'show crypto private key information was disclosed when it should not have'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/keys/shiva1.pem /tmp/shivakey.pem')
            assert result['rc'] == 0, "Key file did not match import"
        with allure.step("X509-REQ-09: System must support importing public cert chains in PEM format"):
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shiva1 public-cert pem /tmp/shivacert.pem"')
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/shiva1.pem /tmp/shivacert.pem')
            assert result['rc'] == 0, 'Certificate did not match import'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shiva1"', module_ignore_errors=True)
        duthost.shell('ucli -c "rm -f /tmp/shivakey.pem /tmp/shivacert.pem"', module_ignore_errors=True)

def test_certmgmt_defaults(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step("X509-REQ-11: System must support default certificate role for HTTPS, gNMI, API, etc"):
            result = dut_run_retry(duthost, 'test -f /etc/sonic/credentials/certs/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'System default certificate was not found'
            result = dut_run_retry(duthost, 'test -f /etc/sonic/credentials/keys/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'System default key was not found'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/_default.pem /etc/sonic/credentials/certs/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'Current default does not match system default certificate'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/keys/_default.pem /etc/sonic/credentials/keys/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'Current default does not match system default key'

            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivadefaultcert generate self-signed"')
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate default-cert name shivadefaultcert"')
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/_default.pem /etc/sonic/credentials/certs/shivadefaultcert.pem')
            assert result['rc'] == 0, 'Current default does not match new default certificate'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/keys/_default.pem /etc/sonic/credentials/keys/shivadefaultcert.pem')
            assert result['rc'] == 0, 'Current default does not match new default key'

        with allure.step("X509-REQ-12: System must revert to self-signed cert if default cert is deleted"):
            duthost.shell('ucli -c "configure terminal" -c "no crypto certificate default-cert"')
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/_default.pem /etc/sonic/credentials/certs/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'Current default does not match system default certificate'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/keys/_default.pem /etc/sonic/credentials/keys/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'Current default does not match system default key'

            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivadefaultcert generate self-signed"')
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate default-cert name shivadefaultcert"')
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/_default.pem /etc/sonic/credentials/certs/shivadefaultcert.pem')
            assert result['rc'] == 0, 'Current default does not match new default certificate'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/keys/_default.pem /etc/sonic/credentials/keys/shivadefaultcert.pem')
            assert result['rc'] == 0, 'Current default does not match new default key'

            duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivadefaultcert"')
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/_default.pem /etc/sonic/credentials/certs/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'Current default does not match system default certificate'
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/keys/_default.pem /etc/sonic/credentials/keys/SYSTEM_DEFAULT.pem')
            assert result['rc'] == 0, 'Current default does not match system default key'

    finally:
        pass

def test_certmgmt_regenerate(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step("X509-REQ-16: System must support regenerating certificates with new validity"):
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivacert generate self-signed days-valid 10 hash-algorithm sha256"')
            result = dut_run_retry(duthost, 'openssl x509 -in /etc/sonic/credentials/certs/shivacert.pem -text -noout | grep "sha256"')
            assert result['rc'] == 0, 'Could not set initial certificate for regeneration'
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivacert regenerate days-valid 100 hash-algorithm sha512"')
            result = dut_run_retry(duthost, 'openssl x509 -in /etc/sonic/credentials/certs/shivacert.pem -text -noout | grep "sha512"')
            assert result['rc'] == 0, 'Could not regenerate certificate'
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivacert"', module_ignore_errors=True)

def test_certmgmt_rotate_no_reboot(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step("X509-REQ-30: System must support certificate rotation without reboot"):
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivadefaultcert generate self-signed days-valid 10 hash-algorithm sha384"')
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate default-cert name shivadefaultcert"')
            result = dut_run_retry(duthost, 'diff /etc/sonic/credentials/certs/_default.pem /etc/sonic/credentials/certs/shivadefaultcert.pem')
            assert result['rc'] == 0, "Initial default certificate was not set"
            result = dut_run_retry(duthost, 'curl -vvIk https://localhost 2>&1 | grep "signed using sha384"')
            assert result['rc'] == 0, "Initial default certificate may not have been propagated"
            result = duthost.shell('curl -vvIk https://localhost 2>&1 | grep "expire date:" | awk -F\': \' \'{print $2}\' | xargs -I {} date -d "{}" +%s')
            old_expire = int(result['stdout'].strip())
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivadefaultcert regenerate days-valid 100 hash-algorithm sha512"')
            result = dut_run_retry(duthost, 'curl -vvIk https://localhost 2>&1 | grep "signed using sha512"')
            assert result['rc'] == 0, "Regenerated certificate may not have been propagated"
            result = duthost.shell('curl -vvIk https://localhost 2>&1 | grep "expire date:" | awk -F\': \' \'{print $2}\' | xargs -I {} date -d "{}" +%s')
            new_expire = int(result['stdout'].strip())
            assert old_expire < new_expire, 'Certificate regeneration did not update expiration'
        with allure.step("X509-REQ-29: System must integrate certificates with API, gNMI, telemetry, and UI"):
            # TODO: Check with gNMI, telemetry, and UI when available'
            pass
    finally:
        duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivadefaultcert"', module_ignore_errors=True)

def test_certmgmt_ca_trust_list(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step("X509-REQ-20: System must support viewing CA trust list"):
            result = duthost.shell('ucli -c "show crypto certificate default-ca-list"')
            assert result['rc'] == 0, 'showing CA trust list failed'
            # TODO: Check something more substantial when available
    finally:
        pass

def test_certmgmt_strong_crypto(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step("X509-REQ-22: System must support strong crypto (AES-GCM, SHA-256/512)"):
            result = duthost.shell('echo "Q" | openssl s_client -connect localhost:443 -tls1', module_ignore_errors=True)
            assert result['rc'] != 0, 'TLSv1 allowed when it should not have'
        with allure.step("X509-REQ-23: System must support PFS with modern DH groups"):
            result = duthost.shell('echo "Q" | openssl s_client -connect localhost:443 -tls1_2 -cipher AES256-SHA', module_ignore_errors=True)
            assert result['rc'] != 0, 'TLSv1.2 without GCM or PFS should not be allowed'
            result = duthost.shell('echo "Q" | openssl s_client -connect localhost:443 -tls1_3', module_ignore_errors=True)
            assert result['rc'] == 0, 'TLSv1.3 should be allowed'
    finally:
        pass

def test_certmgmt_logging(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        # UCLI
        with allure.step('X509-REQ-28: System must log certificate changes and encryption state transitions'):
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivalogcert generate self-signed days-valid 10"')
            duthost.shell('ucli -c "configure terminal" -c "crypto certificate name shivalogcert generate self-signed days-valid 100"')
            duthost.shell('ucli -c "configure terminal" -c "no crypto certificate name shivalogcert"')
            result = dut_run_retry(duthost, 'ucli -c "show logging" | grep CERTMGR | grep cert=shivalogcert | awk \'END {exit !(NR >= 3)}\'')
            assert result['rc'] == 0, 'Expected at least 3 log entries for certificate operations'
    finally:
        pass

