# pichi-vm/fedora

CI-built **Fedora combined base OS image** for the pichi ecosystem — a single
pichi artifact that both serves as a `from:` base and boots directly with
`pichi run`.

The artifact bundles all four pieces of the [`dt`](https://github.com/pichi-vm/pmi)
combined-image format: the **carapace** (scutes — the Fedora rootfs), a
**detached base DTB**, a **detached-mode PMI** (kernel + a tiny custom
initramfs), and the launch **config**. The initramfs is a single **static
`carapace` binary as `/init`** plus the handful of kernel modules the distro
kernel doesn't build in — no systemd, no udev. As PID1 it mounts the API
filesystems, loads those modules, reads `carapacehash=` from the (measured)
command line, assembles `/dev/mapper/root`, and `switch_root`s into the Fedora
rootfs (where systemd is the real init). A *temporary* boot-test unit then
powers off with a console marker so the full chain is verifiable.

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
              (static carapace init + .ko → initrd.cpio)
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
   - `build.sh` builds a **static (musl) `carapace`** and cpios it as `/init`
     together with the exported `.ko` → a ~1 MB uncompressed initramfs (arma
     rejects compressed initrds). No systemd/udev in the initramfs.
2. **`pichi import raw`** ingests that ext4 as a base **carapace** (tagged
   `fedora:<release>-carapace`, a reusable `from:` base) and exposes its
   dm-verity top hash as a manifest annotation. The carapace is imported
   **once** — reused in step 4 via `--carapace`, so there's no throwaway import.
3. **`arma build … --dtb`** seals the detached PMI + base DTB with
   `carapacehash=<top>` (read back via `pichi inspect`) on the cmdline — arma
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
[`.github/workflows/build.yml`](.github/workflows/build.yml) for CI.

## Trademark

Built with mkosi from Fedora packages; redistributed under the Fedora Project's
[Remix](https://docs.fedoraproject.org/en-US/legal/fedora-remix-trademark/)
allowance. Not endorsed by or affiliated with the Fedora Project.

## License

Repository tooling: Apache-2.0 (see [LICENSE](LICENSE)). The image content is
composed of Fedora packages under their respective upstream licenses and is not
covered by this repository's license.
