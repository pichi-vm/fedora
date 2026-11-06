%global cargo_install_lib 0
%global cargo_install_bin 1

%global crate corium
%global build_rustflags %{build_rustflags} -C target-feature=+crt-static

Name:           corium
Version:        0.2.0
Release:        3%{?dist}
Summary:        Minimal initramfs init: mount a read-only Carapace root and execute /sbin/init

# Effective license of the linked binary (this crate plus bundled runtime
# crates). From cargo tree --edges no-build,no-dev,no-proc-macro.
License:        Apache-2.0 AND (Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT) AND (BSD-2-Clause OR Apache-2.0 OR MIT) AND (MIT OR Apache-2.0)
URL:            https://github.com/pichi-vm/corium
Source0:        %{crate}-%{version}.tar.gz
Source1:        %{crate}-%{version}-vendor.tar.xz

BuildRequires:  cargo-rpm-macros >= 26
BuildRequires:  rust >= 1.89
BuildRequires:  glibc-static
BuildRequires:  gcc
BuildRequires:  binutils
ExclusiveArch:  x86_64 aarch64

# Bundled runtime crates, excluding this source tree.
Provides:       bundled(crate(bitflags)) = 2.13.2
Provides:       bundled(crate(carapace)) = 0.1.0
Provides:       bundled(crate(crc)) = 3.4.0
Provides:       bundled(crate(crc-catalog)) = 2.5.0
Provides:       bundled(crate(devmap-core)) = 0.1.0
Provides:       bundled(crate(devmap-linux)) = 0.1.0
Provides:       bundled(crate(devmap-snapshot)) = 0.1.0
Provides:       bundled(crate(devmap-verity)) = 0.1.0
Provides:       bundled(crate(iocuddle)) = 0.4.0
Provides:       bundled(crate(linux-raw-sys)) = 0.12.1
Provides:       bundled(crate(log)) = 0.4.34
Provides:       bundled(crate(rustix)) = 1.1.5
Provides:       bundled(crate(uuid)) = 1.29.0
Provides:       bundled(crate(zerocopy)) = 0.8.63

%description
Minimal initramfs init: mount a read-only Carapace root and execute
/sbin/init.

%files
%doc package-source.json
%license LICENSE
%license LICENSE.dependencies
%doc CONTRIBUTING.md
%doc README.md
%{_bindir}/%{crate}

%prep
%autosetup -n %{crate}-%{version} -p1 -a1
. ./rpm-cargo-setup %{rustflags_opt_level} %{rustflags_codegen_units} %{rustflags_debuginfo} %{buildroot}%{_prefix}

%build
export CARGO=/usr/bin/cargo
export RUSTC=%{__rustc}
export RUSTC_BOOTSTRAP=1
export CARGO_NET_OFFLINE=true
%cargo_build -- --locked
%{cargo_license_summary}
%{cargo_license} > LICENSE.dependencies

%install
export CARGO=/usr/bin/cargo
export RUSTC=%{__rustc}
export CARGO_NET_OFFLINE=true
%cargo_install -- --locked

%check
# PID 1 must run before any shared libraries are mounted.
readelf -l target/rpm/corium > program-headers.txt
readelf -d target/rpm/corium > dynamic-section.txt
! grep -q INTERP program-headers.txt
! grep -q NEEDED dynamic-section.txt

%changelog
* Sat Oct 31 2026 Nathaniel McCallum <nathaniel.mccallum@amd.com> - 0.2.0-2
- Move Fedora packaging to the image repository with pinned source exports.

* Tue Oct 27 2026 Nathaniel McCallum <nathaniel@mccallum.life> - 0.2.0-1
- Add Copr packaging with vendored crates
