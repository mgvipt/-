from django.urls import path

from .creatives import CreativeSalesView
from .views import ContactAttrView, ConversationAttrView, PhrasesView

urlpatterns = [
    path("contact/<int:pk>/", ContactAttrView.as_view()),
    path("conversation/<int:pk>/", ConversationAttrView.as_view()),
    path("phrases/", PhrasesView.as_view()),
    path("creative-sales/", CreativeSalesView.as_view()),  # продажі по креативах (14.09 meta-creatives)
]
