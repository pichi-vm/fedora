# Source0 exports only the pinned packaging/arma/src tree.
# Source1 contains the locked vendor tree and generated source map.

%bcond_with check

# Keep crate sources out of the payload. arma ships one binary.
%global cargo_install_lib 0
%global cargo_install_bin 1

# No -Wl package note. See the header comment.
%global _package_note_status 0
%global build_rustflags -Copt-level=3 -Cdebuginfo=2 -Ccodegen-units=1 -Cstrip=none -Cforce-frame-pointers=yes

%global crate arma

Name:           arma
Version:        0.1.0
Release:        2%{?dist}
Summary:        PMI builder for pichi-vm

# Linked crates are Apache-2.0, MIT, or a dual license that offers one
# of those (0BSD, BSD-2-Clause, BSD-3-Clause, Unlicense, Zlib).
License:        Apache-2.0 AND MIT
URL:            https://github.com/pichi-vm/arma
Source0:        %{crate}-%{version}.tar.gz
Source1:        %{crate}-%{version}-vendor.tar.xz

# tatu is built for the host arch's bare-metal target. Other arches
# have no artifact dependency in Cargo.toml.
ExclusiveArch:  x86_64 aarch64

%ifarch x86_64
%global tatu_target x86_64-unknown-none
%endif
%ifarch aarch64
%global tatu_target aarch64-unknown-none-softfloat
%endif

BuildRequires:  rust >= 1.88
BuildRequires:  cargo

# Cargo macros must be available before %%prep runs.
BuildRequires:  cargo-rpm-macros >= 26

# Crates linked into the binary. Path members (tatu, dtb2acpi,
# dtb2e820) are this source tree, not bundled third-party crates.
# Regenerate from:
#   cargo tree -p arma --edges no-build,no-dev,no-proc-macro \
#     --prefix none --format '{p}'
Provides:       bundled(crate(adler2)) = 2.0.1
Provides:       bundled(crate(aho-corasick)) = 1.1.5
Provides:       bundled(crate(anstream)) = 1.0.0
Provides:       bundled(crate(anstyle)) = 1.0.14
Provides:       bundled(crate(anstyle-parse)) = 1.0.0
Provides:       bundled(crate(anstyle-query)) = 1.1.5
Provides:       bundled(crate(anyhow)) = 1.0.104
Provides:       bundled(crate(arrayvec)) = 0.7.8
Provides:       bundled(crate(block-buffer)) = 0.12.1
Provides:       bundled(crate(cfg-if)) = 1.0.5
Provides:       bundled(crate(ciborium)) = 0.2.2
Provides:       bundled(crate(ciborium-io)) = 0.2.2
Provides:       bundled(crate(ciborium-ll)) = 0.2.2
Provides:       bundled(crate(clap)) = 4.6.7
Provides:       bundled(crate(clap_builder)) = 4.6.7
Provides:       bundled(crate(clap_lex)) = 1.1.1
Provides:       bundled(crate(colorchoice)) = 1.0.5
Provides:       bundled(crate(const-oid)) = 0.10.2
Provides:       bundled(crate(cpufeatures)) = 0.3.1
Provides:       bundled(crate(crc32fast)) = 1.5.3
Provides:       bundled(crate(crypto-common)) = 0.2.2
Provides:       bundled(crate(devtree)) = 0.1.0
Provides:       bundled(crate(digest)) = 0.11.3
Provides:       bundled(crate(flate2)) = 1.1.10
Provides:       bundled(crate(goblin)) = 0.10.7
Provides:       bundled(crate(half)) = 2.7.1
Provides:       bundled(crate(hybrid-array)) = 0.4.15
Provides:       bundled(crate(is_terminal_polyfill)) = 1.70.2
Provides:       bundled(crate(log)) = 0.4.34
Provides:       bundled(crate(lzma-rust2)) = 0.24.0
Provides:       bundled(crate(memchr)) = 2.8.3
Provides:       bundled(crate(miniz_oxide)) = 0.9.1
Provides:       bundled(crate(plain)) = 0.2.3
Provides:       bundled(crate(pmi)) = 0.1.0
Provides:       bundled(crate(regex)) = 1.13.1
Provides:       bundled(crate(regex-automata)) = 0.4.18
Provides:       bundled(crate(regex-syntax)) = 0.8.11
Provides:       bundled(crate(ruzstd)) = 0.9.1
Provides:       bundled(crate(scroll)) = 0.13.0
Provides:       bundled(crate(serde)) = 1.0.229
Provides:       bundled(crate(serde_core)) = 1.0.229
Provides:       bundled(crate(sha2)) = 0.11.1
Provides:       bundled(crate(simd-adler32)) = 0.3.10
Provides:       bundled(crate(strsim)) = 0.11.1
Provides:       bundled(crate(thiserror)) = 2.0.21
Provides:       bundled(crate(twox-hash)) = 2.1.5
Provides:       bundled(crate(typenum)) = 1.20.1
Provides:       bundled(crate(utf8parse)) = 0.2.2
Provides:       bundled(crate(vm-fdt)) = 0.3.0
Provides:       bundled(crate(zerocopy)) = 0.8.63

%global _description %{expand:
Build a Portable Machine Image from a kernel, optional initrd, and
command line. The tatu boot stub is compiled with arma and stored
inside the arma binary.}

%description %{_description}

%prep
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

%generate_buildrequires
# Fedora supplies prebuilt core for both bare-metal tatu targets:
# x86_64-unknown-none and aarch64-unknown-none-softfloat.
echo "rust-std-static-%{tatu_target}"
echo "lld"

%build
export CARGO=/usr/bin/cargo
export RUSTC=%{__rustc}
export RUSTC_BOOTSTRAP=1
# Use -- to pass Cargo flags through the RPM macros.
export RUSTC_BOOTSTRAP=1
export CARGO_NET_OFFLINE=true
%cargo_build -- --locked

%install
export CARGO=/usr/bin/cargo
export RUSTC=%{__rustc}
export RUSTC_BOOTSTRAP=1
export CARGO_NET_OFFLINE=true
%cargo_install -- --locked

# Tests fetch kernels through burrow. Copr %%build has no network.
%if %{with check}
%check
export RUSTC_BOOTSTRAP=1
%cargo_test -- --locked
%endif

%files
%license LICENSE
%doc README.md
%{_bindir}/arma

%changelog
* Sat Oct 31 2026 Nathaniel McCallum <nathaniel.mccallum@amd.com> - 0.1.0-2
- Move Fedora packaging to the image repository with pinned source exports.

* Tue Oct 27 2026 Nathaniel McCallum <nathaniel@mccallum.life> - 0.1.0-1
- Initial host package for Copr.
