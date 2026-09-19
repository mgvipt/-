from django.urls import path

from . import my_views, views  # my_views: 14.09 моя ЗП і KPI
from .fund_link import FundLinksView  # 14.09 фонди «Автоматично зі Ставок»
from .detail_views import CalcDetailView  # 15.09 «Як прорахувалась ЗП»
from .wh_kpi import WhKpiView  # 15.09 підказка CRM і позначки стандарту складу
from .whatif import MyWhatIfView  # 16.09 Розвиток v2: «Що буде, якщо» у «Моя ЗП»
from .plan_grid import PlanGridView, PlanTeamView  # 19.09 план по тижнях і днях + зведена

urlpatterns = [
    path("schemes/", views.SchemesView.as_view()),
    path("schemes/<int:pk>/save/", views.SchemeSaveView.as_view()),
    path("schemes/<int:pk>/archive/", views.SchemeArchiveView.as_view()),
    path("components/<int:pk>/mark/", views.ComponentMarkView.as_view()),
    path("calc/", views.CalcView.as_view()),
    path("breakeven/", views.BreakevenView.as_view()),
    path("policy/", views.PolicyView.as_view()),
    path("log/", views.LogView.as_view()),
    path("acts/", views.ActsView.as_view()),
    path("acts/<int:pk>/close/", views.ActCloseView.as_view()),
    path("runs/", views.RunsView.as_view()),
    path("funds/sync/", views.FundSyncView.as_view()),
    path("funds/links/", FundLinksView.as_view()),
    path("my/", my_views.MyPayrollView.as_view()),
    path("my/detail/", my_views.MyDetailView.as_view()),
    path("my/whatif/", MyWhatIfView.as_view()),
    path("my/plan-grid/", PlanGridView.as_view()),
    path("plan-team/", PlanTeamView.as_view()),
    path("deal-kpi/<int:deal_id>/", my_views.DealKpiView.as_view()),
    path("runs/approve/", views.RunApproveView.as_view()),
    path("calc-detail/", CalcDetailView.as_view()),
    path("wh-kpi/", WhKpiView.as_view()),
    path("runs/<int:pk>/<str:act>/", views.RunActionView.as_view()),
]
