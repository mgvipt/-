from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from apps.crm import views as crm_views
from apps.accounts import views as acc_views
from apps.inbox import views as inbox_views
from apps.warehouse import views as wh_views
from apps.finance import views as fin_views
from apps.integrations import views as intg_views
from apps.telephony import views as tel_views

router = DefaultRouter()
router.register("product-categories", wh_views.ProductCategoryViewSet)
router.register("finmodel-articles", fin_views.FinModelArticleViewSet)
router.register("fin-directions", fin_views.FinDirectionViewSet)
router.register("channel-spend", fin_views.ChannelSpendViewSet)
router.register("contacts", crm_views.ContactViewSet)
router.register("companies", crm_views.CompanyViewSet)
router.register("funnels", crm_views.FunnelViewSet)
router.register("stages", crm_views.StageViewSet)
router.register("leads", crm_views.LeadViewSet)
router.register("deals", crm_views.DealViewSet)
router.register("payments", crm_views.PaymentViewSet)
router.register("automation-rules", crm_views.AutomationRuleViewSet)
router.register("global-rules", crm_views.GlobalRuleViewSet)
router.register("tasks", crm_views.TaskViewSet)
router.register("roles", acc_views.RoleViewSet)
router.register("users", acc_views.UserViewSet)
router.register("departments", acc_views.DepartmentViewSet)
router.register("invites", acc_views.InviteViewSet)
router.register("channels", inbox_views.ChannelViewSet)
router.register("conversations", inbox_views.ConversationViewSet)
router.register("warehouses", wh_views.WarehouseViewSet)
router.register("products", wh_views.ProductViewSet)
router.register("stock-documents", wh_views.StockDocumentViewSet)
router.register("accounts", fin_views.AccountViewSet)
router.register("categories", fin_views.CategoryViewSet)
router.register("transactions", fin_views.TransactionViewSet)
router.register("fund-allocations", fin_views.FundAllocationViewSet)
router.register("advisory-reports", fin_views.AdvisoryReportViewSet)
router.register("manager-plans", fin_views.ManagerPlanViewSet)
router.register("workdays", fin_views.WorkDayViewSet)
router.register("calls", tel_views.CallViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/", include("rest_framework.urls")),
    path("api/auth/token/", obtain_auth_token),  # POST username/password -> {token}
    path("api/me/", acc_views.MeView.as_view()),
    path("api/search/", crm_views.GlobalSearchView.as_view()),
    path("api/permissions/", acc_views.PermissionsCatalogView.as_view()),
    path("api/invite/<str:token>/", acc_views.AcceptInviteView.as_view()),
    path("api/inbox/telegram/webhook/<int:channel_id>/", inbox_views.TelegramWebhookView.as_view()),
    path("api/inbox/viber/webhook/<int:channel_id>/", inbox_views.ViberWebhookView.as_view()),
    path("api/inbox/echat/webhook/<int:channel_id>/", inbox_views.EchatWebhookView.as_view()),
    path("api/inbox/echat/setup/", inbox_views.EchatSetupView.as_view()),
    path("api/inbox/meta/webhook/", inbox_views.MetaWebhookView.as_view()),
    path("api/inbox/meta/webhook", inbox_views.MetaWebhookView.as_view()),
    path("api/inbox/chatplace/sync/", inbox_views.ChatPlaceSyncView.as_view()),
    path("api/contact-center/", inbox_views.ContactCenterView.as_view()),
    path("api/activity/", crm_views.ActivityLogView.as_view()),
    path("api/privacy/", inbox_views.PrivacyPolicyView.as_view()),
    path("api/privacy", inbox_views.PrivacyPolicyView.as_view()),
    path("api/data-deletion/", inbox_views.DataDeletionView.as_view()),
    path("api/data-deletion", inbox_views.DataDeletionView.as_view()),
    path("api/finance/dashboard/", fin_views.FinanceDashboardView.as_view()),
    path("api/finance/overview/", fin_views.OverviewView.as_view()),
    path("api/finance/pnl/", fin_views.ProfitLossView.as_view()),
    path("api/finance/breakeven/", fin_views.BreakevenView.as_view()),
    path("api/finance/directions/", fin_views.DirectionsReportView.as_view()),
    path("api/finance/channels/", fin_views.ChannelsView.as_view()),
    path("api/finance/funds/", fin_views.FundsView.as_view()),
    path("api/finance/fx-rate/", fin_views.FxRateView.as_view()),
    path("api/finance/fx-impact/", fin_views.FxImpactView.as_view()),
    path("api/finance/counterparties/", fin_views.CounterpartiesView.as_view()),
    path("api/worktime/", fin_views.WorkTimeView.as_view()),
    path("api/attachments/<int:pk>/file/", fin_views.AttachmentFileView.as_view()),
    path("api/finance/salary/", fin_views.SalaryView.as_view()),
    path("api/analytics/", crm_views.AnalyticsView.as_view()),
    path("api/analytics/inventory/", wh_views.InventoryAnalyticsView.as_view()),
    path("api/warehouse/inventory-sheet/", wh_views.InventorySheetView.as_view()),
    path("api/telephony/webhook/", tel_views.CallWebhookView.as_view()),
    path("api/telephony/originate-queue/", tel_views.OriginateQueueView.as_view()),
    path("api/telephony/ringing/", tel_views.RingingView.as_view()),
    path("api/telephony/ringing/active/", tel_views.RingingActiveView.as_view()),
    path("api/telephony/webrtc-config/", tel_views.WebrtcConfigView.as_view()),
    path("api/integrations/settings/", intg_views.IntegrationSettingsView.as_view()),
    path("api/integrations/liqpay/link/", intg_views.LiqpayLinkView.as_view()),
    path("api/integrations/novaposhta/track/", intg_views.NovaPoshtaTrackView.as_view()),
]
