{
  config,
  inputs,
  lib,
  modulesPath,
  pkgs,
  ...
}:
let
  python = pkgs.python3.withPackages (ps: [ ps.pyside6 ]);
  installer = pkgs.stdenvNoCC.mkDerivation {
    pname = "nixos-zfs-installer";
    version = "2.0.0";
    src = ../installer;
    nativeBuildInputs = [ pkgs.makeWrapper ];
    dontBuild = true;
    installPhase = ''
      mkdir -p $out/share/nixos-zfs-installer $out/bin $out/share/applications
      cp *.py $out/share/nixos-zfs-installer/
      cp ${../scripts/prepare-zfs.sh} $out/share/nixos-zfs-installer/prepare-zfs.sh
      makeWrapper ${python}/bin/python $out/bin/nixos-zfs-installer \
        --add-flags $out/share/nixos-zfs-installer/gui.py \
        --set QT_QPA_PLATFORM wayland \
        --prefix QT_PLUGIN_PATH : ${pkgs.qt6.qtwayland}/${pkgs.qt6.qtbase.qtPluginPrefix} \
        --prefix PATH : ${
          lib.makeBinPath [
            pkgs.mkpasswd
            pkgs.gptfdisk
            pkgs.dosfstools
            pkgs.util-linux
          ]
        }
      cat > $out/share/applications/nixos-zfs-installer.desktop <<EOF
      [Desktop Entry]
      Type=Application
      Name=Install NixOS (ZFS)
      Name[ja]=NixOSをインストール (ZFS)
      Exec=$out/bin/nixos-zfs-installer
      Icon=drive-harddisk
      Categories=System;
      Terminal=false
      EOF
    '';
  };
in
{
  imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-graphical-base.nix" ];
  services.xserver.enable = lib.mkForce false;
  services.greetd.settings.initial_session = {
    user = "nixos";
    command = "/run/current-system/sw/bin/nixos-umbriel-session";
  };

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
    Umbriel + Noctalia v5 graphical ZFS installer.
  '';
  environment.systemPackages = [
    installer
    pkgs.mkpasswd
  ];
  system.build.installerApp = installer;
  systemd.user.services.zfs-installer = {
    description = "Graphical NixOS ZFS installation wizard";
    wantedBy = [ "graphical-session.target" ];
    after = [
      "graphical-session.target"
      "noctalia.service"
    ];
    partOf = [ "graphical-session.target" ];
    serviceConfig = {
      ExecStart = "${installer}/bin/nixos-zfs-installer";
      Restart = "no";
    };
  };
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
    umbriel = config.programs.umbriel.package.version;
    noctalia = config.programs.noctalia.package.version;
  };
}
