{
  description = "voicetype flake";

  inputs = {
    # pulls in the flake.nix file from this github repo
    nixpkgs.url = "github:nixos/nixpkgs/nixos-23.11";
    speechrecognition.url = "git+ssh://git@github.com/Adam-D-Lewis/speech_recognition_flake.git?ref=main";
    speechrecognition.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs@{ self, nixpkgs, speechrecognition, ... }:
    let
      my_overlays = [
        (self: super: {
          # nix-shell -p python.pkgs.my_stuff
          python3 = super.python3.override {
            # Careful, we're using a different self and super here!
            packageOverrides = self: super: {
              speech_recognition = speechrecognition.speech_recognition;
            };
          };
        })
      ];
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        overlays = my_overlays;
      };

      # Bulidtime dependencies
      buildtimePythonDependencies = with pkgs.python3Packages; [
        setuptools
      ];
      # Runtime dependencies
      runtimePythonDependencies = pypkgs: with pypkgs; [
        fastapi
        uvicorn
        speech_recognition
        pyaudio
        pynput
      ];
      runtimeSystemDependencies = with pkgs; [
        portaudio
        flac
      ];
      pythonRuntimeEnv = pkgs.python3.withPackages runtimePythonDependencies;
      runtimeDependencies = with pkgs; [
        pythonRuntimeEnv
      ] ++ runtimeSystemDependencies;

      # Development dependencies
      devPythonDependencies = pypkgs: with pypkgs; [
        pytest
      ];
      devSystemDependencies = with pkgs; [
        vlc
        ruff
      ];

      devDependencies = with pkgs; [
        (pkgs.python3.withPackages devPythonDependencies)
      ] ++ devSystemDependencies;

    in
    rec {
      voiceType = pkgs.python3Packages.buildPythonPackage {
        pname = "voicetype";
        version = "latest";
        format = "pyproject";

        src = ./.;

        propagatedBuildInputs = runtimeDependencies;
        # buildInputs = [buildtimePythonDependencies];
        nativeBuildInputs = buildtimePythonDependencies;
        doCheck = false;
      };
      defaultPackage.x86_64-linux = voiceType;

      # modules
      # nixosModules.voicetype = import ./voicetype-user-service.nix;
      nixosModules.default = { config, lib, pkgs, ... }:

        with lib;

        let
          cfg = config.services.voicetype;
        in
        {
          options = {
            services.voicetype = {
              enable = mkEnableOption "VoiceType Service";

              package = mkOption {
                type = types.package;
                default = voiceType;
                description = "The voicetype package to use.";
              };
            };
          };

          config = mkIf cfg.enable {
            systemd.user.services.voicetype = {
              Unit = {
                Description = "VoiceType Service";
                After = [ "network.target" ];
              };

              Install = {
                WantedBy = [ "default.target" ];
              };

              Service = {
                Type = "simple";
                ExecStart = "${pkgs.bash}/bin/bash -lc 'env; ${cfg.package}/bin/voicetype'";
                Restart = "always";
              };
            };
          };
        };

          # develop
          devShell.x86_64-linux = pkgs.mkShell {
      buildInputs = runtimeDependencies ++ devDependencies ++ [ voiceType ];
    };
};
}
