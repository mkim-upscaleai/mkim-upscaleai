# Test Plan: Issue #22246 — BGP Session Test Fixture Refactor

**File:** `tests/bgp/test_bgp_session.py`
**Branch:** `fec_value_update`
**Date:** 2026-03-28

## Problem

`test_bgp_session_interface_down` previously relied on try/finally blocks inside the test body to restore fanout and neighbor interfaces after shutting them down. If a pytest assertion failed before the finally block, or if the test was interrupted mid-run, the DUT was left with interfaces or neighbor sessions in a shut-down state. This caused cascading failures in other tests sharing the same testbed session, because the `setup` module-scoped fixture assumed all sessions were up at teardown.

## What Changed

The cleanup logic was extracted from the test body into a new `failure_injection` function-scoped yield fixture. The fixture exposes two methods: `inject(failure_type)` to apply the failure (shutdown fanout interfaces or neighbor ports), and `restore()` to explicitly bring them back up so the test can verify BGP recovery. The fixture's teardown section (after `yield`) acts as a safety net: if the test exits for any reason — assertion failure, skip, exception — before calling `restore()`, the teardown code detects `state['injected'] == True` and runs the same restoration logic unconditionally. No try/finally appears anywhere in the test body.

The `setup` module-scoped fixture and all test assertions, topology markers, parametrize decorators, and functional behavior are unchanged. The helper functions `_shutdown_interfaces`, `_restore_interfaces`, `_shutdown_neighbors`, and `_restore_neighbors` were introduced to deduplicate the shutdown/restore logic shared between `inject()`, `restore()`, and fixture teardown. The overall diff is minimal: the test body is shorter and cleaner, and cleanup reliability is guaranteed by pytest's own fixture lifecycle.

## Verification

Run: `pytest bgp/test_bgp_session.py -v --testbed=vms-kvm-t0 --inventory=../ansible/veos_vtb`

All six parametrized variants (`bgp_docker` × `interface`/`neighbor`, `swss_docker` × `interface`/`neighbor`, `reboot` × `interface`/`neighbor`) should pass. To confirm cleanup reliability, introduce a deliberate assertion failure early in the test body and verify the fanout/neighbor interfaces are restored in the teardown logs — previously they would have remained shut down.
