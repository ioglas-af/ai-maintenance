"""PDF export for Maintenance Copilot (ReportLab, no external fonts required)."""
from datetime import datetime
from html import escape
from io import BytesIO
import re

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak,
)

NAVY = colors.HexColor('#12263B')
TEAL = colors.HexColor('#087E8B')
SLATE = colors.HexColor('#516172')
SOFT = colors.HexColor('#EFF5F7')
RULE = colors.HexColor('#DCE6EB')
WHITE = colors.white


def _pdf_text(value):
    """Escape user/data text before passing it to Paragraph markup."""
    s = '' if value is None else str(value)
    s = s.replace('\u2028', ' ').replace('\u2029', ' ').replace('\x00', '')
    return escape(s, quote=True)


def _fmt_number(value, decimals=1):
    if pd.isna(value):
        return 'N/D'
    return f'{float(value):,.{decimals}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _fmt_percent(value):
    return 'N/D' if pd.isna(value) else f'{float(value):.1%}'.replace('.', ',')


def _markdown_inline(text):
    # Escape first, then convert only simple bold spans to ReportLab markup.
    safe = _pdf_text(text)
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', safe)


def _footer(canvas, document):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(RULE)
    canvas.line(16 * mm, 18 * mm, width - 16 * mm, 18 * mm)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(SLATE)
    canvas.drawString(16 * mm, 13 * mm, 'MAINTENANCE COPILOT | Relatório de análise')
    canvas.drawRightString(width - 16 * mm, 13 * mm, f'Página {document.page}')
    canvas.restoreState()


