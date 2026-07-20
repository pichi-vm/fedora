#!/usr/bin/env bash
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

# Build the Fedora combined base OS image — a single pichi artifact carrying the
# carapace (scutes) + a detached base DTB + a detached-mode PMI + the launch
# config. `pichi run` boots it: the PMI's systemd initramfs runs the carapace
# generator, which assembles /dev/mapper/root from `carapacehash=`, and systemd
# pivots into the Fedora rootfs. A temporary boot-test unit then powers off with
# a console marker so the boot is verifiable.
#
# One kernel version underpins all three module consumers (PMI vmlinuz,
# initramfs modules, carapace /usr/lib/modules): the rootfs build installs the
# kernel and the initrd build is pinned to that exact version.
#
# Requires: mkosi, pichi, arma (ARMA=<path> or on PATH), jq, mkfs.ext4,
# truncate, cargo. Runs rootless (mkosi uses user namespaces).
set -euo pipefail

RELEASE="${RELEASE:-43}"
IMAGE="${IMAGE:-ghcr.io/pichi-vm/fedora}"
SIZE="${SIZE:-2G}"
ARMA="${ARMA:-arma}"
CARAPACE_GIT="${CARAPACE_GIT:-https://github.com/pichi-vm/carapace}"

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
work="$here/.build"
# mkosi's rootfs tree is owned by us but read-only (dir mode 0555); make it
# writable before removing a previous run's output.
[ -e "$work" ] && chmod -R u+w "$work"
rm -rf "$work"
mkdir -p "$work"

# ---- 1. rootfs (the single kernel source) --------------------------------
# Installs kernel-core + systemd + the temporary boot-test unit (mkosi.extra).
mkosi --force --output-dir "$work"

KVER="$(basename "$(ls -d "$work"/rootfs/usr/lib/modules/*/ | head -1)")"
echo ">>> kernel $KVER"

# ---- 2. stage the carapace binary + generator symlink for the initrd -----
# The in-binary systemd generator turns `carapacehash=` into the attach unit.
cargo install --git "$CARAPACE_GIT" --root "$work/carapace" --quiet carapace
ext="$here/initrd/mkosi.extra"
rm -rf "$ext"
mkdir -p "$ext/usr/bin" "$ext/usr/lib/systemd/system-generators"
cp "$work/carapace/bin/carapace" "$ext/usr/bin/carapace"
ln -sf ../../../bin/carapace "$ext/usr/lib/systemd/system-generators/systemd-carapace-generator"

# ---- 3. matching initramfs (pinned to the rootfs kernel) ------------------
mkosi -C initrd --force --output-dir "$work" \
	--package "kernel-core-$KVER"

# ---- 4. extract the kernel, strip boot payload, pack the carapace --------
# Run as namespace-root (`unshare -r` maps us to uid 0): the rootfs carries
# root-owned, unreadable files (e.g. /etc/shadow) and read-only directories
# that a plain user can neither read for mkfs nor remove. We own the tree, so
# the mapping grants full access without real privilege.
#   - extract vmlinuz for the PMI, then drop it and /boot from the carapace
#     (the kernel image is the PMI's domain; the carapace keeps only .ko);
#   - pack the result into a bare ext4 image (4096-byte = carapace verity block).
unshare -r bash -eu -c '
	work="$1"; kver="$2"; size="$3"
	export PATH="/usr/sbin:/sbin:$PATH"
	cp "$work/rootfs/usr/lib/modules/$kver/vmlinuz" "$work/vmlinuz"
	cp "$work/rootfs/usr/lib/modules/$kver/config" "$work/kernel.config"
	rm -rf "$work/rootfs/boot"
	rm -f "$work/rootfs/usr/lib/modules/$kver/vmlinuz" \
		"$work/rootfs/usr/lib/modules/$kver/System.map"
	rm -f "$work/fedora.raw"
	truncate -s "$size" "$work/fedora.raw"
	mkfs.ext4 -q -F -b 4096 -d "$work/rootfs" "$work/fedora.raw"
' _ "$work" "$KVER" "$SIZE"

# ---- 5. carapace top root hash (the trust anchor for the cmdline) ---------
# A carapace-only import prints the verity info; capture rootₙ₋₁.
hash="$(pichi import "$work/fedora.raw" "fedora:$RELEASE-tmp" \
	--quiet --print-verity-info | jq -r .root_hash)"
pichi rmi "fedora:$RELEASE-tmp" >/dev/null 2>&1 || true
echo ">>> carapace root $hash"

# ---- 6. detached-mode PMI + base DTB -------------------------------------
# Cmdline notes (this is still a boot-test image, see pichi-boot-test.service):
#   carapacehash=       trust anchor consumed by the carapace generator.
#   console=hvc0        the virtio-console; dillo surfaces it to the host.
#   systemd.volatile=state  the carapace root is read-only; /var must be a
#                       writable tmpfs for logind/tmpfiles/journal to work.
#   systemd.unit=multi-user.target  the Fedora default is graphical.target,
#                       which needs a display-manager we don't ship; a VM
#                       base boots headless multi-user.
"$ARMA" build \
	--kernel "$work/vmlinuz" \
	--config "$work/kernel.config" \
	--initrd "$work/initrd" \
	--cmdline "root=/dev/mapper/root carapacehash=$hash console=hvc0 systemd.volatile=state systemd.unit=multi-user.target" \
	--dtb "$work/base.dtb" \
	"$work/boot.pmi"

# ---- 7. package the combined artifact ------------------------------------
pichi import "$work/fedora.raw" "fedora:$RELEASE" \
	--pmi "$work/boot.pmi" \
	--dtb "$work/base.dtb" \
	--config "$here/config.json"

echo ">>> imported combined artifact fedora:$RELEASE (carapace + dtb + pmi + config)"
echo "    boot-test: pichi run fedora:$RELEASE  # expect PICHI-CARAPACE-BOOT-OK then clean poweroff"
echo "    push with: pichi push fedora:$RELEASE $IMAGE:$RELEASE-<arch>"
