from django.urls import path

from . import views

urlpatterns = [
    path("", views.MissedListView.as_view()),
    path("summary/", views.MissedSummaryView.as_view()),
    path("report/", views.MissedReportView.as_view()),
    path("settings/", views.MissedSettingsView.as_view()),
    path("<int:pk>/action/", views.MissedActionView.as_view()),
]
