{
  config,
  inputs,
  lib,
  modulesPath,
  pkgs,
  ...
}:
{
  imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix" ];

  networking.hostName = "nixos-zfs-installer";
  # This ID belongs only to the live environment, not the installed machine.
  networking.hostId = "8425a701";
  boot.kernelModules = [ "zfs" ];
  boot.kernelParams = [
    "console=tty0"
    "console=ttyS0,115200n8"
  ];
  boot.loader.timeout = lib.mkForce 5;
  image.baseName = lib.mkForce "nixos-zfs-cachyos-x86_64-linux";
  isoImage.volumeID = "NIXOS_ZFS";
  isoImage.makeEfiBootable = true;
  isoImage.makeUsbBootable = true;
  # Keep GitHub runner disk/RAM usage bounded while making the live image.
  isoImage.squashfsCompression = "zstd -Xcompression-level 6";

  documentation.enable = lib.mkForce false;
  documentation.nixos.enable = lib.mkForce false;
  programs.bash.promptInit = ''
    PS1='installer> '
  '';
  services.getty.helpLine = lib.mkAfter ''
    ZFS + xddxdd CachyOS installer. Run: sudo install-zfs --help
    Source and pinned installation configuration: /etc/nixos-installer/source
    Versions: /etc/nixos-installer/versions.json
  '';
  environment.systemPackages = [
    (pkgs.writeShellApplication {
      name = "install-zfs";
      runtimeInputs = with pkgs; [
        coreutils
        util-linux
        gptfdisk
        dosfstools
      ];
      text = builtins.readFile ../scripts/install-zfs.sh;
    })
  ];
  system.stateVersion = "26.05";
  environment.etc."nixos-installer/source".source = inputs.self.outPath;
  environment.etc."nixos-installer/versions.json".text = builtins.toJSON {
    kernel = config.boot.kernelPackages.kernel.modDirVersion;
    zfs = config.boot.zfs.package.version;
    nixpkgs = inputs.nixpkgs.rev;
    cachyos = inputs.cachyos.rev;
    claudeCode = pkgs.claude-code.version;
    codex = pkgs.codex.version;
    git = pkgs.git.version;
    githubCli = pkgs.gh.version;
  };
}
