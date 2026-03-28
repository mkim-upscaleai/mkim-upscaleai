# sonic-mgmt Top 5 Test Gaps — Implementation Backlog

**Repo:** sonic-net/sonic-mgmt
**Date:** 2026-03-28
**Constraints:** Generic or Mellanox-specific only. No Broadcom-specific. No multi-ASIC.
**Goal:** Each issue is unassigned, has no competing PR, and is approachable for a new contributor.

---

## Issue 1 — #22246: BGP Session Test Fixture Refactor

**Label:** Enhancement | **Priority:** LOW | **Effort:** ~0.5 day
**File:** `tests/bgp/test_bgp_session.py` (350 lines, 1 test function)

### Problem
`test_bgp_session_interface_down` uses a module-scoped `setup` fixture for DUT config, but cleanup is tied to the test body via try/finally. If an assertion fails before the finally block runs, the DUT config leaks into subsequent tests, causing cascading failures.

### What Needs to Change
Convert the cleanup logic to a proper `yield`-based pytest fixture so teardown always runs regardless of test outcome. Pattern is already used extensively elsewhere in `tests/bgp/conftest.py`.

### Acceptance Criteria
- No try/finally for DUT config cleanup in the test body
- All teardown via `yield` fixtures with proper scope
- Tests still pass: `pytest bgp/test_bgp_session.py -v --testbed=vms-kvm-t0`
- No behavior change — only cleanup reliability improves

### Reference Pattern
```python
@pytest.fixture
def bgp_interface_down_setup(duthosts, rand_one_dut_hostname, fanouthosts):
    # setup: bring interface down
    yield setup_data
    # teardown: restore interface — ALWAYS runs, even on failure
```

---

## Issue 2 — #21824: PDDF LED CLI Has Zero Test Coverage

**Label:** Test Gap | **Priority:** CRITICAL | **Effort:** ~1 day
**New file:** `tests/platform_tests/cli/test_pddf_led.py`

### Problem
`pddf_ledutil` is the CLI utility for reading and setting LED states on all PDDF-based platforms (used by Mellanox/NVIDIA and others). It has **zero test coverage** in sonic-mgmt. The only LED test (`tests/platform_tests/daemon/test_ledd.py`) checks that the daemon process is running — not that the CLI commands produce valid output.

### What Needs to Be Built
New test file with the following test cases:

1. **`test_pddf_ledutil_getledcurstate`** — run `pddf_ledutil getledcurstate`, verify output format and valid state values (`green`, `amber`, `red`, `off`, `N/A`)
2. **`test_pddf_ledutil_setled_and_verify`** — set an LED state, verify via `getledcurstate`, restore original state
3. **`test_pddf_ledutil_help`** — verify the CLI has help text and exits 0

### Skip Guard (Required)
```python
@pytest.fixture(scope="module", autouse=True)
def skip_if_no_pddf(duthosts, enum_rand_one_per_hwsku_hostname):
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    result = duthost.shell("which pddf_ledutil", module_ignore_errors=True)
    if result['rc'] != 0:
        pytest.skip("pddf_ledutil not available on this platform")
```

### Acceptance Criteria
- Tests skip gracefully on non-PDDF platforms (no crash, clean skip message)
- `getledcurstate` output is validated against expected LED state values
- LED set/verify/restore cycle completes without leaving DUT in bad state
- Follows `tests/platform_tests/cli/test_show_platform.py` patterns

---

## Issue 3 — #23149: SSD Health Check Under Write Stress

**Label:** Test Gap | **Priority:** MEDIUM | **Effort:** ~1-2 days
**New file:** `tests/platform_tests/test_ssd_health.py`

### Problem
The existing `test_show_platform_ssdhealth` in `tests/platform_tests/cli/test_show_platform.py` only validates that the `show platform ssdhealth` CLI output has the right fields and reasonable values. It never puts the disk under stress. Issue #23149 asks for tests that validate disk health holds up under write load.

### What Needs to Be Built

1. **`test_ssd_health_baseline`** — get baseline health metrics before any stress
2. **`test_ssd_write_stress_and_health`** — run `dd` write stress, re-check health; assert health degradation is within threshold (e.g., less than 5% drop)
3. **`test_ssd_io_stats_within_limits`** — read `/proc/diskstats` or `iostat` output before and after, validate write throughput and error counts are sane

