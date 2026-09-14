from django.urls import path

from . import views

urlpatterns = [
    path("levels/", views.LevelsView.as_view()),
    path("levels/<int:pk>/", views.LevelDetailView.as_view()),
    path("settings/", views.SettingsView.as_view()),
    path("matrix/", views.MatrixView.as_view()),
    path("products/", views.ProductsView.as_view()),
    path("products/<int:pk>/", views.ProductDetailView.as_view()),
    path("discounts/preview/", views.DiscountPreviewView.as_view()),
    path("discounts/apply/", views.DiscountApplyView.as_view()),
    path("discounts/suggest/", views.SuggestView.as_view()),
    path("log/", views.RuleLogView.as_view()),
    path("list/", views.PartnersListView.as_view()),
    path("contacts/<int:pk>/", views.ContactPartnerView.as_view()),
    path("deals/<int:pk>/margin/", views.DealMarginView.as_view()),
]
