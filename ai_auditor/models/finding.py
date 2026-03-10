from django.db import models
from .audit_engagement import AuditEngagement


class Finding(models.Model):
    engagement = models.ForeignKey(
        AuditEngagement,
        on_delete=models.CASCADE,
        related_name="findings",
    )
    title = models.CharField(max_length=255)
    severity = models.CharField(
        max_length=20,
        choices=(
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ),
    )
    narrative = models.TextField()
    recommendations = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