### Key Considerations
- Must clean up stress test files (`/tmp/ssd_stress_*`) in fixture teardown
- Use `wait_until` pattern, not `time.sleep`
- Skip on platforms where `ssdhealth` is not supported (check disk type in output)
- Device type: `physical` only (VS doesn't have real SSD)

### Acceptance Criteria
- Baseline health check passes before stress
- Post-stress health delta is asserted, not just logged
- Stress file cleanup always runs (yield fixture)
- Test skips cleanly on unsupported disk types

---

## Issue 4 — #23222: Make Liquid Cooling Test Platform-Agnostic

**Label:** Test Gap | **Priority:** HIGH | **Effort:** ~1-2 days
**File:** `tests/platform_tests/test_liquid_cooling_leakage_detection.py`

### Problem
Three hard-coded Mellanox dependencies prevent this test from running on any other vendor's liquid-cooled hardware:

1. **Line 9:** `from tests.common.mellanox_data import get_platform_data` — used only to get `leak_sensors.number`
2. **Line 10:** `from tests.common.helpers.mellanox_liquid_leakage_control_test_helper import MlxLiquidLeakageMocker` — direct import in test file
3. **Line 37:** `duthost.shell("ls /var/run/hw-management/system/leakage* |wc -l")` — Mellanox-specific sysfs path

### What Needs to Change

**Fix 1:** Replace `get_platform_data(duthost)['leak_sensors']['number']` with:
```python
leak_sensors_num = duthost.facts.get("leak_sensors", {}).get("number")
```

**Fix 2:** Remove the direct `MlxLiquidLeakageMocker` import from the test file. Move mocker registration to `tests/platform_tests/conftest.py` inside `mocker_factory`, so each vendor registers its own mocker. The test body already calls `mocker_factory(duthost, 'LiquidLeakageMocker')` — that part stays.

**Fix 3:** Remove the hard-coded `/var/run/hw-management/system/leakage*` sysfs path. Either:
- Source it from platform.json via `duthost.facts`, or
- Mark the specific test case as `@pytest.mark.platform('mellanox')` if the path is truly Mellanox-only

### Reference
`tests/platform_tests/api/test_liquid_cooling_leakage.py` — the platform-agnostic sibling. Uses `duthost.facts.get("leak_sensors", {}).get("number")` correctly.

### Acceptance Criteria
- No direct Mellanox imports in `test_liquid_cooling_leakage_detection.py`
- Sensor count comes from `duthost.facts`, not `get_platform_data()`
- Mocker registration is in `conftest.py`, not the test file
- Mellanox behavior is preserved (no regression)

---

## Issue 5 — #23395: PFCWD Storm Induced While Traffic Is Flowing

**Label:** Test Gap | **Priority:** HIGH | **Effort:** ~3-4 days
**New file:** `tests/qos/test_pfcwd_runtime_storm.py`

### Problem
All existing PFCWD tests induce PFC storms on idle queues. There is no test that:
1. Establishes active traffic through a lossless priority queue
2. Induces a PFC storm mid-flight
3. Verifies PFCWD triggers and traffic recovers after watchdog action

This matters because SDK/SAI may handle programming flow control registers differently when the queue is already active — a real-world scenario that currently has no coverage.

### What Needs to Be Built
PTF-based test (no IXIA/Snappi required):

```
Flow:
  PTFHost ──[lossless prio traffic]──> DUT port ──[forward]──> PTF egress
                                           │
                                    (mid-flight)
                                           │
                                    fanout induces PFC storm
                                           │
                                    PFCWD triggers (verify via
                                    `show pfcwd stats`)
                                           │
                                    storm clears
                                           │
                                    traffic recovers (verify counters)
```

### Key References
- `tests/ixia/pfcwd/test_pfcwd_runtime_traffic.py` — IXIA version, port the concept to PTF
- `tests/ixia/pfcwd/files/pfcwd_runtime_traffic_helper.py` — helper logic to adapt
- `tests/qos/test_pfc_counters.py` — existing PTF-based PFC counter test for setup patterns

### Acceptance Criteria
- Traffic is actively flowing before storm is induced (verify with PTF counters)
- PFCWD detection is confirmed via `show pfcwd stats`
- Traffic recovery is verified after storm clears
- DUT config is fully restored in fixture teardown
- Topology: `t1` (needs lossless priority queues and fanout control)

---

## Implementation Order (Recommended)

| Week | Issue | Reason |
|------|-------|--------|
| 1 | #22246 BGP fixture refactor | Fastest to ship, zero risk, introduces you to reviewers |
| 2 | #21824 PDDF LED CLI | Critical gap, ~1 day, no existing code to break |
| 3 | #23222 Liquid cooling | Clear spec + reference pattern, Arista motivation |
| 4 | #23149 SSD health stress | Builds on existing show platform helpers |
| 5+ | #23395 PFCWD runtime storm | Most complex, save for last |

## PR Requirements (All Issues)

- Commit format: `[platform/test]: Description` or `[qos/test]: Description`
- Signed-off-by required: `git commit -s`
- All new tests need `@pytest.mark.topology(...)` declared
- Comment on the GitHub issue before starting: "Working on this"
- Use `.github/PULL_REQUEST_TEMPLATE.md` for PR description
