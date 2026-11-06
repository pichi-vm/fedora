#!/usr/bin/env python3
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Resolve exact COPR packages before image jobs acquire native runners."""
import argparse
import base64
import configparser
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from srpm import ROOT, package_identity

API = 'https://copr.fedorainfracloud.org/api_3/'
OWNER = 'npmccallum'
PACKAGES = ('corium', 'arma', 'dillo', 'pichi')
ARCHES = ('x86_64', 'aarch64')
FAILED = {'failed', 'canceled', 'skipped', 'forked', 'importing'}


class Copr:
    def __init__(self, project, config=None):
        if project not in ('pichi', 'pichi-staging'):
            raise ValueError('Unknown COPR project')
        self.project = project
        self.authorization = None
        if config:
            settings = configparser.ConfigParser(interpolation=None)
            settings.read(config)
            credentials = settings['copr-cli']
            if credentials['copr_url'].rstrip('/') != API.removesuffix('/api_3/'):
                raise ValueError('Unexpected COPR server')
            self.authorization = 'Basic ' + base64.b64encode(
                f"{credentials['login']}:{credentials['token']}".encode()).decode()

    def request(self, endpoint, data=None):
        headers = {'Accept': 'application/json'}
        if data is not None:
            if not self.authorization:
                raise RuntimeError('Submission requires a COPR config')
            headers.update({'Authorization': self.authorization, 'Content-Type': 'application/json'})
        request = urllib.request.Request(
            API + endpoint, headers=headers,
            data=None if data is None else json.dumps(data).encode())
        # Never retry POST automatically: a lost response may still create a build.
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    def find(self, package, identity, revision):
        name = 'dillo-vm' if package == 'dillo' else package
        offset = 0
        while True:
            # SCM submissions are not associated with a package name until
            # their SRPM exists. Include unnamed source builds in this query.
            query = urllib.parse.urlencode(dict(ownername=OWNER, projectname=self.project,
                                                limit=100, offset=offset))
            builds = self.request('build/list?' + query)['items']
            for build in builds:
                version = (build.get('source_package') or {}).get('version') or ''
                if (build['state'] not in FAILED
                        and (build.get('source_package') or {}).get('name') == name
                        and version.endswith('.g' + identity[:16])):
                    if all(f'fedora-43-{arch}' in build['chroots'] for arch in ARCHES):
                        return build['id']
                elif build['state'] not in FAILED | {'succeeded'}:
                    source = self.request(f"build/source-build-config/{build['id']}")['source_dict']
                    if (source.get('subdirectory') == f'packaging/{package}'
                            and source.get('clone_url', '').removesuffix('.git')
                            == 'https://github.com/pichi-vm/fedora'
                            and all(f'fedora-43-{arch}' in build['chroots'] for arch in ARCHES)):
                        commit = source.get('committish', '')
                        if commit == revision or self.input_at(package, commit) == identity:
                            return build['id']
            if len(builds) < 100:
                return None
            offset += len(builds)

    @staticmethod
    def input_at(package, commit):
        # A PR merge commit or image-only update may share all package inputs
        # with a source build already running. Inspect local fetched history;
        # never resolve a moving branch name as an immutable build identity.
        if not re.fullmatch('[0-9a-f]{40}', commit):
            return None
        result = subprocess.run([
            'git', '-C', ROOT, 'ls-tree', '-rz', commit, '--', '.copr',
            'scripts/srpm.py', '.gitmodules', f'packaging/{package}', f'sources/{package}'],
            capture_output=True)
        return hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None

    def submit(self, package, revision):
        return self.request('build/create/scm', {
            'ownername': OWNER, 'projectname': self.project,
            'clone_url': 'https://github.com/pichi-vm/fedora.git',
            'committish': revision, 'subdirectory': f'packaging/{package}',
            'spec': f'{package}.spec', 'scm_type': 'git', 'source_build_method': 'make_srpm',
            'chroots': [f'fedora-43-{arch}' for arch in ARCHES], 'enable_net': False,
        })['id']

    def configure_sources(self):
        """Retire application-repository triggers after central packaging lands."""
        query = urllib.parse.urlencode(dict(ownername=OWNER, projectname=self.project))
        existing = {package['name']: package
                    for package in self.request('package/list?' + query)['items']}
        for package in (*PACKAGES, 'madrillo'):
            name = 'dillo-vm' if package == 'dillo' else package
            desired = {'package_name': name, 'type': 'git',
                       'clone_url': 'https://github.com/pichi-vm/fedora.git',
                       'committish': 'main', 'subdirectory': f'packaging/{package}',
                       'spec': f'{package}.spec', 'source_build_method': 'make_srpm',
                       'webhook_rebuild': False}
            current = existing.get(name)
            if current and not current['auto_rebuild'] and all(
                    current['source_dict'].get(key) == value for key, value in desired.items()
                    if key not in ('package_name', 'webhook_rebuild')):
                continue
            action = 'edit' if current else 'add'
            self.request(f'package/{action}/{OWNER}/{self.project}/{name}/scm', desired)

    def resolve(self, output, submit=False, timeout=5400):
        if submit:
            self.configure_sources()
        revision = subprocess.check_output(['git', '-C', ROOT, 'rev-parse', 'HEAD'], text=True).strip()
        identities = {package: package_identity(package) for package in PACKAGES}
        key = ROOT / 'keys' / f'{self.project}.asc'
        key_sha256 = hashlib.sha256(key.read_bytes()).hexdigest()
        set_id = hashlib.sha256(json.dumps(
            {'project': self.project, 'inputs': identities, 'key': key_sha256},
            sort_keys=True).encode()).hexdigest()
        output.mkdir(parents=True, exist_ok=True)
        lockfile = output / 'packages.lock.json'
        try:
            fetch('https://github.com/pichi-vm/fedora/releases/download/'
                  f'rpms-{set_id}/packages.lock.json', lockfile, attempts=1)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        else:
            archived = json.loads(lockfile.read_text())
            if (archived['inputs'] != identities or archived['project'] != self.project
                    or archived['set'] != set_id or archived['key_sha256'] != key_sha256):
                raise ValueError('Archived package set does not match selected inputs')
            for arch in ARCHES:
                download(lockfile, output, arch, PACKAGES)
            print(f'Reused archived package set {set_id}', flush=True)
            return
        builds, missing = {}, []
        for package, identity in identities.items():
            build = self.find(package, identity, revision)
            if build is None and submit:
                build = self.submit(package, revision)
            if build is None:
                missing.append(package)
            else:
                builds[package] = build
                print(f'{package}: COPR build {build}', flush=True)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'builds.json').write_text(json.dumps(builds, indent=2) + '\n')
        if missing:
            raise RuntimeError('Missing qualified package inputs: ' + ', '.join(missing)
                               + '. Dispatch the staging workflow for this exact commit.')
        deadline = time.monotonic() + timeout
        pending = dict(builds)
        failures = {}
        while pending:
            for package, build in list(pending.items()):
                state = self.request(f'build/{build}')['state']
                print(f'{package} {build}: {state}', flush=True)
                if state == 'succeeded' or state in FAILED:
                    del pending[package]
                    if state != 'succeeded':
                        failures[package] = state
            if pending:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'COPR builds still active: {pending}')
                time.sleep(45)
        if failures:
            raise RuntimeError(f'COPR package failures: {failures}')
        result = {'version': 1, 'project': self.project, 'inputs': identities, 'packages': {}}
        result['key_sha256'] = key_sha256
        result['set'] = set_id
        for package, build in builds.items():
            name = 'dillo-vm' if package == 'dillo' else package
            source = self.request(f'build/source-build-config/{build}')['source_dict']
            available = self.request(f'build/built-packages/{build}')
            result['packages'][package] = {
                'build': build, 'revision': source['committish'], 'rpms': {},
                'source': subprocess.check_output(
                    ['git', '-C', ROOT, 'rev-parse', f'HEAD:sources/{package}'], text=True).strip(),
            }
            for arch in ARCHES:
                chroot = f'fedora-43-{arch}'
                status = self.request(f'build-chroot?build_id={build}&chrootname={chroot}')
                if status['state'] != 'succeeded':
                    raise RuntimeError(f'{build}/{chroot} did not succeed')
                matches = [rpm for rpm in available[chroot]['packages']
                           if rpm['name'] == name and rpm['arch'] == arch]
                if len(matches) != 1:
                    raise RuntimeError(f'Expected exactly one {name}/{arch} RPM')
                rpm = matches[0]
                if not rpm['release'].endswith(f".g{identities[package][:16]}.fc43"):
                    raise RuntimeError(f'Package inputs do not match {build}/{chroot}')
                filename = f"{name}-{rpm['version']}-{rpm['release']}.{arch}.rpm"
                url = status['result_url'].rstrip('/') + '/' + filename
                path = output / filename
                fetch(url, path)
                verify(path, key)
                result['packages'][package]['rpms'][arch] = {
                    'filename': filename, 'url': url,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'archive_url': ('https://github.com/pichi-vm/fedora/releases/download/'
                                    f"rpms-{result['set']}/{filename}"),
                }
        (output / 'packages.lock.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


def fetch(url, destination, attempts=6):
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('Package URLs must use HTTPS')
    # COPR may finish before its download endpoint is ready. Retry GET only.
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as source, destination.open('wb') as target:
                while block := source.read(1024 * 1024):
                    target.write(block)
            return
        except (urllib.error.HTTPError, urllib.error.URLError):
            destination.unlink(missing_ok=True)
            if attempt == attempts - 1:
                raise
            time.sleep(10)


def verify(path, key):
    with tempfile.TemporaryDirectory() as db:
        subprocess.run(['rpmkeys', '--dbpath', db, '--import', key], check=True)
        result = subprocess.run(['rpmkeys', '--dbpath', db, '--checksig', '--verbose', path],
                                check=True, text=True, capture_output=True)
        if not re.search(r'signature.*: OK', result.stdout, re.I):
            raise RuntimeError(f'{path.name} has no verified RPM signature')


def download(lockfile, output, arch, packages):
    lock = json.loads(lockfile.read_text())
    if lock['project'] not in ('pichi', 'pichi-staging') or arch not in ARCHES:
        raise ValueError('Unexpected package project or architecture')
    key = ROOT / 'keys' / f"{lock['project']}.asc"
    if hashlib.sha256(key.read_bytes()).hexdigest() != lock['key_sha256']:
        raise ValueError('Signing key does not match package lock')
    output.mkdir(parents=True, exist_ok=True)
    for package in packages:
        rpm = lock['packages'][package]['rpms'][arch]
        if Path(rpm['filename']).name != rpm['filename'] or not rpm['filename'].endswith('.rpm'):
            raise ValueError('Invalid RPM filename')
        target = output / rpm['filename']
        if not target.exists():
            try:
                # Archived published inputs survive COPR pruning.
                fetch(rpm['archive_url'], target, attempts=1)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                fetch(rpm['url'], target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != rpm['sha256']:
            raise ValueError(f'Checksum mismatch: {target.name}')
        verify(target, key)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    resolve = commands.add_parser('resolve')
    resolve.add_argument('--project', choices=('pichi', 'pichi-staging'), default='pichi-staging')
    resolve.add_argument('--config', type=Path)
    resolve.add_argument('--submit', action='store_true')
    resolve.add_argument('--out', type=Path, required=True)
    get = commands.add_parser('download')
    get.add_argument('--lock', type=Path, default=Path('packages.lock.json'))
    get.add_argument('--out', type=Path, required=True)
    get.add_argument('--arch', choices=ARCHES, required=True)
    get.add_argument('--packages', nargs='+', choices=PACKAGES, default=list(PACKAGES))
    args = parser.parse_args()
    if args.command == 'resolve':
        Copr(args.project, args.config).resolve(args.out, args.submit)
    else:
        download(args.lock, args.out, args.arch, args.packages)
