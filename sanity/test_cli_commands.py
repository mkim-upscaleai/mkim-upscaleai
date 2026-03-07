import pytest
import paramiko

# List of commands to test
COMMANDS = [
    "show interfaces status",
    "show platform summary",
    "show platform current",
    "show platform firmware status",
    "show platform firmware version",
    "show platform psustatus",
    "show platform pcieinfo",
    "show platform temperature",
    "show platform fan",
    "show platform ssdhealth",
    "show platform syseeprom"
]

@pytest.mark.parametrize("cmd", COMMANDS)
def test_show_command(ssh_connection, cmd):
    """
    Test to run the show commands via SSH on DUT.
    """
    # Run the command on DUT and capture the output
    result = ssh_connection(cmd)

    # Check if the command returned a successful response
    assert result["rc"] == 0, f"Command '{cmd}' failed with return code {result['rc']}"

    # Check for error strings in the output
    error_keywords = ["Error", "Invalid", "Traceback"]
    output = result.get("stdout", "")

    for error in error_keywords:
        assert error not in output, f"Found error keyword '{error}' in the output:\n{output}"

@pytest.fixture
def ssh_connection(request):
    """
    Setup an SSH connection to the DUT based on CLI arguments.
    """
    # Get DUT SSH details from pytest command line options
    dut_ip = request.config.getoption("--dut-ip")  # Get DUT IP
    dut_user = request.config.getoption("--dut-user")  # Get DUT username
    dut_pass = request.config.getoption("--dut-pass")  # Get DUT password

    # Create SSH client
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Auto add host keys

    # Connect to the DUT via SSH
    ssh_client.connect(dut_ip, username=dut_user, password=dut_pass)

    # Create a simple wrapper for running commands
    def run_command(command):
        stdin, stdout, stderr = ssh_client.exec_command(command)
        return {
            "rc": stdout.channel.recv_exit_status(),
            "stdout": stdout.read().decode("utf-8"),
            "stderr": stderr.read().decode("utf-8")
        }

    # Return the command runner function
    yield run_command

    # Cleanup: Close SSH connection
    ssh_client.close()
