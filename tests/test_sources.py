# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Check that package identity and exports follow committed source inputs."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'srpm', Path(__file__).resolve().parents[1] / 'scripts/srpm.py')
srpm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(srpm)


class Sources(unittest.TestCase):
    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

    def commit(self, repo):
        self.git(repo, 'add', '.')
        self.git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'fixture')

    def test_export_includes_recorded_nested_submodule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child, parent, output = (root / name for name in ('child', 'parent', 'output'))
            for repo in (child, parent):
                repo.mkdir()
                self.git(repo, 'init', '-q')
            (child / 'payload').write_text('pinned source')
            self.commit(child)
            self.git(parent, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q',
                     str(child), 'deps/child')
            self.commit(parent)
            (parent / 'untracked-secret').write_text('must not be exported')
            srpm.export(parent, 'HEAD', output)
            self.assertEqual((output / 'deps/child/payload').read_text(), 'pinned source')
            self.assertFalse((output / 'untracked-secret').exists())
            self.assertFalse((output / 'deps/child/.git').exists())

    def test_identity_ignores_image_changes_but_tracks_packaging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.git(root, 'init', '-q')
            (root / 'packaging/corium').mkdir(parents=True)
            spec = root / 'packaging/corium/corium.spec'
            spec.write_text('original')
            self.commit(root)
            with patch.object(srpm, 'ROOT', root):
                original = srpm.package_identity('corium')
                (root / 'pichi.yaml').write_text('image-only change')
                self.commit(root)
                self.assertEqual(srpm.package_identity('corium'), original)
                spec.write_text('changed packaging')
                self.commit(root)
                self.assertNotEqual(srpm.package_identity('corium'), original)
