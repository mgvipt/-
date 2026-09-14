from django.urls import path

from . import views

urlpatterns = [
    path("board/", views.BoardView.as_view()),
    path("categories/", views.CategoriesView.as_view()),
    path("categories/<int:pk>/", views.CategoryDetailView.as_view()),
    path("categories/<int:pk>/move/", views.CategoryMoveView.as_view()),
    path("offers/", views.OffersView.as_view()),
    path("offers/activate/", views.ActivateView.as_view()),
    path("offers/<int:pk>/", views.OfferDetailView.as_view()),
    path("offers/<int:pk>/move/", views.OfferMoveView.as_view()),
    path("offers/<int:pk>/restore/", views.OfferRestoreView.as_view()),
    path("offers/<int:pk>/take/", views.TakeView.as_view()),
    path("claims/", views.ClaimsView.as_view()),
    path("claims/<int:pk>/files/", views.ClaimFilesView.as_view()),
    path("claims/<int:pk>/<str:act>/", views.ClaimActionView.as_view()),
    path("files/<int:pk>/", views.FileView.as_view()),
    path("summary/", views.SummaryView.as_view()),
]
