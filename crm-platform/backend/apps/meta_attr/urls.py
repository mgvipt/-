from django.urls import path

from .views import ContactAttrView, ConversationAttrView, PhrasesView

urlpatterns = [
    path("contact/<int:pk>/", ContactAttrView.as_view()),
    path("conversation/<int:pk>/", ConversationAttrView.as_view()),
    path("phrases/", PhrasesView.as_view()),
]
