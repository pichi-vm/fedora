# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Rootless regression checks; fixtures never touch host mounts or devices."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CONFIG = """CONFIG_BLOCK=y
CONFIG_BLK_DEV_INITRD=y
CONFIG_DEVTMPFS=y
CONFIG_PROC_FS=y
CONFIG_SYSFS=y
CONFIG_EFI_PARTITION=y
CONFIG_VIRTIO_PCI=y
CONFIG_VIRTIO_BLK=y
CONFIG_VIRTIO_CONSOLE=y
CONFIG_BLK_DEV_DM=y
CONFIG_DM_ZERO=y
CONFIG_DM_SNAPSHOT=y
CONFIG_DM_VERITY=m
CONFIG_EXT4_FS=y
CONFIG_MODULES=y
CONFIG_MODULE_DECOMPRESS=y
CONFIG_MODULE_COMPRESS_XZ=y
"""


class Finalize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "root"
        self.out = Path(self.tmp.name) / "out"
        self.out.mkdir()
        self.kver = "7.1.4-104.fc43.x86_64"
        self.kd = self.root / "usr/lib/modules" / self.kver
        self.kd.mkdir(parents=True)
        for name, data in {"vmlinuz": "kernel", "config": CONFIG,
                           "System.map": "symbols", "modules.builtin": ""}.items():
            (self.kd / name).write_text(data)
        (self.kd / "modules.dep").write_text(
            "kernel/dm-verity.ko.xz: kernel/reed_solomon.ko.xz\n"
            "kernel/reed_solomon.ko.xz:\n"
            "kernel/unused.ko.xz:\n"
        )
        (self.kd / "kernel").mkdir()
        for name in ["dm-verity", "reed_solomon", "unused"]:
            (self.kd / "kernel" / f"{name}.ko.xz").write_text(name)
        for name in ["boot", "dev", "proc", "sys", "run", "sbin"]:
            (self.root / name).mkdir()
        (self.root / "sbin/init").write_text("real init")
        (self.root / "sbin/init").chmod(0o755)

    def run_hook(self):
        return subprocess.run(
            ["python3", str(REPO / "mkosi.finalize")],
            env={**os.environ, "BUILDROOT": str(self.root), "OUTPUTDIR": str(self.out)},
            capture_output=True, text=True,
        )

    def test_exports_matching_kernel_and_dependency_closure(self):
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.out / "kver").read_text().strip(), self.kver)
        self.assertEqual((self.out / "vmlinuz").read_text(), "kernel")
        modules = self.out / "initrd-mods/usr/lib/modules" / self.kver / "kernel"
        self.assertEqual(sorted(p.name for p in modules.iterdir()),
                         ["dm-verity.ko.xz", "reed_solomon.ko.xz"])
        self.assertFalse((self.root / "boot").exists())
        self.assertFalse((self.kd / "vmlinuz").exists())
        self.assertTrue((self.kd / "kernel/unused.ko.xz").exists())

    def test_rejects_pre_7_kernel(self):
        self.kd.rename(self.kd.with_name("6.19.0-old"))
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Linux 7.0+", result.stderr)
        self.assertFalse((self.out / "vmlinuz").exists())

    def test_rejects_multiple_kernel_trees(self):
        (self.kd.parent / "7.0-other").mkdir()
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one kernel", result.stderr)

    def test_requires_gpt_discovery_and_root_drivers(self):
        for option in ["CONFIG_EFI_PARTITION", "CONFIG_EXT4_FS", "CONFIG_DM_VERITY"]:
            with self.subTest(option=option):
                (self.kd / "config").write_text("\n".join(
                    line for line in CONFIG.splitlines() if not line.startswith(option + "=")
                ))
                result = self.run_hook()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(option, result.stderr)

    def test_requires_kernel_module_decompressor(self):
        (self.kd / "config").write_text(CONFIG.replace("CONFIG_MODULE_DECOMPRESS=y", ""))
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFIG_MODULE_DECOMPRESS", result.stderr)

    def test_missing_modular_driver_is_not_treated_as_builtin(self):
        (self.kd / "config").write_text(CONFIG.replace("CONFIG_EXT4_FS=y", "CONFIG_EXT4_FS=m"))
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ext4", result.stderr)

    def test_requires_dm_zero_and_exports_it_when_modular(self):
        (self.kd / "config").write_text(CONFIG.replace("CONFIG_DM_ZERO=y", "CONFIG_DM_ZERO=m"))
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dm_zero", result.stderr)
        with (self.kd / "modules.dep").open("a") as f:
            f.write("kernel/dm-zero.ko.xz:\n")
        (self.kd / "kernel/dm-zero.ko.xz").write_text("zero target")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "initrd-mods/usr/lib/modules" / self.kver /
                         "kernel/dm-zero.ko.xz").is_file())

    def test_rejects_disabled_dm_zero(self):
        (self.kd / "config").write_text(CONFIG.replace("CONFIG_DM_ZERO=y", ""))
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFIG_DM_ZERO", result.stderr)

    def test_requires_real_init_and_mountpoints(self):
        (self.root / "sbin/init").unlink()
        result = self.run_hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/sbin/init", result.stderr)

    def test_resolves_absolute_init_symlinks_inside_image(self):
        (self.root / "sbin/init").unlink()
        (self.root / "sbin").rmdir()
        (self.root / "sbin").symlink_to("/usr/sbin")
        (self.root / "usr/sbin").mkdir()
        (self.root / "usr/sbin/init").symlink_to("../lib/systemd/systemd")
        (self.root / "usr/lib/systemd").mkdir()
        real_init = self.root / "usr/lib/systemd/systemd"
        real_init.write_text("fixture init")
        real_init.chmod(0o755)
        (self.root / "run").rmdir()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "run").is_dir())


class Build(unittest.TestCase):
    """Exercise shell orchestration with tool doubles, not a simulated VM."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copy2(REPO / "build.sh", self.root / "build.sh")
        shutil.copy2(REPO / "config.json", self.root / "config.json")
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.log = self.root / "calls.jsonl"
        self.binary = self.root / "corium"
        self.binary.write_bytes(b"regression fixture, not executable guest code")
        self.tool("mkosi", """
work = Path(args[args.index('--output-dir') + 1])
work.mkdir(exist_ok=True)
(work / 'fedora.root-x86-64.raw').touch()
(work / 'kver').write_text('7.1.4-test')
(work / 'vmlinuz').touch()
(work / 'kernel.config').touch()
mods = work / 'initrd-mods/usr/lib/modules/7.1.4-test'
mods.mkdir(parents=True)
(mods / 'dm-verity.ko').write_text('module fixture')
""")
        self.tool("dumpe2fs", "print('Block size:               4096')")
        self.tool("pichi", """
if args[0] == 'inspect':
    print(os.environ.get('TEST_ROOT_HASH', 'ab' * 32))
""")
        self.tool("arma", "")
        self.tool("rustup", "")
        self.tool("cargo", """
dest = Path(args[args.index('--root') + 1]) / 'bin/corium'
dest.parent.mkdir(parents=True)
dest.write_bytes(Path(os.environ['TEST_CORIUM']).read_bytes())
""")
        self.env = {**os.environ, "PATH": f"{self.tools}:{os.environ['PATH']}",
                    "CORIUM_BIN": str(self.binary), "TEST_CORIUM": str(self.binary),
                    "TEST_CALLS": str(self.log), "RELEASE": "43", "REVISION": "test-revision"}
        for name in ["CARAPACE_BIN", "CARAPACE_GIT", "ARMA", "CORIUM_GIT", "CORIUM_REV"]:
            self.env.pop(name, None)

    def tool(self, name, body):
        path = self.tools / name
        path.write_text("#!/usr/bin/env python3\nimport json, os, sys\nfrom pathlib import Path\n"
                        "args = sys.argv[1:]\n"
                        "with open(os.environ['TEST_CALLS'], 'a') as f:\n"
                        "    f.write(json.dumps([Path(sys.argv[0]).name, *args]) + '\\n')\n" + body)
        path.chmod(0o755)

    def run_build(self):
        result = subprocess.run(["bash", str(self.root / "build.sh")], env=self.env,
                                capture_output=True, text=True)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    def test_packages_corium_and_seals_only_current_root_argument(self):
        result, calls = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        init = self.root / ".build/initrd-root/init"
        self.assertEqual(init.read_bytes(), self.binary.read_bytes())
        self.assertTrue(os.access(init, os.X_OK))
        archive = subprocess.run(["cpio", "-it"], input=(self.root / ".build/initrd.cpio").read_bytes(),
                                 capture_output=True, check=True)
        self.assertIn(b"init", [line.removeprefix(b"./") for line in archive.stdout.splitlines()])
        self.assertIn(b"dm-verity.ko", archive.stdout)
        arma = next(call for call in calls if call[0] == "arma")
        cmdline = arma[arma.index("--cmdline") + 1].split()
        self.assertEqual([x for x in cmdline if x.startswith("corium=")], ["corium=" + "ab" * 32])
        self.assertFalse(any(x.startswith(("root=", "carapacehash=", "root.carapace=")) for x in cmdline))
        self.assertEqual(sum(call[:3] == ["pichi", "import", "raw"] for call in calls), 1)
        mkosi = next(call for call in calls if call[0] == "mkosi")
        self.assertEqual(mkosi[mkosi.index("--release") + 1], "43")

    def test_builds_locked_pinned_corium_for_native_musl(self):
        self.env.pop("CORIUM_BIN")
        self.tool("uname", "print(os.environ['TEST_ARCH'])")
        for arch, target in [("x86_64", "x86_64-unknown-linux-musl"),
                             ("aarch64", "aarch64-unknown-linux-musl")]:
            with self.subTest(arch=arch):
                self.log.unlink(missing_ok=True)
                self.env["TEST_ARCH"] = arch
                result, calls = self.run_build()
                self.assertEqual(result.returncode, 0, result.stderr)
                cargo = next(call for call in calls if call[0] == "cargo")
                self.assertIn("--locked", cargo)
                self.assertIn("--rev", cargo)
                self.assertEqual(cargo[-1], "corium")
                self.assertEqual(cargo[cargo.index("--target") + 1], target)
                self.assertEqual(cargo[cargo.index("--git") + 1], "https://github.com/pichi-vm/corium")

    def test_rejects_unsupported_architecture(self):
        self.tool("uname", "print('riscv64')")
        result, calls = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported arch", result.stderr)
        self.assertFalse(any(call[0] in ("mkosi", "cargo", "arma") for call in calls))

    def test_rejects_invalid_integrity_roots_before_sealing(self):
        for root in ["", "0x" + "ab" * 32, "ab", "zz" * 32]:
            with self.subTest(root=root):
                self.log.unlink(missing_ok=True)
                self.env["TEST_ROOT_HASH"] = root
                result, calls = self.run_build()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("verity root", result.stderr)
                self.assertFalse(any(call[0] == "arma" for call in calls))


if __name__ == "__main__":
    unittest.main()
