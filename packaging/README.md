# Fedora packages

This repository owns RPMs, Fedora's installable software packages, for
corium, arma, dillo-vm and pichi. Each package folder contains a spec,
the build instructions, and a Git submodule, a linked source repository,
at `packaging/<project>/src`. Exact source commits appear in
`packaging/versions.json`, the ledger that records each package version
and source pin, the selected commit identifier.

Run `git submodule update --init --recursive` to populate sources.
`python3 scripts/srpm.py corium --out /tmp/srpm-corium` builds an SRPM,
a source package containing code and instructions for the binary build.
Preparation exports the selected source commit into a temporary folder.
Vendoring, copying dependencies into the source package, follows the
locked dependency list. Binary builds require no network access.

Preparation needs Python 3.12+, Git, patch, GNU tar, xz, gzip, rpmbuild,
and Cargo, Rust's build tool, installed through rustup, its toolchain
installer. Dillo's toolchain, the compiler and related tools, comes from
its `rust-toolchain.toml`. Both supported processor toolchains travel in
the SRPM. Its general Cargo configuration comes from the source repository.
Pichi's host manifest patch selects the host program and rejects dependency
pin additions. Corium, Arma and Pichi use Fedora's Rust for binary builds.

A source pin change requires a higher Version and Release 1. Version
cannot change at the same pin. A packaging repair can increase Release
without changing Version or pin. Edit both the spec and ledger. Check
with `python3 scripts/versions.py --base origin/main` and
`python3 -m unittest discover -s tests -v`.

Copr, Fedora's build service, uses Git source builds with method
`make_srpm`. Configure each package with clone URL
`https://github.com/pichi-vm/fedora`, committish (selected branch) `main`,
subdirectory `packaging/<project>`, spec `<project>.spec`, and
`auto_rebuild` enabled. The package named dillo-vm uses project `dillo`.
The root `.copr/Makefile` receives absolute `spec` and `outdir` paths.
It installs preparation tools using dnf, Fedora's package installer,
installs Rust through rustup, populates that package's submodule, and
builds its SRPM into `outdir`. `PREPARED=1` uses developer-supplied tools.

GitHub push notifications select packages whose folders contain changed
files. A submodule change touches `packaging/<project>/src` and qualifies.
The ledger check requires a version increase for all four packages when
any file under `scripts/` or `.copr/`, `packaging/versions.json`,
`.gitmodules`, or `.github/workflows/packaging.yml` is edited. At the same
source pin and Version, increase each spec's Release and ledger entry.
A source pin increase with a higher Version and Release 1 also qualifies.
Even an edit to one ledger entry selects this shared-input rule. Inputs
inside a package folder follow the source/version rules above. Documentation,
tests, image inputs and unrelated workflows do not select this rule.
Without a base ledger, validation checks the complete package record.
Publishing uses no key. Publishing starts once the infrastructure team
points the four Copr packages at these settings and turns off the source
repository builds. Use Fedora 43, 44, 45 and rawhide, the development
release, on x86_64 and aarch64, the two supported processor types.

The separate CI, automated check, workflow builds all packages on those
releases and processors. Dillo installs to `/usr/bin/dillo`; a follow-up
change moves it to `/usr/libexec/pichi/dillo` once Pichi knows that path.
There is no `Conflicts: dillo` declaration by maintainer decision.
Dillo-vm and Fedora's Dillo web browser both ship `/usr/bin/dillo`.
