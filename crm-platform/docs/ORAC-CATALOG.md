# Orac catalogue and price source

Prepared 2026-09-09. Scope: Orac only. Cezar catalogue, prices and media are outside this release.

## Source and pricing

- Manufacturer: Orac NV, https://www.oracdecor.com/ . Product pages and official image download centre supply facts/media.
- Drive retail list: «Ціни ORAC 24.08.2026.xlsx», id `1zCzKkROH4PozOU3btqRrvQsEUwgDWBey`, 423 regular and85 clearance SKUs. Oleg explicitly confirmed retail1:1, UAH inclVAT, no markup.
- Public live retail observations: exact-SKU product pages on `https://ampir.ua/product/...`. Initial matching source prices are eligible for daily checking;9 price-list/site conflicts are held. Unmapped live sources are held and retain the dated list price. No inference of stock from price-list presence.
-9 conflicts: C338A,D330LR,FDP500,FL300,FX400,K1152,P3020A,P4025F,WX211-2600. Initial price is the dated list, not the website price.
- SX157 Product1251 manually saved by Oleg at480UAH; explicit manual hold. Warehouse balances and movements never written by this importer.
- D330LR sells as a two-piece set (`компл`). Box quantities in the supplier spreadsheet are not sale prices per box.

## Data and files

CRM: Netcup159.195.136.213 `/root/gmideas`, branch `codex/webchat-landing-crm`; app `/root/gmideas/crm-platform`. Standard deployment: `./deploy.sh web`.

Persistent source evidence and backup directory: host `/root/crm-media/warehouse_photos/orac-import-20260909`, container `/app/warehouse_photos/orac-import-20260909`.
Files: `orac-products.json`, `orac-seo-overlay.json`, `orac-import-dry-run.json`, `media-manifest.json`, `media/<sha256>.webp`, `before-products-<timestamp>.json`, `result-<timestamp>.json`.

`scripts/import_orac_20260909.py`: DRY_RUN=1 default. SKUS=C200,C323 pilot. Matches by reviewed exact SKU/length/Flex; retains existing CRM ids and legacy internal SKUs. New SKU prefix `ORAC-`. Optimistic updated_at/price verification before writes, row locks and advisory lock during transaction. Existing import_version makes repeat execution a no-op. Every media file checksum verified before DB writes. The importer never changes stock/cost/history.

Existing Orac root category34 is reused. Stable product group/slug `orac-<manufacturer-sku-lowercase>`, variant_type=product, one sale SKU per group. Product.price is authoritative for the library and existing shop sync queue. Product.shop_specs.orac records source facts, SEO copy, price_sync config and media provenance.

Media:1143 original URLs collapsed to800 unique WebP files before selection. Proportional max1800px,EXIF orientation,quality90; no generated product imagery/content changes. Generic Flex-radius legend images are excluded from galleries. One SharedLink file per unique image; each SKU has a contextual MediaLibraryItem relation to that shared file and ProductImage references the same persistent file. This preserves exact SKU/price context for sending; no duplicate image bytes are stored. Internal provenance retains original and exported hashes. No external hotlinked photo replaces a local product image.

## Release gates

-421 planned sale cards:194new,227existing,225pricechanges,210categorychanges,3reactivations,997image links to790unique selected files.
- Oleg authorized reactivation of FDP5002286,FX4002287,PX120F1230 only without duplicates. Full1378-product scan found one of each.
- CB503N:1130and1332both active, zero movements/deal items/stock at audit. No deletion/rewiring; duplicate disposition still requires Oleg's explicit choice.
- WX218F: present in official FlexRadius table, but exact official dimensional/gallery confirmation is incomplete. Remains unpublished.
- Clearance85rows remain separate, no automatic activation.
- Manufacturer index evidence is regional-model membership; it is not a promise of all regional sale variants or physical availability.

## Protected daily price job

`python manage.py sync_orac_prices` is dry run. `--apply` stores observations and may update prices; `--limit2` pilot (CLI spelling `--limit 2`). Only active products with this Orac import version are selected.

Systemd `wallcov-orac-prices.timer` runs06:30Europe/Kyiv with up to10min jitter; service calls the existing web container management command. Source/state logs persist under `/root/crm-media/warehouse_photos/orac-price-sync`.

Guards:exact source hostname and SKU,positive finite UAH amount,maximum plausible ceiling,manual price mismatch hold,explicit conflict hold,source errors/missing URL hold,price jumps over10%hold,changed price must repeat on a later UTC calendar date.10%is a change-review safety threshold,not markup. No product creation/removal by the scheduled price job. Every successful price write is row-locked,rechecked,journaled before update,and queued via existing shop sync. Empty/failed source never writes zero or clears a product. Repeating the same price does not queue another update.

Logs: timestamped dry/apply JSON with status per SKU,source URL/hash/check time;state.json preserves last_applied and candidate history;price-journal.jsonl preserves previous/new price before actual updates. A crash after DB update but before state persistence safely holds a mismatch on the next run. Manual hold release requires a deliberate reviewed configuration/state change; there is no silent reset.

## Verification and rollback

4 focused price-safety unit tests; standard CRM deployment45read-only smoke checks. PilotC200id1017(existing),C323id3008(new),events427/428. Remaining419must follow successful shop/media pilot checks and a fresh dry run.

Rollback only reviewed exact ids/fields from the timestamped before-products snapshot. Never reverse warehouse movements. Stop timer to pause future price observations. Shop-only release is owned separately by OracSEO task and documented in `Projects/Wallcov-Shop/Orac-SEO` in the vault.
