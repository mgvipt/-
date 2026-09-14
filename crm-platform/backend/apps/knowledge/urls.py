from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import KnowledgeItemViewSet, MetaView, PreviewView, SettingsView

router = SimpleRouter()
router.register("items", KnowledgeItemViewSet, basename="knowledge-items")

from . import views_v2 as v2  # noqa: E402 — ai-kb2 (14.09): тестовий чат, перевірка, контролер, публікація

urlpatterns = [
    path("test-chat/", v2.TestChatView.as_view()),
    path("test-chat/chatplace/", v2.ChatPlaceTestView.as_view()),
    path("precheck/", v2.PrecheckView.as_view()),
    path("precheck/approve-ready/", v2.ApproveReadyView.as_view()),
    path("controller/", v2.ControllerView.as_view()),
    path("runs/<int:pk>/", v2.RunView.as_view()),
    path("publish/preview/", v2.PublishPreviewView.as_view()),
    path("publish/", v2.PublishView.as_view()),
    path("webchat/audience/", v2.WebchatAudienceView.as_view()),
    path("meta/", MetaView.as_view()),
    path("preview/", PreviewView.as_view()),
    path("settings/", SettingsView.as_view()),
    path("", include(router.urls)),
]
