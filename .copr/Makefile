# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
export ROOT
export spec outdir

.PHONY: srpm make_srpm
make_srpm: srpm

# Copr supplies absolute spec/outdir paths and calls srpm in the subdirectory.
srpm:
	project=$$(basename "$$(dirname "$${spec:?spec is required}")")
	case "$$project" in corium|arma|dillo|pichi) ;; *) exit 2 ;; esac
	test "$$(realpath "$$spec")" = "$$ROOT/packaging/$$project/$$project.spec"
	: "$${outdir:?outdir is required}"
	# The source builder includes make and dnf and permits network access.
	# Prepared developer environments can supply these tools without installs.
	if [[ $${PREPARED:-0} != 1 ]]; then
		dnf install -y git python3 rpm-build patch tar xz gzip curl gcc ca-certificates
		tools=$$(mktemp -d)
		trap 'rm -rf "$$tools"' EXIT
		export CARGO_HOME="$$tools/cargo" RUSTUP_HOME="$$tools/rustup"
		curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o "$$tools/rustup.sh"
		sh "$$tools/rustup.sh" -y --no-modify-path --profile minimal \
			--default-toolchain nightly-2026-07-06
		export PATH="$$CARGO_HOME/bin:$$PATH"
	fi
	git -C "$$ROOT" submodule update --init --recursive -- "packaging/$$project/src"
	python3 "$$ROOT/scripts/srpm.py" "$$project" --out "$$outdir"
