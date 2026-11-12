# AI Maintenance Copilot

Industrial BI + Generative AI copilot for maintenance prioritization, reliability analysis and explainable reporting.

![Dashboard Preview](assets/dashboard-overview.png)

## Overview
AI Maintenance Copilot is a portfolio project that combines industrial maintenance KPIs, reliability analysis and LLM-based assistance into a single decision-support application.

The tool allows users to:
- upload maintenance indicators and event history
- rank assets by maintenance priority
- analyze MTBF, MTTR and failure patterns
- generate AI-assisted explanations and reports
- export professional PDF summaries

## Key Features
- Streamlit web interface
- KPI analysis with Python and Pandas
- Reliability analysis (MTBF, MTTR, availability)
- Failure Pareto visualization
- AI assistant with Gemini
- Multi-agent orchestration for explainable analysis
- PDF report generation

## Tech Stack
- Python
- Streamlit
- Pandas
- Plotly / visualization
- Gemini API
- Pytest

## Demo Screenshots
### Overview Dashboard
![Overview](assets/dashboard-overview.png)

### AI Analysis
![AI Analysis](assets/maintenance-ai-tab.png)

### PDF Report
![PDF Report](assets/report-preview.png)

## Project Structure
```text
app.py
analytics.py
agent_tools.py
agent_gemini.py
multiagent.py
report_pdf.py
data/
tests/
