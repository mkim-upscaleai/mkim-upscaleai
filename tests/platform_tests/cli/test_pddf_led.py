"""
Tests for the `pddf_ledutil` CLI tool in SONiC.

Covers:
  - pddf_ledutil --help (exit 0 smoke test)
  - pddf_ledutil getledcurstate (output format and valid state values)
  - pddf_ledutil setstatusled / getstatusled set-verify-restore cycle

Issue: #21824 — PDDF LED CLI has zero test coverage
"""

import logging
import pytest
from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.device_type('physical'),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
]

VALID_LED_STATES = {"green", "amber", "red", "off", "N/A"}

# The system LED component name exposed by pddf_ledutil on most PDDF platforms.
# Used as the default target for the set/verify test when dynamic detection fails.
SYSTEM_LED_NAME = "SYS_LED"


# ---------------------------------------------------------------------------
# Module-level skip guard
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def skip_if_no_pddf(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    Skip the entire module on platforms where pddf_ledutil is not installed.
    Runs automatically before any test in this file.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    logging.info("Checking for pddf_ledutil on '{}'".format(duthost.hostname))
    result = duthost.shell("which pddf_ledutil", module_ignore_errors=True)
    if result['rc'] != 0:
        pytest.skip("pddf_ledutil not available on this platform — skipping PDDF LED tests")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _parse_led_state_output(output_lines):
    """
    Parse colon-separated lines produced by pddf_ledutil getledcurstate.

    Expected format per line:
        <LED component name>: <state>

    Returns a dict mapping LED name -> state string.
    Lines that do not match the expected format are silently skipped.
    """
    led_states = {}
    for line in output_lines:
        if ':' not in line:
            continue
        parts = line.split(':', 1)
        name = parts[0].strip()
        state = parts[1].strip()
        if name:
            led_states[name] = state
    return led_states


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pddf_ledutil_help(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    @summary: Verify that 'pddf_ledutil --help' exits with return code 0.

    This is a basic smoke test confirming the CLI binary is functional.
    Some implementations may use '-h' instead of '--help'; we try '--help'
    first and fall back to '-h' if the first invocation fails.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    cmd = "pddf_ledutil --help"

    logging.info("Verifying '{}' exits 0 on '{}'".format(cmd, duthost.hostname))
    result = duthost.shell(cmd, module_ignore_errors=True)

    if result['rc'] != 0:
        # Some platforms implement only the short flag
        cmd = "pddf_ledutil -h"
        logging.info("'--help' returned non-zero; retrying with '{}'".format(cmd))
        result = duthost.shell(cmd, module_ignore_errors=True)

    pytest_assert(
        result['rc'] == 0,
        "Expected 'pddf_ledutil --help' to exit 0 on '{}', got rc={}. "
        "stderr: {}".format(duthost.hostname, result['rc'], result.get('stderr', ''))
    )
    logging.info("'{}' exited 0 as expected on '{}'".format(cmd, duthost.hostname))


def test_pddf_ledutil_getledcurstate(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    @summary: Verify output of 'pddf_ledutil getledcurstate'.

    Checks:
      1. The command exits with return code 0.
      2. Stdout is non-empty (at least one LED entry reported).
      3. Every LED state value in the parsed output is in VALID_LED_STATES.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    cmd = "pddf_ledutil getledcurstate"

    logging.info("Verifying output of '{}' on '{}'".format(cmd, duthost.hostname))
    result = duthost.shell(cmd, module_ignore_errors=True)

    pytest_assert(
        result['rc'] == 0,
        "Command '{}' failed on '{}' with rc={}. stderr: {}".format(
            cmd, duthost.hostname, result['rc'], result.get('stderr', '')
        )
    )

    output_lines = result['stdout_lines']
    pytest_assert(
        len(output_lines) > 0,
        "Command '{}' produced no output on '{}'".format(cmd, duthost.hostname)
    )

    led_states = _parse_led_state_output(output_lines)
    pytest_assert(
        len(led_states) > 0,
        "Could not parse any LED state entries from output of '{}' on '{}'. "
        "Raw output: {}".format(cmd, duthost.hostname, result['stdout'])
    )

    logging.info("Parsed {} LED state entries on '{}'".format(len(led_states), duthost.hostname))

    invalid_entries = {
        name: state
        for name, state in led_states.items()
        if state not in VALID_LED_STATES
    }
    pytest_assert(
        len(invalid_entries) == 0,
        "Unexpected LED state values on '{}': {}. "
        "Valid states are: {}".format(duthost.hostname, invalid_entries, VALID_LED_STATES)
    )

    logging.info("All LED states are valid on '{}': {}".format(duthost.hostname, led_states))


@pytest.fixture(scope="function")
def led_set_restore(duthosts, enum_rand_one_per_hwsku_hostname):
    """
    Fixture that captures the current LED state for a single component,
    yields (duthost, led_name, original_state) to the test, then
    unconditionally restores the original state in teardown.

    If no settable LED component can be identified, the test is skipped.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]

    # Discover the first LED component whose current state is a concrete value
    logging.info("Discovering LED components on '{}' for set/restore test".format(duthost.hostname))
    get_cmd = "pddf_ledutil getledcurstate"
    result = duthost.shell(get_cmd, module_ignore_errors=True)

    if result['rc'] != 0:
        pytest.skip(
            "Cannot run '{}' on '{}'; skipping set/restore test".format(get_cmd, duthost.hostname)
        )

    led_states = _parse_led_state_output(result['stdout_lines'])
    if not led_states:
        pytest.skip("No LED entries found in '{}' output on '{}'".format(get_cmd, duthost.hostname))

    # Pick the first LED with a non-N/A state (settable LEDs have real states)
    target_led = None
    original_state = None
    for name, state in led_states.items():
        if state != "N/A":
            target_led = name
            original_state = state
            break

    if target_led is None:
        pytest.skip(
            "All LED states are 'N/A' on '{}'; cannot perform set/restore test".format(duthost.hostname)
        )

    logging.info(
        "Selected LED '{}' with current state '{}' on '{}' for set/restore test".format(
            target_led, original_state, duthost.hostname
        )
    )

    yield duthost, target_led, original_state

    # Teardown: always restore the original LED state
    restore_cmd = "sudo pddf_ledutil setstatusled {} {}".format(target_led, original_state)
    logging.info(
        "Restoring LED '{}' to '{}' on '{}': running '{}'".format(
            target_led, original_state, duthost.hostname, restore_cmd
        )
    )
    restore_result = duthost.shell(restore_cmd, module_ignore_errors=True)
    if restore_result['rc'] != 0:
        logging.warning(
            "Restore command '{}' failed on '{}' with rc={}. "
            "LED '{}' may remain in a non-original state.".format(
                restore_cmd, duthost.hostname, restore_result['rc'], target_led
            )
        )


def test_pddf_ledutil_setled_and_verify(led_set_restore):
    """
    @summary: Set a PDDF LED to a target state, verify via getledcurstate, then restore.

    Steps:
      1. Read current state of a discovered LED component (done in fixture).
      2. Choose a target state different from the current one.
      3. Run 'pddf_ledutil setstatusled <led> <target_state>' and assert rc=0.
      4. Run 'pddf_ledutil getledcurstate' and assert the LED reflects target_state.
      5. Fixture teardown restores the original state unconditionally.
    """
    duthost, target_led, original_state = led_set_restore

    # Choose a target state that differs from the current state
    if original_state != "green":
        new_state = "green"
    else:
        new_state = "off"

    # Step 1: Set the LED to the new state
    set_cmd = "sudo pddf_ledutil setstatusled {} {}".format(target_led, new_state)
    logging.info(
        "Setting LED '{}' from '{}' to '{}' on '{}': '{}'".format(
            target_led, original_state, new_state, duthost.hostname, set_cmd
        )
    )
    set_result = duthost.shell(set_cmd, module_ignore_errors=True)
    pytest_assert(
        set_result['rc'] == 0,
        "Command '{}' failed on '{}' with rc={}. stderr: {}".format(
            set_cmd, duthost.hostname, set_result['rc'], set_result.get('stderr', '')
        )
    )

    # Step 2: Verify the new state via getledcurstate
    get_cmd = "pddf_ledutil getledcurstate"
    logging.info(
        "Verifying LED '{}' state after set on '{}': running '{}'".format(
            target_led, duthost.hostname, get_cmd
        )
    )
    get_result = duthost.shell(get_cmd, module_ignore_errors=True)
    pytest_assert(
        get_result['rc'] == 0,
        "Command '{}' failed on '{}' with rc={}. stderr: {}".format(
            get_cmd, duthost.hostname, get_result['rc'], get_result.get('stderr', '')
        )
    )

    led_states_after = _parse_led_state_output(get_result['stdout_lines'])
    pytest_assert(
        target_led in led_states_after,
        "LED '{}' not found in '{}' output after set on '{}'. "
        "Parsed entries: {}".format(target_led, get_cmd, duthost.hostname, led_states_after)
    )

    actual_state = led_states_after[target_led]
    pytest_assert(
        actual_state == new_state,
        "LED '{}' on '{}' expected state '{}' after set, but got '{}'. "
        "Full LED states: {}".format(
            target_led, duthost.hostname, new_state, actual_state, led_states_after
        )
    )

    logging.info(
        "LED '{}' correctly reflects state '{}' on '{}' after set".format(
            target_led, new_state, duthost.hostname
        )
    )
    # Teardown (restore to original_state) is handled by the led_set_restore fixture
