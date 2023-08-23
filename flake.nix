{
  description = "A flake to build timetagger";

  inputs = {
    # pulls in the flake.nix file from this github repo    
    nixpkgs.url = "github:nixos/nixpkgs/nixos-23.05";
    speechrecognition.url = "git+ssh://git@github.com/Adam-D-Lewis/speech_recognition_flake.git?ref=main";
  };

  outputs = inputs@{ self, nixpkgs, speechrecognition }:
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
    {
      defaultPackage.x86_64-linux = pkgs.python3Packages.buildPythonPackage {
        pname = "voicetype";
        version = "latest";
        format = "pyproject";

        src = ./.;

        propagatedBuildInputs = runtimeDependencies;
        # buildInputs = [buildtimePythonDependencies];
        nativeBuildInputs = buildtimePythonDependencies;
        doCheck = false;
      };

      # packages.${system} = {
      #   output1 = pkgs.writeScriptBin "myscript" ''
      #     export PATH=${pkgs.lib.makeBinPath runtimeSystemDependencies}:$PATH
      #     ${pythonRuntimeEnv}/bin/python /home/balast/CodingProjects/voicetype/main.py
      #   '';
      # };

      # defaultPackage.x86_64-linux = self.packages.${system}.output1;

      # develop
      devShell.x86_64-linux = pkgs.mkShell {
        buildInputs = runtimeDependencies ++ devDependencies;
      };
    };
}
