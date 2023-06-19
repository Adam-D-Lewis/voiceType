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
      python = pkgs.python3.withPackages (
        pypkgs: with pypkgs; [
          speech_recognition
          pyaudio
          pynput
        ]
      );
    in
    {
      packages.${system} = {
        output1 = pkgs.writeScriptBin "myscript" ''
          export PATH=${pkgs.lib.makeBinPath (with pkgs; [ portaudio flac ])}:$PATH
          ${python}/bin/python /home/balast/CodingProjects/voicetype/main.py
        '';
      };

      defaultPackage.x86_64-linux = self.packages.${system}.output1;

      # develop
      devShell.x86_64-linux = pkgs.mkShell {
        buildInputs =
          [
            (pkgs.python3.withPackages (pypkgs: with pypkgs; [
              speech_recognition
              pyaudio
              pynput
            ]))
          ] ++ (with pkgs; [ portaudio flac vlc]);
      };
    };
}
