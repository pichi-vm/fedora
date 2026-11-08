# pichi-vm/fedora

Fedora 43 base image for Pichi, built by [`pichi.yaml`](pichi.yaml). It combines
an ext4 carapace, an Arma-produced PMI with Corium as its initramfs, and the
requirements for booting Fedora with `pichi run`.

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

## Service policy for ephemeral workloads

The base retains Fedora's general-purpose service presets. A short-lived
derivative that does not need background package-cache updates or periodic
filesystem discard can disable those timers in a stage extending this image,
after package installation and preset application:

```yaml
- exec:
    command: systemctl --root=/ disable dnf-makecache.timer fstrim.timer
```

This opts out of scheduled maintenance; it does not remove DNF, filesystem
tools, or their services. Keep the timers where useful for long-lived guests
or persistent storage. Check the enabled-unit inventory again if subsequent
package installation reapplies presets.

## Instance hostname

The base image leaves `/etc/hostname` unset. Fedora's `fedora` fallback and
systemd's "No hostname configured" message are normal when no name is supplied.
For a named instance, set the `systemd.hostname` kernel parameter. In a derived
image recipe, add its boot extension under `image.boot.extend`:

```yaml
kernel.systemd.hostname: worker-01
```

Choose a different name for each instance. This works with read-only `/etc`
and takes precedence over a baked hostname; it does not configure networking
or DNS. See systemd's [hostname semantics](https://www.freedesktop.org/software/systemd/man/258/hostname.html).

## Network readiness

The shutdown-only demo needs no network device or wait-online service.
Reaching `network-online.target` alone does not prove connectivity.

For a networking workload, provide a virtual NIC, configure its guest
interface, and enable a network manager with its matching wait-online
service. For example, `systemd-networkd` uses
`systemd-networkd-wait-online.service`; configure which interfaces and
address families must be ready. A service that needs this startup ordering
can include:

```ini
[Unit]
Wants=network-online.target
After=network-online.target
```

This waits for the configured readiness check to finish, but a failed or
timed-out check can still leave the target active and the workload running.
If failure must prevent startup, require and order after the relevant
readiness service itself. Applications must also handle connection failures
and retry their actual destination: neither a configured address nor an
active target guarantees DNS, Internet access, or continued connectivity.

See systemd's [network synchronization documentation](https://systemd.io/NETWORK_ONLINE/).

## Optional PC-speaker exclusion

For a headless workload that does not need the PC speaker, add this to its
existing image boot configuration:

```yaml
image:
  boot:
    extend:
      kernel.modprobe.blacklist: snd_pcsp
```

The tested Fedora 43 x86 kernel resolves the `platform:pcspkr` device alias
to `snd_pcsp`. This setting prevents its normal udev autoload; the platform
device can still exist without a bound driver. It does not remove the module
or prohibit an explicit load. Leave the setting out when the workload needs
the speaker; the general-purpose base image keeps its default behavior.

After replacing the kernel, check `modprobe -R platform:pcspkr`
again rather than assuming the driver name. See [modprobe's command-line
blacklist documentation](https://man7.org/linux/man-pages/man8/modprobe.8.html).

## Optional tty1 getty exclusion

The base image statically enables `getty@tty1.service`. Setting
`kernel.systemd.getty_auto: "no"` disables automatic getty generation but
does not remove that enablement.

For a headless derivative, add this step to a stage extending the Fedora
image, after any package installation or preset application:

```yaml
- exec:
    command: systemctl --root=/ disable getty@tty1.service
```

Also set this under its existing `image.boot.extend` configuration if it
does not need automatically generated login consoles:

```yaml
kernel.systemd.getty_auto: "no"
```

This removes the static tty1 startup request while preserving the console
device for workload output. It does not disable other explicitly enabled
login services. Keep an intentional login console enabled for derivatives
that require interactive recovery, and inspect their enabled units after
applying presets. The general-purpose base keeps its default login policy.
See [systemd-getty-generator](https://www.freedesktop.org/software/systemd/man/latest/systemd-getty-generator.html).

## Instance identity

The base image ships an empty `/etc/machine-id` and no D-Bus machine ID.
Systemd generates an ID on first boot, and tmpfiles copies it to the regular
file `/var/lib/dbus/machine-id` if that file is absent. When persistent `/var`
is mounted before systemd starts, later boots reuse that saved ID. Each fresh
state volume gets its own identity; copying a state volume also copies its ID.

Persistence requires an image configured for persistent `/var` and a retained
backing disk, selected with `pichi run --storage-file`. Retaining a disk alone
does not change an image's mount policy. With volatile `/var`, the
saved file disappears with the guest and the next launch gets a fresh ID.

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
