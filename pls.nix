{ nixpkgs ? import <nixpkgs> { } }:

with nixpkgs;

{
  pls = pkgs.writeShellScriptBin "pls" ''
    ${go-task}/bin/go-task "$@"
  '';
  please = pkgs.writeShellScriptBin "please" ''
    ${go-task}/bin/go-task "$@"
  '';
  plz = pkgs.writeShellScriptBin "plz" ''
    ${go-task}/bin/go-task "$@"
  '';
  pl0x = pkgs.writeShellScriptBin "pl0x" ''
    ${go-task}/bin/go-task "$@"
  '';
}
