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
urlpatterns += [
    path("api/content-factory/telegram/", views.TelegramView.as_view()),
    path("api/content-factory/telegram/settings/", views.TelegramSettingsView.as_view()),
    path("api/content-factory/telegram/draft/", views.TelegramDraftView.as_view()),
    path("api/content-factory/telegram/posts/<int:pk>/", views.TelegramPostView.as_view()),
    path("api/content-factory/telegram/posts/<int:pk>/photos/", views.TelegramPhotosView.as_view()),
]
urlpatterns += [
    path("api/content-factory/telegram/posts/", views.TelegramManualPostView.as_view()),
    path("api/content-factory/telegram/media/", views.TelegramMediaView.as_view()),
    path("api/content-factory/telegram/posts/<int:pk>/test/", views.TelegramSendView.as_view(), {"action": "test"}),
    path("api/content-factory/telegram/posts/<int:pk>/publish/", views.TelegramSendView.as_view(), {"action": "publish"}),
]
urlpatterns += [
    path("api/content-factory/sources/", views.SourcesView.as_view()),
    path("api/content-factory/sources/ingest/", views.SourceIngestView.as_view()),
    path("api/content-factory/sources/thumb/<str:token>/", views.SourceThumbView.as_view()),
    path("api/content-factory/sources/chats/<int:pk>/", views.SourceChatView.as_view()),
    path("api/content-factory/sources/<int:pk>/", views.SourceAssetView.as_view()),
]
urlpatterns += [
    path("api/content-factory/sources/drive/", views.DriveFoldersView.as_view()),
    path("api/content-factory/sources/drive/sync/", views.DriveSyncView.as_view()),
    path("api/content-factory/sources/drive/<int:pk>/", views.DriveFolderView.as_view()),
]
urlpatterns += [
    path("api/content-factory/telegram/published/", views.TelegramPublishedView.as_view()),
]
urlpatterns += [
    path("api/content-factory/feed/", views.FeedView.as_view()),
    path("api/content-factory/feed/<int:pk>/", views.FeedItemView.as_view()),
    path("api/content-factory/analyst/", views.AnalystView.as_view()),
]
urlpatterns += [
    path("api/content-factory/reels/", views.ReelsView.as_view()),
    path("api/content-factory/reels/<int:pk>/", views.ReelView.as_view()),
    path("api/content-factory/reels/<int:pk>/test/", views.ReelView.as_view(), {"action": "test"}),
    path("api/content-factory/reels/<int:pk>/render/", views.ReelView.as_view(), {"action": "render"}),
    path("api/content-factory/reels/scenes/", views.ReelScenesView.as_view()),
    path("api/content-factory/reels/styles/", views.ReelStylesView.as_view()),
]
