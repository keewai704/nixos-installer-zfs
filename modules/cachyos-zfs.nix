{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
{
  nixpkgs.overlays = [ inputs.cachyos.overlays.pinned ];
  boot.kernelPackages = pkgs.cachyosKernels.linuxPackages-cachyos-latest;
  boot.supportedFilesystems.zfs = true;
  boot.zfs.package = config.boot.kernelPackages.zfs_cachyos;
  boot.zfs.forceImportRoot = false;

  # Never silently substitute another kernel or mismatched ZFS implementation.
  assertions = [
    {
      assertion = lib.hasInfix "cachyos" config.boot.kernelPackages.kernel.pname;
      message = "The installer must use xddxdd's CachyOS kernel.";
    }
  ];
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
}
