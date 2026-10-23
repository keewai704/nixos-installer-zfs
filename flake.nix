{
  description = "NixOS ZFS installer with xddxdd's CachyOS kernel and coding tools";

  inputs = {
    cachyos.url = "github:xddxdd/nix-cachyos-kernel/release";
    # Keep the kernel, ZFS and NixOS module aggregation on a compatible revision.
    # Do not override the CachyOS flake's own nixpkgs input.
    nixpkgs.follows = "cachyos/nixpkgs";
    claude-code = {
      url = "github:sadjow/claude-code-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    codex = {
      url = "github:sadjow/codex-cli-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    { self, nixpkgs, ... }@inputs:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      installer = nixpkgs.lib.nixosSystem {
        inherit system;
        specialArgs = { inherit inputs; };
        modules = [
          ./modules/cachyos-zfs.nix
          ./modules/tools.nix
          ./modules/installer.nix
        ];
      };
      installed = nixpkgs.lib.nixosSystem {
        inherit system;
        specialArgs = { inherit inputs; };
        modules = [
          ./modules/cachyos-zfs.nix
          ./modules/tools.nix
          ./modules/installed.nix
          ./hardware-configuration.nix
          ./machine.nix
        ];
      };
    in
    {
      nixosConfigurations = { inherit installer installed; };
      nixosModules.cachyos-zfs = import ./modules/cachyos-zfs.nix;
      packages.${system} = {
        default = self.packages.${system}.iso;
        iso = installer.config.system.build.isoImage;
        # Prime the VM's store for an offline installation of the same modules.
        # The test still builds/installs the generated, machine-specific flake.
        install-closure = installed.config.system.build.toplevel;
        install-build-inputs = pkgs.buildEnv {
          name = "installation-build-inputs";
          ignoreCollisions = true;
          paths = with pkgs; [
            stdenvNoCC
            bash
            coreutils
            findutils
            gnugrep
            gnused
            gawk
            diffutils
            perl
            python3Minimal
            jq
            cpio
            gzip
            bzip2
            xz
            zstd
            kmod
            rsync
            makeInitrdNGTool
            systemd
            nixos-install-tools
          ];
        };
      };
      formatter.${system} = pkgs.nixfmt;
      devShells.${system}.ci = pkgs.mkShellNoCC {
        packages = [
          (pkgs.python3.withPackages (ps: [ ps.pexpect ]))
          pkgs.qemu
          pkgs.shellcheck
          pkgs.nixfmt
        ];
        OVMF_CODE = "${pkgs.OVMF.fd}/FV/OVMF_CODE.fd";
        OVMF_VARS = "${pkgs.OVMF.fd}/FV/OVMF_VARS.fd";
      };
    };
}
