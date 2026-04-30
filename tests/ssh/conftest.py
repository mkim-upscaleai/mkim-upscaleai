try:
    import importlib.util
    import importlib.machinery
    use_importlib = True
except ImportError:
    import imp
    use_importlib = False
import subprocess
import pytest
import logging

logger = logging.getLogger(__name__)

# enc_ciphers list
PERMITTED_ENC_CIPHERS = [
    "aes256-gcm@openssh.com",
    "aes256-ctr",
    "aes192-ctr"
]

# MACs list
PERMITTED_MACS = [
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com"
]

# Kexs list
PERMITTED_KEXS = [
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521"
]


def load_source(modname, filename):
    loader = importlib.machinery.SourceFileLoader(modname, filename)
    spec = importlib.util.spec_from_file_location(modname, filename, loader=loader)
    module = importlib.util.module_from_spec(spec)
    # The module is always executed and not cached in sys.modules.
    # Uncomment the following line to cache the module.
    # sys.modules[module.__name__] = module
    loader.exec_module(module)
    return module


def _query_local_ssh_algorithms(ssh_q_arg):
    # pexpect.spawn("ssh ...") in the tests runs the sonic-mgmt container's own
    # ssh binary, which may be older than both the PTF and the DUT. Intersect its
    # advertised algorithms too so we never parametrize a name the local client
    # rejects at CLI parse time (e.g. sntrup761x25519-sha512 on OpenSSH < 9.9).
    try:
        raw_output = subprocess.check_output(
            ["ssh", "-Q", ssh_q_arg],
            stderr=subprocess.STDOUT, universal_newlines=True)
        return raw_output.split()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        logger.warning(
            "Failed to query local ssh client for '{}' algorithms; skipping local "
            "intersection: {}".format(ssh_q_arg, e))
        return None


def generate_ssh_ciphers(request, typename):
    if typename == "enc":
        remote_cmd_C = "ssh -Q cipher"
        remote_cmd_S = "sudo sshd -T | grep -i '^ciphers'"
        local_ssh_q_arg = "cipher"
        permitted_list = PERMITTED_ENC_CIPHERS
    elif typename == "mac":
        remote_cmd_C = "ssh -Q mac"
        remote_cmd_S = "sudo sshd -T | grep -i '^macs'"
        local_ssh_q_arg = "mac"
        permitted_list = PERMITTED_MACS
    elif typename == "kex":
        remote_cmd_C = "ssh -Q kex"
        remote_cmd_S = "sudo sshd -T | grep -i '^kexalgorithms'"
        local_ssh_q_arg = "kex"
        permitted_list = PERMITTED_KEXS

    # If --collect-only is specified, return the permitted list directly. Otherwise, pytest will try to
    # connect to DUT. If DUT is not online, pytest will fail with collecting test items.
    if hasattr(request.config.option, "collectonly") and request.config.option.collectonly:
        return permitted_list

    testbed_name = request.config.option.testbed
    testbed_file = request.config.option.testbed_file
    if use_importlib:
        testbed_module = load_source('testbed', 'common/testbed.py')
    else:
        testbed_module = imp.load_source('testbed', 'common/testbed.py')
    tbinfo = testbed_module.TestbedInfo(
        testbed_file).testbed_topo.get(testbed_name, None)

    dut_name = tbinfo['duts'][0]
    inv_name = tbinfo['inv_name'] if 'inv_name' in list(
        tbinfo.keys()) else 'lab'
    ptf_name = tbinfo['ptf']

    cmd_C = ["ansible", "-m", "shell", "-i", "../ansible/{}".format(inv_name), ptf_name, "-a", remote_cmd_C]
    cmd_S = ["ansible", "-m", "shell", "-i", "../ansible/{}".format(inv_name), dut_name, "-a", remote_cmd_S]
    logger.debug('ansible_cmd_C:\n{}'.format(" ".join(cmd_C)))
    logger.debug('ansible_cmd_S:\n{}'.format(" ".join(cmd_S)))

    try:
        raw_output = subprocess.check_output(
            cmd_C, shell=False, stderr=subprocess.STDOUT, universal_newlines=True)
        cipher_list_C = raw_output.split("rc=0 >>", 1)[1].split()
        logger.debug('client cipher full list: {}'.format(cipher_list_C))

        raw_output = subprocess.check_output(
            cmd_S, shell=False, stderr=subprocess.STDOUT, universal_newlines=True)
        cipher_list_S = raw_output.split("rc=0 >>", 1)[1].split(" ")[1].strip("\n").split(",")
        logger.debug('server cipher full list: {}'.format(cipher_list_S))

        cipher_list_local = _query_local_ssh_algorithms(local_ssh_q_arg)
        if cipher_list_local is not None:
            logger.debug('local sonic-mgmt client cipher full list: {}'.format(cipher_list_local))
            common_cipher_list = list(
                set(cipher_list_C) & set(cipher_list_S) & set(cipher_list_local))
        else:
            common_cipher_list = list(set(cipher_list_C) & set(cipher_list_S))
        logger.debug('common cipher list: {}'.format(common_cipher_list))

        cipher_param_list = []
        for cipher in common_cipher_list:
            cipher_param_list.append(cipher)

        return cipher_param_list
    except subprocess.CalledProcessError as e:
        logger.error('Failed to get DUT\'s {} ciphers full list: {}'.format(
            typename, e.output))
        return []


def pytest_generate_tests(metafunc):
    if 'enum_dut_ssh_enc_cipher' in metafunc.fixturenames:
        metafunc.parametrize('enum_dut_ssh_enc_cipher',
                             generate_ssh_ciphers(metafunc, "enc"))
    elif 'enum_dut_ssh_mac' in metafunc.fixturenames:
        metafunc.parametrize('enum_dut_ssh_mac',
                             generate_ssh_ciphers(metafunc, "mac"))
    elif 'enum_dut_ssh_kex' in metafunc.fixturenames:
        metafunc.parametrize('enum_dut_ssh_kex',
                             generate_ssh_ciphers(metafunc, "kex"))
