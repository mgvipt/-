from django.urls import path

from . import views

urlpatterns = [
    path("api/content-factory/overview/", views.OverviewView.as_view()),
    path("api/content-factory/channels/", views.ChannelListView.as_view()),
    path("api/content-factory/channels/<int:pk>/", views.ChannelDetailView.as_view()),
]
urlpatterns += [
    path("api/content-factory/questions/", views.QuestionsView.as_view()),
    path("api/content-factory/questions/settings/", views.QuestionSettingsView.as_view()),
    path("api/content-factory/questions/run/", views.QuestionRunView.as_view()),
    path("api/content-factory/questions/<int:pk>/", views.QuestionTopicView.as_view()),
]
