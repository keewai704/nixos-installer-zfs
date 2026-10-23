{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
let
  noctaliaConfig = pkgs.writeText "noctalia-config.toml" ''
    [shell]
    telemetry_enabled = false
    polkit_agent = true
    setup_wizard_enabled = false
    launch_apps_as_systemd_services = true
    [shell.launcher]
    fetch_exchange_rates = false
    [theme]
    mode = "dark"
    source = "builtin"
    builtin = "Catppuccin"
    [bar.main]
    margin_ends = 12
    start = ["launcher", "workspaces"]
    center = ["clock"]
    end = ["tray", "network", "volume", "battery", "control-center", "session"]
    [idle.behavior.lock]
    enabled = false
    [idle.behavior.screen-off]
    enabled = false
  '';
  session = pkgs.writeShellScriptBin "nixos-umbriel-session" ''
    set -eu
    config_dir="''${XDG_CONFIG_HOME:-$HOME/.config}/noctalia"
    if [ ! -e "$config_dir/config.toml" ]; then
      mkdir -p "$config_dir"
      cp ${noctaliaConfig} "$config_dir/config.toml"
      chmod u+w "$config_dir/config.toml"
    fi
    exec ${config.programs.umbriel.package}/bin/start-umbriel
  '';
  sessionEntry =
    pkgs.runCommand "umbriel-noctalia-session"
      {
        passthru.providedSessions = [ "umbriel-noctalia" ];
      }
      ''
        mkdir -p $out/share/wayland-sessions
        cat > $out/share/wayland-sessions/umbriel-noctalia.desktop <<EOF
        [Desktop Entry]
        Name=Umbriel + Noctalia v5
        Comment=Umbriel with the native Noctalia v5 desktop shell
        Exec=${session}/bin/nixos-umbriel-session
        Type=Application
        DesktopNames=umbriel
        EOF
      '';
in
{
  imports = [
    inputs.umbriel.nixosModules.default
    inputs.noctalia.nixosModules.default
  ];
  programs.umbriel.enable = true;
  programs.noctalia = {
    enable = true;
    systemd.enable = true;
    recommendedServices.enable = true;
  };
  assertions = [
    {
      assertion = lib.versions.major config.programs.noctalia.package.version == "5";
      message = "This installer requires native Noctalia v5.";
    }
  ];
  services.displayManager.regreet.enable = true;
  services.displayManager.sessionPackages = lib.mkForce [ sessionEntry ];
  services.displayManager.defaultSession = "umbriel-noctalia";
  services.pipewire = {
    enable = true;
    pulse.enable = true;
  };
  security.rtkit.enable = true;
  xdg.portal.extraPortals = [ pkgs.xdg-desktop-portal-gtk ];
  # Permit llvmpipe on machines/VMs without an accelerated driver.
  environment.sessionVariables.WLR_RENDERER_ALLOW_SOFTWARE = "1";
  environment.systemPackages = [
    session
    pkgs.foot
    pkgs.networkmanagerapplet
    pkgs.xwayland
    pkgs.wayland-utils
    pkgs.grim
  ];
  fonts.packages = [
    pkgs.noto-fonts
    pkgs.noto-fonts-cjk-sans
  ];
  environment.etc."xdg/umbriel/config.toml".text = ''
    [general]
    xwayland = true
    show_cheatsheet = false
    [appearance]
    border_width = 2
    corner_radius = 12
    [appearance.blur]
    enabled = false
    [input.keyboard]
    layout = "${config.services.xserver.xkb.layout}"
    [keybinds]
    "Mod" = "spawn:noctalia msg panel-toggle launcher"
    "Mod+Return" = "spawn:foot"
    "Mod+Q" = "window-close"
    "Mod+F" = "window-toggle-fullscreen"
    "Mod+T" = "window-toggle-floating"
    "Mod+1" = "workspace-switch:1"
    "Mod+2" = "workspace-switch:2"
    "Mod+3" = "workspace-switch:3"
    "Mod+Shift+1" = "window-move-to-workspace:1"
    "Mod+Shift+2" = "window-move-to-workspace:2"
    "Mod+Shift+3" = "window-move-to-workspace:3"
  '';
}
