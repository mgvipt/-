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
    path("api/content-factory/studio/", views.StudioView.as_view()),
    path("api/content-factory/studio/ideas/", views.StudioView.as_view(), {"action": "ideas"}),
    path("api/content-factory/studio/search/", views.StudioView.as_view(), {"action": "search"}),
    path("api/content-factory/studio/voices/", views.StudioView.as_view(), {"action": "voices"}),
    path("api/content-factory/studio/images/", views.StudioView.as_view(), {"action": "images"}),
    path("api/content-factory/reels/<int:pk>/studio/", views.ReelView.as_view(), {"action": "studio"}),
    path("api/content-factory/reels/<int:pk>/publish/", views.ReelView.as_view(), {"action": "publish"}),
    path("api/content-factory/carousels/<int:pk>/publish/", views.CarouselView.as_view(), {"action": "publish"}),
    path("api/content-factory/reels/styles/", views.ReelStylesView.as_view()),
]
urlpatterns += [  # 25.09: блоги, каруселі, ШІ-кадри, вичитка
    path("api/content-factory/blogs/", views.BlogsView.as_view()),
    path("api/content-factory/blogs/<int:pk>/", views.BlogView.as_view()),
    path("api/content-factory/blogs/<int:pk>/accounts/", views.BlogAccountsView.as_view()),
    path("api/content-factory/blogs/<int:pk>/facts/", views.BlogFactsView.as_view()),
    path("api/content-factory/blogs/<int:pk>/facts/<int:fid>/", views.BlogFactView.as_view()),
    path("api/content-factory/blogs/<int:pk>/brief/", views.BlogBriefView.as_view()),
    path("api/content-factory/carousels/", views.CarouselsView.as_view()),
    path("api/content-factory/carousels/<int:pk>/", views.CarouselView.as_view()),
    path("api/content-factory/carousels/<int:pk>/test/", views.CarouselView.as_view(), {"action": "test"}),
    path("api/content-factory/carousels/<int:pk>/tiktok/", views.CarouselView.as_view(), {"action": "tiktok"}),
    path("api/content-factory/carousels/<int:pk>/image/", views.CarouselView.as_view(), {"action": "image"}),
    path("api/content-factory/reels/<int:pk>/frame/", views.ReelView.as_view(), {"action": "frame"}),
    path("api/content-factory/reels/<int:pk>/advice/", views.ReelView.as_view(), {"action": "advice"}),
    path("api/content-factory/proofread/", views.ProofreadView.as_view()),
    path("api/content-factory/telegram/posts/<int:pk>/photo-ai/", views.TelegramPhotoAIView.as_view()),
]
urlpatterns += [  # 25.09 v2: каруселі (текст, поради), памʼять блогу
    path("api/content-factory/carousels/<int:pk>/text/", views.CarouselView.as_view(), {"action": "text"}),
    path("api/content-factory/carousels/<int:pk>/advice/", views.CarouselView.as_view(), {"action": "advice"}),
    path("api/content-factory/blogs/<int:pk>/memory/", views.BlogMemoryView.as_view()),
    path("api/content-factory/blogs/<int:pk>/active/", views.BlogActiveView.as_view()),
    path("api/content-factory/blogs/<int:pk>/tiktok/", views.BlogTiktokView.as_view()),
]
urlpatterns += [  # 25.09: навчання блогу знаннями ззовні
    path("api/content-factory/blogs/<int:pk>/learn/", views.BlogLearnView.as_view()),
    path("api/content-factory/blogs/<int:pk>/learn/accept/", views.BlogLearnView.as_view(), {"action": "accept"}),
]
urlpatterns += [path("api/content-factory/channels/<int:pk>/virale/", views.ChannelDetailView.as_view())]
urlpatterns += [path("api/content-factory/channels/<int:pk>/content/", views.ChannelContentView.as_view())]
urlpatterns += [
    path("api/content-factory/blogs/<int:pk>/learn/drive-list/", views.BlogLearnView.as_view(), {"action": "drive-list"}),
    path("api/content-factory/blogs/<int:pk>/learn/drive/", views.BlogLearnView.as_view(), {"action": "drive"}),
]
urlpatterns += [path("api/content-factory/blogs/<int:pk>/visual/", views.BlogVisualView.as_view())]
urlpatterns += [
    path("api/content-factory/write/", views.WriteView.as_view()),
    path("api/content-factory/reels/<int:pk>/versions/", views.ReelView.as_view(), {"action": "versions"}),
    path("api/content-factory/reels/<int:pk>/adapt/", views.ReelView.as_view(), {"action": "adapt"}),
    path("api/content-factory/carousels/<int:pk>/adapt/", views.CarouselView.as_view(), {"action": "adapt"}),
    path("api/content-factory/agent/", views.AgentView.as_view()),
    path("api/content-factory/agent/<int:pk>/", views.AgentChatView.as_view()),
]
