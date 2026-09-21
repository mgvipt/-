# Content library and Microcement web capture

Scope approved 21 September 2026: article, CRM library insertion, web capture and audience analytics. PDF is explicitly excluded. Telegram bot flows remain outside this release.

CRM owns Instruction.content and product relations. publish_microcement first runs dry, then creates one reviewed record with --apply; it refuses to overwrite different content. Article uses the existing shop editorial collection and retrieves step titles from the published CRM record. Public full guide is stable /instructions/microcement on the shop, redirecting to the CRM backend; no login or expiry is required. Tracking tokens do not grant account access and do not gate the guide.

Library uses the existing chat composer: prepare-instruction creates an opaque share token, then onInsertText inserts the message. Only successful ordinary send marks instruction_shared. No second outbound sender or automated client messaging is introduced.

Website form accepts name plus phone OR email, optional explicit marketing consent, CSRF, throttle, honeypot, session-bound idempotency key and minimum fill time. Existing signed shop lead webhook/outbox is reused. CRM deduplicates normalized phone/email with advisory locks and refuses conflicting identities. Existing Contact blank fields may be enriched; nonempty identity/account/name is preserved. No sale/deal is manufactured for a guide request. Consent omission does not revoke an earlier grant; explicit unsubscribe does. Contacts with indicated channels are not claimed verified.

Shop events queue through existing LeadSubmission; customer requests are prioritized over analytics. Article anonymous events are linked to a contact after a request from the same opaque visitor. Guide opens use request/share tokens and late delivery can link prior opens. Public bots/preview GETs alone do not count opens; browser-visible POST does. Attribution is not authentication or proof of causality.

Audience dashboard requires marketing.view; contact rows also require contact.view; amounts require marketing.money. Contact and anonymous counts are separated. Sales are actual won deals created after first content touch, paid amount excludes payments marked returned. This is a cohort, not proof the guide caused the sale. External social impressions/comments are unavailable, not zero. Sources/campaign/content filters select request cohorts.

Validation: isolated Django tests for capture/dedup/consent/conflicts/events/permissions/public guide; existing site lead regression tests; TypeScript/Vite build; Laravel article/product/SEO/capture/outbox tests and existing editorial/form regressions. Live verification and release IDs recorded in the task publication report.

Deployment: backup databases/images and exact tracked source; additive content_library migration only; CRM via deploy.sh (build, migrate, smoke, switch), then dry-run/apply seed. Shop built from the exact live image plus scoped files; recreate app/worker/scheduler and reload nginx after config test. Backup paths and image tags captured at release time. Rollback application images and scoped commits; retain new contacts/events, never restore an old full DB over new sales. Disable new entry links first if rollback required.
