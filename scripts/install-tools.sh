#!/bin/bash
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Runs in Fedora userspace on either host architecture, before image work.
directory=${1:-.build/packages}
python3 scripts/copr.py download --lock "$directory/packages.lock.json" \
    --out "$directory" --arch "$(uname -m)"
project=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project"])' \
    "$directory/packages.lock.json")
rpmkeys --import "keys/$project.asc"
dnf -y --setopt=install_weak_deps=False --setopt=localpkg_gpgcheck=True \
    install "$directory"/*."$(uname -m)".rpm
python3 - "$directory/packages.lock.json" <<'PYCODE'
import json, pathlib, sys
lock = json.load(open(sys.argv[1]))
for package, entry in lock['packages'].items():
    name = 'dillo-vm' if package == 'dillo' else package
    installed = json.loads(pathlib.Path(f'/usr/share/doc/{name}/package-source.json').read_text())
    assert installed == {'input': lock['inputs'][package], 'source': entry['source']}, package
PYCODE
export PICHI_DILLO=/usr/bin/dillo
pichi --version
dillo --version
arma --help >/dev/null
printf '%s\n' 'PICHI_DILLO=/usr/bin/dillo' >> "$GITHUB_ENV"
printf 'XDG_DATA_HOME=%s/fedora-image-cache\n' "$RUNNER_TEMP" >> "$GITHUB_ENV"
