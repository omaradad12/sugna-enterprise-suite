from rest_framework import serializers

from ai_auditor.models import AuditEngagement, Anomaly, Finding


class AuditEngagementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEngagement
        fields = ["id", "name", "period_start", "period_end"]


class AnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = Anomaly
        fields = [
            "id",
            "source_system",
            "reference_id",
            "score",
            "category",
            "summary",
            "details",
        ]


class FindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Finding
        fields = [
            "id",
            "title",
            "severity",
            "narrative",
            "recommendations",
        ]


class AuditEngagementDetailSerializer(serializers.ModelSerializer):
    anomalies = AnomalySerializer(many=True, read_only=True)
    findings = FindingSerializer(many=True, read_only=True)

    class Meta:
        model = AuditEngagement
        fields = [
            "id",
            "name",
            "period_start",
            "period_end",
            "status",
            "created_at",
            "updated_at",
            "anomalies",
            "findings",
        ]

