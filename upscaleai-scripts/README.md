# upscaleai-scripts

Automation scripts for managing Caspian SONiC switches and testbeds.

## Directory layout

```
upscaleai-scripts/
  deploy-switch.sh          ← deploy an image to a switch (one command)
  testbed.sh                ← manage testbed topologies
  .env                      ← credentials (gitignored, see .env.example)
  .env.example              ← credential template
  deploy-image/             ← individual deploy steps (can run standalone)
    download-sonic.sh         download image from build dashboard
    copy-image-to-switch.sh   SCP image to a switch
    install-image.sh          sonic-installer install + reboot
    factory-reset-switch.sh   factory reset preserving mgmt IP
    creds.sh                  shared credential loader
    check-deps.sh              dependency checker / auto-installer
    README.md                 detailed docs for deploy scripts
  downloaded-images/         ← downloaded .bin files (gitignored)
  upscaleai-switches.csv     ← switch inventory
```

---

## deploy-switch.sh

Full pipeline: download → copy → install → factory reset. One command to deploy an image and leave the switch in a clean factory state.

```bash
# Download latest prod image and deploy
./deploy-switch.sh -s 10.9.100.61

# Download latest gating image and deploy
./deploy-switch.sh -s 10.9.100.61 -t gating

# Deploy a specific build by ID
./deploy-switch.sh -s 10.9.100.61 -b 473

# Use a local .bin file instead of downloading (any path works)
./deploy-switch.sh -s 10.9.100.61 -i /path/to/sonic-mellanox.bin

# Force re-download even if image is already cached
./deploy-switch.sh -s 10.9.100.61 -b 473 -f
```

| Flag | Description | Default |
|------|-------------|---------|
| `-s` | Switch IP address | required |
| `-t` | Build tag (`prod`, `gating`, `upload`, `dev`) | `prod` |
| `-b` | Download a specific build by ID from the dashboard | — |
| `-i` | Local `.bin` image path (skips download) | — |
| `-f` | Force re-download even if image already exists locally | — |
| `-h` | Show help | |

When `-i` is provided, the download step is skipped. The file can be anywhere on disk.

Images are cached in `downloaded-images/` — if the same filename already exists, the download is skipped automatically. Use `-f` to force a fresh download.

See [`deploy-image/README.md`](deploy-image/README.md) for detailed docs on each sub-script.

---

## testbed.sh

Manage Caspian testbed topologies across all spines (6–10) and topologies (32-port and 64-port).

```bash
# Set up a topology (add-topo + deploy-mg)
./testbed.sh setup -s 8 -t t0

# Individual operations
./testbed.sh add-topo    -s 7 -t t1
./testbed.sh remove-topo -s 9 -t t0-64
./testbed.sh deploy-mg   -s 10 -t t1-lag

# Run tests
./testbed.sh run-tests   -s 8 -t t0
./testbed.sh single-test -s 8 -t t0 -c clock/test_clock.py

# Dry run — print commands without executing
./testbed.sh show -s 8 -t t0
```

| Flag | Description | Values |
|------|-------------|--------|
| `-s` | Spine number | `6`, `7`, `8`, `9`, `10` |
| `-t` | Topology | `t0`, `t1`, `t1-lag`, `t0-64`, `t1-64` |
| `-c` | Test path (for `single-test`) | e.g. `clock/test_clock.py` |
| `-h` | Show help | |

| Action | Description |
|--------|-------------|
| `setup` | Add topology + deploy minigraph |
| `add-topo` | Add topology to testbed |
| `remove-topo` | Remove topology from testbed |
| `deploy-mg` | Deploy minigraph |
| `run-tests` | Run full test suite (auto-creates `tests.txt`/`tests_deselect.txt` if missing) |
| `single-test` | Run a single test |
| `show` | Print all commands without executing (dry run) |

---

## Credentials

Scripts load credentials in this order:

1. **Environment variables** — highest priority (e.g. `export SWITCH_PASS=...`)
2. **`.env` file** — loaded from `upscaleai-scripts/.env`
3. **Interactive prompt** — fallback if neither is set

To get started, copy the template and fill in your passwords:

```bash
cp .env.example .env
```

The `.env` file is gitignored and will never be committed.

| Variable | Description | Default |
|----------|-------------|---------|
| `JUMP_HOST` | Jump host IP | `192.168.211.12` |
| `JUMP_USER` | Jump host username | `casper` |
| `JUMP_PASS` | Jump host password | (prompted) |
| `SWITCH_USER` | Switch username | `admin` |
| `SWITCH_PASS` | Switch password | (prompted) |

---

## Prerequisites

`deploy-switch.sh` automatically checks for required dependencies on startup and offers to install any that are missing (detects macOS/Homebrew, apt, dnf/yum).

| Dependency | Purpose | Required |
|------------|---------|----------|
| `curl` | Downloading images from the build dashboard | yes |
| `python3` | JSON parsing on the switch during factory reset | yes |
| `sshpass` | Password-based SSH authentication | yes |
| `pv` | Progress bar for SCP transfers | optional |
