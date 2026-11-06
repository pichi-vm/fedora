# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Exercise Copr's root Makefile contract from each package directory."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CoprMakefileTests(unittest.TestCase):
    def invoke(self, project):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            for name in ('git', 'python3'):
                executable = work / name
                executable.write_text('#!/bin/bash\nprintf "%s\\n" "$0" "$@" >> "$CALL_LOG"\n')
                executable.chmod(0o755)
            result = subprocess.run(
                ['make', '-f', str(ROOT / '.copr/Makefile'), 'srpm',
                 f'spec={ROOT / "packaging" / project / (project + ".spec")}',
                 f'outdir={work / "result"}'],
                cwd=ROOT / 'packaging' / project, text=True, capture_output=True,
                env={**os.environ, 'PREPARED': '1', 'CALL_LOG': str(work / 'calls'),
                     'PATH': str(work) + ':' + os.environ['PATH']})
            calls = (work / 'calls').read_text() if (work / 'calls').exists() else ''
            return result, calls, work

    def test_each_package_from_copr_working_directory(self):
        for project in ('corium', 'arma', 'dillo', 'pichi', 'madrillo'):
            with self.subTest(project=project):
                result, calls, work = self.invoke(project)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'{ROOT}/scripts/srpm.py\n{project}\n--out\n{work}/result\n', calls)
                self.assertEqual(calls.count('/scripts/srpm.py'), 1)
