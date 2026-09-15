from django.urls import path

from . import views

urlpatterns = [
    path("deal/<int:deal_id>/", views.DealReturnsView.as_view()),
    path("<int:pk>/photos/", views.ReturnPhotoUploadView.as_view()),
    path("<int:pk>/money/", views.ReturnMoneyView.as_view()),
    path("photos/<int:pk>/", views.ReturnPhotoView.as_view()),
    path("report/", views.ReturnsReportView.as_view()),
]
