# pichi-vm/fedora

Fedora 43 base image for Pichi, built by [`pichi.yaml`](pichi.yaml). It combines
an ext4 carapace, an Arma-produced PMI with Corium as its initramfs, and the
requirements for booting Fedora with `pichi run`.

## Build

Use a native Linux/KVM host with a Fedora 43 userspace, Pichi and Dillo
installed from the selected COPR package set, and 4096 available 2 MiB
hugepages for the 8 GiB build VM. CI uses Fedora containers on its native
Ubuntu and NixOS hosts. Set `PICHI_DILLO=/usr/bin/dillo`.

## Packages and source ownership

This repository owns Fedora RPM definitions for Corium, Arma, Dillo, Pichi,
and Madrillo. The `sources/*` gitlinks pin upstream code. Madrillo is packaged
independently; it is not an input to this image recipe.

COPR runs `.copr/Makefile` to prepare one SRPM per package, then compiles it
natively for Fedora 43 x86_64 and aarch64 with networking disabled. Source
preparation vendors locked dependencies and includes both host toolchains
where Dillo needs its pinned nightly. Corium is linked statically for `/init`.
GitHub runners do not prepare SRPMs or compile these tools.

Package releases include the input timestamp and a content hash. The hash
covers the source gitlink, spec, packaging patches, and source preparation.
Image-only changes reuse successful builds. `scripts/copr.py` rejects failed
builds, missing architectures, unexpected package identities, invalid RPM
signatures, and checksum mismatches. Trusted keys are committed in `keys/`.

Trusted main runs submit missing packages using the repository's `COPR_CONFIG`
secret. PRs only resolve existing public results. A maintainer can use the
**COPR package submission** workflow on main to submit a PR's exact canonical
repository commit. A missing package fails the package check before an image
job acquires a native runner; it does not silently use an older version.

For local preparation of image inputs, after the selected packages have built:

```sh
python3 scripts/copr.py resolve --project pichi-staging --out .build/packages
cp .build/packages/packages.lock.json packages.lock.json
git add packages.lock.json
git commit -m 'build: lock verified COPR package inputs'
pichi pull ghcr.io/pichi-vm/fedora:43
pichi build . --ref HEAD --memory 8192 \
  --build-image ghcr.io/pichi-vm/conglobate@sha256:2239264c3281d53beedabdbfe8b3c587ac8ff8f2e87d4642e192f943f6cd5c45 \
  -t ghcr.io/pichi-vm/fedora:43
```

The lock records exact COPR builds, source revisions, signing-key identity,
and RPM checksums for both architectures. CI creates a deterministic commit
containing that lock before invoking `pichi build`; it retains the input Git
bundle with its qualification evidence. The committed recipe installs Arma
and Corium in temporary stages, leaving build tools out of the final root.

## Bootstrap and qualification

CI first tries the published Fedora image. If unavailable, it constructs a
minimal DNF-capable ext4 seed in Fedora userspace and imports it. Both paths
then run the same `pichi build` recipe. The initial seed is not published.

The tool input is marked `!bootstrap`, so it needs no `pichi.lock`. CI builds
the first image, uses it for a locked successor, and rebuilds the bootstrap
recipe under its input name. It checks provenance annotations and boots the
produced image through packaged Pichi and Dillo to a console login on both
native architectures. The boot check terminates the guest afterward; it does
not claim a graceful shutdown.

Only qualified main runs publish the multi-architecture image index. Before
publication, the exact signed RPM set and package manifest are archived in a
`rpms-<input-set>` GitHub prerelease, independently of COPR retention. Downloads
prefer that archive and verify the same checksums and signatures. Existing
archive contents are not overwritten. Published input sets can be reused for
rollback without rebuilding the application sources.

The current integration uses `npmccallum/pichi-staging`. Production cutover
must switch the resolver to `npmccallum/pichi` only after both architectures
pass qualification and upstream packaging triggers have been retired.

## Trademark

Built from Fedora packages; redistributed under the Fedora Project's
[Remix](https://docs.fedoraproject.org/en-US/legal/fedora-remix-trademark/)
allowance. Not endorsed by or affiliated with the Fedora Project.

## License

Repository tooling: Apache-2.0 (see [LICENSE](LICENSE)). The image content is
composed of Fedora packages under their respective upstream licenses and is not
covered by this repository's license.
