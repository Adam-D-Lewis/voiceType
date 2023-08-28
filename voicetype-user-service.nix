# { config, lib, pkgs, ... }:

# with lib;

# let
#   cfg = config.services.voicetype;
# in
# {
#   options = {
#     services.voicetype = {
#       enable = mkEnableOption "VoiceType Service";

#       package = mkOption {
#         type = types.package;
#         default = pkgs.voiceType;
#         description = "The voicetype package to use.";
#       };
#     };
#   };

#   config = mkIf cfg.enable {
#     systemd.user.services.voicetype = {
#       Unit = {
#         Description = "VoiceType Service";
#         After = [ "network.target" ];
#       };

#       Install = {
#         WantedBy = [ "default.target" ];
#       };

#       Service = {
#         Type = "simple";
#         ExecStart = "${pkgs.bash}/bin/bash -lc 'env; nix run path:${cfg.package}'";
#         Restart = "always";
#       };
#     };
#   };
# }
