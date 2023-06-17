{
  description = "A flake to build timetagger";

  inputs = {
    # pulls in the flake.nix file from this github repo    
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    speechrecognition.url = "git+ssh://git@github.com:Adam-D-Lewis/speech_recognition_flake.git?ref=main";
  };

  outputs = inputs@{ self, nixpkgs, speechrecognition }: rec {
    my_overlay = self: super: {
      # nix-shell -p python.pkgs.my_stuff
      python3 = super.python3.override {
        # Careful, we're using a different self and super here!
        packageOverrides = self: super: {
          speech_recognition = speechrecognition.speech_recognition;
        };
      };
    };

    # I'm not sure why I need to import nixpkgs in order for python3Packages to appear. 
    pkgs = import nixpkgs {
      system = "x86_64-linux";
      overlays = [ my_overlay ];
    };
    timetagger = pkgs.python3Packages.buildPythonPackage {
      pname = "timetagger";
      version = "v22.1.3";
      src = pkgs.fetchFromGitHub {
        owner = "almarklein";
        repo = "timetagger";
        rev = "e3526da61c32276d315056483f6b3cfa03d4b657";
        sha256 = "RMQ4l/mmE4/LpNhYbuibAfItLczRbE4fSSa6aHnyEPQ=";
      };
      # pythonImportsCheck = [ "timetagger" ]; 
      propagatedBuildInputs = with pkgs.python3Packages; [
        speechrecognition.speech_recognition
        keyboard
      ];
      checkPhase = ''
        runHook preCheck
        runHook postCheck
      '';
    };
    legacyPackages.x86_64-linux = { 
      # inherit timetagger; 
    };
    # defaultPackage.x86_64-linux = legacyPackages.x86_64-linux.timetagger;

    # develop
    devShell.x86_64-linux = pkgs.mkShell {
      buildInputs =
        [ (pkgs.python3.withPackages (pypkgs: with pypkgs; [ ])) ];
    };
  };
}
