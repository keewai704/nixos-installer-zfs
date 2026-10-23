#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Internal GUI worker: prepare-zfs.sh --disk DEVICE --hostname HOST --prepare-only

Single-disk, UEFI installation. ERASES THE ENTIRE SELECTED DISK.
Creates a 1 GiB FAT32 ESP and rpool/{root,home,nix} ZFS datasets.
Requires typing "ERASE /dev/DEVICE" before any disk modification.
Only prepares /mnt and generates /mnt/etc/nixos. Invoked by the graphical installer.
EOF
}

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
disk=""
hostname="nixos"
prepare_only=false
while (( $# )); do
  case "$1" in
    --disk) (( $# >= 2 )) || die "--disk needs a value"; disk=$2; shift 2 ;;
    --hostname) (( $# >= 2 )) || die "--hostname needs a value"; hostname=$2; shift 2 ;;
    --prepare-only) prepare_only=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ $EUID == 0 ]] || die "Run with sudo."
"$prepare_only" || die "This worker only prepares disks for the graphical installer."
[[ -n $disk ]] || die "Specify --disk; use lsblk to identify the target."
[[ $hostname =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || die "Invalid hostname."
[[ -d /sys/firmware/efi ]] || die "Boot the ISO in UEFI mode to install."
disk=$(readlink -f -- "$disk")
[[ -b $disk ]] || die "Not a block device: $disk"
[[ $(lsblk -dnro TYPE "$disk") == disk ]] || die "Select a whole disk."
[[ $(blockdev --getro "$disk") == 0 ]] || die "Disk is read-only."
(( $(blockdev --getsize64 "$disk") >= 32 * 1024 * 1024 * 1024 )) || die "Disk must be at least 32 GiB."
if lsblk -nrpo MOUNTPOINTS "$disk" | grep -q '[^[:space:]]'; then
  die "The disk or one of its partitions is mounted or used as swap."
fi
if lsblk -nro TYPE "$disk" | grep -Evq '^(disk|part)$'; then
  die "The disk has active device-mapper, RAID or other holders."
fi
if findmnt --mountpoint /mnt >/dev/null; then die "/mnt is already mounted."; fi
modprobe zfs
if zpool list -H -o name 2>/dev/null | grep -qx rpool; then die "rpool is already imported."; fi
while IFS= read -r member; do
  if lsblk -srnpo NAME "$member" | grep -Fxq -- "$disk"; then
    die "The disk belongs to an imported ZFS pool. Export that pool first."
  fi
done < <(zpool status -LP 2>/dev/null | awk '$1 ~ /^\/dev\// { print $1 }')
[[ -d /etc/nixos-installer/source ]] || die "Run from this installer ISO."

lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS "$disk"
printf '\nAll data on %s will be erased. Type "ERASE %s": ' "$disk" "$disk"
IFS= read -r confirmation
[[ $confirmation == "ERASE $disk" ]] || die "Confirmation did not match; nothing was changed."

esp_uuid=$(cat /proc/sys/kernel/random/uuid)
zfs_uuid=$(cat /proc/sys/kernel/random/uuid)
sgdisk --zap-all "$disk"
sgdisk --clear --new=1:0:+1G --typecode=1:ef00 --change-name=1:NIXOS_EFI \
  --partition-guid="1:$esp_uuid" --new=2:0:0 --typecode=2:bf01 \
  --change-name=2:NIXOS_ZFS --partition-guid="2:$zfs_uuid" "$disk"
blockdev --rereadpt "$disk"
udevadm settle
esp="/dev/disk/by-partuuid/$esp_uuid"
zfs_partition="/dev/disk/by-partuuid/$zfs_uuid"
[[ -b $esp && -b $zfs_partition ]] || die "Partition devices did not appear."
wipefs --all "$esp" "$zfs_partition"

zpool create -o ashift=12 -o autotrim=on -O compression=zstd -O atime=off \
  -O xattr=sa -O acltype=posixacl -O mountpoint=none -R /mnt rpool "$zfs_partition"
zfs create -o mountpoint=legacy rpool/root
zfs create -o mountpoint=legacy rpool/home
zfs create -o mountpoint=legacy rpool/nix
mount -t zfs rpool/root /mnt
mkdir -p /mnt/boot /mnt/home /mnt/nix
mount -t zfs rpool/home /mnt/home
mount -t zfs rpool/nix /mnt/nix
mkfs.fat -F 32 -n NIXOS_EFI "$esp"
mount -o umask=0077 "$esp" /mnt/boot
mkdir -p /mnt/etc/nixos
cp -a /etc/nixos-installer/source/. /mnt/etc/nixos/
chmod -R u+w /mnt/etc/nixos
nixos-generate-config --root /mnt
host_id=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
printf '{ ... }: { networking.hostName = "%s"; networking.hostId = "%s"; }\n' \
  "$hostname" "$host_id" > /mnt/etc/nixos/machine.nix

printf '\nZFS datasets prepared for the graphical installation worker.\n'
