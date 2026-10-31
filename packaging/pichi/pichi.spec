# Source0 exports only the pinned packaging/pichi/src tree.
# Source1 contains the locked vendor tree and generated source map.

%bcond_with check

%global cargo_install_lib 0
%global cargo_install_bin 1
%global crate pichi

Name:           pichi
Version:        0.1.0
Release:        2%{?dist}
Summary:        Front-end for pichi VM images

License:        Apache-2.0 AND MIT AND Unicode-3.0 AND Zlib AND ISC AND BSD-3-Clause AND Unlicense AND BSL-1.0 AND CDLA-Permissive-2.0
URL:            https://github.com/pichi-vm/pichi
Source0:        %{crate}-%{version}.tar.gz
Source1:        %{crate}-%{version}-vendor.tar.xz

BuildRequires:  cargo-rpm-macros >= 26
BuildRequires:  rust >= 1.89
BuildRequires:  cmake
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  make
# Installing pichi also pulls in the dillo-vm VMM package.
Requires:       dillo-vm

ExclusiveArch:  x86_64 aarch64

%global _description %{expand:
Host CLI that manages pichi VM images as OCI artifacts and launches them.
This package does not ship guest images.}

%description %{_description}

%prep
# Source0 is already patch-applied by scripts/srpm.py before cargo vendor.
%autosetup -n %{crate}-%{version} -p1 -a1
# Keep upstream build settings and use Cargo's generated source map.
mkdir -p .cargo
cat cargo-vendor-config.toml >> .cargo/config.toml
mkdir -p target/rpm
ln -s rpm target/release
cat >> .cargo/config.toml << EOF

[profile.rpm]
inherits = "release"
opt-level = %{rustflags_opt_level}
codegen-units = %{rustflags_codegen_units}
debug = %{rustflags_debuginfo}
strip = "none"

[install]
root = "%{buildroot}%{_prefix}"
EOF

%build
export CARGO=/usr/bin/cargo
export RUSTC=%{__rustc}
export RUSTC_BOOTSTRAP=1
export RUSTC_BOOTSTRAP=1
export CARGO_NET_OFFLINE=true
%cargo_build -- --locked

%install
export CARGO=/usr/bin/cargo
export RUSTC=%{__rustc}
export RUSTC_BOOTSTRAP=1
export CARGO_NET_OFFLINE=true
%cargo_install -- --locked

%if %{with check}
%check
export RUSTC_BOOTSTRAP=1
export CARGO_NET_OFFLINE=true
%cargo_test -- --locked
%endif

%files
%license LICENSE
%doc README.md
%{_bindir}/pichi

%changelog
* Sat Oct 31 2026 Nathaniel McCallum <nathaniel.mccallum@amd.com> - 0.1.0-2
- Move Fedora packaging to the image repository with pinned source exports.

* Tue Oct 27 2026 Nathaniel McCallum <nathaniel@mccallum.life> - 0.1.0-1
- Add Copr packaging; vendor generated at SRPM time
