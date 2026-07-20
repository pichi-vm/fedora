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
carapace's `/usr/lib/modules` — all from one mkosi build. `/boot` and the kernel
image are boot payload (the PMI's domain) and are stripped from the carapace.

## How it's built

1. `mkosi` produces the Fedora rootfs with `systemd` + the kernel (`mkosi.conf`).
2. `vmlinuz` is extracted and a matching systemd initramfs is built via mkosi's
   `mkosi-initrd`, pinned to the same kernel, with the carapace binary +
   generator and `dm-snapshot` added (`initrd/`).
3. `/boot` and the kernel image are stripped; `mkfs.ext4 -d` packs the carapace.
4. `arma build … --dtb` seals the detached PMI + base DTB with
   `carapacehash=<top>` on the cmdline.
5. `pichi import … --pmi --dtb --config` packages the combined artifact;
   `pichi push` / `pichi push-index` publish the multi-arch index.

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
