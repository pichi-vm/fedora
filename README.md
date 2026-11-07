# pichi-vm/fedora

Fedora 43 base image for Pichi, built by [`pichi.yaml`](pichi.yaml). It combines
an ext4 carapace, an Arma-produced PMI with Corium as its initramfs, and the
requirements for booting Fedora with `pichi run`.

## Build

Use a native Linux/KVM host with the `pichi` and `dillo-vm` packages from
[COPR](https://copr.fedorainfracloud.org/coprs/npmccallum/pichi/) or
[the Ubuntu PPA](https://launchpad.net/~nmccallum/+archive/ubuntu/pichi), and
4096 available 2 MiB hugepages for the 8 GiB build VM. Set `PICHI_DILLO` if
Dillo is not beside Pichi.
With a published Fedora tool image available:

```sh
pichi pull ghcr.io/pichi-vm/fedora:43
pichi build . --ref HEAD --memory 8192 \
  --build-image ghcr.io/pichi-vm/conglobate@sha256:dda6d25f6f51ad171611f159f4202bdec4e50482d6e741ad566c1b4d7c61d946 \
  -t ghcr.io/pichi-vm/fedora:43
```

The build uses the committed image recipe. It installs the root filesystem
from Fedora packages and assembles the boot payload with `arma` and `corium`
from COPR. Only the firmware stage installs these tools; the final root
filesystem remains the Fedora base system. This repo contains no package
specs, source submodules, or source compilation steps.
Arma selects the required kernel modules and constructs the initramfs. The
package-install stages mount `/run`, `/tmp` and `/var` as tmpfs so their
transient state is not included in the image.

## Initial bootstrap

Only if the registry has no prior Fedora image, prepare a minimal tool image
locally on each target architecture. This requires DNF, RPM, e2fsprogs, and
Pichi. The temporary root contains only enough Fedora userspace to run DNF;
it is not the production image and is not published.

```sh
bootstrap_dir=$(mktemp -d)
sudo dnf -y --installroot="$bootstrap_dir/root" --releasever=43 \
  --repofrompath=fedora,https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/$(uname -m)/os/ \
  --repo=fedora --setopt=fedora.gpgkey=https://fedoraproject.org/fedora.gpg \
  --setopt=gpgcheck=1 --setopt=install_weak_deps=False install \
  filesystem bash coreutils dnf glibc-minimal-langpack ca-certificates
sudo dnf --installroot="$bootstrap_dir/root" --releasever=43 clean all
sudo mkfs.ext4 -F -d "$bootstrap_dir/root" "$bootstrap_dir/bootstrap.raw" 1G
pichi import raw "$bootstrap_dir/bootstrap.raw" -t ghcr.io/pichi-vm/fedora:43
```

Then run the same `pichi build` command from the Build section, using this
cached input instead of pulling it. Build once on each native architecture
and export each result with `pichi save ghcr.io/pichi-vm/fedora:43 -o oci-amd64`
or `-o oci-arm64`. Copy both layouts to the publishing host. With GHCR write
authentication configured:

```sh
pichi load oci-amd64 --tag fedora:43-amd64
pichi load oci-arm64 --tag fedora:43-arm64
pichi manifest create fedora:43 fedora:43-amd64 fedora:43-arm64
pichi manifest annotate fedora:43 fedora:43-amd64 --os pichi --arch amd64
pichi manifest annotate fedora:43 fedora:43-arm64 --os pichi --arch arm64
pichi manifest push fedora:43 ghcr.io/pichi-vm/fedora:43
```

## CI

CI installs Pichi and Dillo from the PPA, pulls the existing Fedora image,
and builds the new image **once per architecture**. It has no bootstrap
fallback: if the registry has no prior image, perform the local procedure
above first. Only main publishes the combined multi-architecture index;
PRs build without publishing.

The recipe marks its tool input `!bootstrap`, so it needs no `pichi.lock`.
The output manifest has `dev.pichi.build.bootstrapped=true`, identifying the
unlocked input boundary. Pichi resolves the cached input before replacing its
tag, so the produced image can serve as the next build's tool image.

## Trademark

Built from Fedora packages; redistributed under the Fedora Project's
[Remix](https://docs.fedoraproject.org/en-US/legal/fedora-remix-trademark/)
allowance. Not endorsed by or affiliated with the Fedora Project.

## License

Repository tooling: Apache-2.0 (see [LICENSE](LICENSE)). The image content is
composed of Fedora packages under their respective upstream licenses and is not
covered by this repository's license.
