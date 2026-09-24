from django.urls import path

from . import views

urlpatterns = [
    path("api/assistant/", views.AssistantView.as_view()),
    path("api/assistant/ingest/", views.IngestView.as_view()),
    path("api/assistant/chats/<int:pk>/", views.ChatView.as_view()),
    path("api/assistant/proposals/<int:pk>/", views.ProposalView.as_view()),
]
