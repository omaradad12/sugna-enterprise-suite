from rest_framework.routers import DefaultRouter

from ai_auditor.api.views import AuditEngagementViewSet

router = DefaultRouter()
router.register("engagements", AuditEngagementViewSet, basename="ai-auditor-engagement")

urlpatterns = router.urls

