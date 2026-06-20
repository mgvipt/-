# Worklog — Wallcov-CRM (gmideas/crm-platform)

> Лог всех изменений по проекту. Новые записи — сверху. Формат: дата · ветка/коммит · что сделано · файлы.

## 2026-06-20 · ветка `claude/wallcov-crm-dealcard-merge`

### Коммит `7db1879` — merge переработанной карточки сделки (по анализу конкурентов)
**Backend:**
- `backend/apps/crm/models.py` — `Deal`: +`discount_pct`, +`pay_type`, +`ttn`, +`checkbox_status`; `Contact`: +`loyalty_tag`, +`birthday`.
- `backend/apps/crm/migrations/0003_dealcard_fields.py` — миграция (только AddField с дефолтами). Применена на проде ✓.
- `backend/apps/crm/serializers.py` — `ContactSerializer`/`DealSerializer` отдают новые поля; `DealDetailSerializer` +`margin`, +`bonus`, +`days_in_stage`, +`contact_loyalty`, +`contact_id`.

**Frontend:**
- `frontend/src/pages/DealCard.tsx` — лента реальных событий вместо заглушки, инлайн-edit суммы/скидки, дни на стадии, блоки лояльность / скидка(+VIP авто-реко) / доставка-документы(ТТН/чек+бейджи) / маржа+бонус, быстрые действия (ссылка на оплату / ТТН / чек).

**Деплой:** `docker compose -f docker-compose.prod.yml build web caddy && up -d` → миграция OK, сайт 200, API отдаёт новые поля (проверено на сделке #9). Бэкапы `*.bak.*_dealcardmerge` на сервере.

**Демо-данные:** 6 контактов с тегами лояльности (VIP/Активный/Новый/Спящий) через `manage.py shell`.

### Документация
- `docs/CODEMAP.md` — код-карта всей CRM (модули backend, экраны frontend, «где менять типовые вещи», поток данных, точки интеграции). Зеркало в волте: `Projects/Wallcov-CRM/Код-карта.md`.
- `docs/WORKLOG.md` — этот файл.

### TODO (из Merge-плана)
- [ ] DealCard.tsx — реструктурировать в чёткие пронумерованные блоки (требование Олега).
- [ ] Канбан (Board.tsx): чипы Чек✓/ТТН✓ + Rotting.
- [ ] Финмодуль (Finance.tsx): P&L по ATM + дебиторка.
- [ ] Реальный чат в ленту из app `inbox`.
- [ ] Боевые кнопки ТТН/Checkbox/ссылка → `@action` в `DealViewSet` поверх готовых `integrations/adapters.py`.
- [ ] push ветки в origin (по запросу).
