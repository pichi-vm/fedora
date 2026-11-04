%global crate dillo

# src/lib.rs is an internal launch library, not a published crate.
# cargo package cannot repack this workspace (path + git deps, publish = false).
%global cargo_install_lib 0
%global cargo_install_bin 1

Name:           dillo-vm
Version:        0.1.0
Release:        2%{?dist}
Summary:        VMM that boots PMI files
# Fedora's Dillo web browser installs the same command.
Conflicts:      dillo
# Upstream sources are Apache-2.0; a few files are Apache-2.0 OR BSD-3-Clause
# (see NOTICE). The AND expression also covers statically linked crates.
License:        0BSD AND Apache-2.0 AND BSD-3-Clause AND MIT AND (Apache-2.0 OR BSD-3-Clause) AND (Apache-2.0 OR MIT) AND (BSD-2-Clause OR Apache-2.0 OR MIT) AND (MIT OR Apache-2.0) AND (Unlicense OR MIT)
URL:            https://github.com/pichi-vm/dillo
Source0:        %{name}-%{version}.tar.gz
Source1:        %{name}-%{version}-vendor.tar.xz
# Both host toolchains travel with the SRPM for offline native builds.
Source2:        dillo-toolchains.tar.xz

ExclusiveArch:  x86_64 aarch64

BuildRequires:  cargo-rpm-macros >= 26
BuildRequires:  rust >= 1.91
BuildRequires:  cargo >= 1.91
BuildRequires:  python3
BuildRequires:  gcc

%description
Dillo is a virtual machine monitor that boots PMI files. This package
installs the Linux host binary, which drives the guest through KVM.

%prep
%autosetup -n %{name}-%{version} -p1 -a1
tar -xf %{SOURCE2}
. ./rpm-cargo-setup %{rustflags_opt_level} %{rustflags_codegen_units} %{rustflags_debuginfo} %{buildroot}%{_prefix}

# Direct binaries from the upstream pinned toolchain, without rustup/network.
%global __cargo /usr/bin/env CARGO_HOME=.cargo RUSTC_BOOTSTRAP=1 RUSTFLAGS='%{build_rustflags} --sysroot=%{_builddir}/%{?buildsubdir}/toolchains/%{_arch}-unknown-linux-gnu' %{_builddir}/%{?buildsubdir}/toolchains/%{_arch}-unknown-linux-gnu/bin/cargo
%global __rustc %{_builddir}/%{?buildsubdir}/toolchains/%{_arch}-unknown-linux-gnu/bin/rustc

%build
export RUSTC="%{__rustc}"
export CARGO="$PWD/toolchains/%{_arch}-unknown-linux-gnu/bin/cargo"
export PATH="$PWD/toolchains/%{_arch}-unknown-linux-gnu/bin:$PATH"
export CARGO_NET_OFFLINE=true
export RUSTC_BOOTSTRAP=1
# The virtio-net backend needs four interface addresses.
export SMOLTCP_IFACE_MAX_ADDR_COUNT=4
%cargo_build -- --locked
%{cargo_license_summary}
%{cargo_license} > LICENSE.dependencies
# License expressions are not a cargo-vendor.txt dependency manifest.
python3 - <<'PYCODE' > LICENSE.vendor-crates
import pathlib, tomllib
for path in sorted(pathlib.Path('vendor').glob('*/Cargo.toml')):
    package = tomllib.loads(path.read_text())['package']
    print(package['name'], package['version'], package.get('license', 'SEE LICENSE'))
PYCODE

%install
install -Dpm0755 target/rpm/dillo %{buildroot}%{_bindir}/dillo

%files
%license LICENSE
%license NOTICE
%license LICENSE.dependencies
%license LICENSE.vendor-crates
%{_bindir}/dillo

%changelog
* Sat Oct 31 2026 Nathaniel McCallum <nathaniel.mccallum@amd.com> - 0.1.0-2
- Move Fedora packaging to the image repository with pinned source exports.

* Tue Oct 27 2026 Nathaniel McCallum <nathaniel@mccallum.life> - 0.1.0-1
- Package the dillo VMM as dillo-vm. Vendor Cargo.lock when building the SRPM.
