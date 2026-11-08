# pichi-vm/fedora

Fedora 43 base image for Pichi, built by [`pichi.yaml`](pichi.yaml). It combines
an ext4 carapace, an Arma-produced PMI with Corium as its initramfs, and the
requirements for booting Fedora with `pichi run`.

## Hostname configuration

For a derived image with read-only `/etc`, set the hostname under
`image.boot.extend`:

```yaml
kernel.systemd.hostname: worker-01
```

Every instance of that image receives this name. This sets the guest hostname;
it does not configure DNS. See [systemd's hostname documentation](https://www.freedesktop.org/software/systemd/man/258/hostname.html).

## Build

Use a native Linux/KVM host with the `pichi` package (which depends on
`dillo-vm`) from
[COPR](https://copr.fedorainfracloud.org/coprs/npmccallum/pichi/) or
[the Ubuntu PPA](https://launchpad.net/~nmccallum/+archive/ubuntu/pichi), and
4096 available 2 MiB hugepages for the 8 GiB build VM. Put Dillo on `PATH` so Pichi can find it.
With a published Fedora tool image available:

```sh
pichi pull ghcr.io/pichi-vm/fedora:43
pichi build . --ref HEAD --memory 8192 \
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

## CI and bootstrap

[CI](.github/workflows/ci.yml) checks commit messages and builds the new image
**once per native architecture**. It pulls the published Fedora image. If the
pull fails, CI creates a minimal Fedora root containing DNF and its dependencies,
imports it into Pichi's local cache under the same image name, and runs the
production recipe. The temporary tool image is never published.

Both builds transfer their outputs as workflow artifacts. Only main publishes
the combined multi-architecture index after commit checking and both builds
succeed; PRs build without publishing.

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
