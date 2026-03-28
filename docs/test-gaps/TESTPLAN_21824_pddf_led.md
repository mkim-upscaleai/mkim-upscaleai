# Test Plan: PDDF LED CLI Coverage (Issue #21824)

**File:** `tests/platform_tests/cli/test_pddf_led.py`
**Topology:** `any`
**Device type:** `physical`

## Problem Statement

`pddf_ledutil` is the CLI utility for reading and setting LED states on PDDF-based platforms. It has zero test coverage in sonic-mgmt today. The only existing LED test (`tests/platform_tests/daemon/test_ledd.py`) validates that the `ledd` daemon process is running, not that the CLI commands produce valid output. This gap means regressions in LED state reporting or LED set/restore logic would go undetected.

## What the Tests Cover

Three test functions are implemented:

1. **`test_pddf_ledutil_help`** — Runs `pddf_ledutil --help` (with fallback to `-h`) and asserts the process exits with return code 0. This is a low-cost smoke test confirming the binary is installed and the CLI entry point is functional. It runs first because if the binary is broken at the help level no further tests are meaningful.

2. **`test_pddf_ledutil_getledcurstate`** — Runs `pddf_ledutil getledcurstate` and validates that stdout is non-empty and that every LED state value present in the output belongs to the set `{"green", "amber", "red", "off", "N/A"}`. Output lines are expected to follow a `<LED name>: <state>` colon-separated format (matching the PDDF CLI convention seen in spytest references and the PSU JSON test in `test_show_platform.py`). Lines that do not match are logged as warnings rather than failures, since header or blank lines may appear.

3. **`test_pddf_ledutil_setled_and_verify`** — The most important test: it reads the current system LED state, attempts to set it to a known safe target state (`"green"` if the current state differs, otherwise `"off"`), re-reads via `getledcurstate` to confirm the change took effect, then unconditionally restores the original state in fixture teardown via the `yield` pattern. The system LED component name is resolved dynamically from the `getledcurstate` output (first parseable LED name). If no settable LED is found (e.g. all entries are `N/A`) the test is skipped gracefully.

## Skip Guard and Safety

A module-scoped `autouse` fixture (`skip_if_no_pddf`) runs `which pddf_ledutil` before any test in the module. If the binary is absent (non-PDDF platform) the entire module is skipped with a clean message. All DUT state mutations use `duthost.shell(cmd, module_ignore_errors=True)` so a failing shell command surfaces as a test failure rather than an Ansible exception. The set/restore fixture uses `yield` so teardown always runs regardless of assertion outcomes, preventing LED state leaks between test sessions.
