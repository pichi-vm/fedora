# pichi-vm/fedora

Fedora 43 base image for Pichi, built by [`pichi.yaml`](pichi.yaml). It combines
an ext4 carapace, an Arma-produced PMI with Corium as its initramfs, and the
requirements for booting Fedora with `pichi run`.

## Build

Use a native Linux/KVM host, Pichi and Dillo from their
[sources/pichi](sources/pichi) and [sources/dillo](sources/dillo) submodules, and
4096 available 2 MiB hugepages for the 8 GiB build VM. Set `PICHI_DILLO` if
Dillo is not beside Pichi.
With a published Fedora tool image available:

```sh
git submodule update --init --recursive
pichi pull ghcr.io/pichi-vm/fedora:43
pichi build . --ref HEAD --memory 8192 \
  --build-image ghcr.io/pichi-vm/conglobate@sha256:2239264c3281d53beedabdbfe8b3c587ac8ff8f2e87d4642e192f943f6cd5c45 \
  -t ghcr.io/pichi-vm/fedora:43
```

The build installs Arma and Corium from COPR into a temporary tool stage
and assembles the boot payload. The final root filesystem does not contain
those build tools.
Arma selects the required kernel modules and constructs the initramfs. The
package-install stages mount `/run`, `/tmp` and `/var` as tmpfs so their
transient state is not included in the image.

## Packages

Fedora owns the static specs and pinned application sources. COPR prepares
one SRPM per package and builds both native architectures. Image qualification
currently uses `npmccallum/pichi-staging`.

Increment the affected spec's `Release` whenever its source pin, spec, or
source-preparation recipe changes so DNF selects the new packages. Trusted
main builds submit changed package inputs to COPR and wait for both
architectures before image jobs start; image-only changes reuse existing RPMs.
Keep automatic repository publication enabled: COPR waits for publication
before reporting success. The image refreshes repository metadata before
installing packages by name, with normal signature checks. PR jobs use already
submitted packages without COPR credentials. Use the manual **COPR packages**
workflow on main to submit a packaging revision explicitly.

CI continues to build Pichi and Dillo from the pinned sources for its Ubuntu
and NixOS hosts, using the existing Cargo caches.

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
