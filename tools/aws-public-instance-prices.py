#!/usr/bin/env python3
"""Read the public AWS Price List; never uses account credentials or paid APIs."""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
import urllib.request

URL = 'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/sa-east-1/index.csv'
TARGETS = {'t3.small', 't3.medium', 't3a.medium'}


def parse(stream, max_rows=1000000):
    for line in stream:
        if line.startswith('"SKU"'):
            header = next(csv.reader([line]))
            break
    else:
        raise ValueError('pricing_header_missing')
    found = {}
    for index, row in enumerate(csv.DictReader(stream, fieldnames=header)):
        if index >= max_rows:
            raise ValueError('pricing_scan_limit')
        kind = row.get('Instance Type')
        if (kind in TARGETS and row.get('Operating System') == 'Linux'
                and row.get('Tenancy') == 'Shared' and row.get('Pre Installed S/W') == 'NA'
                and row.get('TermType') == 'OnDemand' and row.get('Unit') == 'Hrs'
                and row.get('CapacityStatus') == 'Used' and row.get('Currency') == 'USD'
                and row.get('Location') == 'South America (Sao Paulo)'):
            price = Decimal(row['PricePerUnit'])
            if not price.is_finite() or not 0 < price < 10:
                raise ValueError('invalid_price')
            found[kind] = {key: row.get(key) for key in ('SKU', 'Instance Type', 'Operating System',
                'Tenancy', 'Location', 'vCPU', 'Memory', 'Processor Architecture', 'EffectiveDate', 'PriceDescription')}
            found[kind].update(hourly_usd=str(price), monthly_730_hours_usd=str(price * 730))
            if set(found) == TARGETS:
                return found
    raise ValueError('pricing_targets_missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-public', action='store_true')
    args = parser.parse_args()
    if not args.fetch_public:
        print(json.dumps({'mode': 'plan', 'public_source': URL, 'account_api_calls': False}))
        return
    try:
        with urllib.request.urlopen(URL, timeout=45) as response:
            rates = parse(io.TextIOWrapper(response, encoding='utf-8-sig', newline=''))
        print(json.dumps({'source': URL, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'Public AWS Price List; Linux shared on-demand, no account credits/taxes/EBS/IPv4/CPU surplus',
            'rates': rates}, indent=2))
    except Exception:
        raise SystemExit('public_price_verification_failed') from None


if __name__ == '__main__':
    main()
