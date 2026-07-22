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
# ONE mkosi run produces everything the PMI and carapace need:
#   * the Fedora rootfs, packed by mkosi.repart/ into a bare ext4 root partition
#     emitted as <output>.root.raw (SplitArtifacts=partitions, no GPT);
#   * the matching systemd initramfs (mkosi.images/initrd/ subimage);
#   * vmlinuz + kernel config, copied out by mkosi.finalize.
# The subimage shares this run's package snapshot, so its kernel matches the
# rootfs by construction — one kernel version underpins the PMI vmlinuz, the
# initramfs modules, and the carapace /usr/lib/modules. build.sh cross-checks it.
#
# Requires: mkosi, pichi, arma (ARMA=<path> or on PATH), cpio, dumpe2fs
# (e2fsprogs), cargo. Runs rootless (mkosi uses user namespaces).
set -euo pipefail

RELEASE="${RELEASE:-43}"
IMAGE="${IMAGE:-ghcr.io/pichi-vm/fedora}"
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

# ---- 1. stage the carapace binary + generator symlink for the initrd -----
# The in-binary systemd generator turns `carapacehash=` into the attach unit.
# mkosi copies the subimage's mkosi.extra/ into the initramfs verbatim.
cargo install --git "$CARAPACE_GIT" --root "$work/carapace" --quiet carapace
ext="$here/mkosi.images/initrd/mkosi.extra"
rm -rf "$ext"
mkdir -p "$ext/usr/bin" "$ext/usr/lib/systemd/system-generators"
cp "$work/carapace/bin/carapace" "$ext/usr/bin/carapace"
ln -sf ../../../bin/carapace "$ext/usr/lib/systemd/system-generators/systemd-carapace-generator"

# ---- 2. build rootfs + initrd + kernel in one mkosi run ------------------
mkosi --force --output-dir "$work"

# Resolve the split artifacts. mkosi drops the main image's outputs and every
# subimage's output into --output-dir; the root partition is written as
# <output>.root.raw by SplitArtifacts=partitions. Fail with a listing rather
# than a cryptic "no such file" if a name ever shifts.
find_one() {
	local desc="$1" f; shift
	for f in "$@"; do [ -e "$f" ] && { printf '%s' "$f"; return; }; done
	echo "!!! could not find $desc in $work; mkosi produced:" >&2
	ls -1 "$work" >&2
	exit 1
}
# repart names the split partition after its label: <output>.root-<arch>.raw
# (e.g. fedora.root-x86-64.raw) — NOT the full-disk fedora.raw.
root="$(find_one 'root ext4 partition' "$work"/*.root-*.raw "$work"/*.root.raw)"
initrd="$(find_one 'initrd' "$work"/initrd.cpio "$work/initrd" "$work"/*initrd*.cpio)"
kver="$(cat "$work/kver")"
echo ">>> kernel $kver  root $(basename "$root")  initrd $(basename "$initrd")"

# Guard the subimage/rootfs kernel match: the uncompressed initrd's module tree
# must be the same NEVRA as the rootfs kernel (see mkosi.images/initrd note).
# `sort -u` (not `head`) drains cpio fully: a truncating consumer would
# SIGPIPE cpio, and `set -o pipefail` would abort the script on that.
initrd_kver="$(cpio -t < "$initrd" 2>/dev/null \
	| sed -n 's#^\(\./\)\?usr/lib/modules/\([^/]*\)/.*#\2#p' | sort -u | head -n1)"
if [ "$initrd_kver" != "$kver" ]; then
	echo "!!! initrd kernel ($initrd_kver) != rootfs kernel ($kver)" >&2
	exit 1
fi

# Sanity-check the carapace verity block size (4096B) on the emitted ext4.
bs="$(dumpe2fs -h "$root" 2>/dev/null | sed -n 's/^Block size: *//p')"
[ "$bs" = "4096" ] || { echo "!!! root ext4 block size $bs != 4096" >&2; exit 1; }

# ---- 3. import the carapace once; read its top root hash ------------------
# `import raw` caches the carapace and, thanks to sparse SEEK_HOLE handling,
# ingests the large mostly-empty ext4 in O(content). It's tagged as the reusable
# base carapace and reused via `--carapace` in step 5, so the carapace is
# imported ONCE (no throwaway import). The dm-verity top hash — arma's
# `carapacehash=` trust anchor — is a manifest annotation, read via `inspect`
# (which needs a resolvable ref, hence the tag rather than the bare digest).
carapace="fedora:$RELEASE-carapace"
pichi import raw "$root" -t "$carapace" --quiet
hash="$(pichi inspect "$carapace" \
	--format '{{ manifest.annotations["dev.pichi.carapace.verity.hash"] }}')"
echo ">>> carapace $carapace  root $hash"

# ---- 4. detached-mode PMI + base DTB -------------------------------------
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
	--initrd "$initrd" \
	--cmdline "root=/dev/mapper/root carapacehash=$hash console=hvc0 systemd.volatile=state systemd.unit=multi-user.target" \
	--dtb "$work/base.dtb" \
	"$work/boot.pmi"

# ---- 5. combine PMI + DTB + config onto the carapace ---------------------
# `import pmi --carapace <ref>` reuses the already-cached carapace's scutes
# (read-only) and layers the boot payload on, producing the combined bootable
# artifact tagged fedora:$RELEASE.
pichi import pmi "$work/boot.pmi" \
	--dtb "$work/base.dtb" \
	--config "$here/config.json" \
	--carapace "$carapace" \
	-t "fedora:$RELEASE"

echo ">>> imported combined artifact fedora:$RELEASE (carapace + dtb + pmi + config)"
echo "    boot-test: pichi run fedora:$RELEASE  # expect PICHI-CARAPACE-BOOT-OK then clean poweroff"
echo "    push with: pichi push fedora:$RELEASE $IMAGE:$RELEASE-<arch>"
