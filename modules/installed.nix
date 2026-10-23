{ lib, ... }:
{
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = false;
  boot.initrd.availableKernelModules = [
    "ahci"
    "nvme"
    "sd_mod"
    "usb_storage"
    "xhci_pci"
    "virtio_pci"
    "virtio_blk"
  ];
  boot.zfs.devNodes = "/dev/disk/by-partuuid";
  boot.kernelParams = [
    "console=ttyS0,115200n8"
    "console=tty0"
  ];
  networking.networkmanager.enable = true;
  networking.hostName = lib.mkDefault "nixos";
  services.zfs.autoScrub.enable = true;
  documentation.enable = false;
  system.stateVersion = "26.05";
}
