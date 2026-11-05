# pichi-vm/fedora

Fedora 43 base image for Pichi, built by [`pichi.yaml`](pichi.yaml). It combines
an ext4 carapace, an Arma-produced PMI with Corium as its initramfs, and the
requirements for booting Fedora with `pichi run`.

## Build

Use a native Linux/KVM host, Pichi and Dillo at the revisions pinned in
[the workflow](.github/workflows/build.yml), and 4096 available 2 MiB hugepages
for the 8 GiB build VM. Set `PICHI_DILLO` if Dillo is not beside Pichi.
With a published Fedora tool image available:

```sh
git submodule update --init --recursive
pichi pull ghcr.io/pichi-vm/fedora:43
pichi build . --ref HEAD --memory 8192 \
  --build-image ghcr.io/pichi-vm/conglobate@sha256:262f87ecd7a178a90979eebd9689a0a28c1a4d844e6572a0fea116bf782a0b6f \
  -t ghcr.io/pichi-vm/fedora:43
```

The build uses committed sources, including the Arma and Corium submodule
pins. The stages install the root filesystem, extend it with Fedora's Rust
toolchain, compile Arma and Corium separately, and assemble the boot payload.
Arma selects the required kernel modules and constructs the initramfs. The
package-install stages mount `/run`, `/tmp` and `/var` as tmpfs so their
transient state is not included in the image.

## Bootstrap and CI

CI first tries to pull the published Fedora image. If unavailable, inline
workflow steps use Ubuntu's DNF to install only enough Fedora packages to run
DNF, create a bare ext4 image with `mkfs.ext4 -d`, and import it under the same
`ghcr.io/pichi-vm/fedora:43` name. This initial tool image is never published.
Both paths then run the same `pichi build` recipe.

The recipe marks that tool input `!bootstrap`, so it needs no `pichi.lock`.
The output manifest has `dev.pichi.build.bootstrapped=true`, identifying the
unlocked input boundary. Pichi resolves the cached input before replacing its
tag, so the produced image can serve as the next build's tool image.

On both native amd64 and arm64 KVM runners, CI builds the first image, uses it
for an ordinary locked successor, and rebuilds the bootstrap recipe under its
input name. It checks the output manifest annotations and retains image
metadata and the successor's committed source in a Git bundle. The jobs
exercise image production and reuse; they do not test the output's login boot.
Only main publishes the combined multi-architecture index; PRs publish nothing.

## Trademark

Built from Fedora packages; redistributed under the Fedora Project's
[Remix](https://docs.fedoraproject.org/en-US/legal/fedora-remix-trademark/)
allowance. Not endorsed by or affiliated with the Fedora Project.

## License

Repository tooling: Apache-2.0 (see [LICENSE](LICENSE)). The image content is
composed of Fedora packages under their respective upstream licenses and is not
covered by this repository's license.
