#!/usr/bin/env python3
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Check the package ledger against Git and a prior revision."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECTS = ('corium', 'arma', 'dillo', 'pichi')
ROOT = Path(__file__).resolve().parents[1]

# Source preparation reads the ledger and submodule URLs. The packaging
# workflow supplies tools and binary build commands. Treat each of these
# shared files, and every script/Copr entry point, as affecting all packages.
# Even a single ledger entry edit therefore requires all four version bumps.
# Package-specific inputs belong under packaging/<project>/; they do not
# trigger this shared-input rule. Documentation, tests, license-check config,
# image inputs and unrelated workflows do not affect package build contents.
SHARED_BUILD_FILES = frozenset((
    'packaging/versions.json', '.gitmodules', '.github/workflows/packaging.yml',
))
SHARED_BUILD_PREFIXES = ('scripts/', '.copr/')


def affected_packages(paths):
    return PROJECTS if any(path in SHARED_BUILD_FILES or
                           path.startswith(SHARED_BUILD_PREFIXES)
                           for path in paths) else ()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def number(value):
    if not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*', value):
        raise ValueError(f'expected a numeric dotted version: {value}')
    return tuple(map(int, value.split('.')))


def compare(old, new, paths=()):
    """Enforce source/version pairs and shared-input package revisions."""
    for project in PROJECTS:
        before, after = old[project], new[project]
        changed = before['pin'] != after['pin']
        left = number(before['version'])
        right = number(after['version'])
        release = int(after['release'])
        if changed and right <= left:
            raise ValueError(f'{project}: a new pin requires a higher Version')
        if not changed and right != left:
            raise ValueError(f'{project}: Version changed without a pin bump')
        if right != left and release != 1:
            raise ValueError(f'{project}: Release must reset to 1 on a Version bump')
        if right == left and release < int(before['release']):
            raise ValueError(f'{project}: Release cannot decrease at the same Version')

    missing = [project for project in affected_packages(paths)
               if number(new[project]['version']) == number(old[project]['version'])
               and int(new[project]['release']) <= int(old[project]['release'])]
    if missing:
        raise ValueError('shared packaging inputs require a higher Version or Release for: '
                         + ', '.join(missing))


def validate(ledger, pins, specs):
    if set(ledger) != set(PROJECTS):
        raise ValueError('ledger must contain exactly the four packages')
    for project in PROJECTS:
        entry = ledger[project]
        if entry['source'] != f'packaging/{project}/src':
            raise ValueError(f'{project}: ledger source path differs from package layout')
        if entry['pin'] != pins[project] or not re.fullmatch('[0-9a-f]{40}', entry['pin']):
            raise ValueError(f'{project}: ledger pin differs from the Git submodule')
        version, release = specs[project]
        if (entry['version'], entry['release']) != (version, release):
            raise ValueError(f'{project}: spec version-release differs from ledger')
        number(version)
        if not release.isdigit() or int(release) < 1:
            raise ValueError(f'{project}: Release must be a positive integer')


def changed_packages(old, new):
    """Select new packages and Version/Release updates for publication."""
    return [project for project in PROJECTS
            if project not in old or any(old[project][field] != new[project][field]
                                         for field in ('version', 'release'))]


def check(base):
    ledger = json.loads((ROOT / 'packaging/versions.json').read_text())
    pins, specs = {}, {}
    for project in PROJECTS:
        line = git('ls-files', '--stage', f'packaging/{project}/src').split()
        if not line or line[0] != '160000':
            raise ValueError(f'{project}: missing Git submodule')
        pins[project] = line[1]
        spec = (ROOT / f'packaging/{project}/{project}.spec').read_text()
        specs[project] = tuple(re.search(rf'^{key}:\s*(\S+)', spec, re.M)[1]
                               .removesuffix('%{?dist}') for key in ('Version', 'Release'))
    validate(ledger, pins, specs)
    paths = git('ls-tree', '-r', '--name-only', base).splitlines()
    old = {}
    if 'packaging/versions.json' in paths:
        old = json.loads(git('show', f'{base}:packaging/versions.json'))
        # Validate the base ledger too, so edited metadata cannot hide a bump.
        for project in PROJECTS:
            pin = git('rev-parse', f'{base}:packaging/{project}/src')
            if old[project]['pin'] != pin:
                raise ValueError(f'{project}: base ledger has an invalid pin')
        # Disable rename detection so both removed and added paths are checked.
        paths = git('diff', '--name-only', '--no-renames', '-z', base, 'HEAD').split('\0')
        compare(old, ledger, paths)
    else:
        if any(f'packaging/{p}/src' in paths for p in PROJECTS):
            raise ValueError('baseline has sources but no version ledger')
        # There is no prior package version when packaging has no base ledger.
        # Validate every entry above; relative version increases start with it.
        print('Validating the complete packaging baseline', file=sys.stderr)
    return ledger, old


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='origin/main')
    parser.add_argument('--changed', action='store_true')
    args = parser.parse_args()
    try:
        ledger, old = check(args.base)
        changed = changed_packages(old, ledger)
        print(' '.join(changed) if args.changed else 'Version ledger passed')
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')
