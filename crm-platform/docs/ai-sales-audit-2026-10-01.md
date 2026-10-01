# AI sales corrections — prepared, not released (2026-10-01)

This branch contains a first corrective package. It does not switch the production model, disable ChatPlace, change channel routing, edit customer data, or send messages.

## Changes

- Admin usage estimates use exact model tariffs and nested 5-minute/1-hour cache creation. Unknown models fail explicitly. The API response distinguishes the estimate from an invoice.
- Seller instructions and approved rules are complete, separately budgeted from relevant facts. Repeated facts no longer consume multiple retrieval slots. Stable instructions are eligible for prompt caching; product data remains fresh.
- Customer-supplied numbers cannot authorize quoted prices. Explicit requests for a manager call survive model-emitted orders.
- Funnel tools are checked against an allowlist before execution. Internal notes are excluded from customer dialogue. Identical successful scheduled inputs within 24 hours are not billed again; manual retries and failed runs remain retryable.
- Purchase-intent daily-limit exceptions use a single throttle claim. Draft replies are rechecked after generation against manager intervention, newer incoming messages and channel/chat state.
- Automatic gallery selection uses real tagged photos only; an exact product preference is not padded with another product. A single available photo is valid.
- Conflicting seller instructions have explicit closing-stage exceptions, catalog precedence and technical clarification requirements.
- Sonnet 5.5 is available as an optional candidate in the existing AI center. It is not selected automatically. Quality and actual token cost require a separate bounded evaluation.
- The UI cost estimate assembles a representative real prompt instead of assuming a fixed short prompt.

## Verification

87 isolated tests passed across the new audit regressions, closed-lead race regressions, knowledge/test-chat, channel gating and material pages. Two legacy AiOrderTests fail also on the unmodified baseline: test_no_duplicate_offer and test_repeat_resends_same_link. They expect superseded repeat-payment-link behavior and were excluded from the passing regression run, not silently rewritten.

No external generation or customer sends were used in tests. Compile and diff whitespace checks pass.

## Remaining release and migration gates

Owner approved implementation on 2026-10-01 ("ОК делай") and specified three roles and live nomenclature as the source of prices and composition. Recheck current branch, HEAD, locks and unrelated changes, then release only through deploy.sh. Publish and visually verify the employee ChangeLogEntry after release, not before.

This is not a completed ChatPlace migration. Card processing can no longer create parallel offers. Still required: external/internal reply ownership at cutover; durable cross-worker processing; preventing the shift toggle from re-enabling external AI; parity for active keyword/comment flows; owner-account tests of direct transport and native media; explicit cutover and rollback. The post-generation check narrows but does not eliminate the interval between state validation and network send.

Knowledge data has not been mass-edited. Literal prices and conflicting stored rules require guarded, versioned edits against current product records. Media-tag correctness has not been independently verified.

The private business/cost analysis is retained in the task outputs, not committed to the public source repository.

Tariffs: https://platform.claude.com/docs/en/about-claude/pricing
Cost-report units: https://platform.claude.com/docs/en/manage-claude/usage-cost-api

## Live catalogue and three roles (owner-approved follow-up)

- Seller owns customer communication and order creation; card processing and draft assistance are internal seller functions. ROP coaches; analyst reviews evidence without sending to customers.
- Current Product and ProductComponent values are read on every answer, including current names/SKU, exact decimal prices, currency, units and component quantities. Unknown/zero/quote-required prices are not described as free.
- New products can be located by current name/SKU; product aliases remain optional aids. Relevant kits only are included to avoid loading the entire kit inventory on every reply.
- Literal monetary examples in product-topic knowledge are suppressed during seller retrieval without rewriting stored knowledge. Delivery/discount policies are preserved.
- Catalogue facts are checked again after generation; a detected change discards the quote/order and hands off for a fresh calculation. This is not a transaction lock through network delivery.
- Historical paid orders are not repriced. Package board/tint options remain defined by the exact kit variant; warehouse components describe material quantities.
- 150 isolated tests passed in the combined release regression suite, including live price updates, changed kit composition, unknown/zero prices, exact currency/units, changed catalogue during generation and blocked parallel offer creation. Four baseline failures were reproduced separately and excluded: the two order tests above and tests_volume.TaraTests.test_tara_by_density / TintTests.test_color_from_library (unchanged volume code, original catalogue).

Prepared for gated release. ChatPlace cutover and model activation remain separate unfinished steps.
