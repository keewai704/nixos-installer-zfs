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
        # Keep installed-system packages in the Actions cache as well as the ISO.
        install-closure = installed.config.system.build.toplevel;
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
