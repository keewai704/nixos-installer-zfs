#!/usr/bin/env python3
"""Boot the release ISO, install its generated flake on ZFS, boot without ISO.

Uses disposable QCOW2 disks and no host block devices. Installation uses QEMU
user networking and the ISO's configured caches; other boots have no network.
Requires: nix develop .#ci and the ISO built by CI.
"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import uuid

import pexpect


def host(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


class VM:
    def __init__(self, work, mode, disk, *, iso=None, network=False):
        self.log = (work / f"{mode}.log").open("w")
        kvm = os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)
        args = [
            "-machine", "q35", "-accel", "kvm" if kvm else "tcg",
            "-cpu", "host" if kvm else "max", "-m", "6144", "-smp", "2",
            "-display", "none", "-serial", "stdio", "-monitor", "none",
            "-no-reboot", "-nic", "user,model=virtio-net-pci" if network else "none",
            "-drive", f"file={disk},if=virtio,format=qcow2",
        ]
        if mode != "bios-live":
            firmware = work / "OVMF_VARS.fd"
            if not firmware.exists():
                shutil.copyfile(os.environ["OVMF_VARS"], firmware)
            args += [
                "-drive", f"if=pflash,format=raw,readonly=on,file={os.environ['OVMF_CODE']}",
                "-drive", f"if=pflash,format=raw,file={firmware}",
            ]
        if iso:
            args += ["-cdrom", str(iso), "-boot", "order=d"]
        else:
            args += ["-boot", "order=c"]
        print(f"Starting {mode} ({'KVM' if kvm else 'TCG'})", flush=True)
        self.child = pexpect.spawn("qemu-system-x86_64", args, encoding="utf-8", codec_errors="replace", timeout=600)
        self.child.logfile_read = self.log
        self.child.setwinsize(40, 200)
        if iso:
            self.child.expect_exact("installer> ")
            self.child.sendline("sudo -i")
            self.child.expect_exact("installer> ")
        else:
            self.child.expect(re.compile(r"login: ?$", re.MULTILINE))
            self.child.sendline("root")
            self.child.expect_exact("[root@ci-zfs:")
        self.child.sendline("stty -echo")
        self.run("id -u | grep -qx 0", timeout=30)

    def run(self, command, *, timeout=600, ok=True):
        marker = "__STATUS_" + uuid.uuid4().hex
        self.child.sendline(f"{command}; rc=$?; printf '\\n{marker}:%s\\n' \"$rc\"")
        # Guest serial output and the host PTY can both translate LF to CRLF.
        self.child.expect(re.escape(marker) + r":([0-9]+)\r*\n", timeout=timeout)
        output, code = self.child.before, int(self.child.match.group(1))
        print(f"guest exit={code}: {command}", flush=True)
        if ok and code:
            raise AssertionError(f"Command failed ({code}): {command}\n{output}")
        return output, code

    def stop(self):
        self.child.sendline("systemctl poweroff")
        self.child.expect(pexpect.EOF, timeout=180)
        self.child.close()

    def close(self):
        if self.child.isalive():
            self.child.terminate(force=True)
        self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=Path(".vm-test"))
    args = parser.parse_args()
    iso, work = args.iso.resolve(), args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise RuntimeError("Use an empty work directory so old disks/logs cannot affect the test.")
    expected = json.loads(host(
        "nix", "eval", "--json", ".#nixosConfigurations.installer.config.environment.etc",
        "--apply", 'etc: builtins.fromJSON etc."nixos-installer/versions.json".text',
    ))
    disk = work / "target.qcow2"
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(disk), "32G"], check=True)
    results = {
        "expected": expected,
        "tests": [],
        "network": "UEFI installation: QEMU user networking, no forwarded ports; BIOS and installed boot: no NIC",
    }

    def tools(vm):
        for command in ("claude --version", "codex --version", "git --version", "gh --version"):
            vm.run(command, timeout=120)
        vm.run("modprobe zfs && zfs version && zpool version")
        vm.run(f"test \"$(uname -r)\" = {shlex.quote(expected['kernel'])}")
        version_pattern = "^" + re.escape(expected["zfs"]) + "(-|$)"
        vm.run("grep -Eq " + shlex.quote(version_pattern) + " /sys/module/zfs/version")

    with contextlib.closing(VM(work, "bios-live", disk, iso=iso)) as vm:
        tools(vm)
        vm.stop()
        results["tests"].append("BIOS: actual ISO boots; CachyOS, ZFS and all four CLIs work")

    with contextlib.closing(VM(work, "uefi-live", disk, iso=iso, network=True)) as vm:
        tools(vm)
        vm.run("curl --fail --silent --show-error --connect-timeout 10 --retry 8 --retry-delay 2 --retry-all-errors https://cache.nixos.org/nix-cache-info", timeout=180)
        # Refusal paths must leave the disposable disk unchanged.
        vm.run("install-zfs --help")
        _, code = vm.run("printf 'NO\\n' | install-zfs --disk /dev/vda --prepare-only", ok=False)
        if code == 0:
            raise AssertionError("Installer accepted an incorrect wipe confirmation")
        vm.run("test -z \"$(lsblk -nro FSTYPE /dev/vda)\"")
        vm.run("printf 'ERASE /dev/vda\\n' | install-zfs --disk /dev/vda --hostname ci-zfs --prepare-only", timeout=600)
        vm.run("grep -q 'ci-zfs' /mnt/etc/nixos/machine.nix")
        # Use the same network/caches as a normal install of the generated flake.
        vm.run("nixos-install --flake /mnt/etc/nixos#installed --no-root-passwd --no-channel-copy --option accept-flake-config false", timeout=2400)
        # Set an empty target password only for the following networkless boot.
        # The published ISO/source do not grant passwordless installed-system login.
        vm.run("nixos-enter --root /mnt --command 'passwd -d root'")
        vm.run("echo zfs-root-persistent > /mnt/root/persistence-test; echo zfs-home-persistent > /mnt/home/persistence-test; echo zfs-nix-persistent > /mnt/nix/persistence-test")
        vm.run("test -f /mnt/boot/EFI/BOOT/BOOTX64.EFI && test -f /mnt/boot/loader/loader.conf")
        vm.run("sync && umount -R /mnt && zpool export rpool")
        vm.stop()
        results["tests"].append("UEFI: real nixos-install builds and installs the generated flake on ZFS using configured public caches")

    with contextlib.closing(VM(work, "installed-boot", disk)) as vm:
        tools(vm)
        vm.run("test \"$(findmnt -n -o FSTYPE /)\" = zfs && test \"$(findmnt -n -o SOURCE /)\" = rpool/root")
        vm.run("test \"$(findmnt -n -o SOURCE /home)\" = rpool/home && test \"$(findmnt -n -o SOURCE /nix)\" = rpool/nix")
        vm.run("grep -qx zfs-root-persistent /root/persistence-test && grep -qx zfs-home-persistent /home/persistence-test && grep -qx zfs-nix-persistent /nix/persistence-test")
        vm.run("zpool status -x | grep -q 'all pools are healthy'")
        vm.run("test -z \"$(systemctl --failed --no-legend)\"")
        vm.stop()
        results["tests"].append("UEFI: boots installed disk with ISO removed; ZFS root/home/nix, persistence and CLIs work; no failed units")

    results["status"] = "passed"
    (work / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
