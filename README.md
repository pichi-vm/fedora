# pichi-vm/fedora

CI-built **Fedora combined base OS image** for the pichi ecosystem — a single
pichi artifact that both serves as a `from:` base and boots directly with
`pichi run`.

The artifact bundles all four pieces of the [`dt`](https://github.com/pichi-vm/pmi)
combined-image format: the **carapace** (scutes — the Fedora rootfs), a
**detached base DTB**, a **detached-mode PMI** (kernel + a tiny custom
initramfs), and the launch **config**. The initramfs is a single **static
`corium` binary as `/init`** plus the handful of kernel modules the distro
kernel doesn't build in — no systemd, no udev. As PID1 it mounts the API
filesystems, loads those modules, reads `corium=<root-hash>` from the measured
command line, discovers the scutes' GPT partitions, and mounts the assembled
Carapace root read-only. It pivots out of the initramfs and executes `/sbin/init`
(systemd). There is no fixed root-device name or `root=` argument. The result
is a general-purpose base
image that boots to `multi-user.target` with a console login, for other pichi
images to build on.

One kernel version underpins the PMI's `vmlinuz`, the initramfs modules, and the
carapace's `/usr/lib/modules` — all from **one mkosi run**. `/boot` and the
kernel image are boot payload (the PMI's domain) and are stripped from the
carapace.

## How it's built

One `mkosi` run builds the rootfs; `build.sh` then assembles the tiny custom
initramfs, `arma` seals the PMI, and `pichi import` packages the artifact
([`build.sh`](build.sh)):

```
mkosi ──▶ import raw ──▶ arma build ──▶ import pmi
              (static Corium init + .ko → initrd.cpio)
```

1. **`mkosi`** builds the Fedora rootfs (`systemd` + `kernel-core`), then:
   - `mkosi.finalize` copies `vmlinuz` + kernel config out, **exports the
     initramfs module set** (the carapace-boot pivot modules that aren't builtin,
     + deps — ~just `dm-verity` on a stock Fedora kernel) to `initrd-mods/`, and
     strips `/boot` and the in-tree kernel image;
   - `mkosi.repart/` packs the stripped tree into a single **bare ext4 root**
     partition, emitted as `fedora.root-<arch>.raw` (`SplitArtifacts=partitions`,
     no GPT). The filesystem is sized to the carapace's fixed apparent
     root-device length (**64 GiB**, carapace `ZERO_COUNT_SECTORS`); because
     `pichi import raw` walks the image sparsely (`SEEK_HOLE`) and drops zero
     blocks, that size costs nothing in the stored artifact — the scute is
     proportional to real content, not fs size;
   - `build.sh` builds a **static (musl) `corium`** and cpios it as `/init`
     together with the exported `.ko` into an uncompressed initramfs (arma
     rejects compressed initrds). No systemd/udev in the initramfs.
2. **`pichi import raw`** ingests that ext4 as a base **carapace** (tagged
   `fedora:<release>-carapace`, a reusable `from:` base) and exposes its
   dm-verity top hash as a manifest annotation. The carapace is imported
   **once** — reused in step 4 via `--carapace`, so there's no throwaway import.
3. **`arma build … --dtb`** seals the detached PMI + base DTB with
   `corium=<top>` (read back via `pichi inspect`) on the cmdline — arma
   needs the hash before the bootable artifact can be sealed.
4. **`pichi import pmi … --carapace <ref> --dtb --config`** layers the boot
   payload onto the cached carapace, producing the combined artifact; CI then
   `pichi save`/`load` per arch and does one atomic multi-arch `pichi push`
   (see below).

## Multi-arch

`amd64` and `arm64` are built **natively** — no QEMU — on GitHub's free hosted
runners (`ubuntu-latest` and `ubuntu-24.04-arm`; the latter requires a public
repo). The index entries use `platform.os = "pichi"`: a carapace is a pichi
VM-guest root filesystem, not an artifact "used on" an OS, so the OCI
`platform.os` field doesn't apply — it's a selector token the producer and
`pichi pull` agree on (which also makes container runtimes correctly refuse the
artifact). `platform.architecture` is the conventional OCI/GOARCH `amd64`/`arm64`.

See [`build.sh`](build.sh) for the local equivalent and
[`.github/workflows/build.yml`](.github/workflows/build.yml) for CI. Builds run
on pushes and pull requests; registry publication is restricted to `main`.

## Boot contract and local verification

[Corium](https://github.com/pichi-vm/corium) 0.2 requires **Linux 7.0 or newer**
for its initramfs `pivot_root`; older kernels have no fallback. Fedora 43 is the
default package source, not a promise that every historical Fedora 43 kernel
works. `mkosi.finalize` rejects older kernels, multiple module trees, missing
GPT/API-filesystem support, unavailable pivot drivers, and compressed modules
without matching in-kernel decompression. Use a distribution/package source
with a compatible kernel; do not bypass these checks. Kernel, configuration
and modules all come from the same mkosi run, on both architectures.

The imported filesystem is bare ext4, **not** a GPT disk. At launch `pichi run`
provides the COW and verity blobs as GPT partitions through dillo; their
PARTUUIDs are derived from the trusted chain root. Corium discovers these
partitions and uses Carapace for validation and storage assembly. Carapace
remains the storage format/library; it is no longer the initramfs entrypoint.
The 64 GiB filesystem size is still Carapace's storage geometry, not a fixed
device name. The builder supplies `/dev`, `/proc`, `/sys`, `/run`, and the
executable `/sbin/init` in the root. Corium does not carry API mounts into it;
systemd owns subsequent setup, including volatile `/var` on this read-only base.

Local build prerequisites are listed in `build.sh`; Corium uses stable Rust
(1.89+), separate from arma/pichi's nightly toolchain. Run:

```sh
python3 -m unittest discover -s tests -v
bash -n build.sh
./build.sh
```

Corium is acquired at the `CORIUM_REV` pinned in `build.sh`, with `--locked`.
`CORIUM_GIT`, `CORIUM_REV`, and `CORIUM_TOOLCHAIN` are explicit development
overrides. `CORIUM_BIN=/absolute/path/to/corium` instead supplies a trusted
prebuilt static binary for the native musl architecture; the former
`CARAPACE_BIN`/`CARAPACE_GIT` init hooks are no longer used. `RELEASE` overrides
both mkosi's package release and artifact tags. `ARMA` selects the PMI producer.

The rootless regression tests exercise actual builder/finalizer scripts against
isolated fixtures and tool doubles. They are not boot tests. CI runs them in
addition to native combined-artifact builds for amd64 and arm64, license-header
checks and gitlint. A successful build alone does not prove VM handoff.

On a native Linux/KVM host with a current dillo supporting detached DTBs and
a pre-provisioned pool of 2 MiB hugepages sufficient for the configured guest
RAM (2048 MiB recommended by `config.json`):

```sh
# PICHI_DILLO can select a current launcher instead of pichi's sibling binary.
PICHI_DILLO=/absolute/path/to/dillo python3 tests/boot.py --release 43
```

This boots the actual combined artifact through `pichi run`, requiring Fedora's
systemd-managed console login. The harness then terminates that guest; it does
not claim a graceful shutdown. Two separately sealed negative artifacts verify
that a wrong trusted root and the obsolete `carapacehash=` argument fail before
real-init handoff. Test tags are unique, local-only, and left in pichi's cache;
console logs, command lines and results remain under `.build/boot-tests-*`.
No host mounts, loop devices or device-mapper changes are used. CI runs this
lane on amd64; arm64 currently has native artifact-build coverage only.

## Trademark

Built with mkosi from Fedora packages; redistributed under the Fedora Project's
[Remix](https://docs.fedoraproject.org/en-US/legal/fedora-remix-trademark/)
allowance. Not endorsed by or affiliated with the Fedora Project.

## License

Repository tooling: Apache-2.0 (see [LICENSE](LICENSE)). The image content is
composed of Fedora packages under their respective upstream licenses and is not
covered by this repository's license.
