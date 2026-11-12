from pathlib import Path
import io
import pandas as pd
import pytest
from analytics import (demo_assets, demo_events, prepare_assets, prepare_events,
                       event_analytics, load_assets, _read_csv)
from report_pdf import make_pdf_report

ROOT = Path(__file__).resolve().parents[1]

class Upload:
    def __init__(self, name, data):
        self.name = name
        self.data = data
    def getvalue(self):
        return self.data


def test_demo_priority_and_kpis():
    ranked, warnings = prepare_assets(demo_assets())
    assert ranked.iloc[0]['asset_name'] == 'Pump P-04'
    assert ranked.iloc[0]['priority_score'] == 88.2
    assert ranked.iloc[-1]['asset_name'] == 'Steam Valve V-08'
    assert ranked['total_maintenance_cost'].sum() == 84000
    assert round(ranked['availability_ratio'].mean(),3) == .967
    assert not warnings


def test_csv_with_semi_colon_and_decimal_comma():
    path = ROOT / 'data/exemplo_indicadores_ponto_virgula.csv'
    u = Upload('example.csv', path.read_bytes())
    data, source, _ = load_assets(u)
    ranked, _ = prepare_assets(data)
    assert len(ranked) == 10
    assert ranked.iloc[0]['availability_ratio'] == pytest.approx(.927)
    assert ranked.iloc[0]['total_maintenance_cost'] == pytest.approx(18300)


def test_uploaded_assets_without_failures_does_not_invent_pareto():
    path = ROOT / 'data/exemplo_indicadores.csv'
    d, _, extra = load_assets(Upload('example.csv', path.read_bytes()))
    ranked, _ = prepare_assets(d)
    p, m, month, per_asset, scope = event_analytics(None, ranked['asset_name'].tolist(), extra)
    assert p.empty and m.empty and per_asset.empty and month.empty
    assert 'Sem histórico' in scope


def test_uploaded_events_pareto_mix_and_month():
    events_raw = _read_csv(Upload('events.csv', (ROOT/'data/exemplo_eventos.csv').read_bytes()))
    events, _ = prepare_events(events_raw, demo_assets()['asset_name'].tolist())
    p, m, monthly, per_asset, _ = event_analytics(events, demo_assets()['asset_name'].tolist())
    assert int(p['count'].sum()) == int((events['maintenance_type'] == 'CORR').sum())
    assert int(m['count'].sum()) == len(events)
    assert len(monthly) >= 2
    assert p.iloc[-1]['cumulative_pct'] == 100
    assert int(per_asset['corrective_count'].sum()) == int(p['count'].sum())


def test_invalid_input_rejected():
    d, _, _ = load_assets(Upload('example.csv', (ROOT/'data/exemplo_invalido.csv').read_bytes()))
    with pytest.raises(ValueError, match='duplicados'):
        prepare_assets(d)
    d = demo_assets()
    d.loc[0,'availability_ratio'] = 1.1
    with pytest.raises(ValueError, match='entre 0 e 1'):
        prepare_assets(d)
    d = demo_assets()
    d.loc[0,'criticality'] = 'D'
    with pytest.raises(ValueError, match='Criticidade inválida'):
        prepare_assets(d)
    d = demo_assets()
    d.loc[0,'mtbf_hours'] = None
    ranked, warnings = prepare_assets(d)
    assert any('mtbf_hours' in w for w in warnings)
    assert pd.isna(ranked.loc[ranked['asset_name']=='Pump P-04','mtbf_hours']).all()


def test_foreign_asset_events_rejected():
    e = demo_events()
    e.loc[0, 'asset_name'] = 'UNKNOWN-DEVICE'
    with pytest.raises(ValueError, match='não presentes'):
        prepare_events(e, demo_assets()['asset_name'].tolist())


def test_pdf_has_pdf_magic_and_two_sections():
    assets, _ = prepare_assets(demo_assets())
    events, _ = prepare_events(demo_events(), assets['asset_name'].tolist())
    pareto, mix, *_ = event_analytics(events, assets['asset_name'].tolist())
    blob = make_pdf_report(
        assets, 'Demonstração (dados fictícios)',
        'Custos em u.m.; sem dados de ROI.', 'Qual é o ROI?',
        pareto_df=pareto, mix_df=mix, failure_scope='Eventos fictícios', data_warnings=[])
    assert blob.startswith(b'%PDF')
    assert len(blob) > 2500


def test_independent_scenario_upload():
    d = _read_csv(Upload('scenario.csv', (ROOT/'data/cenario2_indicadores.csv').read_bytes()))
    r, _ = prepare_assets(d)
    assert len(r) == 14
    assert 'Pump P-04' not in r['asset_name'].tolist()
    e = _read_csv(Upload('scenario_events.csv', (ROOT/'data/cenario2_eventos.csv').read_bytes()))
    events, _ = prepare_events(e, r['asset_name'].tolist())
    pareto, mix, _, _, _ = event_analytics(events, r['asset_name'].tolist())
    assert pareto['count'].sum() == (events['maintenance_type']=='CORR').sum()
    assert mix['count'].sum() == len(events)


def test_no_mtbf_no_false_reliability_points():
    d = demo_assets()
    d['mtbf_hours'] = None
    r, warnings = prepare_assets(d)
    assert r['priority_score'].max() < 100
    assert any('mtbf_hours' in w for w in warnings)
