# SPDX-FileCopyrightText: Advanced Micro Devices, Inc.
# SPDX-License-Identifier: Apache-2.0

.ONESHELL:
.SHELLFLAGS := -eu -c
root := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

# COPR supplies the selected spec and an output directory, once per package.
.PHONY: srpm
srpm:
	dnf -y install git rpm-build tar gzip
	package=$$(basename "$$(dirname "$(spec)")")
	git -C "$(root)" submodule update --init --recursive "sources/$$package"
	name=$$(rpmspec -q --srpm --qf '%{name}-%{version}' "$(spec)")
	mkdir -p "$(outdir)"
	tar -C "$(root)/sources/$$package" --exclude-vcs \
		--exclude=.copr --exclude=packaging --exclude=debian \
		--transform "s,^\./,$$name/," -czf "$(outdir)/$$name.tar.gz" .
	rpmbuild -bs "$(spec)" --define "_sourcedir $(outdir)" \
		--define "_srcrpmdir $(outdir)"
