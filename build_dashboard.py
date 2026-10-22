"""Generate Vega-Lite specifications from reconciled PostgreSQL exports."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(datasets):
    def save(name, spec):
        spec = {'$schema': 'https://vega.github.io/schema/vega-lite/v5.json',
                'background': 'transparent',
                'config': {'font': 'Arial', 'view': {'stroke': None},
                           'axis': {'gridColor': '#e8edf3', 'domain': False,
                                    'labelColor': '#536279', 'titleColor': '#536279'},
                           'title': {'anchor': 'start', 'color': '#12233d'},
                           'legend': {'orient': 'bottom'}}, **spec}
        target = ROOT / 'dashboard/specs' / (name + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(spec, ensure_ascii=False, indent=2, default=float) + '\n',
                          encoding='utf-8')

    metrics = datasets['metrics']
    latest = metrics[-1]
    kpis = [('Портфель', 'portfolio_kzt', 'portfolio_change_ratio', False),
            ('PAR30', 'par30_ratio', 'par30_change_pp', True),
            ('PAR90', 'par90_ratio', 'par90_change_pp', True),
            ('NPL', 'npl_ratio', 'npl_change_pp', True),
            ('Провизии', 'provisions_kzt', 'provisions_change_ratio', False),
            ('Top-10 групп', 'top10_ratio', 'top10_change_pp', True)]
    charts = []
    for label, field, delta, ratio in kpis:
        value = float(latest[field])
        display = f'{value * 100:.2f}%' if ratio else f'{value / 1e9:.2f} млрд ₸'
        change = float(latest[delta]) * (1 if ratio else 100)
        suffix = 'п.п.' if ratio else '%'
        rows = [{'value': display, 'change': f'{change:+.2f} {suffix} к 01.09'}]
        charts.append({'title': {'text': label, 'fontSize': 13, 'fontWeight': 'normal'},
                       'width': 160, 'height': 66, 'data': {'values': rows},
                       'layer': [
                           {'mark': {'type': 'text', 'align': 'left', 'fontSize': 24,
                                     'fontWeight': 'bold', 'color': '#12233d'},
                            'encoding': {'x': {'value': 0}, 'y': {'value': 22},
                                         'text': {'field': 'value'}}},
                           {'mark': {'type': 'text', 'align': 'left', 'fontSize': 12,
                                     'color': '#526479'},
                            'encoding': {'x': {'value': 0}, 'y': {'value': 52},
                                         'text': {'field': 'change'}}}]})
    save('kpis', {'concat': charts, 'columns': 3, 'spacing': 30})
    rows = []
    for r in metrics:
        for label, key in [('PAR30', 'par30_ratio'), ('PAR90', 'par90_ratio'), ('NPL', 'npl_ratio')]:
            rows.append({'date': r['report_date'], 'metric': label, 'value': r[key]})
    save('risk_trend', {'width': 'container', 'height': 185,
                       'data': {'values': rows}, 'mark': {'type': 'line', 'point': True, 'strokeWidth': 3},
                       'encoding': {
                           'x': {'field': 'date', 'type': 'ordinal', 'title': None,
                                 'axis': {'labelAngle': 0}},
                           'y': {'field': 'value', 'type': 'quantitative', 'title': None,
                                 'axis': {'format': '.0%'}, 'scale': {'zero': True}},
                           'color': {'field': 'metric', 'title': None,
                                     'scale': {'domain': ['PAR30','PAR90','NPL'],
                                               'range': ['#2670db','#91a8c8','#e18a3a']}},
                           'tooltip': [{'field': 'date', 'title': 'Дата'}, {'field': 'metric', 'title': 'Метрика'},
                                       {'field': 'value', 'format': '.2%', 'title': 'Доля'}]}})
    save('portfolio_trend', {
        'width': 'container', 'height': 185, 'data': {'values': metrics},
        'transform': [{'calculate': 'datum.portfolio_kzt / 1e9', 'as': 'billions'}],
        'mark': {'type': 'bar', 'cornerRadiusTopLeft': 5, 'cornerRadiusTopRight': 5,
                 'color': '#2670db', 'size': 70},
        'encoding': {'x': {'field': 'report_date', 'type': 'ordinal', 'title': None,
                           'axis': {'labelAngle': 0}},
                     'y': {'field': 'billions', 'type': 'quantitative', 'title': 'млрд ₸'},
                     'tooltip': [{'field': 'report_date', 'title': 'Дата'},
                                 {'field': 'portfolio_kzt', 'title': 'Портфель, ₸', 'format': ',.2f'}]}})
    for dimension in ('sector', 'program'):
        rows = [r for r in datasets['segments'] if r['dimension'] == dimension]
        save(dimension, {
            'width': 'container', 'height': 235, 'data': {'values': rows},
            'params': [{'name': 'snapshot', 'value': latest['report_date'],
                        'bind': {'input': 'select', 'options': [r['report_date'] for r in metrics],
                                 'name': 'Дата: '}}],
            'transform': [{'filter': 'datum.report_date === snapshot'},
                          {'calculate': 'datum.portfolio_kzt / 1e9', 'as': 'billions'}],
            'mark': {'type': 'bar', 'cornerRadiusEnd': 4},
            'encoding': {
                'y': {'field': 'segment', 'type': 'nominal', 'sort': '-x', 'title': None,
                      'axis': {'labelLimit': 170}},
                'x': {'field': 'billions', 'type': 'quantitative', 'title': 'Портфель, млрд ₸'},
                'color': {'field': 'npl_ratio', 'type': 'quantitative', 'title': 'NPL',
                          'scale': {'domain': [0, 0.4], 'range': ['#c9ddfa','#195fbd']},
                          'legend': {'format': '.0%'}},
                'tooltip': [{'field': 'segment', 'title': 'Сегмент'},
                            {'field': 'portfolio_kzt', 'format': ',.2f', 'title': 'Портфель, ₸'},
                            {'field': 'npl_ratio', 'format': '.2%', 'title': 'NPL'},
                            {'field': 'provisions_kzt', 'format': ',.2f', 'title': 'Провизии, ₸'}]}})
    rows = [r for r in datasets['groups'] if r['exposure_rank'] <= 10]
    save('concentration', {
        'width': 'container', 'height': 245, 'data': {'values': rows},
        'params': [{'name': 'group_date', 'value': latest['report_date'],
                    'bind': {'input': 'select', 'options': [r['report_date'] for r in metrics],
                             'name': 'Дата: '}}],
        'transform': [{'filter': 'datum.report_date === group_date'},
                      {'calculate': 'datum.outstanding_kzt / 1e9', 'as': 'billions'}],
        'mark': {'type': 'bar', 'color': '#2670db', 'cornerRadiusEnd': 3},
        'encoding': {'y': {'field': 'group_id', 'type': 'nominal', 'sort': '-x', 'title': None},
                     'x': {'field': 'billions', 'type': 'quantitative', 'title': 'млрд ₸'},
                     'tooltip': [{'field': 'group_id', 'title': 'Группа'},
                                 {'field': 'outstanding_kzt', 'title': 'Остаток, ₸', 'format': ',.2f'}]}})


if __name__ == '__main__':
    build({name: json.loads((ROOT / f'dashboard/data/{name}.json').read_text(encoding='utf-8'))
           for name in ('metrics', 'segments', 'groups', 'quality')})
