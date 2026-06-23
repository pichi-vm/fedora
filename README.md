# pichi-vm/fedora

CI-built **Fedora base carapace** for the pichi ecosystem — a generic `from:`
for `pichi build` and the project's tests.

This is a *pure distro* base: a truly-minimal Fedora rootfs, no pichi or corium
content. It is packaged as a [carapace](https://github.com/pichi-vm/carapace)
OCI artifact and published to `ghcr.io/pichi-vm/fedora`. corium and any
app/kernel-builder tooling are layered on top at `pichi build` time, so this
repo depends only on **carapace + mkosi + skopeo** — never on pichi.

## How it's built

1. `mkosi` produces a minimal Fedora rootfs directory (`mkosi.conf`).
2. `mkfs.ext4 -d` packs it into a bare ext4 image.
3. `carapace import` converts that into a carapace OCI image layout.
4. `skopeo copy` pushes each per-arch layout to `:43-<arch>`, and `oras`
   assembles them into a multi-arch OCI **image index** tagged `:43`.

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
