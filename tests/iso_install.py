#!/usr/bin/env python3
"""Drive the real graphical ISO through QEMU's keyboard and install/reboot ZFS.

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
import socket
import subprocess
import time
import uuid

import pexpect
from PIL import Image, ImageStat


class QMP:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX)
        deadline = time.monotonic() + 30
        while True:
            try:
                self.socket.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        self.stream = self.socket.makefile("rwb", buffering=0)
        json.loads(self.stream.readline())
        self.command("qmp_capabilities")

    def command(self, command, **arguments):
        self.stream.write(json.dumps({"execute": command, "arguments": arguments}).encode() + b"\n")
        while True:
            answer = json.loads(self.stream.readline())
            if "error" in answer:
                raise RuntimeError(answer["error"])
            if "return" in answer:
                return answer["return"]

    def key(self, keys):
        self.command("human-monitor-command", **{"command-line": "sendkey " + keys})
        time.sleep(0.2)

    def text(self, value):
        symbols = {" ": "spc", "/": "slash", "-": "minus", "_": "shift-minus", ".": "dot"}
        for char in value:
            if char.isascii() and char.isalnum():
                self.key("shift-" + char.lower() if char.isupper() else char)
            elif char in symbols:
                self.key(symbols[char])
            else:
                raise ValueError("Unsupported test keyboard character")

    def close(self):
        self.stream.close()
        self.socket.close()


def host(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


class VM:
    def __init__(self, work, mode, disk, *, iso=None, network=False, password=None):
        self.work, self.mode = work, mode
        self.log = (work / f"{mode}.log").open("w")
        kvm = os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)
        args = [
            "-machine", "q35", "-accel", "kvm" if kvm else "tcg",
            "-cpu", "host" if kvm else "max", "-m", "6144", "-smp", "2",
            "-display", "none", "-serial", "stdio", "-monitor", "none",
            "-vga", "none", "-device", "virtio-vga,xres=1280,yres=800",
            "-device", "qemu-xhci", "-device", "usb-tablet",
            "-qmp", f"unix:{work / (mode + '.qmp')},server=on,wait=off",
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
        self.qmp = QMP(work / (mode + ".qmp"))
        if iso:
            self.child.expect_exact("installer> ")
            self.child.sendline("sudo -i")
            self.child.expect_exact("installer> ")
        else:
            self.child.expect(re.compile(r"login: ?$", re.MULTILINE))
            self.child.sendline("ciuser")
            self.child.expect_exact("Password:")
            self.child.sendline(password)
            self.child.expect_exact("ciuser@ci-zfs:", timeout=60)
            self.child.sendline("sudo -i")
            self.child.expect(re.compile(r"[Pp]assword.*:"))
            self.child.sendline(password)
            # NixOS inserts an OSC window-title sequence after the opening '['.
            self.child.expect_exact("root@ci-zfs:", timeout=60)
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

    def user(self, command, username="nixos"):
        # A serial login does not inherit the graphical session's IPC variables.
        session = (
            'for sock in "$XDG_RUNTIME_DIR"/umbriel-*.sock; do '
            'if [ -S "$sock" ]; then '
            'export UMBRIEL_SOCKET="$sock"; name=${sock##*/}; '
            'name=${name#umbriel-}; export WAYLAND_DISPLAY=${name%.sock}; '
            'break; fi; done; exec ' + command
        )
        return f"runuser -u {username} -- env XDG_RUNTIME_DIR=/run/user/$(id -u {username}) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u {username})/bus bash -c {shlex.quote(session)}"

    def desktop(self, username="nixos"):
        command = self.user("systemctl --user is-active umbriel.service noctalia.service", username)
        command += " && " + self.user("noctalia msg color-scheme-get", username)
        command += " && " + self.user("umbriel layers", username) + " | grep -Fq noctalia-bar"
        self.run("timeout 180 bash -c " + shlex.quote(f"until {command}; do sleep 2; done"), timeout=200)
        self.run("umbriel --version && noctalia --version")

    def page(self, name, timeout=120):
        query = "journalctl -b _SYSTEMD_USER_UNIT=zfs-installer.service --no-pager | grep -Fq " + shlex.quote("GUI_PAGE " + name)
        failed = "journalctl -b _SYSTEMD_USER_UNIT=zfs-installer.service --no-pager | grep -Fq GUI_INSTALL_FAILED"
        self.run("timeout " + str(timeout) + " bash -c " + shlex.quote(f"until {query}; do if {failed}; then exit 1; fi; sleep 1; done"), timeout=timeout + 20)

    def screenshot(self, name):
        ppm = self.work / (name + ".ppm")
        self.qmp.command("screendump", filename=str(ppm))
        with Image.open(ppm) as shot:
            rgb = shot.convert("RGB")
            if max(ImageStat.Stat(rgb).stddev) < 5:
                raise AssertionError("The VM display is blank")
            rgb.save(self.work / (name + ".png"))
        ppm.unlink()

    def field(self, mnemonic, text):
        self.qmp.key("alt-" + mnemonic)
        self.qmp.key("ctrl-a")
        self.qmp.text(text)

    def close(self):
        if self.child.isalive():
            with contextlib.suppress(Exception):
                self.run("journalctl -b -u greetd --no-pager; journalctl -b _UID=1000 --no-pager | tail -250", ok=False, timeout=30)
                self.screenshot(self.mode + "-last-screen")
            self.child.terminate(force=True)
        self.qmp.close()
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
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(disk), "40G"], check=True)
    password = "ci" + uuid.uuid4().hex[:16]
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
        vm.desktop()
        vm.page("Welcome")
        vm.run(vm.user("umbriel windows") + " | grep -F 'NixOS Installer'")
        vm.screenshot("bios-desktop")
        vm.stop()
        results["tests"].append("BIOS: actual ISO boots into Umbriel + Noctalia v5 and the graphical wizard; CachyOS, ZFS and all four CLIs work")

    with contextlib.closing(VM(work, "uefi-live", disk, iso=iso, network=True)) as vm:
        tools(vm)
        vm.run("curl --fail --silent --show-error --connect-timeout 10 --retry 8 --retry-delay 2 --retry-all-errors https://cache.nixos.org/nix-cache-info", timeout=180)
        vm.desktop()
        vm.page("Welcome")
        vm.screenshot("uefi-desktop")
        vm.qmp.key("alt-n")
        vm.page("Storage")
        vm.screenshot("disk-selection")
        vm.qmp.key("alt-n")
        vm.page("Account")
        vm.field("h", "ci-zfs")
        vm.field("u", "ciuser")
        vm.field("p", password)
        vm.field("c", password)
        vm.qmp.key("alt-l")
        vm.qmp.key("end")
        vm.qmp.key("alt-n")
        vm.page("Review")
        vm.screenshot("confirmation")
        # Operate the actual GUI; a rejected confirmation must not write to disk.
        vm.qmp.key("alt-e")
        vm.field("d", "WRONG")
        vm.qmp.key("alt-i")
        vm.run("test -z \"$(lsblk -nro FSTYPE /dev/vda)\"")
        vm.run("! journalctl -b _SYSTEMD_USER_UNIT=zfs-installer.service --no-pager | grep -Fq 'GUI_PAGE Installing'")
        vm.field("d", "ERASE /dev/vda")
        vm.qmp.key("alt-i")
        vm.page("Installing")
        vm.screenshot("installing")
        # The GUI worker itself invokes nixos-install; no substitute install path.
        vm.page("Complete", timeout=3600)
        vm.run("journalctl -b _SYSTEMD_USER_UNIT=zfs-installer.service --no-pager")
        vm.screenshot("installation-complete")
        vm.run("! zpool list -H -o name 2>/dev/null | grep -qx rpool")
        vm.run("zpool import -N -R /mnt rpool && mount -t zfs rpool/root /mnt && mount -t zfs rpool/home /mnt/home && mount -t zfs rpool/nix /mnt/nix")
        vm.run("grep -q 'ci-zfs' /mnt/etc/nixos/machine.nix && grep -q 'ciuser' /mnt/etc/nixos/machine.nix && test \"$(stat -c %a /mnt/etc/user-passwords/ciuser)\" = 600")
        vm.run("echo zfs-root-persistent > /mnt/root/persistence-test; echo zfs-home-persistent > /mnt/home/persistence-test; echo zfs-nix-persistent > /mnt/nix/persistence-test")
        vm.run("mount /dev/disk/by-label/NIXOS_EFI /mnt/boot && test -f /mnt/boot/EFI/BOOT/BOOTX64.EFI && test -f /mnt/boot/loader/loader.conf")
        vm.run("sync && umount -R /mnt && zpool export rpool")
        vm.stop()
        results["tests"].append("UEFI: QEMU keyboard drives disk selection, account creation, erase refusal and complete graphical ZFS installation using public caches")

    with contextlib.closing(VM(work, "installed-boot", disk, password=password)) as vm:
        tools(vm)
        vm.run("test \"$(findmnt -n -o FSTYPE /)\" = zfs && test \"$(findmnt -n -o SOURCE /)\" = rpool/root")
        vm.run("test \"$(findmnt -n -o SOURCE /home)\" = rpool/home && test \"$(findmnt -n -o SOURCE /nix)\" = rpool/nix")
        vm.run("grep -qx zfs-root-persistent /root/persistence-test && grep -qx zfs-home-persistent /home/persistence-test && grep -qx zfs-nix-persistent /nix/persistence-test")
        vm.run("zpool status -x | grep -q 'all pools are healthy'")
        vm.run("getent shadow root | cut -d: -f2 | grep -qx '!' && test \"$(id -u ciuser)\" -ge 1000")
        # Nix's GTK wrapper runs .regreet-wrapped, so match its executable path.
        vm.run("timeout 120 bash -c 'until systemctl is-active --quiet greetd && pgrep -f \"/bin/[.]?regreet(-wrapped)?( |$)\" >/dev/null; do sleep 1; done'", timeout=140)
        vm.screenshot("installed-login")
        # ReGreet selects the sole regular user. Log in with the GUI-created password.
        vm.qmp.key("ret")
        time.sleep(2)
        vm.qmp.text(password)
        vm.qmp.key("ret")
        vm.desktop("ciuser")
        vm.screenshot("installed-desktop")
        vm.run("test -z \"$(systemctl --failed --no-legend)\"")
        vm.stop()
        results["tests"].append("UEFI: boots without ISO/network; password login to Umbriel + Noctalia v5, ZFS root/home/nix, persistence and CLIs work; no failed units")

    results["status"] = "passed"
    (work / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
