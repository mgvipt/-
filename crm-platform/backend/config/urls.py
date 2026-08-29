from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.crm import views as crm_views
from apps.accounts import views as acc_views
from apps.inbox import views as inbox_views
from apps.inbox.webchat import WebChatView
from apps.inbox import tiktok as tiktok_views
from apps.warehouse import views as wh_views
from apps.warehouse import wh_views as whv
from apps.warehouse import shop_import_views
from apps.warehouse import shop_site
from apps.finance import views as fin_views
from apps.integrations import views as intg_views
from apps.crm.duplicates import DuplicatesView
from apps.crm.zamer import (
    CalcSettingsView, ClientRegisterZamerView, ClientSelfEstimateView,
    EstimateView, PricelistView, ZamerProjectsView, ZamerStageReviewView,
    ZamerView,
)
from apps.gamification import views as gam_views
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
router.register("kb-entries", crm_views.KbEntryViewSet)
router.register("kb-questions", crm_views.KbUnknownQuestionViewSet)
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
router.register("planned-payments", fin_views.PlannedPaymentViewSet)
router.register("fund-allocations", fin_views.FundAllocationViewSet)
router.register("advisory-reports", fin_views.AdvisoryReportViewSet)
router.register("manager-plans", fin_views.ManagerPlanViewSet)
router.register("workdays", fin_views.WorkDayViewSet)
router.register("calls", tel_views.CallViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/zamer/", ZamerView.as_view()),  # приёмник замера из iOS-приложения
    path("api/zamer/register/", ClientRegisterZamerView.as_view()),  # клиент из приложения -> лид
    path("api/zamer/reviews/", ZamerStageReviewView.as_view()),  # клиентские заявки на проверку
    path("api/zamer/reviews/<int:pk>/", ZamerStageReviewView.as_view()),
    path("api/zamer/self-estimate/", ClientSelfEstimateView.as_view()),
    path("api/pricelist/", PricelistView.as_view()),  # прайс эффектов/материалов/инструментов для приложения
    path("api/zamer/projects/", ZamerProjectsView.as_view()),  # устойчивые проекты замера
    path("api/calc-settings/", CalcSettingsView.as_view()),  # административные условия калькулятора
    path("api/estimates/", EstimateView.as_view()),  # сметы из замеров с CRM-scope
    path("api/estimates/<int:pk>/", EstimateView.as_view()),
    path("api/auth/register/", acc_views.ClientRegisterView.as_view()),
    path("api/auth/", include("rest_framework.urls")),
    path("api/auth/token/", acc_views.FlexibleAuthTokenView.as_view()),
    path("api/me/", acc_views.MeView.as_view()),
    path("api/search/", crm_views.GlobalSearchView.as_view()),
    path("api/changelog/", crm_views.ChangeLogView.as_view()),
    path("api/permissions/", acc_views.PermissionsCatalogView.as_view()),
    path("api/ai-usage/", crm_views.AiUsageView.as_view()),
    path("api/ai-usage/anthropic/", crm_views.AnthropicCostView.as_view()),
    path("api/invite/<str:token>/", acc_views.AcceptInviteView.as_view()),
    path("api/inbox/telegram/webhook/<int:channel_id>/", inbox_views.TelegramWebhookView.as_view()),
    path("api/inbox/viber/webhook/<int:channel_id>/", inbox_views.ViberWebhookView.as_view()),
    path("api/inbox/echat/webhook/<int:channel_id>/", inbox_views.EchatWebhookView.as_view()),
    path("api/inbox/echat/setup/", inbox_views.EchatSetupView.as_view()),
    path("api/inbox/meta/webhook/", inbox_views.MetaWebhookView.as_view()),
    # ── TikTok Direct (без ChatPlace): статус / підключення / callback OAuth / вебхук подій ──
    path("api/inbox/tiktok/status/", tiktok_views.TiktokStatusView.as_view()),
    path("api/inbox/tiktok/connect/", tiktok_views.TiktokConnectView.as_view()),
    path("api/inbox/tiktok/disconnect/", tiktok_views.TiktokDisconnectView.as_view()),
    path("api/inbox/tiktok/callback/", tiktok_views.TiktokCallbackView.as_view()),
    path("api/inbox/tiktok/callback", tiktok_views.TiktokCallbackView.as_view()),
    path("api/inbox/tiktok/webhook/", tiktok_views.TiktokWebhookView.as_view()),
    path("api/inbox/tiktok/webhook", tiktok_views.TiktokWebhookView.as_view()),
    path("api/duplicates/", DuplicatesView.as_view()),
    path("api/gamification/me/", gam_views.MeView.as_view()),
    path("api/gamification/leaderboard/", gam_views.LeaderboardView.as_view()),
    path("api/gamification/manager/<int:pk>/", gam_views.ManagerView.as_view()),
    path("api/inbox/ping/", inbox_views.InboxPingView.as_view()),
    path("api/inbox/deal-badges/", inbox_views.DealBadgesView.as_view()),
    path("api/sounds/", inbox_views.SoundLibraryView.as_view()),
    path("api/sounds/<int:pk>/file/", inbox_views.SoundFileView.as_view()),
    path("api/sounds/<int:pk>/", inbox_views.SoundDeleteView.as_view()),
    path("api/inbox/media-library/", inbox_views.MediaLibraryView.as_view()),
    path("api/inbox/tg-file/<int:message_id>/<int:idx>/", inbox_views.TgFileView.as_view()),
    path("api/telephony/lines/", tel_views.PhoneLineView.as_view()),
    path("api/telephony/line-status/", tel_views.LineStatusView.as_view()),
    path("api/team-chat/contacts/", inbox_views.TeamContactsView.as_view()),
    path("api/team-chat/<int:user_id>/", inbox_views.TeamThreadView.as_view()),
    path("api/f/<str:token>/", inbox_views.SharedFileView.as_view()),
    path("api/f/<str:token>/<path:name>", inbox_views.SharedFileView.as_view()),
    path("api/contact-form-config/", crm_views.ContactFormConfigView.as_view()),
    path("api/inbox/notifications/", inbox_views.NotificationsView.as_view()),
    path("api/inbox/meta/webhook", inbox_views.MetaWebhookView.as_view()),
    path("api/inbox/chatplace/sync/", inbox_views.ChatPlaceSyncView.as_view()),
    path("api/inbox/chatplace/webhook/", inbox_views.ChatPlaceWebhookView.as_view()),
    path("api/inbox/web-chat/", WebChatView.as_view()),
    path("api/contact-center/", inbox_views.ContactCenterView.as_view()),
    path("api/activity/", crm_views.ActivityLogView.as_view()),
    path("api/staff/analytics/", crm_views.StaffAnalyticsView.as_view()),
    path("api/staff/activity/", crm_views.StaffActivityView.as_view()),
    path("api/privacy/", inbox_views.PrivacyPolicyView.as_view()),
    path("api/privacy", inbox_views.PrivacyPolicyView.as_view()),
    path("api/data-deletion/", inbox_views.DataDeletionView.as_view()),
    path("api/data-deletion", inbox_views.DataDeletionView.as_view()),
    path("api/finance/dashboard/", fin_views.FinanceDashboardView.as_view()),
    path("api/finance/overview/", fin_views.OverviewView.as_view()),
    path("api/finance/cashflow/", fin_views.CashflowSeriesView.as_view()),
    path("api/finance/bank-rules/", fin_views.BankRuleViewSet.as_view({"get": "list", "post": "create"})),
    path("api/finance/bank-rules/<int:pk>/", fin_views.BankRuleViewSet.as_view({"patch": "partial_update", "delete": "destroy"})),
    path("api/finance/bank-rules/apply-journal/", fin_views.BankRuleViewSet.as_view({"post": "apply_journal"})),
    path("api/finance/bank-rules/suggest/", fin_views.BankRuleViewSet.as_view({"get": "suggest"})),
    path("api/finance/bank-rules/suggest-create/", fin_views.BankRuleViewSet.as_view({"post": "suggest_create"})),
    path("api/finance/pnl/", fin_views.ProfitLossView.as_view()),
    path("api/finance/breakeven/", fin_views.BreakevenView.as_view()),
    path("api/finance/directions/", fin_views.DirectionsReportView.as_view()),
    path("api/finance/breakdown/", fin_views.AnalyticsBreakdownView.as_view()),
    path("api/finance/channels/", fin_views.ChannelsView.as_view()),
    path("api/agent/config/", crm_views.AgentConfigView.as_view()),
    path("api/crm/liqpay/callback/", crm_views.LiqPayCallbackView.as_view()),
    path("p/<str:code>/", crm_views.paylink_redirect),
    path("p/<str:code>", crm_views.paylink_redirect),
    path("api/finance/funds/", fin_views.FundsView.as_view()),
    path("api/finance/fx-rate/", fin_views.FxRateView.as_view()),
    path("api/finance/fx-impact/", fin_views.FxImpactView.as_view()),
    path("api/finance/counterparties/", fin_views.CounterpartiesView.as_view()),
    path("api/worktime/", fin_views.WorkTimeView.as_view()),
    path("api/yulia/status/", fin_views.YuliaStatusView.as_view()),
    path("api/attachments/<int:pk>/file/", fin_views.AttachmentFileView.as_view()),
    path("api/finance/salary/", fin_views.SalaryView.as_view()),
    path("api/finance/salary/deals/", fin_views.ManagerDealsView.as_view()),
    path("api/analytics/", crm_views.AnalyticsView.as_view()),
    path("api/analytics/funnel-daily/", crm_views.FunnelDailyView.as_view()),
    path("d/<str:code>/", crm_views.render_kp_public),
    path("api/analytics/manager-actions/", crm_views.ManagerActionsView.as_view()),
    path("api/analytics/weekly-review/", crm_views.WeeklyReviewView.as_view()),
    path("api/analytics/manager-stages/", crm_views.ManagerStagesView.as_view()),
    path("api/analytics/sales-funnel/", crm_views.SalesFunnelView.as_view()),
    path("api/analytics/sales-journey/", crm_views.SalesJourneyView.as_view()),
    path("api/meta-marketing/funnel/", crm_views.MetaFunnelView.as_view()),
    path("api/marketing/offline/", crm_views.MarketingOfflineView.as_view()),
    path("api/marketing/ga4/", crm_views.MarketingGa4View.as_view()),
    path("api/meta-marketing/sync-now/", crm_views.MetaSyncNowView.as_view()),
    path("api/meta-marketing/sync-status/", crm_views.MetaSyncStatusView.as_view()),
    path("api/meta-marketing/settings/", crm_views.MetaSyncSettingsView.as_view()),
    path("api/meta-marketing/pixel-events/", crm_views.MetaPixelEventsView.as_view()),
    path("api/analytics/manager-dialogs/", crm_views.ManagerDialogsView.as_view()),
    path("api/meta-marketing/", crm_views.MetaMarketingView.as_view()),
    path("api/analytics/inventory/", wh_views.InventoryAnalyticsView.as_view()),
    path("api/warehouse/inventory-sheet/", wh_views.InventorySheetView.as_view()),
    path("api/warehouse/inventory-summary/", wh_views.InventorySummaryView.as_view()),
    path("api/warehouse/inventory-draft/", wh_views.InventoryDraftView.as_view()),
    path("api/warehouse/product-shipments/", wh_views.ProductShipmentsView.as_view()),
    path("api/warehouse/queue/", whv.queue),
    path("api/warehouse/jobs/<int:pk>/", whv.job_detail),
    path("api/warehouse/jobs/<int:pk>/take/", whv.take),
    path("api/warehouse/jobs/<int:pk>/reassign/", whv.reassign),
    path("api/warehouse/jobs/<int:pk>/cancel/", whv.cancel_job),
    path("api/warehouse/jobs/<int:pk>/tinting/", whv.tinting),
    path("api/warehouse/jobs/<int:pk>/packing/", whv.packing),
    path("api/warehouse/jobs/<int:pk>/photo/", whv.photo),
    path("api/warehouse/jobs/<int:pk>/ship/", whv.ship),
    path("api/warehouse/deal/<int:deal_id>/shipment/", whv.deal_shipment),
    path("api/warehouse/shipments/", whv.shipments_history),
    path("api/warehouse/my-salary/", whv.my_salary),
    path("api/warehouse/my-shift/", whv.my_shift),
    path("api/warehouse/day/start/", whv.day_start),
    path("api/warehouse/day/close/", whv.day_close),
    path("api/warehouse/lunch/", whv.lunch_toggle),
    path("api/warehouse/tare-types/", whv.tare_types),
    path("api/warehouse/errors/", whv.errors),
    path("api/warehouse/errors/<int:pk>/confirm/", whv.confirm_error),
    path("api/warehouse/ideas/", whv.ideas),
    path("api/warehouse/ideas/<int:pk>/award/", whv.award_idea),
    path("api/warehouse/dashboard/", whv.dashboard),
    path("api/shop-import/batches/", shop_import_views.ShopImportBatchListView.as_view()),
    path("api/shop-import/upload/", shop_import_views.ShopImportUploadView.as_view()),
    path("api/shop-import/batches/<int:pk>/", shop_import_views.ShopImportBatchDetailView.as_view()),
    path("api/shop-import/batches/<int:pk>/apply/", shop_import_views.ShopImportApplyView.as_view()),
    path("api/shop-import/rows/<int:pk>/", shop_import_views.ShopImportRowView.as_view()),
    path("api/shop-site/content/", shop_site.ShopSiteContentView.as_view()),
    path("api/shop-site/publish/", shop_site.ShopSitePublishView.as_view()),
    path("api/shop-site/media/", shop_site.ShopSiteMediaView.as_view()),
    path("api/shop-site/analytics/", shop_site.ShopSiteAnalyticsView.as_view()),
    path("api/telephony/webhook/", tel_views.CallWebhookView.as_view()),
    path("api/telephony/rec/<int:pk>/", tel_views.RecordingView.as_view()),
    path("api/telephony/pending-transcribe/", tel_views.PendingTranscribeView.as_view()),
    path("api/telephony/transcribe/", tel_views.TranscribeView.as_view()),
    path("api/telephony/originate-queue/", tel_views.OriginateQueueView.as_view()),
    path("api/telephony/ringing/", tel_views.RingingView.as_view()),
    path("api/telephony/ringing/active/", tel_views.RingingActiveView.as_view()),
    path("api/telephony/webrtc-config/", tel_views.WebrtcConfigView.as_view()),
    path("api/telephony/queue/", tel_views.CallQueueView.as_view()),
    path("api/telephony/ring-plan/", tel_views.RingPlanView.as_view()),
    path("api/telephony/ring-now/", tel_views.RingNowView.as_view()),
    path("api/integrations/settings/", intg_views.IntegrationSettingsView.as_view()),
    path("api/integrations/email-invoices/test/", intg_views.EmailInvoicesTestView.as_view()),
    path("api/integrations/email-invoices/poll/", intg_views.EmailInvoicesPollView.as_view()),
    path("api/integrations/incoming-docs/", intg_views.IncomingDocListView.as_view()),
    path("api/integrations/incoming-docs/<int:pk>/", intg_views.IncomingDocDetailView.as_view()),
    path("api/integrations/incoming-docs/<int:pk>/action/", intg_views.IncomingDocActionView.as_view()),
    path("api/integrations/incoming-docs/<int:pk>/file/<int:idx>/", intg_views.IncomingDocFileView.as_view()),
    path("api/integrations/incoming-docs/<int:pk>/view/", intg_views.IncomingDocViewView.as_view()),
    path("api/integrations/incoming-docs/<int:pk>/pay-candidates/", intg_views.IncomingDocPayCandidatesView.as_view()),
    path("api/integrations/incoming-docs/upload/", intg_views.IncomingDocUploadView.as_view()),
    path("api/integrations/liqpay/link/", intg_views.LiqpayLinkView.as_view()),
    path("api/integrations/novaposhta/track/", intg_views.NovaPoshtaTrackView.as_view()),
    path("api/integrations/shop/orders/", intg_views.ShopOrderWebhookView.as_view()),
]
