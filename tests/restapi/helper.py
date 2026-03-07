import time

# Maximum time to wait for RESTAPI to be ready (listening on port 8081)
RESTAPI_READY_TIMEOUT = 120
# Interval between checks for RESTAPI readiness
RESTAPI_READY_CHECK_INTERVAL = 5
# Number of retries for applying cert config (useful after reboots)
APPLY_CERT_CONFIG_RETRIES = 3
# Wait time before retrying cert config
APPLY_CERT_CONFIG_RETRY_WAIT = 30


def apply_cert_config(duthost):
    """
    Configure RESTAPI certificates in CONFIG_DB and restart the service.
    Uses docker exec to run redis-cli inside the database container to ensure
    correct DB connectivity across all SONiC containers.

    This function includes retry logic to handle race conditions after reboots
    where other services may overwrite CONFIG_DB.
    """
    for attempt in range(APPLY_CERT_CONFIG_RETRIES):
        if attempt > 0:
            time.sleep(APPLY_CERT_CONFIG_RETRY_WAIT)

        # Wait for database container to be ready
        wait_for_database_ready(duthost)

        # Set the certificate configuration
        if not set_cert_config_in_db(duthost):
            continue

        # Verify the configuration was set correctly
        if not verify_cert_config(duthost):
            continue

        # Restart RESTAPI server with the updated config
        duthost.shell("sudo systemctl restart restapi")

        # Wait for RESTAPI to be ready (listening on port 8081)
        if wait_for_restapi_ready(duthost):
            # Final verification that config is still correct
            if verify_cert_config(duthost):
                return True
            else:
                continue

    return False

def set_trusted_client_cert_subject_name(duthost, new_subject_name):
    # Set trusted client certificate subject name in config DB
    dut_command = f"redis-cli -n 4 hset \
                    'RESTAPI|certs' \
                    'client_crt_cname' \
                    '{new_subject_name}'"
    duthost.shell(dut_command)

    time.sleep(5)

    # Restart RESTAPI server with the updated config
    dut_command = "sudo systemctl restart restapi"
    duthost.shell(dut_command)
    time.sleep(RESTAPI_SERVER_START_WAIT_TIME)


def wait_for_database_ready(duthost, timeout=60):
    """
    Wait for the database container and Redis to be ready.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = duthost.shell("docker exec database redis-cli ping", module_ignore_errors=True)
        if result['rc'] == 0 and 'PONG' in result['stdout']:
            return True
        time.sleep(5)
    return False


def set_cert_config_in_db(duthost):
    """
    Set the certificate configuration in CONFIG_DB.
    """
    redis_cli_prefix = "docker exec database redis-cli -n 4"

    commands = [
        f"{redis_cli_prefix} hset 'RESTAPI|certs' 'client_crt_cname' 'test.client.restapi.sonic'",
        f"{redis_cli_prefix} hset 'RESTAPI|certs' 'ca_crt' '/etc/sonic/credentials/restapiCA.pem'",
        f"{redis_cli_prefix} hset 'RESTAPI|certs' 'server_crt' '/etc/sonic/credentials/testrestapiserver.crt'",
        f"{redis_cli_prefix} hset 'RESTAPI|certs' 'server_key' '/etc/sonic/credentials/testrestapiserver.key'",
    ]

    for cmd in commands:
        result = duthost.shell(cmd, module_ignore_errors=True)
        if result['rc'] != 0:
            return False

    return True


def verify_cert_config(duthost):
    """
    Verify that the CONFIG_DB has the correct certificate configuration.
    """
    redis_cli_prefix = "docker exec database redis-cli -n 4"

    expected_values = {
        'ca_crt': '/etc/sonic/credentials/restapiCA.pem',
        'client_crt_cname': 'test.client.restapi.sonic',
        'server_crt': '/etc/sonic/credentials/testrestapiserver.crt',
        'server_key': '/etc/sonic/credentials/testrestapiserver.key',
    }

    for key, expected in expected_values.items():
        result = duthost.shell(f"{redis_cli_prefix} hget 'RESTAPI|certs' '{key}'", module_ignore_errors=True)
        actual = result['stdout'].strip()
        if actual != expected:
            return False

    return True


def wait_for_restapi_ready(duthost, timeout=RESTAPI_READY_TIMEOUT, interval=RESTAPI_READY_CHECK_INTERVAL):
    """
    Wait for RESTAPI service to be ready by checking if port 8081 is listening.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = duthost.shell("sudo netstat -tlnp | grep 8081", module_ignore_errors=True)
        if result['rc'] == 0 and '8081' in result['stdout']:
            # Additional wait for go-server to fully initialize TLS
            time.sleep(10)
            return True
        time.sleep(interval)

    return False
