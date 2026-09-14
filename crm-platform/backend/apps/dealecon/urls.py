from django.urls import path

from .views import DealEconomicsView, DealEconSettingsView

urlpatterns = [
    path("settings/", DealEconSettingsView.as_view()),
    path("<int:deal_id>/", DealEconomicsView.as_view()),
]
