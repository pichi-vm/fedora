# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Exercise the policy at the package/source boundary."""
import copy
import importlib.util
from pathlib import Path
import unittest
import json
import subprocess
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('versions', Path(__file__).resolve().parents[1] / 'scripts/versions.py')
versions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(versions)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.old = {p: {'pin': 'a' * 40, 'version': '0.1.0', 'release': '1', 'source': f'packaging/{p}/src'}
                    for p in versions.PROJECTS}
        self.new = copy.deepcopy(self.old)

    def test_packaging_only_unchanged_version(self):
        versions.compare(self.old, self.new)

    def test_version_without_pin(self):
        self.new['arma']['version'] = '0.2.0'
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_packaging_only_release_bump(self):
        self.new['pichi']['release'] = '2'
        versions.compare(self.old, self.new)

    def test_packaging_only_release_decrease(self):
        self.old['pichi']['release'] = '2'
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_pin_without_version(self):
        self.new['dillo']['pin'] = 'b' * 40
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_pin_with_only_release_bump(self):
        self.new['dillo'].update(pin='b' * 40, release='2')
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_pin_with_lower_version(self):
        self.new['corium'].update(pin='b' * 40, version='0.0.9')
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_numeric_version_order(self):
        self.old['arma']['version'] = '0.9'
        self.new['arma'].update(pin='b' * 40, version='0.10')
        versions.compare(self.old, self.new)

    def test_release_resets_on_version_bump(self):
        self.old['arma']['release'] = '4'
        self.new['arma'].update(pin='b' * 40, version='0.2.0', release='1')
        versions.compare(self.old, self.new)

    def test_version_bump_without_release_reset(self):
        self.new['arma'].update(pin='b' * 40, version='0.2.0', release='2')
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_other_package_bump_does_not_authorize_version(self):
        self.new['arma'].update(pin='b' * 40, version='0.2.0')
        self.new['dillo']['version'] = '0.2.0'
        with self.assertRaises(ValueError):
            versions.compare(self.old, self.new)

    def test_spec_mismatch(self):
        pins = {p: e['pin'] for p, e in self.new.items()}
        specs = {p: (e['version'], e['release']) for p, e in self.new.items()}
        specs['arma'] = ('0.2.0', '1')
        with self.assertRaises(ValueError):
            versions.validate(self.new, pins, specs)

    def test_pin_mismatch(self):
        pins = {p: e['pin'] for p, e in self.new.items()}
        specs = {p: (e['version'], e['release']) for p, e in self.new.items()}
        pins['pichi'] = 'c' * 40
        with self.assertRaises(ValueError):
            versions.validate(self.new, pins, specs)

    def test_source_path_mismatch(self):
        self.new['arma']['source'] = 'packaging/pichi/src'
        pins = {p: e['pin'] for p, e in self.new.items()}
        specs = {p: (e['version'], e['release']) for p, e in self.new.items()}
        with self.assertRaises(ValueError):
            versions.validate(self.new, pins, specs)

    def test_invalid_version(self):
        with self.assertRaises(ValueError):
            versions.number('latest')

    def test_noncanonical_version(self):
        with self.assertRaises(ValueError):
            versions.number('0.01.0')

    def test_zero_release(self):
        self.new['arma']['release'] = '0'
        pins = {p: e['pin'] for p, e in self.new.items()}
        specs = {p: (e['version'], e['release']) for p, e in self.new.items()}
        with self.assertRaises(ValueError):
            versions.validate(self.new, pins, specs)


class PackageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.old = {p: {'pin': 'a' * 40, 'version': '0.1.0', 'release': '1', 'source': f'packaging/{p}/src'}
                    for p in versions.PROJECTS}
        self.new = copy.deepcopy(self.old)

    def test_pin_and_version_bump(self):
        self.new['arma'].update(pin='b' * 40, version='0.2.0')
        versions.compare(self.old, self.new)
        self.assertEqual(versions.changed_packages(self.old, self.new), ['arma'])

    def test_release_only_bump(self):
        self.new['pichi']['release'] = '2'
        versions.compare(self.old, self.new)
        self.assertEqual(versions.changed_packages(self.old, self.new), ['pichi'])

    def test_unchanged(self):
        self.assertEqual(versions.changed_packages(self.old, self.new), [])

    def test_several_packages(self):
        self.new['arma'].update(pin='b' * 40, version='0.2.0')
        self.new['corium']['release'] = '2'
        self.new['dillo']['release'] = '3'
        versions.compare(self.old, self.new)
        self.assertEqual(versions.changed_packages(self.old, self.new),
                         ['corium', 'arma', 'dillo'])

    def test_cross_package_isolation(self):
        self.new['dillo']['release'] = '2'
        self.assertEqual(versions.changed_packages(self.old, self.new), ['dillo'])
        self.assertEqual(versions.changed_packages(self.new, self.new), [])

    def test_initial_migration_selects_all(self):
        self.assertEqual(versions.changed_packages({}, self.new), list(versions.PROJECTS))

    def test_metadata_only_change_does_not_publish(self):
        self.new['arma']['upstream_version'] = '0.2.0'
        self.assertEqual(versions.changed_packages(self.old, self.new), [])


