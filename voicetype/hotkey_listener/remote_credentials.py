"""TLS certificate and shared token for the remote hotkey listener.

The remote device (e.g. a Pico 2 W) pins the self-signed certificate, so it only
talks to this machine, and proves itself to voiceType with the shared token.
"""

import os
import secrets
import shutil
import socket
import ssl
import subprocess
from pathlib import Path

# Name the device checks the certificate against (its server_hostname). The
# certificate is pinned, so this name doesn't have to resolve anywhere; it only
# has to be in the certificate. That way the device can reach this machine by
# hostname, .local name, or IP address without changing the certificate.
TLS_NAME = "voicetype"

MIN_TOKEN_LENGTH = 16

SETUP_HINT = "Run `voicetype remote-setup` to create it."


class RemoteCredentialsError(RuntimeError):
    """The remote listener's certificate, key, or token is missing or unusable."""


def certificate_names() -> list[str]:
    """Names for the certificate: the fixed TLS name plus this machine's hostnames."""
    hostname = socket.gethostname()
    names = [TLS_NAME, hostname, f"{hostname}.local", "localhost"]
    return list(dict.fromkeys(name for name in names if name))


def _write_private(path: Path, text: str) -> None:
    """Write a file only the current user can read."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def generate_credentials(
    cert_file: Path, key_file: Path, token_file: Path, force: bool = False
) -> list[Path]:
    """Create the token and a self-signed certificate + key, keeping existing ones.

    Args:
        cert_file: Where to write the certificate (PEM)
        key_file: Where to write the private key (PEM)
        token_file: Where to write the shared token
        force: Replace files that already exist

    Returns:
        The files that were written.

    Raises:
        RemoteCredentialsError: If the certificate can't be created.
    """
    for path in (cert_file, key_file, token_file):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    written = []
    if force or not token_file.exists():
        _write_private(token_file, secrets.token_urlsafe(32) + "\n")
        written.append(token_file)

    if force or not (cert_file.exists() and key_file.exists()):
        openssl = shutil.which("openssl")
        if openssl is None:
            raise RemoteCredentialsError(
                "The `openssl` command is needed to create the certificate. "
                "Install it and try again."
            )
        subject_alt_names = ",".join(f"DNS:{name}" for name in certificate_names())
        # RSA works with every CircuitPython TLS build. CircuitPython doesn't
        # check certificate dates (its clock isn't set), so the long lifetime
        # only matters to other clients such as scripts/fake_pico.py.
        command = [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-days",
            "3650",
            "-subj",
            f"/CN={TLS_NAME}",
            "-addext",
            f"subjectAltName={subject_alt_names}",
            "-keyout",
            str(key_file),
            "-out",
            str(cert_file),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RemoteCredentialsError(
                f"openssl failed to create the certificate: {e.stderr.strip()}"
            ) from e
        os.chmod(key_file, 0o600)
        written += [cert_file, key_file]

    return written


def load_token(token_file: Path) -> str:
    """Read the shared token the remote device must send.

    Raises:
        RemoteCredentialsError: If the token is missing or too short.
    """
    try:
        token = token_file.read_text().strip()
    except FileNotFoundError:
        raise RemoteCredentialsError(
            f"Remote token file not found: {token_file}. {SETUP_HINT}"
        ) from None
    if len(token) < MIN_TOKEN_LENGTH:
        raise RemoteCredentialsError(
            f"The remote token in {token_file} is too short (need at least "
            f"{MIN_TOKEN_LENGTH} characters). {SETUP_HINT}"
        )
    return token


def create_server_ssl_context(cert_file: Path, key_file: Path) -> ssl.SSLContext:
    """Build the TLS context the remote listener serves with.

    Raises:
        RemoteCredentialsError: If the certificate or key is missing.
    """
    for path in (cert_file, key_file):
        if not path.exists():
            raise RemoteCredentialsError(
                f"Remote TLS file not found: {path}. {SETUP_HINT}"
            )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # CircuitPython's TLS stack only speaks TLS 1.2
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    return context
