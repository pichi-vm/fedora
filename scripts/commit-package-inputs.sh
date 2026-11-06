#!/bin/bash
# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Pichi builds committed sources. Both architectures create the same input
# commit so the package lock is included in its source/provenance boundary.
cp .build/packages/packages.lock.json packages.lock.json
git add packages.lock.json
if ! git diff --cached --quiet; then
    epoch=$(git show -s --format=%ct HEAD)
    GIT_AUTHOR_DATE="@$epoch +0000" GIT_COMMITTER_DATE="@$epoch +0000" \
        git -c user.name='Pichi CI' -c user.email=ci@pichi.invalid \
        commit -m 'build: lock verified COPR package inputs'
fi
mkdir -p .build
git bundle create .build/package-inputs.bundle HEAD
