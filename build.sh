#!/usr/bin/env bash
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

RELEASE="${RELEASE:-43}"
IMAGE="${IMAGE:-ghcr.io/pichi-vm/fedora}"
SIZE="${SIZE:-2G}"

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

# 1. Build the rootfs directory.
mkosi --force

# 2. Pack it into a bare ext4 image (4096-byte blocks = carapace verity block).
rm -f fedora.raw
truncate -s "$SIZE" fedora.raw
mkfs.ext4 -q -F -b 4096 -d rootfs fedora.raw

# 3. Import into a carapace OCI image layout.
rm -rf layout
carapace import --image fedora.raw --out layout --tag "$RELEASE"

echo "built carapace OCI layout in ./layout (tag $RELEASE)"
echo "push with: skopeo copy oci:layout:$RELEASE docker://$IMAGE:$RELEASE"
