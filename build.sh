#!/usr/bin/env bash
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

# Build the Fedora combined base OS image — a single pichi artifact carrying the
# carapace (scutes) + a detached base DTB + a detached-mode PMI + the launch
# config. `pichi run` boots it: the PMI's initramfs is a single static `carapace`
# binary as init — it loads the shipped modules, reads `carapacehash=`, assembles
# /dev/mapper/root, and switch_roots into the Fedora rootfs. No systemd or udev
# in the initramfs. A temporary boot-test unit then powers off with a console
# marker so the boot is verifiable.
#
# ONE mkosi run builds the rootfs carapace and exports what the PMI needs;
# build.sh then assembles the tiny custom initramfs:
#   * mkosi.repart/ packs the rootfs into a bare ext4 root partition emitted as
#     <output>.root-<arch>.raw (SplitArtifacts=partitions, no GPT);
#   * mkosi.finalize copies out vmlinuz + kernel config + kver, and exports the
#     initramfs module set (pivot modules not builtin, + deps) to initrd-mods/;
#   * the initramfs = static `carapace` (musl) as /init + those .ko, cpio'd here.
# One kernel version underpins the PMI vmlinuz, the initramfs modules, and the
# carapace /usr/lib/modules — all from the single mkosi build.
#
# Requires: mkosi, pichi, arma (ARMA=<path> or on PATH), cargo + rustup (static
# musl target), cpio, dumpe2fs (e2fsprogs). Runs rootless (userns).
set -euo pipefail

RELEASE="${RELEASE:-43}"
IMAGE="${IMAGE:-ghcr.io/pichi-vm/fedora}"
ARMA="${ARMA:-arma}"
CARAPACE_GIT="${CARAPACE_GIT:-https://github.com/pichi-vm/carapace}"

case "$(uname -m)" in
	x86_64)  MUSL=x86_64-unknown-linux-musl ;;
	aarch64) MUSL=aarch64-unknown-linux-musl ;;
	*) echo "!!! unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
work="$here/.build"
# mkosi's rootfs tree is owned by us but read-only (dir mode 0555); make it
# writable before removing a previous run's output.
[ -e "$work" ] && chmod -R u+w "$work"
rm -rf "$work"
mkdir -p "$work"

# ---- 1. build the static carapace init binary ----------------------------
# The initramfs is just this one static (musl) binary as /init — it is PID1:
# mount, load modules, assemble the carapace, switch_root. No libc/systemd/udev
# needed in the initramfs. CARAPACE_BIN=<path> supplies a prebuilt static binary
# (dev/CI hook, like ARMA=); otherwise build it from CARAPACE_GIT.
if [ -n "${CARAPACE_BIN:-}" ]; then
	carapace_bin="$CARAPACE_BIN"
else
	rustup target add "$MUSL" >/dev/null 2>&1 || true
	cargo install --git "$CARAPACE_GIT" --target "$MUSL" --root "$work/carapace" --quiet carapace
	carapace_bin="$work/carapace/bin/carapace"
fi

# ---- 2. build the rootfs carapace in one mkosi run -----------------------
mkosi --force --output-dir "$work"

# Resolve the split artifacts (fail with a listing rather than a cryptic error).
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
kver="$(cat "$work/kver")"
echo ">>> kernel $kver  root $(basename "$root")"

# Sanity-check the carapace verity block size (4096B) on the emitted ext4.
bs="$(dumpe2fs -h "$root" 2>/dev/null | sed -n 's/^Block size: *//p')"
[ "$bs" = "4096" ] || { echo "!!! root ext4 block size $bs != 4096" >&2; exit 1; }

# ---- 3. assemble the custom initramfs (static init + shipped modules) -----
# All regular files (no device nodes — the init mounts devtmpfs itself), so the
# cpio builds rootless. Uncompressed newc (arma rejects compressed initrds).
stage="$work/initrd-root"
rm -rf "$stage"; mkdir -p "$stage"
install -m0755 "$carapace_bin" "$stage/init"
[ -d "$work/initrd-mods" ] && cp -a "$work/initrd-mods/." "$stage/"
( cd "$stage" && find . -print0 | cpio --null --create --format=newc --quiet ) > "$work/initrd.cpio"
initrd="$work/initrd.cpio"
echo ">>> initrd $(du -h "$initrd" | cut -f1)  modules: $(find "$stage" -name '*.ko*' | wc -l)"

# ---- 4. import the carapace once; read its top root hash ------------------
# `import raw` caches the carapace (sparse SEEK_HOLE ingest, O(content)), tagged
# as the reusable base and reused via `--carapace` in step 6 (imported ONCE). The
# dm-verity top hash — the `carapacehash=` trust anchor — is a manifest
# annotation, read via `inspect`.
carapace="fedora:$RELEASE-carapace"
pichi import raw "$root" -t "$carapace" --quiet
hash="$(pichi inspect "$carapace" \
	--format '{{ manifest.annotations["dev.pichi.carapace.verity.hash"] }}')"
echo ">>> carapace $carapace  root $hash"

# ---- 5. detached-mode PMI + base DTB -------------------------------------
# Cmdline notes (this is still a boot-test image, see pichi-boot-test.service):
#   carapacehash=       trust anchor read by the carapace init (PID1).
#   console=hvc0        the virtio-console; dillo surfaces it to the host.
#   carapace.timing     boot-test scaffolding: opt in to the carapace init's
#                       switch_root timing marker (off by default). Remove with
#                       pichi-boot-test.service when real workloads run.
#   systemd.*           apply to the REAL init (systemd in the rootfs, post-
#                       switch_root): volatile /var (the carapace root is
#                       read-only), headless multi-user, quiet console status.
# Slot inference (from --config) now emits a PCIe bridge and no virtio-mmio
# slots for this kernel: virtio_pci is builtin (works from the first
# instruction, carries the early console) while virtio-mmio is a module we
# neither ship nor need, so arma correctly omits the empty mmio transport
# slots the guest would otherwise probe and reject at boot.
"$ARMA" build \
	--kernel "$work/vmlinuz" \
	--config "$work/kernel.config" \
	--initrd "$initrd" \
	--cmdline "root=/dev/mapper/root carapacehash=$hash console=hvc0 carapace.timing systemd.volatile=state systemd.unit=multi-user.target systemd.show_status=false" \
	--dtb "$work/base.dtb" \
	"$work/boot.pmi"

# ---- 6. combine PMI + DTB + config onto the carapace ---------------------
# Stamp OCI provenance annotations onto the artifact manifest (pichi carries
# them verbatim; structural verity keys can't be overridden). revision comes
# from git when available (CI checks out the repo), else "unknown".
rev="$(git -C "$here" rev-parse HEAD 2>/dev/null || echo unknown)"
pichi import pmi "$work/boot.pmi" \
	--dtb "$work/base.dtb" \
	--config "$here/config.json" \
	--carapace "$carapace" \
	-a "org.opencontainers.image.source=https://github.com/pichi-vm/fedora" \
	-a "org.opencontainers.image.revision=$rev" \
	-a "org.opencontainers.image.version=$RELEASE" \
	-a "org.opencontainers.image.title=Fedora $RELEASE" \
	-a "org.opencontainers.image.description=Fedora $RELEASE base OS carapace for pichi" \
	-t "fedora:$RELEASE"

echo ">>> imported combined artifact fedora:$RELEASE (carapace + dtb + pmi + config)"
echo "    boot-test: pichi run fedora:$RELEASE  # expect PICHI-CARAPACE-BOOT-OK then clean poweroff"
echo "    push with: pichi push fedora:$RELEASE $IMAGE:$RELEASE-<arch>"