def make_pdf_report(df, source, ai_answer='', question='',
                    pareto_df=None, mix_df=None, failure_scope='', data_warnings=None,
                    analysis_mode='', model_requests=None, tool_count=0):
    """Return formatted PDF bytes for the currently filtered/sorted assets."""
    if df is None or df.empty:
        raise ValueError('Não há equipamentos para incluir no PDF.')

    mem = BytesIO()
    page_width, _ = A4
    doc = SimpleDocTemplate(
        mem, pagesize=A4, leftMargin=16*mm, rightMargin=16*mm,
        topMargin=17*mm, bottomMargin=25*mm,
        title='Maintenance Copilot - Relatório de Manutenção',
        author='Maintenance Copilot',
    )
    usable = page_width - 32*mm
    style = getSampleStyleSheet()
    style.add(ParagraphStyle(
        name='ReportTitle', fontName='Helvetica-Bold', fontSize=19,
        leading=22, textColor=NAVY, spaceAfter=5,
    ))
    style.add(ParagraphStyle(
        name='ReportSubtitle', fontName='Helvetica', fontSize=9.3,
        leading=14, textColor=SLATE, spaceAfter=14,
    ))
    style.add(ParagraphStyle(
        name='SectionHead', fontName='Helvetica-Bold', fontSize=11.5,
        leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=8,
    ))
    style.add(ParagraphStyle(
        name='BodyReport', fontName='Helvetica', fontSize=9,
        leading=14, textColor=NAVY, spaceAfter=6,
    ))
    style.add(ParagraphStyle(
        name='SmallReport', fontName='Helvetica', fontSize=8,
        leading=12, textColor=SLATE, spaceAfter=5,
    ))
    style.add(ParagraphStyle(
        name='TableHeader', fontName='Helvetica-Bold', fontSize=7.1,
        leading=9, textColor=WHITE,
    ))
    style.add(ParagraphStyle(
        name='TableCell', fontName='Helvetica', fontSize=7.25,
        leading=10.4, textColor=NAVY,
    ))

    story = []
    story.append(Paragraph('MAINTENANCE COPILOT', style['ReportTitle']))
    story.append(Paragraph('Relatório de priorização e análise assistida por IA', style['ReportSubtitle']))

    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    source_line = f'<b>Fonte:</b> {_pdf_text(source)}<br/><b>Gerado em:</b> {date_str}'
    meta = Table([[Paragraph(source_line, style['SmallReport'])]], colWidths=[usable])
    meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT),
        ('BOX', (0, 0), (-1, -1), .5, RULE),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(meta)
    story.append(Spacer(1, 10))

    mean_availability = df['availability_ratio'].mean()
    total_cost = df['total_maintenance_cost'].sum(min_count=1)
    crit_a = (df['criticality'] == 'A').sum()
    metrics = [
        ('EQUIPAMENTOS', str(len(df))),
        ('DISPONIBILIDADE MÉDIA', _fmt_percent(mean_availability)),
        ('CUSTO TOTAL (u.m.)', _fmt_number(total_cost, 0)),
        ('CRITICIDADE A', str(int(crit_a))),
    ]
    headers = [Paragraph(_pdf_text(t), style['SmallReport']) for t, _ in metrics]
    values = [Paragraph(f'<font color="#087E8B"><b>{_pdf_text(v)}</b></font>',
                        style['SectionHead']) for _, v in metrics]
    kpi = Table([headers, values], colWidths=[usable/4]*4)
    kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT),
        ('LINEBELOW', (0, -1), (-1, -1), .6, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
        ('TOPPADDING', (0, 1), (-1, 1), 0),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 8),
    ]))
    story.append(kpi)

    story.append(Paragraph('Equipamentos com maior prioridade', style['SectionHead']))
    labels = ['#', 'Equipamento', 'Crit.', 'Disp.', 'MTTR (h)', 'MTBF (h)', 'Custo (u.m.)', 'Score']
    rows = [[Paragraph(_pdf_text(s), style['TableHeader']) for s in labels]]
    for position, (_, row) in enumerate(df.head(5).iterrows(), 1):
        vals = [
            str(position), str(row['asset_name']), str(row['criticality']),
            _fmt_percent(row['availability_ratio']),
            _fmt_number(row['mttr_hours']), _fmt_number(row['mtbf_hours']),
            _fmt_number(row['total_maintenance_cost'], 0),
            _fmt_number(row['priority_score']),
        ]
        rows.append([Paragraph(_pdf_text(s), style['TableCell']) for s in vals])
    # 178 mm usable: sums to 178 mm.
    widths = [8, 49, 12, 18, 19, 19, 32, 21]
    table = Table(rows, colWidths=[w*mm for w in widths], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, SOFT]),
        ('LINEBELOW', (0, -1), (-1, -1), .6, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 6))

    # Separate BI data from commentary for predictable pagination.
    story.append(Paragraph('Histórico de falhas e manutenção', style['SectionHead']))
    if failure_scope:
        story.append(Paragraph(_pdf_text(failure_scope), style['SmallReport']))
    if pareto_df is not None and not pareto_df.empty:
        headers = [Paragraph(_pdf_text(s), style['TableHeader']) for s in ('Família de falha', 'Ocorrências', 'Acumulado')]
        data_rows = [headers]
        for _, rr in pareto_df.head(5).iterrows():
            data_rows.append([
                Paragraph(_pdf_text(str(rr['failure_family'])), style['TableCell']),
                Paragraph(_fmt_number(rr['count'], 0), style['TableCell']),
                Paragraph(_fmt_number(rr['cumulative_pct']) + '%', style['TableCell']),
            ])
        overview = Table(data_rows, colWidths=[100*mm, 36*mm, 42*mm], repeatRows=1)
        overview.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, SOFT]),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(overview)
    else:
        story.append(Paragraph('Famílias de falhas não disponíveis no histórico enviado.', style['SmallReport']))
    if mix_df is not None and not mix_df.empty:
        mix_summary = ', '.join(f"{_pdf_text(r['maintenance_type'])}: {_fmt_number(r['count'], 0)}"
                                for _, r in mix_df.iterrows())
        story.append(Spacer(1, 8))
        story.append(Paragraph('<b>Mix de manutenção:</b> ' + mix_summary, style['SmallReport']))

    story.append(PageBreak())
    story.append(Paragraph('Análise assistida por IA', style['SectionHead']))
    # Record the actually selected mode; report carries only the final answer,
    # not the Analyst's intermediary draft or raw JSON tool traces.
    if ai_answer and analysis_mode:
        label = f'<b>Modo:</b> {_pdf_text(analysis_mode)}'
        if model_requests is not None:
            label += f' &nbsp; | &nbsp; <b>Chamadas à API:</b> {int(model_requests)}'
        if tool_count:
            label += f' &nbsp; | &nbsp; <b>Funções do Analista:</b> {int(tool_count)}'
        story.append(Paragraph(label, style['SmallReport']))
    if question and ai_answer:
        story.append(Paragraph('<b>Pergunta:</b> '+_pdf_text(question), style['SmallReport']))
    answer = (ai_answer or '').strip()
    if not answer:
        story.append(Paragraph(
            'Nenhuma análise por IA foi solicitada. O ranking acima é calculado pelo Python.',
            style['BodyReport']))
    else:
        for line in answer.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            # Strip headings / bullets if any; preserve semantic content.
            cleaned = re.sub(r'^#{1,5}\s*', '', cleaned)
            cleaned = re.sub(r'^[-*]\s+', '• ', cleaned)
            story.append(Paragraph(_markdown_inline(cleaned), style['BodyReport']))

    methodology = [Paragraph('Metodologia e limitações', style['SectionHead'])]
    for statement in [
        'A pontuação é uma heurística: criticidade (até 35 pontos), baixa disponibilidade (até 30), custo relativo (até 20), MTTR relativo (até 10) e MTBF relativo inverso (até 5).',
        'Os indicadores foram importados do arquivo; a aplicação não recalcula os KPIs do PostgreSQL. Os pesos não foram validados para uso operacional real.',
        'O score não é um modelo de previsão de falhas. Recomendações geradas por IA devem ser verificadas por um profissional.',
    ]:
        methodology.append(Paragraph(_pdf_text(statement), style['SmallReport']))
    if data_warnings:
        methodology.append(Paragraph('<b>Alertas de dados:</b>', style['SmallReport']))
        for item in data_warnings[:4]:
            methodology.append(Paragraph(_pdf_text(item), style['SmallReport']))
    story.append(KeepTogether(methodology))

    if 'fictíci' in source.lower() or 'demonstra' in source.lower():
        story.append(Paragraph(
            '<b>IMPORTANTE:</b> este relatório usa dados totalmente fictícios para demonstração.',
            style['SmallReport']))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return mem.getvalue()
