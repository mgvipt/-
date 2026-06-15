from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from apps.crm import views as crm_views
from apps.accounts import views as acc_views

router = DefaultRouter()
router.register("contacts", crm_views.ContactViewSet)
router.register("companies", crm_views.CompanyViewSet)
router.register("funnels", crm_views.FunnelViewSet)
router.register("stages", crm_views.StageViewSet)
router.register("leads", crm_views.LeadViewSet)
router.register("deals", crm_views.DealViewSet)
router.register("payments", crm_views.PaymentViewSet)
router.register("roles", acc_views.RoleViewSet)
router.register("users", acc_views.UserViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/", include("rest_framework.urls")),
    path("api/auth/token/", obtain_auth_token),  # POST username/password -> {token}
    path("api/me/", acc_views.MeView.as_view()),
]
