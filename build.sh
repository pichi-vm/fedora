#!/usr/bin/env bash
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

# Build a Fedora image with a partitioned carapace, immutable PMI, native
# bootconfig and launch requirements. Static Corium in the initramfs assembles
# the chain, discovers its GPT root partition and pivots to systemd.
#
# One mkosi run supplies the kernel, matching module tree and complete GPT
# disk. The PMI embeds its platform device tree and fixed bootconfig command
# line; the selected carapace root travels in a separate configuration blob.
# Corium requires Linux 7.0+ for the initramfs pivot. No systemd or udev is
# needed in the initramfs. Fedora boots to a console login.
#
# Requires: mkosi, pichi, arma (ARMA=<path> or on PATH), cargo + rustup (static
# musl target), cpio, dumpe2fs (e2fsprogs). Runs rootless (userns).
set -euo pipefail

RELEASE="${RELEASE:-43}"
IMAGE="${IMAGE:-ghcr.io/pichi-vm/fedora}"
ARMA="${ARMA:-arma}"
CORIUM_GIT="${CORIUM_GIT:-https://github.com/pichi-vm/corium}"
# Corium reads native bootconfig and maps the discovered GPT root partition.
CORIUM_REV="${CORIUM_REV:-c33ae0e01d58b657f8f62cb91672885326a903b9}"
CORIUM_TOOLCHAIN="${CORIUM_TOOLCHAIN:-stable}"

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

# ---- 1. build the static Corium init binary ------------------------------
# The initramfs is just this one static (musl) binary as /init — it is PID1:
# mount, load modules, discover/assemble the carapace, pivot, exec /sbin/init.
# CORIUM_BIN=<path> supplies a prebuilt static binary for the native arch
# (dev/CI hook, like ARMA=); otherwise build the pinned source with its lockfile.
if [ -n "${CORIUM_BIN:-}" ]; then
	corium_bin="$CORIUM_BIN"
else
	rustup target add --toolchain "$CORIUM_TOOLCHAIN" "$MUSL"
	cargo "+$CORIUM_TOOLCHAIN" install --locked --git "$CORIUM_GIT" --rev "$CORIUM_REV" \
		--target "$MUSL" --root "$work/corium" --quiet corium
	corium_bin="$work/corium/bin/corium"
fi

# ---- 2. build the rootfs carapace in one mkosi run -----------------------
mkosi --force --release "$RELEASE" --output-dir "$work"

# Resolve the split artifacts (fail with a listing rather than a cryptic error).
find_one() {
	local desc="$1" f; shift
	for f in "$@"; do [ -e "$f" ] && { printf '%s' "$f"; return; }; done
	echo "!!! could not find $desc in $work; mkosi produced:" >&2
	ls -1 "$work" >&2
	exit 1
}
# Keep the split filesystem for inspection; import the complete GPT disk.
disk="$work/fedora.raw"
[ -f "$disk" ] || { echo "!!! mkosi did not produce a GPT disk" >&2; exit 1; }
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
install -m0755 "$corium_bin" "$stage/init"
[ -d "$work/initrd-mods" ] && cp -a "$work/initrd-mods/." "$stage/"
( cd "$stage" && find . -print0 | cpio --null --create --format=newc --quiet ) > "$work/initrd.cpio"
initrd="$work/initrd.cpio"
echo ">>> initrd $(du -h "$initrd" | cut -f1)  modules: $(find "$stage" -name '*.ko*' | wc -l)"

# ---- 4. import the carapace once; read its top root hash ------------------
# `import raw` caches the carapace (sparse SEEK_HOLE ingest, O(content)), tagged
# as the reusable base and reused via `--carapace` in step 6 (imported ONCE). The
# dm-verity top hash — the `corium.root` trust anchor — is a manifest
# annotation, read via `inspect`.
carapace="fedora:$RELEASE-carapace"
pichi import raw "$disk" -t "$carapace" --quiet
hash="$(pichi inspect "$carapace" \
	--format '{{ manifest.annotations["dev.pichi.carapace.verity.hash"] }}')"
# The manifest contract is SHA-256. Never seal an empty/malformed trust anchor.
[[ "$hash" =~ ^[[:xdigit:]]{64}$ && "$hash" =~ [1-9a-fA-F] ]] || { echo "!!! invalid carapace verity root: $hash" >&2; exit 1; }
echo ">>> carapace $carapace  root $hash"

# ---- 5. immutable PMI plus native boot configuration --------------------
# The command line is fixed. The trusted root and systemd settings can change
# with image composition while preserving the measured kernel and initramfs.
cat > "$work/bootconfig" <<EOF
corium.root = "$hash"
kernel {
    ro
    console = "hvc0"
    systemd.volatile = "state"
    systemd.unit = "multi-user.target"
    systemd.show_status = "false"
}
EOF
"$ARMA" build \
	--kernel "$work/vmlinuz" \
	--config "$work/kernel.config" \
	--initrd "$initrd" \
	--cmdline bootconfig \
	--dtb attached \
	"$work/boot.pmi"

# ---- 6. combine PMI and bootconfig onto the carapace ----------------------
# Stamp OCI provenance annotations onto the artifact manifest (pichi carries
# them verbatim; structural verity keys can't be overridden). revision prefers
# an explicit $REVISION (set by CI), falling back to git, then "unknown".
rev="${REVISION:-$(git -C "$here" rev-parse HEAD 2>/dev/null || echo unknown)}"
pichi import pmi "$work/boot.pmi" \
	--bootconfig "$work/bootconfig" \
	--config "$here/config.json" \
	--carapace "$carapace" \
	-a "org.opencontainers.image.source=https://github.com/pichi-vm/fedora" \
	-a "org.opencontainers.image.revision=$rev" \
	-a "org.opencontainers.image.version=$RELEASE" \
	-a "org.opencontainers.image.title=Fedora $RELEASE" \
	-a "org.opencontainers.image.description=Fedora $RELEASE base OS carapace for pichi" \
	-t "fedora:$RELEASE"

echo ">>> imported combined artifact fedora:$RELEASE (carapace + pmi + bootconfig + config)"
echo "    run:  pichi run fedora:$RELEASE  # boots to a console login (multi-user)"
echo "    publish: tag fedora:$RELEASE as $IMAGE:$RELEASE-<arch>, then pichi push that tag"
