from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import KnowledgeItemViewSet, MetaView, PreviewView, SettingsView

router = SimpleRouter()
router.register("items", KnowledgeItemViewSet, basename="knowledge-items")

urlpatterns = [
    path("meta/", MetaView.as_view()),
    path("preview/", PreviewView.as_view()),
    path("settings/", SettingsView.as_view()),
    path("", include(router.urls)),
]
