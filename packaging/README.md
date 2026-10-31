# Fedora packages

This repository owns RPMs for corium, arma, dillo-vm and pichi, with pinned
sources at `packaging/<project>/src` and Version/Release in each spec.
Bump Release by hand for packaging fixes. Initialize sources with
`git submodule update --init --recursive`.

Run `make -f .copr/Makefile srpm spec="$PWD/packaging/corium/corium.spec"
outdir="$PWD/srpm-corium"` (on one line). Preparation needs dnf and make;
`PREPARED=1` uses installed Git, Python 3.12+, patch, tar, xz, gzip,
rpmbuild and rustup/Cargo. SRPMs vendor locked crates and Dillo's pinned
nightly toolchains for offline rebuilds. This repository generates Dillo's
Cargo settings; Pichi's manifest patch forbids new dependency pins.

Copr builds each package from main only, with no PR builds. Set Git source
method `make_srpm`, clone URL `https://github.com/pichi-vm/fedora`,
committish `main`, subdirectory `packaging/<project>`, spec `<project>.spec`,
and `auto_rebuild` for main. Disable source-repository builds. dillo-vm uses
project `dillo`. Targets: Fedora 43/44/45/rawhide on x86_64/aarch64.

The PR-only workflow selects changed package folders; shared scripts,
Copr glue, submodule configuration or the workflow select all packages.
It rebuilds offline and installs RPMs for every target; Pichi jobs also
build dillo-vm for its dependency. The required check is `packages`.

Dillo installs `/usr/bin/dillo`, where pichi finds it on PATH. dillo-vm
conflicts with Fedora's unrelated Dillo browser, which owns the same path.
