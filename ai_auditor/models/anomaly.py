from django.db import models
from .audit_engagement import AuditEngagement


class Anomaly(models.Model):
    engagement = models.ForeignKey(
        AuditEngagement,
        on_delete=models.CASCADE,
        related_name="anomalies",
    )
    source_system = models.CharField(max_length=50)
    reference_id = models.CharField(max_length=100)
    score = models.FloatField()
    category = models.CharField(max_length=100)
    summary = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]

