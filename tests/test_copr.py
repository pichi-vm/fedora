# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Reject stale or corrupted package inputs before allocating image runners."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import copr


class Selection(unittest.TestCase):
    def test_reuses_only_matching_success_on_both_architectures(self):
        identity = 'a' * 64
        matching = {'id': 3, 'state': 'succeeded',
                    'chroots': ['fedora-43-x86_64', 'fedora-43-aarch64'],
                    'source_package': {'version': '0.1-3.123.g' + identity[:16]}}
        candidates = [
            {**matching, 'id': 1, 'source_package': {'version': '0.1-3.123.g' + 'b' * 16}},
            {**matching, 'id': 2, 'chroots': ['fedora-43-x86_64']}, matching]
        client = copr.Copr('pichi-staging')
        with patch.object(client, 'request', return_value={'items': candidates}):
            self.assertEqual(client.find('arma', identity, 'c' * 40), 3)

    def test_failed_build_is_never_reused(self):
        client = copr.Copr('pichi-staging')
        with patch.object(client, 'request', return_value={'items': [
                {'id': 1, 'state': 'failed', 'source_package': {'version': '0.1-3.g' + 'a' * 16}}]}):
            self.assertIsNone(client.find('arma', 'a' * 64, 'c' * 40))

    def test_unsigned_rpm_is_rejected_even_when_digests_pass(self):
        with patch('copr.subprocess.run', return_value=subprocess.CompletedProcess(
                [], 0, stdout='Header SHA256 digest: OK\nPayload SHA256 digest: OK\n')):
            with self.assertRaisesRegex(RuntimeError, 'no verified RPM signature'):
                copr.verify(Path('unsigned.rpm'), Path('key'))

    def test_corrupt_cached_rpm_is_not_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'keys').mkdir()
            key = root / 'keys/pichi-staging.asc'
            key.write_text('key fixture')
            lock = {'project': 'pichi-staging',
                    'key_sha256': hashlib.sha256(key.read_bytes()).hexdigest(),
                    'packages': {'arma': {'rpms': {'x86_64': {
                        'filename': 'arma.rpm', 'sha256': hashlib.sha256(b'original').hexdigest()}}}}}
            manifest = root / 'lock.json'
            manifest.write_text(json.dumps(lock))
            (root / 'arma.rpm').write_bytes(b'corrupted')
            with patch.object(copr, 'ROOT', root), patch('copr.verify') as verify:
                with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                    copr.download(manifest, root, 'x86_64', ['arma'])
                verify.assert_not_called()
