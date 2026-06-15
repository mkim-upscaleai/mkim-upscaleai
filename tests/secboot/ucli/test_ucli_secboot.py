
import pytest
import logging
import time

from tests.common.reboot import reboot
from tests.common.fixtures.duthost_utils import backup_and_restore_config_db  # noqa F401
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.skip_check_dut_health,
    pytest.mark.disable_loganalyzer
]

logger = logging.getLogger(__name__)
allure.logger = logger

def _download_images(duthost):
    # sonic-mellanox-signed.bin sonic-mellanox-unsigned.bin sonic-mellanox-dbxsigned.bin
    pass

def _download_certs(duthost):
    # new_db.auth new_dbx.auth clean_db.auth clean_dbx.auth 
    pass

def _download_kmodules(duthost):
    # dbsigned.ko dbxsigned.ko unsigned.ko
    pass

def dut_run_retry(duthost, cmd, attempts: int = 5, wait_time_sec: int = 2):
    attempts = 1 if attempts < 1 else attempts
    while attempts > 0:
        result = duthost.shell(cmd, module_ignore_errors=True)
        if result['rc'] == 0:
            return result
        time.sleep(wait_time_sec)
        attempts = attempts - 1
    return result

def test_secboot_show_boot(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        _download_images(duthost)
        with allure.step("SB-REQ-01: UEFI Secure Boot State Reporting"):
            duthost.shell('sudo sonic-installer install -y /tmp/sonic-mellanox-signed.bin')
            reboot(duthost, localhost, safe_reboot=True)
            result = dut_run_retry(duthost, 'ls')
            assert result['rc'] == 0, "Secure boot failed"
            result = duthost.shell('ucli -c "show boot" | grep secure | grep enabled')
            assert result['rc'] == 0, "UCLI should show secure boot is enabled"
    finally:
        pass

def test_secboot_unsigned(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        _download_images(duthost)
        with allure.step("SB-REQ-03: Unsigned/Invalid Component Rejection"):
            result = duthost.shell('sudo sonic-installer install -y /tmp/sonic-mellanox-unsigned.bin')
            assert result['rc'] != 0, "Unsigned image should have not have been installed"
    finally:
        pass

def test_secboot_dbx(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    pytest.skip("test_secboot_dbx; will brick your switch unless you can get a properly signed image back")
    try:
        _download_images(duthost)
        with allure.step("SB-REQ-04: Blacklisted Component Rejection (dbx)"):
            duthost.shell('sudo sonic-installer install -y /tmp/sonic-mellanox-dbxsigned.bin')
            reboot(duthost, localhost, safe_reboot=True)
            result = dut_run_retry(duthost, 'ls')
            assert result['rc'] != 0, "Secure boot succeeded when it should have failed dbx"
    finally:
        # TODO: Restore signed image without shell and power cycle
        pass

def test_secboot_kmodules(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        _download_kmodules(duthost)
        with allure.step("SB-REQ-05: Kernel Module Signature Enforcement"):
            result = duthost.shell('sudo insmod /tmp/signedkm.ko')
            assert result['rc'] == 0, "Should have loaded signed kernel module"
            result = duthost.shell('sudo insmod /tmp/unsignedkm.ko')
            assert result['rc'] != 0, "Should have not loaded unsigned kernel module"
            result = duthost.shell('sudo insmod /tmp/dbxsignedkm.ko')
            assert result['rc'] != 0, "Should have not loaded dbx kernel module"
    finally:
        duthost.shell('sudo rmmod signedkm', module_ignore_errors=True)
        duthost.shell('sudo rmmod unsignedkm', module_ignore_errors=True)
        duthost.shell('sudo rmmod dbxsignedkm', module_ignore_errors=True)

def test_secboot_certmgmt(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    try:
        _download_certs(duthost)
        with allure.step("SB-REQ-06: Certificate Management (db/dbx)"):
            result = duthost.shell("sudo efi-updatevar -f /tmp/new_db.auth db")
            assert result['rc'] == 0, "Could not install db cert"
            result = duthost.shell("sudo efi-updatevar -f /tmp/new_dbx.auth dbx")
            assert result['rc'] == 0, "Could not install dbx cert"
            result  = dut_run_retry(duthost, "[ $(efi-readvar -v db | grep -c db:) -eq 2 ]")
            assert result['rc'] == 0, "Did not successfully install db certs"
            result = duthost.shell("sudo efi-updatevar -f /tmp/clean_db.auth db")
            assert result['rc'] == 0, "Could not restore db certs"
            result = duthost.shell("sudo efi-updatevar -f /tmp/clean_dbx.auth dbx")
            assert result['rc'] == 0, "Could not restore dbx certs"
    finally:
        duthost.shell("sudo efi-updatevar -f /tmp/clean_db.auth db", module_ignore_errors=True)
        duthost.shell("sudo efi-updatevar -f /tmp/clean_dbx.auth dbx", module_ignore_errors=True)

def test_secboot_warmboot(request, duthost, ptfhost, localhost, backup_and_restore_config_db): # noqa F811
    pytest.skip("test_secboot_warmboot; need a way to power cycle switch")
    try:
        _download_images(duthost)
        with allure.step("SB-REQ-07: Warm Boot"):
            duthost.shell('sudo sonic-installer install -y /tmp/sonic-mellanox-signed.bin')
            reboot(duthost, localhost, reboot_type="warm", wait_warmboot_finalizer=True)
            result = dut_run_retry(duthost, 'ucli -c "show boot" | grep secure | grep enabled')
            assert result['rc'] == 0, "UCLI should show secure boot is enabled on cold boot"
    finally:
        pass

