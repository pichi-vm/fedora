Name:           dillo-vm
Version:        0.1.0
Release:        4%{?dist}
Summary:        VMM that boots PMI files

License:        0BSD AND Apache-2.0 AND BSD-3-Clause AND MIT AND (Apache-2.0 OR BSD-3-Clause) AND (Apache-2.0 OR MIT) AND (BSD-2-Clause OR Apache-2.0 OR MIT) AND (MIT OR Apache-2.0) AND (Unlicense OR MIT)
URL:            https://github.com/pichi-vm/dillo
Source0:        %{name}-%{version}.tar.gz
ExclusiveArch:  x86_64 aarch64

BuildRequires:  gcc
BuildRequires:  git
BuildRequires:  rustup
Conflicts:      dillo

%description
VMM that boots PMI files.

%prep
%autosetup

%build
export RUSTUP_HOME="$PWD/.rustup"
export CARGO_HOME="$PWD/.cargo-home"
rustup-init -y --no-modify-path --profile minimal \
    --default-toolchain nightly-2026-07-06
export PATH="$CARGO_HOME/bin:$PATH"
cargo +nightly-2026-07-06 \
    --config 'unstable.bindeps=true' \
    --config 'env.SMOLTCP_IFACE_MAX_ADDR_COUNT="4"' \
    build --locked --release --bin dillo

%install
install -Dpm0755 target/release/dillo %{buildroot}%{_bindir}/dillo

# Preserve license and notice files from the fetched dependencies.
find .cargo-home -type f \( -iname 'license*' -o -iname 'licence*' -o \
    -iname 'copying*' -o -iname 'notice*' -o -iname 'copyright*' \) \
    -exec install -Dm0644 '{}' '%{buildroot}%{_licensedir}/%{name}/dependencies/{}' \;

%files
%license %{_licensedir}/%{name}/dependencies/
%license LICENSE
%license NOTICE
%{_bindir}/dillo
