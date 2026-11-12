# Maintenance Copilot | Industrial BI & Multi-Agent AI

An interactive industrial-maintenance decision-support demo built on my original [Industrial Maintenance Analytics](https://github.com/ioglas-af/industrial-maintenance) project.

**Problem:** maintenance teams need to interpret equipment reliability, repair time, costs and failure history without manually exploring several dashboards. **Solution:** a Streamlit application that imports maintenance data, visualizes KPIs, ranks assets with an explicit heuristic and generates evidence-based AI explanations and PDF reports.

> **Portfolio demonstration:** synthetic maintenance KPIs and event logs, not real industrial operational data. The multi-agent workflow was exercised locally with Gemini, and the code also has offline tests. Reliability metrics are imported, priority ranking is heuristic, and AI suggestions are not diagnoses.

**Practical validation performed:** live multi-agent run on a 14-equipment demonstration dataset, with asset-specific event-family evidence and a trace of four model requests; the application recorded distinct Analyst → Python coordinator → Consultant stages. This is a user-run functional check, not a standardized accuracy benchmark.

## Main features

- Industrial BI: availability, MTBF × MTTR scatter plot, cost by asset, criticality and prioritization ranking.
- Maintenance events: corrective/preventive mix, failure-family Pareto and monthly interventions (only when historical data are available).
- Quality and provenance: data validation, completeness indicators, source identification and documented assumptions.
- AI: Gemini API with **three selectable modes**: direct LLM, tool-using agent, and a **sequential two-agent workflow**.
- Reports: PDF and editable Markdown export based on the results displayed in the app.
- Data input: sample synthetic dataset, custom CSV datasets or an `asset_kpi` Excel export from the original SQL project.

## Multi-agent architecture (V6.2)

```text
User question (Streamlit)
          |
          v
Python coordinator (multiagent.py)
          |
          +--> Agent 1: ANALYST (Gemini)
          |       - Separate system instructions
          |       - Allowed: read-only function calling
          |       - get_dataset_overview()
          |       - get_equipment_ranking()
          |       - get_equipment_details()
          |       - get_failure_analysis()
          |       - get_equipment_failure_history(asset_name)
          |       - Produces a provisional summary + tool trace
          |
          +--> Structured JSON hand-off
          |       - The original user question and data scope
          |       - Actual function outputs from the Analyst
          |       - Extra read-only equipment-specific event evidence
          |         gathered by the Python coordinator (separately logged)
          |       - The provisional analyst summary (NOT treated as facts)
          |
          '--> Agent 2: CONSULTANT (Gemini)
                  - Independent system instructions and model request
                  - No tool permissions
                  - Grounds recommendations in actual tool/event evidence
                  - Cannot treat global Pareto as per-equipment root cause
                  - Returns conditional actions, evidence and limits
                           |
                           v
             Final answer + execution audit + PDF report
```

**What is actually orchestrated?** Two distinct LLM agent roles with different responsibilities and permissions, and a real transfer of tool outputs coordinated by Python. Both agents currently use Gemini. This is a **simple sequential multi-agent workflow**, **not** dynamic task delegation, asynchronous agents, several model providers, or a production-grade autonomous maintenance system.

The workflow display exposes real tool executions, evidence transfer, stages and API request counts. It does **not** expose or claim to capture hidden model reasoning.

### Why keep three AI modes?

| Mode | What happens |
|---|---|
| Direct LLM | Python prepares selected data; Gemini writes an explanation. |
| Tool agent | Gemini chooses and calls read-only Python functions. |
| Multi-agent | Analyst calls tools, Python passes verified outputs to Consultant, Consultant writes recommendations. |

This lets reviewers compare the same question across architectures. The multi-agent mode uses **at least three model requests**, so it is not automatically cheaper, faster or more accurate than a single-agent solution.

## Run locally

Requires Python 3.11+ and a Gemini API key.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`.

To enable Gemini, create `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your-key"
```

The application defaults to `gemini-3.5-flash-lite`. Your API access and quota must support the selected model and function calling. To override the model in Windows PowerShell before running:

```powershell
$env:GEMINI_MODEL = "YOUR_SUPPORTED_GEMINI_MODEL"
```

Keep `.venv`, `.streamlit/secrets.toml` and `.env` outside version control; the `.gitignore` is included. For Streamlit Community Cloud, copy the key to the deployment's **Secrets** settings instead.

## Demonstrate it in two minutes

1. Open **IA & Relatório** and choose **Orquestração multiagente**.
2. Ask: *"Quais equipamentos devemos priorizar com base em custo, MTBF e MTTR? Justifique os números e sugira verificações."*
3. Expand **Orquestração verificável**: the log shows **Analista → Coordenador Python → Consultor**.
4. Expand **Ferramentas executadas pelo Analista** to inspect a readable table of actual tool calls. Optional technical JSON remains hidden by default.
5. Export the PDF report. Repeat with `data/cenario2_indicadores.csv` and `data/cenario2_eventos.csv` to demonstrate that outputs depend on user-provided data.

A typical call sequence is: ranking by priority/cost → analyst summary → structured hand-off → consultant response. Which tool the analyst chooses depends on the question and model.

## Data formats

Asset CSV required columns:

`asset_name`, `criticality` (A/B/C), `availability_ratio` (0–1), `mttr_hours`, `mtbf_hours`, `total_maintenance_cost`.

Optional intervention CSV:

`asset_name`, `maintenance_type` (`CORR`, `PREV`, `AMEL`), `failure_family` (corrective failures). Optional `event_date`, `downtime_hours`.

The `data/` folder has a ten-asset demo, an alternate fourteen-asset scenario, and invalid-input examples. Custom asset uploads **do not inherit synthetic events** without an uploaded event CSV.

## Test and verification

Offline unit tests (28 passing in the V6.2 build environment), including mocked multi-agent coordination:

```powershell
python -m pip install pytest
python -m pytest -q
```

The tests validate data rules, allowlisted tools, the manual Gemini function-response format, the two-agent hand-off, distinct prompt configurations, missing-history behavior, case-specific family counts for an alternate 14-asset / 90-event CSV, and failure when a stage does not return usable output.

### V6.1 release fixes

- Session query counter refreshes immediately after successful completion (via Streamlit rerun). It counts completed UI queries, not raw Gemini API requests.
- Operational trace is presented as an auditable table. Analyst intermediate text is rendered as Markdown instead of displaying escape characters.
- The analyst has a new read-only `get_equipment_failure_history(asset_name)` function.
- When an events CSV is present, the Python coordinator retrieves event-family counts for up to three relevant visible machines. It logs these enrichment calls **separately** from LLM-selected tools. Global Pareto cannot be passed off as individual failure evidence.
- The consultant is instructed to link specific checks to recorded per-asset families when available, and label any otherwise generic checks as hypotheses. Counts do not establish physical root causes.
- Run the included alternate CSV scenario and manually compare Gemini's response with the tool evidence before publication.

**Not yet proven by offline tests:** real model/API calls, visual appearance inside Streamlit, the factual quality of every generated response, real quota behavior or deployed performance. Run the app with your own valid key and check tool calls and PDF locally before putting the public link in a portfolio.

### V6.2 release: professional presentation and technical caution

- **More careful maintenance recommendations:** a failure-family tag is a classification of a record, **not** proof that the associated component exists in the machine. In particular, `Hydraulic` on a compressor is not evidence of a hydraulic circuit. The consultant is instructed to check the maintenance record and machine manual/configuration before suggesting component inspection. LLM responses still require human verification.
- **Cleaner interface:** the final answer stays visible, but the workflow timeline, analyst interim summary, coordinator evidence and raw tool data are collapsed in separate optional sections. The analyst summary gets a light Markdown unescape for accidental `\*` and `\#`.
- **Report provenance:** the PDF now states the AI mode, Gemini request count and executed analyst-tool count when an AI answer is present. The PDF includes the consultant's **final** answer, not a copy of the analyst's intermediate notes or the raw JSON trace.
- **Verified build:** 28 automated tests passed in the build environment. A two-page demonstration PDF using the alternate CSV scenario was generated, rendered, and visually inspected. It is a sample composed from test data, **not** an actual Gemini response. The Streamlit UI and live Gemini behavior must still be checked on your Windows computer.

For the application update, copy `app.py`, `multiagent.py`, `agent_gemini.py` and `report_pdf.py` over the prior V6.1 files. Keep `analytics.py`, `agent_tools.py`, `.venv`, and `.streamlit/secrets.toml`.

## Engineering limitations

- **Synthetic demonstration data.** Do not interpret as real operational improvements or measured savings.
- **Heuristic ranking, not predictive maintenance.** Weights have not been calibrated for a real plant.
- **MTBF and MTTR are imported** and are not recomputed from the event CSV.
- **Failure family ≠ verified root cause**; AI suggestions are conditional checks for human review.
- **Cost currency unspecified.** Amounts are in `u.m.`; no financial ROI is computed without investment and benefit data.
- **Privacy:** some selected asset/KPI values and user questions are transmitted to the Google API when AI modes are used. Upload public, synthetic or authorized data only.
- Prompt instructions and tool grounding reduce risk but **do not guarantee factual correctness**. Inspect responses and audit traces before making maintenance decisions.
- Local three-query session cap is not a secure, global rate-limit or API-cost guarantee.

## Project layout

```text
app.py                  Streamlit interface and report UI
analytics.py            Loading, validation and BI calculations
agent_tools.py          Restricted, read-only Pandas tools + per-asset failure history
agent_gemini.py         Analyst tool-calling engine (V5)
multiagent.py           Two-agent workflow and auditable coordinator enrichment (V6.1)
report_pdf.py           Professional PDF export
requirements.txt        Python dependencies
data/                   Demonstration and validation datasets
tests/                  Offline tests
```
#   a i - m a i n t e n a n c e  
 #   a i - m a i n t e n a n c e  
 