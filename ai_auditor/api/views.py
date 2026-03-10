from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ai_auditor.models import AuditEngagement
from ai_auditor.api.serializers import (
    AuditEngagementCreateSerializer,
    AuditEngagementDetailSerializer,
)


class AuditEngagementViewSet(viewsets.ViewSet):
    """
    Basic endpoints for managing audit engagements.
    """

    def list(self, request):
        qs = AuditEngagement.objects.all().order_by("-created_at")
        serializer = AuditEngagementDetailSerializer(qs, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = AuditEngagementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        engagement = AuditEngagement.objects.create(**serializer.validated_data)
        out = AuditEngagementDetailSerializer(engagement)
        return Response(out.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        engagement = AuditEngagement.objects.get(pk=pk)
        serializer = AuditEngagementDetailSerializer(engagement)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="run")
    def run_audit(self, request, pk=None):
        # Placeholder for wiring Celery/AI pipeline
        # For now we just mark the engagement as completed.
        engagement = AuditEngagement.objects.get(pk=pk)
        engagement.status = "completed"
        engagement.save(update_fields=["status"])
        return Response({"status": "completed"})

