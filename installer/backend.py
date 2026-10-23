"""Privileged worker. One request on stdin; progress only on stdout.

The GUI runs unprivileged. Passwords travel over a private pipe, never argv,
logs, the flake or the Nix store. The normal NixOS installer performs the build.
"""

import fcntl
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

from model import validate


def phase(percent, message):
    print(f"@@PHASE:{percent}:{message}", flush=True)


def run(*command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def identity(disk):
    return subprocess.check_output(
        ["lsblk", "-bdnro", "MAJ:MIN,SIZE,SERIAL", disk], text=True
    ).strip()


def nix_string(value):
    return json.dumps(value, ensure_ascii=False).replace("${", r"\${")


def install(request):
    validate(request)
    if os.geteuid() != 0:
        raise ValueError("The installation worker requires root privileges")
    disk = str(Path(request["disk"]).resolve(strict=True))
    if disk != request["disk"] or not stat.S_ISBLK(os.stat(disk).st_mode):
        raise ValueError("The selected device changed; refresh the disk list")
    if identity(disk) != request["identity"]:
        raise ValueError("The selected disk changed; refresh the disk list")
    try:
        if pwd.getpwnam(request["username"]).pw_uid < 1000:
            raise ValueError("This username is reserved for a system service")
    except KeyError:
        pass
    # Hash before changing the disk, and keep the hash out of store inputs.
    hashed = subprocess.check_output(
        ["mkpasswd", "--method=yescrypt", "--stdin"],
        input=request.pop("password") + "\n", text=True,
    ).strip()
    phase(2, "Checking network and installation requirements")
    run("curl", "--fail", "--silent", "--show-error", "--connect-timeout", "15", "--max-time", "60", "https://cache.nixos.org/nix-cache-info", stdout=subprocess.DEVNULL)
    phase(5, "Creating the EFI partition and ZFS datasets")
    run("bash", str(Path(__file__).with_name("prepare-zfs.sh")), "--disk", disk, "--hostname", request["hostname"], "--prepare-only",
        input=request["confirmation"] + "\n", text=True)
    phase(15, "Configuring Umbriel, Noctalia v5 and the user account")
    secrets = Path("/mnt/etc/user-passwords")
    secrets.mkdir(mode=0o700, exist_ok=True)
    os.chmod(secrets, 0o700)
    secret = secrets / request["username"]
    fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(hashed + "\n")
    del hashed
    machine = Path("/mnt/etc/nixos/machine.nix")
    machine.write_text("{ ... }: {\n"
        f"  networking.hostName = {nix_string(request['hostname'])};\n"
        f"  networking.hostId = {nix_string(os.urandom(4).hex())};\n"
        f"  time.timeZone = {nix_string(request['timezone'])};\n"
        f"  i18n.defaultLocale = {nix_string(request['locale'])};\n"
        f"  services.xserver.xkb.layout = {nix_string(request['keyboard'])};\n"
        f"  console.keyMap = {nix_string('jp106' if request['keyboard'] == 'jp' else 'us')};\n"
        "  users.users.root.hashedPassword = \"!\";\n"
        f"  users.users.{request['username']} = {{\n"
        "    isNormalUser = true;\n"
        "    extraGroups = [ \"wheel\" \"networkmanager\" \"video\" \"audio\" ];\n"
        f"    hashedPasswordFile = {nix_string('/etc/user-passwords/' + request['username'])};\n"
        "  };\n}\n")
    phase(20, "Installing NixOS using the configured binary caches")
    run("nixos-install", "--flake", "/mnt/etc/nixos#installed", "--no-root-passwd", "--no-channel-copy", "--option", "accept-flake-config", "false")
    phase(95, "Flushing files and exporting the ZFS pool")
    run("sync")
    run("umount", "-R", "/mnt")
    run("zpool", "export", "rpool")
    phase(100, "Installation complete")


def main():
    # Reject truncated/oversized or additional requests before any disk mutation.
    raw = sys.stdin.read(65537)
    if len(raw) > 65536:
        raise ValueError("Installation request is too large")
    request = json.loads(raw)
    with open("/run/nixos-zfs-installer.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another installation is already running") from error
        install(request)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Installation failed: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
