#!/usr/bin/env python3
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Opt-in native pichi/dillo smoke tests of a freshly built Fedora artifact.

No host mounts, loop or device-mapper changes. Uses KVM and the local pichi
cache. Test artifacts get unique local tags; nothing is pushed. The successful
login guest is terminated by the harness, not claimed to have powered off.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


REPO = Path(__file__).resolve().parents[1]


def boot(reference, log, expected, timeout, handoff=False):
    with log.open("w") as output:
        guest = subprocess.Popen(["pichi", "run", reference], stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                text = log.read_text(errors="replace")
                if "Kernel panic" in text:
                    raise AssertionError(f"kernel panic: {log}")
                if handoff and re.search(r"(?:^|\s)\S*login: ?", text):
                    if "ERROR corium:" in text or "systemd[1]" not in text:
                        raise AssertionError(f"Corium failed before login: {log}")
                    return "systemd console login reached; harness terminated guest"
                if guest.poll() is not None:
                    fatal = 'ERROR corium: message="boot failed"'
                    if (handoff or guest.returncode != 0 or expected not in text or
                            fatal not in text or "login:" in text or "systemd[1]" in text):
                        raise AssertionError(f"unexpected guest exit {guest.returncode}: {log}")
                    return "expected fatal diagnostic; launcher exited successfully"
                time.sleep(0.1)
            raise AssertionError(f"guest timed out after {timeout}s: {log}")
        finally:
            if guest.poll() is None:
                guest.terminate()
                try:
                    guest.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    guest.kill()
                    guest.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="43")
    parser.add_argument("--build-dir", type=Path, default=REPO / ".build")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    work = args.build_dir.resolve()
    # Unique directory preserves previous success/failure evidence.
    output = work / f"boot-tests-{time.time_ns()}"
    output.mkdir()
    cmdline = (work / "cmdline").read_text().strip()
    roots = [x for x in cmdline.split() if x.startswith("corium=")]
    if len(roots) != 1 or not re.fullmatch(r"corium=[0-9a-fA-F]{64}", roots[0]):
        raise AssertionError("expected exactly one SHA-256 corium=<root-hash>")
    if any(x.startswith(("root=", "carapacehash=", "root.carapace=")) for x in cmdline.split()):
        raise AssertionError("obsolete root argument in built command line")
    reference = f"fedora:{args.release}"
    manifest_root = subprocess.check_output([
        "pichi", "inspect", reference, "--format",
        '{{ manifest.annotations["dev.pichi.carapace.verity.hash"] }}',
    ], text=True).strip()
    if roots[0] != f"corium={manifest_root}":
        raise AssertionError("built command line does not match imported artifact root")
    results = {}
    try:
        results["systemd-handoff"] = boot(reference, output / "systemd-handoff.log", "",
                                           args.timeout, handoff=True)
        print(f"PASS systemd-handoff: {results['systemd-handoff']}", flush=True)
        wrong = ("0" if manifest_root[0] != "0" else "1") + manifest_root[1:]
        for name, argument, diagnostic in [
            ("wrong-root", f"corium={wrong}", "discover root:"),
            ("legacy-root", f"carapacehash={manifest_root}", "missing corium=<root-hash>"),
        ]:
            case = output / name
            case.mkdir()
            options = cmdline.replace(roots[0], argument)
            (case / "cmdline").write_text(options + "\n")
            subprocess.run([
                os.environ.get("ARMA", "arma"), "build", "--kernel", str(work / "vmlinuz"),
                "--config", str(work / "kernel.config"), "--initrd", str(work / "initrd.cpio"),
                "--cmdline", options, "--dtb", str(case / "base.dtb"), str(case / "boot.pmi"),
            ], check=True, timeout=args.timeout)
            tag = f"fedora:corium-test-{output.name}-{name}"
            subprocess.run([
                "pichi", "import", "pmi", str(case / "boot.pmi"),
                "--dtb", str(case / "base.dtb"), "--config", str(REPO / "config.json"),
                "--carapace", f"fedora:{args.release}-carapace", "-t", tag,
            ], check=True, timeout=args.timeout)
            results[name] = boot(tag, case / "console.log", diagnostic, args.timeout)
            print(f"PASS {name}: {results[name]}", flush=True)
    finally:
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(f"Boot evidence: {output}", flush=True)
    if len(results) != 3:
        raise AssertionError("incomplete boot coverage")


if __name__ == "__main__":
    main()
