"""Auto-generate a self-signed certificate for HTTPS (Mockoon-style).

Certs are regenerated only when the files are missing.  Once generated they
persist across restarts.

Two backends are supported (tried in order):

1. ``cryptography`` library  –  pure-Python, cross-platform, preferred.
2. ``openssl`` CLI           –  fallback when cryptography is unavailable.
"""
from __future__ import annotations

import datetime
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_cert(certfile: str, keyfile: str) -> tuple[str, str]:
    """Return (certfile, keyfile), generating both if they do not exist.

    The self-signed certificate has CN=127.0.0.1 with SAN entries for
    ``localhost`` and ``127.0.0.1`` so it works both by hostname and IP.
    Validity is 3650 days (~10 years).
    """
    cert_path = Path(certfile)
    key_path = Path(keyfile)

    if cert_path.exists() and key_path.exists():
        logger.info("SSL cert found: %s", cert_path)
        return certfile, keyfile

    logger.info("SSL cert not found – generating self-signed certificate …")
    cert_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _generate_with_cryptography(cert_path, key_path)
    except ImportError:
        logger.info("cryptography not available – falling back to openssl")
        _generate_with_openssl(cert_path, key_path)

    logger.info("SSL cert written: %s", cert_path)
    return certfile, keyfile


# ---- cryptography backend ------------------------------------------------

def _generate_with_cryptography(cert_path: Path, key_path: Path) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress.from_text("127.0.0.1"),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


# ---- openssl CLI fallback ------------------------------------------------

def _generate_with_openssl(cert_path: Path, key_path: Path) -> None:
    """Generate a self-signed cert via the ``openssl`` CLI.

    Equivalent to::

        openssl req -x509 -newkey rsa:2048 -nodes \\
          -keyout key.pem -out cert.pem -days 3650 \\
          -subj "/CN=127.0.0.1" \\
          -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
    """
    # Write a minimal OpenSSL config snippet for SAN because `-addext` is
    # only available in OpenSSL ≥ 1.1.1.  Using a config file is more
    # portable across versions.
    config_lines = [
        "[req]",
        "distinguished_name = req_distinguished_name",
        "x509_extensions = v3_req",
        "prompt = no",
        "[req_distinguished_name]",
        "CN = 127.0.0.1",
        "[v3_req]",
        "subjectAltName = DNS:localhost,IP:127.0.0.1",
    ]
    config_path = cert_path.with_suffix(".cnf")
    config_path.write_text("\n".join(config_lines), encoding="utf-8")

    try:
        _run_openssl(
            "req",
            "-x509",
            "-newkey", "rsa:2048",
            "-nodes",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-days", "3650",
            "-config", str(config_path),
        )
    finally:
        # Clean up the temp config – it is not needed after generation.
        try:
            os.unlink(config_path)
        except OSError:
            pass


def _run_openssl(*args: str) -> None:
    cmd = ["openssl", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        print(
            "ERROR: OpenSSL is not available on this system.\n"
            "  • Install OpenSSL and ensure it is on your PATH, or\n"
            "  • Install the Python 'cryptography' package:\n"
            "      pip install cryptography\n"
            "  • Or generate the cert/key manually and place them at the paths\n"
            "    shown above.",
            file=sys.stderr,
        )
        sys.exit(1)

    if proc.returncode != 0:
        print(
            f"ERROR: openssl failed (exit {proc.returncode})\n"
            f"stderr: {proc.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
