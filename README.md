# pichi-vm/fedora

CI-built **Fedora combined base OS image** for the pichi ecosystem — a single
pichi artifact that both serves as a `from:` base and boots directly with
`pichi run`.

The artifact bundles all four pieces of the [`dt`](https://github.com/pichi-vm/pmi)
combined-image format: the **carapace** (scutes — the Fedora rootfs), a
**detached base DTB**, a **detached-mode PMI** (kernel + a systemd initramfs),
and the launch **config**. Boot is native systemd: the PMI's initramfs runs
carapace's systemd generator, which assembles `/dev/mapper/root` from
`carapacehash=` on the (measured) command line, and systemd pivots into the
Fedora rootfs. A *temporary* boot-test unit then powers off with a console
marker so the full chain is verifiable.

One kernel version underpins the PMI's `vmlinuz`, the initramfs modules, and the
carapace's `/usr/lib/modules` — all from **one mkosi run**. `/boot` and the
kernel image are boot payload (the PMI's domain) and are stripped from the
carapace.

## How it's built

A single `mkosi` invocation does all the OS work; then `arma` seals the PMI and
`pichi import` packages the artifact ([`build.sh`](build.sh)):

```
mkosi ──▶ import raw ──▶ arma build ──▶ import pmi
```

1. **`mkosi`** builds the whole OS in one run (`mkosi.conf` + `mkosi.images/`):
   - the Fedora rootfs (`systemd` + `kernel-core`);
   - the matching systemd initramfs as a **subimage** (`mkosi.images/initrd/`,
     pulled in via `Dependencies=`) — `mkosi-initrd` plus `dm-snapshot` and the
     staged carapace binary + generator, output uncompressed (arma rejects
     compressed initrds). Sharing the run's package snapshot, its kernel matches
     the rootfs by construction — no version is hand-plumbed;
   - `mkosi.finalize` copies `vmlinuz` + the kernel config out and strips
     `/boot` and the in-tree kernel image;
   - `mkosi.repart/` packs the stripped tree into a single **bare ext4 root**
     partition, emitted as `fedora.root.raw` (`SplitArtifacts=partitions`, no
     GPT). The filesystem is sized to the carapace's fixed apparent root-device
     length (**64 GiB**, carapace `ZERO_COUNT_SECTORS`) so the guest root fills
     the device with no wasted space; because `pichi import raw` walks the image
     sparsely (`SEEK_HOLE`) and drops zero blocks, that size costs nothing in
     the stored artifact — the scute is proportional to real content, not fs
     size.
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
