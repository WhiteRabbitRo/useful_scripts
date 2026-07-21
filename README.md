# useful_scripts

Personal library of useful bash/sh scripts, Python tools, and guides for Linux development.

> **Platform:** most scripts target **Debian/Ubuntu**. Some scripts require `root`/`sudo` and modify system configuration.

## Quick index

| Directory | Purpose | Example |
|-----------|---------|---------|
| [`utilities/`](utilities/) | Dev helpers (hex arrays, search, random strings) | `./utilities/print_hex_in_c_array deadbeef` |
| [`package_management/`](package_management/) | apt packages, Docker install | `sudo ./package_management/docker_install.sh` |
| [`driver_fix/`](driver_fix/) | NVIDIA drivers, displays, Python/pip | `./driver_fix/fix_displays` |
| [`openssl/`](openssl/) | OpenSSL update, GOST engine, cert generation | `./openssl/openssl_gen_certs.sh --help` |
| [`net/`](net/) | Reverse USB tethering, kill port | `sudo ./net/setup_reverse_tether.sh` |
| [`static_analysis/`](static_analysis/) | C static analysis (Python) | `./static_analysis/static_analysis.py -s src --help` |
| [`secure_developing/`](secure_developing/) | Legacy wrapper → Python static analysis | `./secure_developing/static_analysis -s=src` |
| [`guides/`](guides/) | Git & Docker cheat sheets (RU) | — |
| [`hasp.md`](hasp.md) | HASP license key reference (RU) | — |

## Static analysis

Primary tool: [`static_analysis/static_analysis.py`](static_analysis/static_analysis.py)

```bash
pip install -r static_analysis/requirements.txt --break-system-packages
sudo apt-get install cppcheck clang clang-tools gcc clang-format

./static_analysis/static_analysis.py \
  -i include \
  -d DEBUG=1 \
  -s src \
  --format console --format sarif \
  --fail-on error
```

Configuration: copy [`static_analysis/.analyzerrc.example.toml`](static_analysis/.analyzerrc.example.toml) to your project root as `.analyzerrc`.

Migration from the old bash script: see [`static_analysis/README_MIGRATION.md`](static_analysis/README_MIGRATION.md).

## Requirements by category

| Category | Requirements |
|----------|-------------|
| `package_management/` | `apt`, optionally `root` |
| `driver_fix/` | `apt`, `xrandr`, NVIDIA packages |
| `openssl/` | `apt`, `git`, `cmake`; modifies system OpenSSL config |
| `net/setup_reverse_tether.sh` | `root`, `NetworkManager`, builds from source |
| `static_analysis/` | Python 3.10+, external binaries (cppcheck, clang, gcc) |
| `utilities/` | `bc` (for `print_dec_array_in_hex`) |

## Warnings

- **`openssl/openssl_install_gost`** — modifies system `openssl.cnf` (backup recommended).
- **`net/setup_reverse_tether.sh`** — removes distro `usbmuxd`, builds custom stack from source.
- **`utilities/generate_random_string`** — uses `$RANDOM`, not suitable for cryptography.
- **`driver_fix/reinstall_nvidia_drivers`** — purges all NVIDIA packages; reboot required.
