"""Provider usage-report cost estimate, distinct from actual invoice/cost_report.
Tariffs verified 2026-10-01: https://platform.claude.com/docs/en/about-claude/pricing
Unknown models fail explicitly instead of being silently charged as Haiku.
"""
from decimal import Decimal
import re

RATES = {
    'claude-haiku-4-5': (1, 5), 'claude-haiku-3-5': (.8, 4),
    'claude-sonnet-4-5': (3, 15), 'claude-sonnet-4-6': (3, 15),
    'claude-sonnet-5': (2, 10), 'claude-sonnet-5-5': (2, 10),
    'claude-opus-4-1': (15, 75), 'claude-opus-4': (15, 75),
    'claude-opus-4-5': (5, 25), 'claude-opus-4-6': (5, 25),
    'claude-opus-4-7': (5, 25), 'claude-opus-4-8': (5, 25),
    'claude-opus-5': (5, 25), 'claude-opus-5-5': (4, 20),
}


def report_usage_cost(row):
    model = re.sub(r'-\d{8}$', '', row.get('model') or '')
    if model not in RATES:
        raise ValueError('Unknown model: ' + model)
    pin, pout = map(lambda x: Decimal(str(x)), RATES[model])
    n = lambda key: Decimal(str(row.get(key) or 0))
    creation = row.get('cache_creation') or {}
    # Admin API has nested cache_creation; Messages API has a total plus optional breakdown.
    w1 = Decimal(str(creation.get('ephemeral_1h_input_tokens') or 0))
    w5 = Decimal(str(creation.get('ephemeral_5m_input_tokens') or 0))
    if not creation:
        w5 = n('cache_creation_input_tokens')
    read_multiplier = Decimal('.05') if model == 'claude-opus-5-5' else Decimal('.1')
    value = (n('uncached_input_tokens') * pin + n('output_tokens') * pout
             + n('cache_read_input_tokens') * pin * read_multiplier
             + w5 * pin * Decimal('1.25') + w1 * pin * 2) / 1_000_000
    if row.get('service_tier') == 'batch':
        value *= Decimal('.5')
    if row.get('inference_geo') == 'us':
        value *= Decimal('1.1')
    return value
