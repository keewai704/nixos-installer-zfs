{ inputs, pkgs, ... }:
{
  nixpkgs.config.allowUnfreePredicate = pkg: (pkgs.lib.getName pkg) == "claude-code";
  nixpkgs.overlays = [
    inputs.claude-code.overlays.default
    inputs.codex.overlays.default
  ];
  environment.systemPackages = with pkgs; [
    claude-code
    codex
    git
    gh
    curl
    jq
    ripgrep
    nano
    tmux
    parted
    gptfdisk
    dosfstools
  ];
}
