# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

**sonic-mgmt** is the test infrastructure and management automation repository for [SONiC (Software for Open Networking in the Cloud)](https://sonic-net.github.io/SONiC/). It contains thousands of pytest-based test cases for validating SONiC switches on physical testbeds and virtual switch (VS) topologies, plus Ansible playbooks for testbed deployment.

## Common Commands

### Running Tests
```bash
# Run a specific test against a testbed
cd tests
pytest test_feature.py -v --testbed=vms-kvm-t0 --inventory=../ansible/veos_vtb

# Run a single test function
pytest bgp/test_bgp_fact.py::test_bgp_facts -v --testbed=vms-kvm-t0

# Run VS (virtual switch) tests
pytest --testbed_type=vs test_feature.py

# Run with topology marker filter
pytest -m "topology_t0" test_bgp.py

# Via Makefile (from repo root)
make test T=bgp/test_bgp_fact.py
make test T=bgp/test_bgp_fact.py EXTRA='-e "--neighbor_type=sonic"'
```

### Makefile Targets
```bash
make shell        # Enter sonic-mgmt Docker container
make add-topo     # Deploy testbed topology
make remove-topo  # Remove testbed topology
make deploy-mg    # Deploy minigraph to DUT
```

Key Makefile variables: `TOPO` (default: vms-kvm-t0), `TESTBED` (default: vtestbed.yaml), `INVENTORY` (default: veos_vtb), `DUT` (default: vlab-01), `NEIGHBOR` (ceos|veos|vsonic).

### Linting and Formatting
```bash
# Flake8 (line length 120, per .flake8 config)
flake8 tests/

# Black formatter (applies only to tests/common2/)
black tests/common2/

# Pre-commit hooks (includes marker sort checker)
pre-commit run --all-files
```

### Python Environment Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Architecture

```
tests/               # Main pytest test suite (~150 feature directories)
│   conftest.py      # ~4000-line root fixtures file — the source of truth for all shared fixtures
│   common/          # Shared utilities: device abstractions, helpers, plugins
│   bgp/, acl/, vlan/, ecmp/, crm/, ...  # Feature-specific test modules
│   smartswitch/     # SmartSwitch/DPU tests (conftest.py, common/, platform_tests/)
│   pytest.ini       # Pytest config, all marker definitions
ansible/             # Testbed deployment playbooks and roles
│   testbed.yaml     # Testbed topology definitions
│   golden_config_db/  # Config DB JSON templates applied to DUTs
spytest/             # SPyTest (alternative framework, not the primary one)
sdn_tests/           # SDN-specific tests
.azure-pipelines/    # CI pipeline templates
.github/workflows/   # GitHub Actions (reviewer assignment, CodeQL, cherry-pick)
```

### Key Test Fixtures (defined in `tests/conftest.py`)

| Fixture | Purpose |
|---------|---------|
| `duthosts` | Access to all DUTs (Device Under Test) in testbed |
| `rand_one_dut_hostname` | Randomly selected DUT hostname |
| `enum_frontend_dut_hostname` | Iterate over frontend DUTs |
| `tbinfo` | Testbed topology information dict |
| `ptfhost` | PTF container for packet injection/verification |
| `enum_asic_index` | Iterate over ASICs on multi-ASIC platforms |
| `dpuhosts` | List of DPU SONiC instances on SmartSwitch |

### Device Abstractions

- **`DutHost`** — SSH/CLI interface to the SONiC switch under test
- **`PTFHost`** — Packet Test Framework container for data-plane testing
- **`EosHost`/`CiscoHost`** — Neighboring devices in the topology
- **`FanoutHost`** — Upstream fanout switch

### SmartSwitch / DPU Concepts

- **SmartSwitch**: A SONiC switch with on-board DPU modules
- **NPU**: Main switch CPU (`duthost` points here)
- **DPU**: Independent SONiC instance on the SmartSwitch, accessed via midplane IP (`dpuhosts[]`)
- **Dark mode**: DPUs are administratively shut down
- **Lit mode**: DPUs are up; reachable via SSH port forwarding through midplane

### Topology Markers

Tests must declare compatible topologies via `@pytest.mark.topology(...)`. Common values:
- `t0`, `t1`, `t2` — standard switch topologies
- `any` — runs on all topologies
- `dualtor` — dual ToR topology
- `smartswitch` — SmartSwitch/DPU topology

A test marked `t1` will not run on a `t0` testbed.

### Pytest Configuration (`tests/pytest.ini`)

All available markers are defined here. Tests use markers for: topology, platform (broadcom, mellanox, cisco), features (acl, bgp, reboot), and test completeness levels (Debug, Basic, Confident, Thorough).

## Writing Tests

```python
import pytest
from tests.common.helpers.assertions import pytest_assert

@pytest.mark.topology('t0')
def test_my_feature(duthosts, rand_one_dut_hostname, tbinfo):
    """Test that my feature works correctly."""
    duthost = duthosts[rand_one_dut_hostname]

    duthost.shell('config my_feature enable')
    output = duthost.show_and_parse('show my_feature status')
    pytest_assert(output[0]['status'] == 'enabled', "Feature should be enabled")
```

**Key patterns:**
- Use `wait_until` helpers instead of `time.sleep` for network state changes
- Restore config after tests (use `backup_and_restore_config_db_session` fixture for session-scoped safety)
- For multi-ASIC platforms, use `enum_asic_index` to iterate ASICs
- PTF data-plane tests: `ptf_runner(duthost, ptfhost, 'test_name', platform_dir='ptftests', params={...})`
- Feature-specific `conftest.py` files in subdirectories can extend/override root fixtures

## PR Requirements

- **Commit format**: `[component/test]: Description`
- **Signed-off-by required**: `git commit -s`
- **Topology markers**: All tests must declare topology compatibility
- **Test idempotency**: Tests must clean up after themselves
- **PR template**: Use `.github/PULL_REQUEST_TEMPLATE.md` — fill all sections including backport checkboxes

## CI

Azure Pipelines (triggered on PRs to `master` and `202???` branches) runs:
1. Static analysis / pre-commit checks
2. pytest collection validation
3. Test marker validation
4. Dynamic test plans based on changed files
