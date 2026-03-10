from django.db import models

from tenant_integrations.crypto import encrypt_secret, decrypt_secret


class OutboundWebhook(models.Model):
    name = models.CharField(max_length=120)
    url = models.URLField()
    is_active = models.BooleanField(default=True)
    # Optional shared secret (stored encrypted)
    secret_enc = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def set_secret(self, raw: str) -> None:
        self.secret_enc = encrypt_secret(raw or "")

    def get_secret(self):
        return decrypt_secret(self.secret_enc)

    def __str__(self) -> str:
        return self.name


class ErpConnection(models.Model):
    """
    Minimal external integration record (tenant DB). Secrets are stored encrypted.
    """

    class Provider(models.TextChoices):
        GENERIC = "generic", "Generic ERP"
        DYNAMICS = "dynamics", "Microsoft Dynamics"
        NETSUITE = "netsuite", "NetSuite"

    provider = models.CharField(max_length=30, choices=Provider.choices, default=Provider.GENERIC)
    name = models.CharField(max_length=120)
    base_url = models.URLField(blank=True)
    api_key_enc = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def set_api_key(self, raw: str) -> None:
        self.api_key_enc = encrypt_secret(raw or "")

    def get_api_key(self):
        return decrypt_secret(self.api_key_enc)

    def __str__(self) -> str:
        return self.name
