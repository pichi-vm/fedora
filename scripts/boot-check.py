#!/usr/bin/env python3
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Boot the produced Fedora image through packaged Pichi/Dillo to a login prompt."""
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time


def main():
    path = Path('.build/boot-console.log')
    path.parent.mkdir(exist_ok=True)
    process = subprocess.Popen(
        ['pichi', 'run', sys.argv[1], '--cpus', '2', '--memory', '2048'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True)
    deadline = time.monotonic() + 180
    console = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        with path.open('wb') as output:
            while time.monotonic() < deadline:
                for key, _ in selector.select(timeout=1):
                    block = os.read(key.fd, 65536)
                    if not block:
                        raise RuntimeError('Guest exited before reaching login')
                    output.write(block)
                    output.flush()
                    console.extend(block)
                    if re.search(rb'(?:^|[\r\n])[^\r\n]* login: ?', console):
                        print('Packaged tools booted Fedora to its login prompt')
                        return
                if process.poll() is not None:
                    raise RuntimeError(f'Guest exited with status {process.returncode}')
        raise TimeoutError('Fedora did not reach login within 180 seconds')
    finally:
        selector.close()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


if __name__ == '__main__':
    main()
