"""
Optional TOTP 2FA for tenant users. Requires: pip install pyotp
QR code optional: pip install qrcode[pil]
"""


def get_totp(secret: str):
    """Return TOTP instance for secret. Returns None if pyotp not installed."""
    try:
        import pyotp
        if not secret:
            return None
        return pyotp.TOTP(secret)
    except ImportError:
        return None


def generate_secret():
    """Generate a new base32 TOTP secret."""
    try:
        import pyotp
        return pyotp.random_base32()
    except ImportError:
        return None


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Allows 1 step drift for clock skew."""
    totp = get_totp(secret)
    if not totp or not code or len(code.strip()) != 6:
        return False
    try:
        return totp.verify(code.strip(), valid_window=1)
    except Exception:
        return False


def get_provisioning_uri(secret: str, email: str, issuer: str = "Sugna Tenant") -> str:
    """URI for authenticator app (manual entry or QR)."""
    totp = get_totp(secret)
    if not totp:
        return ""
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def get_qr_data_url(provisioning_uri: str) -> str:
    """Return data URL for QR code image, or empty string if qrcode not available."""
    if not provisioning_uri:
        return ""
    try:
        import qrcode
        import io
        import base64
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""
