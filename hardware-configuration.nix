# Evaluation example only. install-zfs replaces this with nixos-generate-config.
{ ... }:
{
  fileSystems."/" = {
    device = "rpool/root";
    fsType = "zfs";
  };
  fileSystems."/home" = {
    device = "rpool/home";
    fsType = "zfs";
  };
  fileSystems."/nix" = {
    device = "rpool/nix";
    fsType = "zfs";
  };
  fileSystems."/boot" = {
    device = "/dev/disk/by-label/NIXOS_EFI";
    fsType = "vfat";
    options = [
      "fmask=0077"
      "dmask=0077"
    ];
  };
  nixpkgs.hostPlatform = "x86_64-linux";
}
