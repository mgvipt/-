from django.urls import path

from . import views

urlpatterns = [
    path("schemes/", views.SchemesView.as_view()),
    path("schemes/<int:pk>/save/", views.SchemeSaveView.as_view()),
    path("schemes/<int:pk>/archive/", views.SchemeArchiveView.as_view()),
    path("components/<int:pk>/mark/", views.ComponentMarkView.as_view()),
    path("calc/", views.CalcView.as_view()),
    path("breakeven/", views.BreakevenView.as_view()),
    path("policy/", views.PolicyView.as_view()),
    path("log/", views.LogView.as_view()),
    path("acts/", views.ActsView.as_view()),
    path("acts/<int:pk>/close/", views.ActCloseView.as_view()),
    path("runs/", views.RunsView.as_view()),
    path("funds/sync/", views.FundSyncView.as_view()),
    path("runs/approve/", views.RunApproveView.as_view()),
    path("runs/<int:pk>/<str:act>/", views.RunActionView.as_view()),
]
