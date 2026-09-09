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

## Release verification update09.09.2026

421Orac products imported;manager picker421unique SKUcards,997contextual library links to790uniqueSharedLinkfiles. Empty legacy SKUsofFDP500/FX400filled only;initial failed transaction rolled back before corrected pilots/full import. StockC21310/SX15735preserved,SX157price480. Repeat importer dryrun0writes.

Daily timer enabled;full dry/apply421observations:358unchanged,9explicit source-conflict holds,53no_verified_live_source holds,1manualSX157hold.0pricewrites. Full later-date changes require the guarded2-observation path.

Shop subtitle VARCHAR255 initially rejected 37 long descriptions. Per Oleg’s instruction, shop owner migrated products.subtitle to TEXT. Full originals restored for all 37 only where current text matched our temporary shortening; zero manual conflicts. Pilot C341 (286 chars) and C352 (308 chars) published successfully, remaining 35 requeued. Importer writes full short_description without truncation; all 421 CRM subtitles match the full SEO source.

CRM instructionsChangeLogEntry125:«Інтернет-магазин»→«Як працювати з каталогом Orac та його цінами». AuthenticatedmanagerAPIandChrome/whats-newvisual checked. Oleg requested improved photo/cardpresentation;officialsources+hashesconfirmed,final designapproval is separate from publisheddata.

Oleg requested full official galleries, exact-SKU interiors, angles and diagrams for all 421 cards. This enrichment is ongoing; published is not design-approved. C200 official Orac catalogue 2019 pages74–75 identifies The Mint Madrid interior with C200 marker1 and PX117 marker2. Technical PDF links remain official links; do not raster-publish technical PDFs bearing explicit reproduction restrictions without permission.

## Gallery enrichment09.09.2026

Regional galleries are merged by exact manufacturer SKU, retaining source pages.1330sourceURLs→866unique preparedWebPfiles.47candidate SKU/file pairs excluded by visual comparison as duplicate views/crops/lighting. Two initial pilot duplicate relations1823/1824 and library items4249/4250 were removed by exact IDs with backup; sourceSharedLinks retained. Revised pilotCX189/CX197 passed, then30products updated.55additional relations across32products, total1052ProductImage/1052librarylinks→819unique livefiles. Existing text/prices/stock untouched.

No arbitrary photo limit; earlier4-interior cap removed. `scripts/enrich_orac_gallery_20260909.py` defaultdry, exactfilehashes, expectedupdated_at,row/advisorylocks, productbackup,append-onlyapprovedassets, existingqueue. `gallery-visual-audit.json` records visual exclusions. Repeated enrichment dryrun0writes.

Coverage421:259with manufacturer interior/application images,409with PDFdrawinglinks,90with at least2profileviews. An image assigned to the manufacturer SKU/model gallery does not prove the specific installed length,Flex orRAL finish. TechnicalPDFs are linked, not raster-republished. C200 all25regional pages and uncached3originals checked:sameprofilebytes underdifferentURLs. TheMint cataloguesource exactC200, but extractedJPEG publicationrights unresolved, not imported. The876officialdownloadcentreassets checked by metadata and thumbnail matching; no confirmed separateTheMintasset found.

421publicproducts independently checked by shopowner forHTTP/SEO/price/unit/images. Initiallisting design rejected by Oleg; shopowner release30c765f fixed scopedlistingCSS/padding/categorybuttons/CTA. Desktop and mobile390px independently visually verified. Oleg approved compact W100 preview as basis. Main Orac PDP release aee0d6b is live; independent desktop W100 check passed: larger complete profile, photo2/4 and original zoom. P3020F listing optical scale remains with shopowner. Final register has423regular rows (421published+2hold) and85separate clearance rows; clearance stock/publication not confirmed.
