"""Load CSV, build PostgreSQL views, reconcile and export a static dashboard."""
import argparse
import csv
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def read_csv(name):
    with (ROOT / 'data' / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def independent_totals():
    """Independent reference directly from source CSV, without SQL or exported data."""
    fx = {(r['date'], r['currency']): Decimal(r['rate_kzt']) for r in read_csv('fx.csv')}
    seen = {}
    totals = defaultdict(lambda: defaultdict(Decimal))
    groups = defaultdict(lambda: defaultdict(Decimal))
    for r in read_csv('portfolio.csv'):
        key = (r['report_date'], r['loan_id'])
        if key in seen:
            assert seen[key] == r, f'Conflicting duplicate: {key}'
            continue
        seen[key] = r
        if int(r['written_off']):
            continue
        day, currency = r['report_date'], r['currency']
        amount = Decimal(r['principal_outstanding']) * (
            Decimal(1) if currency == 'KZT' else fx[(day, currency)])
        dpd = int(r['days_past_due'])
        npl = dpd >= 91 or int(r['restructured']) == 1
        rate = Decimal('0.50') if npl else Decimal('0.10') if dpd >= 31 else Decimal('0.01')
        t = totals[day]
        t['portfolio_kzt'] += amount
        t['loan_count'] += 1
        t['par30_kzt'] += amount if dpd >= 31 else 0
        t['par90_kzt'] += amount if dpd >= 91 else 0
        t['npl_kzt'] += amount if npl else 0
        t['provisions_kzt'] += amount * rate
        groups[day][r['group_id']] += amount
    for day, t in totals.items():
        t['top10_kzt'] = sum(sorted(groups[day].values(), reverse=True)[:10])
        for name in ('par30', 'par90', 'npl', 'top10'):
            t[name + '_ratio'] = t[name + '_kzt'] / t['portfolio_kzt']
        t['provision_ratio'] = t['provisions_kzt'] / t['portfolio_kzt']
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', action='store_true', help='Use the compose db service')
    parser.add_argument('--psql', default='psql', help='psql executable for a local PostgreSQL')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ['PGCLIENTENCODING'] = 'UTF8'
    command = (['docker', 'compose', 'exec', '-T', 'db', 'psql', '-U', 'arqa', '-d', 'arqa']
               if args.docker else [args.psql])

    def psql(sql):
        result = subprocess.run(command + ['-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1'],
                                input=sql, text=True, encoding='utf-8', errors='backslashreplace',
                                capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return result.stdout.strip()

    load = 'BEGIN;\n' + (ROOT / 'sql/01_raw.sql').read_text(encoding='utf-8')
    load += '\nTRUNCATE raw.portfolio, raw.fx;\n'
    for name in ('portfolio', 'fx'):
        load += f'COPY raw.{name} FROM STDIN WITH (FORMAT csv, HEADER true);\n'
        load += (ROOT / f'data/{name}.csv').read_text(encoding='utf-8-sig').rstrip() + '\n\\.\n'
    for name in ('02_views.sql', '03_checks.sql'):
        load += (ROOT / 'sql' / name).read_text(encoding='utf-8') + '\n'
    load += 'COMMIT;'
    psql(load)

    def fetch(view, order):
        return json.loads(psql(f'SELECT coalesce(json_agg(t), \'[]\'::json) FROM '
                              f'(SELECT * FROM reporting.{view} ORDER BY {order}) t;'),
                          parse_float=Decimal)

    datasets = {
        'metrics': fetch('v_metrics_change', 'report_date'),
        'segments': fetch('v_segments', 'report_date, dimension, segment'),
        'groups': fetch('v_group_exposure', 'report_date, exposure_rank'),
        'quality': fetch('v_quality', 'report_date'),
    }
    reference = independent_totals()
    checks = 0
    for row in datasets['metrics']:
        for key, expected in reference[row['report_date']].items():
            tolerance = Decimal('1e-12') if key.endswith('_ratio') else Decimal('0.000001')
            assert abs(Decimal(row[key]) - expected) <= tolerance, (key, row[key], expected)
            checks += 1
        for dimension in ('sector', 'program'):
            subset = [r for r in datasets['segments']
                      if r['report_date'] == row['report_date'] and r['dimension'] == dimension]
            for key in ('portfolio_kzt', 'par30_kzt', 'par90_kzt', 'npl_kzt', 'provisions_kzt'):
                assert sum(r[key] for r in subset) == row[key], (dimension, key)
                checks += 1
    psql((ROOT / 'tests/edge_cases.sql').read_text(encoding='utf-8'))
    # The test transaction rolls back. Reloading proves the real input is repeatable too.
    psql(load)
    assert fetch('v_metrics_change', 'report_date') == datasets['metrics'], 'Reload changed metrics'
    report = {
        'status': 'passed', 'postgres_version': psql('SHOW server_version;'),
        'independent_and_segment_checks': checks, 'sql_edge_tests': 'passed',
        'idempotent_reload': 'passed',
        'source_sha256': {name: hashlib.sha256((ROOT / 'data' / name).read_bytes()).hexdigest()
                          for name in ('portfolio.csv', 'fx.csv')},
    }
    out = ROOT / 'dashboard/data'
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in datasets.items():
        (out / f'{name}.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2,
                                                   default=float) + '\n', encoding='utf-8')
    (ROOT / 'validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    from build_dashboard import build
    build(datasets)
    print(json.dumps(report, indent=2))
    for row in datasets['metrics']:
        print(json.dumps(row, default=str))


if __name__ == '__main__':
    main()
