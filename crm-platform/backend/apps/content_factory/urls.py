from django.urls import path

from . import views

urlpatterns = [
    path("api/content-factory/overview/", views.OverviewView.as_view()),
    path("api/content-factory/channels/", views.ChannelListView.as_view()),
    path("api/content-factory/channels/<int:pk>/", views.ChannelDetailView.as_view()),
]
