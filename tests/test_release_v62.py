"""Regression tests for release 6.2 (prompts, PDF metadata, Markdown safety)."""
import ast
from pathlib import Path
import re

import pytest

from analytics import demo_assets, prepare_assets
from report_pdf import make_pdf_report
from multiagent import CONSULTANT_SYSTEM
from agent_gemini import AGENT_SYSTEM

ROOT = Path(__file__).resolve().parents[1]


def test_hydraulic_is_not_assumed_to_exist_in_compressor():
    assert 'Hydraulic' in CONSULTANT_SYSTEM
    assert 'NÃO comprova' in CONSULTANT_SYSTEM
    assert 'manual' in CONSULTANT_SYSTEM
    assert 'manual' in AGENT_SYSTEM
    assert 'compressor' in AGENT_SYSTEM


def test_intermediate_summary_is_in_collapsed_expander():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'Evidências e síntese do Analista (detalhes)' in source
    assert 'expanded=False' in source
    assert 'renderable_agent_markdown' in source
    assert 'make_pdf_report(' in source
    assert 'analysis_mode=st.session_state.get("ai_mode_used", "")' in source


def test_agent_markdown_escaping_helper():
    """Extract only the helper to test it without needing Streamlit installed."""
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    module = ast.parse(source)
    f = next(node for node in module.body
             if isinstance(node, ast.FunctionDef) and node.name == 'renderable_agent_markdown')
    code = ast.Module(body=[f], type_ignores=[])
    namespace = {'re': re}
    exec(compile(code, str(ROOT / 'app.py'), 'exec'), namespace)
    helper = namespace['renderable_agent_markdown']
    assert helper(r'\* \*\*Pump P-04\*\* \# Prioridade') == '* **Pump P-04** # Prioridade'
    assert helper(r'caminho\pasta') == r'caminho\pasta'


def test_pdf_has_final_multiagent_mode_and_no_analyst_draft():
    df, warnings = prepare_assets(demo_assets())
    assert not warnings
    report = make_pdf_report(
        df, 'Demonstração (dados fictícios)',
        'Conclusão: priorizar Pump P-04, conforme os dados do agente consultor.',
        'Quais equipamentos priorizar?',
        analysis_mode='Orquestração multiagente',
        model_requests=4,
        tool_count=3,
    )
    assert report.startswith(b'%PDF')
    assert len(report) > 1500
    fitz = pytest.importorskip('fitz')
    with fitz.open(stream=report, filetype='pdf') as doc:
        txt = '\n'.join(page.get_text() for page in doc)
    assert 'Orquestração multiagente' in txt
    assert 'Chamadas' in txt and '4' in txt
    assert 'Quais equipamentos priorizar?' in txt
    assert 'Conclusão: priorizar Pump P-04' in txt
    assert 'síntese intermediária' not in txt.lower()
    assert 'analyst_summary' not in txt
