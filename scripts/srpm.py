#!/usr/bin/env python3
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Export one pinned source, vendor it, and build its SRPM."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), cwd=cwd, check=True, **kwargs)


def export(repo, pin, destination):
    destination.mkdir(parents=True, exist_ok=True)
    # Archive the recorded commit, including recursively recorded gitlinks.
    with tempfile.TemporaryFile() as stream:
        run('git', '-C', repo, 'archive', pin, stdout=stream)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            archive.extractall(destination, filter='data')
    tree = subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-rz', pin])
    for entry in tree.split(b'\0'):
        if entry.startswith(b'160000 '):
            metadata, path = entry.split(b'\t')
            export(repo / path.decode(), metadata.split()[2].decode(), destination / path.decode())


def pack(directory, output, paths, epoch):
    # GNU tar preserves vendored dotfiles/checksums, normalizing metadata only.
    run('tar', '--sort=name', f'--mtime=@{epoch}', '--owner=0', '--group=0',
        '--numeric-owner', '-C', directory,
        '-cJf' if str(output).endswith('.xz') else '-czf', output, *paths,
        env={**os.environ, 'XZ_OPT': '-T2 -3', 'GZIP': '-n'})


def prepare(project, out):
    assets = ROOT / 'packaging' / project
    repo = assets / 'src'
    pin = subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', f'HEAD:packaging/{project}/src'], text=True).strip()
    version, release = subprocess.check_output(
        ['rpmspec', '-q', '--srpm', '--qf', '%{VERSION} %{RELEASE}',
         str(assets / f'{project}.spec')], text=True).split()
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != pin:
        raise ValueError(f'{project}: initialize the recorded submodule first')
    epoch = subprocess.check_output(['git', '-C', str(repo), 'show', '-s', '--format=%ct', pin], text=True).strip()
    name = 'dillo-vm' if project == 'dillo' else project
    stem = f'{name}-{version}'
    with tempfile.TemporaryDirectory(prefix=f'{project}-srpm-') as temporary:
        work = Path(temporary)
        src = work / stem
        export(repo, pin, src)
        (src / 'packaging').mkdir(exist_ok=True)
        for asset in assets.iterdir():
            if not asset.is_file():
                continue
            shutil.copy2(asset, src / 'packaging' / asset.name)
        (src / '.cargo').mkdir(exist_ok=True)
        if project == 'dillo' and not (src / '.cargo/config.toml').exists():
            (src / '.cargo/config.toml').write_text(
                '[unstable]\nbindeps = true\n'
                '[target.x86_64-unknown-linux-musl]\n'
                'rustflags = ["-C", "relocation-model=static", "-C", "linker=rust-lld"]\n'
                '[target.aarch64-unknown-linux-musl]\n'
                'rustflags = ["-C", "relocation-model=static", "-C", "linker=rust-lld"]\n'
                '[env]\nSMOLTCP_IFACE_MAX_ADDR_COUNT = "4"\n')
        env = {**os.environ, 'RUSTC_BOOTSTRAP': '1', 'CARGO_NET_GIT_FETCH_WITH_CLI': 'true'}
        if project == 'pichi':
            run('patch', '-p1', '-i', assets / 'rpm-manifest.patch', cwd=src)
            before = tomllib.loads((src / 'Cargo.lock').read_text())['package']
            run('cargo', 'update', '--workspace', cwd=src, env=env)
            after = tomllib.loads((src / 'Cargo.lock').read_text())['package']
            def pins(packages):
                return {tuple(p.get(k) for k in ('name', 'version', 'source', 'checksum')) for p in packages}
            if not pins(after) <= pins(before):
                raise ValueError('host patch introduced new dependency pins')
        with (src / 'cargo-vendor-config.toml').open('w') as config:
            run('cargo', 'vendor', '--locked', '--versioned-dirs', 'vendor', cwd=src, env=env, stdout=config)
        # Source replacements must resolve relative to the unpacked source tree.
        config = src / 'cargo-vendor-config.toml'
        config.write_text(config.read_text().replace(str(src / 'vendor'), 'vendor'))
        # RPM expands its build flags before sourcing this shared prep fragment.
        (src / 'rpm-cargo-setup').write_text('''mkdir -p .cargo target/rpm
ln -s rpm target/release
cat cargo-vendor-config.toml >> .cargo/config.toml
cat >> .cargo/config.toml <<EOF

[profile.rpm]
inherits = "release"
opt-level = $1
codegen-units = $2
debug = $3
strip = "none"

[install]
root = "$4"
EOF
''')
        pack(src, out / f'{stem}-vendor.tar.xz', ['vendor'], epoch)
        shutil.rmtree(src / 'vendor')
        pack(work, out / f'{stem}.tar.gz', [stem], epoch)
        if project == 'dillo':
            channel = tomllib.loads((src / 'rust-toolchain.toml').read_text())['toolchain']['channel']
            # Carry both minimal host toolchains; Copr binary builds are offline.
            toolroot = work / 'toolchains'
            toolroot.mkdir()
            for arch in ('x86_64', 'aarch64'):
                host = f'{arch}-unknown-linux-gnu'
                toolenv = {**os.environ, 'RUSTUP_HOME': str(work / 'rustup'),
                           'CARGO_HOME': str(work / 'cargo'), 'RUSTUP_NO_UPDATE_CHECK': '1'}
                run('rustup', 'set', 'auto-self-update', 'disable', env=toolenv)
                run('rustup', 'toolchain', 'install', f'{channel}-{host}', '--profile', 'minimal', '--force-non-host', env=toolenv)
                shutil.copytree(work / f'rustup/toolchains/{channel}-{host}', toolroot / host, symlinks=True)
            pack(work, out / 'dillo-toolchains.tar.xz', ['toolchains'], epoch)
    run('rpmbuild', '-bs', assets / f'{project}.spec', '--define', f'_sourcedir {out}',
        '--define', f'_srcrpmdir {out}', '--define', f'_topdir {out}/rpm',
        '--define', '_disable_source_fetch 1')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', choices=('corium', 'arma', 'dillo', 'pichi'))
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if list(args.out.glob('*.src.rpm')):
        parser.error('--out contains a source package')
    prepare(args.project, args.out)
