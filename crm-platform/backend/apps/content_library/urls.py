from django.urls import path
from . import views
urlpatterns=[
 path('api/content-library/public/<slug:slug>/',views.public_instruction),
 path('api/content-library/forms/<slug:slug>/',views.public_form),
 path('api/content-library/automations/',views.ContentAutomationView.as_view()),
 path('api/content-library/instructions/',views.LibraryView.as_view()),
 path('api/content-library/audience/',views.AudienceView.as_view()),
 path('instructions/<slug:slug>/',views.guide),
 path('instructions/<slug:slug>/event/',views.track),
 path('instructions/unsubscribe/<str:token>/',views.unsubscribe),
]