class SharedInputTests(unittest.TestCase):
    def setUp(self):
        self.old = {p: {'pin': 'a' * 40, 'version': '0.1.0', 'release': '2'}
                    for p in versions.PROJECTS}
        self.new = copy.deepcopy(self.old)

    def bump_releases(self):
        for entry in self.new.values():
            entry['release'] = '3'

    def test_shared_input_with_all_releases_bumped(self):
        self.bump_releases()
        versions.compare(self.old, self.new, ['scripts/srpm.py'])

    def test_shared_input_names_package_without_bump(self):
        self.bump_releases()
        self.new['pichi']['release'] = '2'
        with self.assertRaisesRegex(ValueError, 'for: pichi$'):
            versions.compare(self.old, self.new, ['.copr/Makefile'])

    def test_unrelated_inputs(self):
        versions.compare(self.old, self.new, [
            'README.md', 'packaging/README.md', 'build.sh', 'mkosi.conf',
            '.github/workflows/build.yml', 'tests/test_versions.py', 'licenserc.toml',
        ])

    def test_package_folder_does_not_select_shared_rule(self):
        versions.compare(self.old, self.new,
                         ['packaging/arma/arma.spec', 'packaging/arma/src'])

    def test_pin_version_bump_with_release_one_qualifies(self):
        self.bump_releases()
        self.new['arma'].update(pin='b' * 40, version='0.2.0', release='1')
        versions.compare(self.old, self.new, ['scripts/versions.py'])

    def test_every_shared_path_selects_all_packages(self):
        for path in ('scripts/future.py', '.copr/future.mk',
                     'packaging/versions.json', '.gitmodules',
                     '.github/workflows/packaging.yml'):
            with self.subTest(path=path):
                self.assertEqual(versions.affected_packages([path]), versions.PROJECTS)
                with self.assertRaisesRegex(ValueError, 'corium, arma, dillo, pichi'):
                    versions.compare(self.old, self.new, [path])

    def test_ledger_entry_edit_requires_every_package(self):
        self.new['arma']['release'] = '3'
        with self.assertRaisesRegex(ValueError, 'for: corium, dillo, pichi$'):
            versions.compare(self.old, self.new, ['packaging/versions.json'])


class SharedRangeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Packaging Tests')
        self.git('config', 'user.email', 'packaging@example.invalid')
        self.ledger = {p: {'pin': 'a' * 40, 'version': '0.1.0', 'release': '2',
                           'source': f'packaging/{p}/src'} for p in versions.PROJECTS}
        self.write_packages()
        for project in versions.PROJECTS:
            self.git('update-index', '--add', '--cacheinfo',
                     f'160000,{"a" * 40},packaging/{project}/src')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/srpm.py').write_text('# source preparation input\n')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def write_packages(self):
        for project, entry in self.ledger.items():
            folder = self.root / 'packaging' / project
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'src').mkdir(exist_ok=True)
            (folder / f'{project}.spec').write_text(
                f'Version: {entry["version"]}\nRelease: {entry["release"]}%{{?dist}}\n')
        (self.root / 'packaging/versions.json').write_text(json.dumps(self.ledger))

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'test: record package inputs')

    def test_check_reads_shared_paths_from_requested_commit_range(self):
        self.commit()
        with patch.object(versions, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'corium, arma, dillo, pichi'):
                versions.check(self.base)

    def test_check_accepts_range_with_every_spec_release_bumped(self):
        for entry in self.ledger.values():
            entry['release'] = '3'
        self.write_packages()
        self.commit()
        with patch.object(versions, 'ROOT', self.root):
            versions.check(self.base)

    def test_check_against_its_own_commit_has_no_shared_difference(self):
        self.commit()
        with patch.object(versions, 'ROOT', self.root):
            versions.check('HEAD')


if __name__ == '__main__':
    unittest.main()
