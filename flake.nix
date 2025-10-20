{
  description = "pixi env";
  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs =
    { flake-utils, nixpkgs, ... }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        fhs = pkgs.buildFHSEnv {
          name = "pixi-env";

          targetPkgs = pkgs: [
            pkgs.pixi
            pkgs.linuxHeaders
            pkgs.gcc
            pkgs.stdenv.cc.cc.lib
            pkgs.portaudio
            pkgs.ffmpeg
            pkgs.gtk3
            pkgs.gobject-introspection
            pkgs.cairo
            pkgs.gdk-pixbuf
            pkgs.atk
            pkgs.pango
          ];

          profile = ''
            export CC=gcc
            export CXX=g++
            export GI_TYPELIB_PATH="${pkgs.gtk3}/lib/girepository-1.0:${pkgs.gobject-introspection}/lib/girepository-1.0"
          '';
        };
      in
      {
        devShell = fhs.env;
      }
    );
}
