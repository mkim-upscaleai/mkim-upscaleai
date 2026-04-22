# deploy-image

Scripts for fetching, deploying, and factory-resetting SONiC switches.

## Quick start

```bash
# Download, copy, install, and factory-reset in one command
./deploy-switch.sh -s <switch_ip>

./deploy-switch.sh -s 10.9.100.61                          # download latest prod build
./deploy-switch.sh -s 10.9.100.61 -t gating                # download latest gating build
./deploy-switch.sh -s 10.9.100.61 -b 473                   # specific build by ID
./deploy-switch.sh -s 10.9.100.61 -i ~/my-sonic-image.bin  # use a local .bin file
./deploy-switch.sh -s 10.9.100.61 -f                       # force re-download
```

`deploy-switch.sh` lives one level up in `upscaleai-scripts/`.

| Flag | Description | Default |
|------|-------------|---------|
| `-s` | Switch IP address | required |
| `-t` | Build tag to download (`prod`, `gating`, `upload`, `dev`) | `prod` |
| `-b` | Download a specific build by ID from the dashboard | — |
| `-i` | Path to a local `.bin` image (skips download) | — |
| `-f` | Force re-download even if image already exists locally | — |
| `-h` | Show help | |

When `-i` is provided, the download step is skipped entirely. The path can be anywhere on disk — it does not need to be inside `downloaded-images/`.

Images are cached in `downloaded-images/`. If the same filename already exists, the download is skipped automatically. Use `-f` to force a re-download.

## Workflow

```text
deploy-switch.sh
  ├─ [ 1/6 ] download-sonic.sh           →  downloaded-images/<image>.bin  (skipped with -i)
  ├─ [ 2/6 ] copy-image-to-switch.sh     →  /home/admin/<image>.bin on switch
  ├─ [ 3/6 ] install-image.sh            →  sonic-installer install + reboot
  ├─ [ 4/6 ] wait for switch             →  poll SSH until switch is back
  ├─ [ 5/6 ] sonic-installer cleanup -y  →  remove old image from previous partition
  └─ [ 6/6 ] factory-reset-switch.sh     →  save mgmt IP, factory reset, restore, config reload
```

Timing is printed at each step and a total elapsed time is shown at the end.

Each step can also be run individually — see the scripts section below.

---

## Scripts

### `download-sonic.sh`

Downloads the latest SONiC image from the internal build dashboard and saves it to `downloaded-images/`.

```bash
./download-sonic.sh                              # latest prod build
./download-sonic.sh -t gating                    # latest gating build
./download-sonic.sh -i 473                       # specific build by ID
./download-sonic.sh -t prod -b upscaleai-202511  # specific branch
./download-sonic.sh -t prod -o my-image.bin      # custom output filename
./download-sonic.sh -t prod -f                   # force re-download
```

| Flag | Description | Default |
|------|-------------|---------|
| `-i` | Download a specific build by ID (overrides `-t` and `-b`) | — |
| `-t` | Build tag to filter by (`prod`, `gating`, `upload`, `dev`) | `prod` |
| `-b` | Branch to filter by | any |
| `-o` | Output filename | auto-detected from URL |
| `-f` | Force re-download even if image already exists | — |
| `-h` | Show help | |

If the target file already exists in `downloaded-images/`, the download is skipped. Use `-f` to override.

---

### `copy-image-to-switch.sh`

Copies a SONiC image from your local machine to a switch over SCP. Switches in `192.168.221.x`–`192.168.223.x` are reached automatically via the `server9` jump host.

```bash
./copy-image-to-switch.sh -s 192.168.220.5 -i downloaded-images/sonic.bin
./copy-image-to-switch.sh -s 192.168.221.5 -i downloaded-images/sonic.bin   # via jump host
./copy-image-to-switch.sh -s 192.168.221.5 -i downloaded-images/sonic.bin -d /tmp/
```

| Flag | Description | Default |
|------|-------------|---------|
| `-s` | Switch IP address | required |
| `-i` | Local path to the image file | `downloaded-images/sonic-mellanox.bin` |
| `-d` | Destination path on the switch | `/home/admin/` |
| `-h` | Show help | |

---

### `install-image.sh`

SSHes into the switch, runs `sudo sonic-installer install`, then reboots.

```bash
./install-image.sh -s 192.168.221.10
./install-image.sh -s 192.168.221.10 -n my-custom-image.bin
```

| Flag | Description | Default |
|------|-------------|---------|
| `-s` | Switch IP address | required |
| `-n` | Image filename on the switch | `sonic-mellanox.bin` |
| `-h` | Show help | |

---

### `factory-reset-switch.sh`

Resets a switch to factory defaults while preserving management connectivity.

Steps performed:
1. Extract `MGMT_INTERFACE` and `MGMT_PORT` from current `config_db.json`
2. Backup `config_db.json` → `config_db.json.bak-before-deploy`
3. Run `sudo config-setup factory`
4. Restore saved mgmt fields into the new factory config (skipped if DHCP)
5. Run `sudo config reload -y -f`

```bash
./factory-reset-switch.sh -s 192.168.221.10
```

| Flag | Description | Default |
|------|-------------|---------|
| `-s` | Switch IP address | required |
| `-h` | Show help | |

---

## End-to-end example (manual steps)

```bash
# 1. Download
./download-sonic.sh -t prod

# 2. Copy to switch
./copy-image-to-switch.sh -s 192.168.221.10

# 3. Install and reboot
./install-image.sh -s 192.168.221.10

# 4. (wait for switch to come back on new image)

# 5. Clean up old image from previous partition
ssh admin@192.168.221.10 "sudo sonic-installer cleanup -y"

# 6. Factory reset
./factory-reset-switch.sh -s 192.168.221.10
```

Or just use `deploy-switch.sh` to do all of this automatically.

---

## Notes

- `downloaded-images/` is created automatically and is gitignored (binary files are not committed).
- `deploy-switch.sh` checks for required dependencies (`curl`, `python3`, `sshpass`) on startup and offers to install any that are missing. Supports macOS (Homebrew), Debian/Ubuntu (apt), and RHEL/Fedora (dnf/yum). `pv` is optional (used for SCP progress bars).
- The build dashboard URL is hardcoded in `download-sonic.sh` (`DASHBOARD` variable).
- Credentials are loaded by `creds.sh` in this order: environment variables, `upscaleai-scripts/.env` file, interactive prompt. Copy `.env.example` to `.env` and fill in your passwords. **Do not commit `.env` to source control** (it is already gitignored).
- Switches in `192.168.221.x`–`192.168.223.x` are reached via the `server9` jump host (`192.168.211.12`). All other IPs are accessed directly.
