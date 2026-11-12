"""Deterministic maintenance analytics, input validation, and synthetic demo fixtures.

Asset-level reliability KPIs are imported from a separate source, not inferred
from the synthetic work-order event feed.
"""
from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import pandas as pd

REQUIRED = [
    "asset_name", "criticality", "availability_ratio", "mttr_hours",
    "mtbf_hours", "total_maintenance_cost",
]
VALID_CRITICALITY = {"A", "B", "C"}
VALID_MAINTENANCE = {"CORR", "PREV", "AMEL"}
MAX_ROWS = 10_000

DEMO_ROWS = [
    (1, "Pump P-04", "A", .927, 9.3, 112, 18300),
    (2, "Compressor C-02", "A", .944, 6.8, 180, 15000),
    (3, "Conveyor CV-07", "B", .961, 4.5, 290, 8700),
    (4, "Filling Machine F-01", "A", .977, 3.6, 420, 11900),
    (5, "Cooling Unit U-03", "B", .956, 5.1, 250, 9500),
    (6, "Fermenter T-06", "B", .985, 2.2, 610, 3900),
    (7, "Mixer M-05", "C", .989, 1.6, 780, 2200),
    (8, "Labeler L-02", "B", .974, 3.4, 460, 5300),
    (9, "Steam Valve V-08", "C", .992, 1.8, 820, 1300),
    (10, "Heat Exchanger HX-01", "A", .969, 4.2, 350, 7900),
]


def demo_assets() -> pd.DataFrame:
    return pd.DataFrame(DEMO_ROWS, columns=["asset_id"] + REQUIRED)


def demo_events() -> pd.DataFrame:
    """Deterministic invented work-order history for demonstrating Pareto and trends."""
    assets = demo_assets()["asset_name"].tolist()
    families = ["Electrical", "Mechanical", "Sensor / Instrumentation", "Pneumatic", "Process"]
    entries = []
    base = pd.Timestamp("2026-01-07")
    for i in range(70):
        name = assets[(i * 7 + i // 10) % len(assets)]
        maintenance = "CORR" if i % 5 != 0 else "PREV"
        entries.append({
            "asset_name": name,
            "event_date": (base + pd.Timedelta(days=i * 4)).date().isoformat(),
            "maintenance_type": maintenance,
            "failure_family": families[(i * 3 + i // 7) % len(families)] if maintenance == "CORR" else "",
            "downtime_hours": round(.4 + ((i * 11) % 27) / 7, 2) if maintenance == "CORR" else 0,
        })
    return pd.DataFrame(entries)


def _parse_number(value: Any) -> float:
    """Support decimals with comma, dot, and basic thousand grouping."""
    if value is None or pd.isna(value):
        return float("nan")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not s or s.lower() in {"na", "nan", "n/d", "none", "null", "-"}:
        return float("nan")
    if s.endswith("%"):
        raise ValueError("Use disponibilidade como proporção entre 0 e 1 (ex.: 0,967).")
    if not re.fullmatch(r"[+-]?[\d.,]+", s):
        raise ValueError(f"Valor numérico inválido: {str(value)[:40]}")
    if "," in s and "." in s:
        # last separator is decimal mark; earlier is thousands separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _read_csv(uploaded) -> pd.DataFrame:
    content = uploaded.getvalue()
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("CSV excede 5 MB. Envie um arquivo menor para esta demo.")
    if not content:
        raise ValueError("Arquivo CSV vazio.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(BytesIO(content), sep=None, engine="python", encoding=encoding, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError("Encoding do CSV não reconhecido.")


def load_assets(uploaded) -> tuple[pd.DataFrame, str, dict]:
    """Return asset data and any global Pareto/mix tables in existing Excel export."""
    if uploaded is None:
        return demo_assets(), "Demonstração (dados fictícios)", {}
    if uploaded.name.lower().endswith(".csv"):
        assets = _read_csv(uploaded)
        extras = {}
    else:
        content = BytesIO(uploaded.getvalue())
        with pd.ExcelFile(content) as book:
            sheet = "asset_kpi" if "asset_kpi" in book.sheet_names else book.sheet_names[0]
            assets = pd.read_excel(book, sheet_name=sheet)
            extras = {}
            if "failure_pareto" in book.sheet_names:
                extras["pareto"] = pd.read_excel(book, sheet_name="failure_pareto")
            if "maintenance_mix" in book.sheet_names:
                extras["mix"] = pd.read_excel(book, sheet_name="maintenance_mix")
    return assets, "Arquivo: " + uploaded.name, extras


def prepare_assets(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    missing = [col for col in REQUIRED if col not in raw.columns]
    if missing:
        raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(missing))
    if raw.empty:
        raise ValueError("Arquivo de equipamentos vazio.")
    if len(raw) > MAX_ROWS:
        raise ValueError(f"Máximo de {MAX_ROWS} equipamentos para esta demonstração.")
    df = raw.copy()
    warnings = []
    df["asset_name"] = df["asset_name"].astype("string").str.strip()
    if df["asset_name"].isna().any() or (df["asset_name"].fillna("") == "").any():
        raise ValueError("Todos os equipamentos precisam ter asset_name.")
    if df["asset_name"].str.len().gt(100).any():
        raise ValueError("Nomes de equipamentos com mais de 100 caracteres não são aceitos.")
    if df["asset_name"].str.casefold().duplicated().any():
        raise ValueError("Há nomes de equipamentos duplicados. Use asset_name único por ativo.")
    df["criticality"] = df["criticality"].astype("string").str.strip().str.upper()
    if not df["criticality"].isin(VALID_CRITICALITY).all():
        raise ValueError("Criticidade inválida: use apenas A, B ou C; não preencha valores ausentes como C automaticamente.")
    for col in REQUIRED[2:]:
        try:
            df[col] = df[col].map(_parse_number).astype(float)
        except ValueError as exc:
            raise ValueError(f"Coluna {col}: {exc}") from exc
    if df["availability_ratio"].isna().any():
        raise ValueError("Disponibilidade ausente. Preencha cada ativo com uma proporção entre 0 e 1.")
    if not df["availability_ratio"].between(0, 1, inclusive="both").all():
        raise ValueError("availability_ratio precisa estar entre 0 e 1, por exemplo 0.967 ou 0,967.")
    for col in ["mttr_hours", "mtbf_hours", "total_maintenance_cost"]:
        if (df[col].dropna() < 0).any():
            raise ValueError(f"{col} não pode ser negativo.")
        absent = int(df[col].isna().sum())
        if absent:
            warnings.append(f"{col}: {absent} valores não informados; não serão tratados como zero observado.")
    if df["mttr_hours"].eq(0).any() or df["mtbf_hours"].eq(0).any():
        warnings.append("Existem MTTR/MTBF iguais a zero. Confirme se representam zero real ou ausência convertida em zero na exportação original.")
    if "asset_id" not in df:
        df["asset_id"] = range(1, len(df) + 1)
    # Constant scoring rule for traceability; relative terms depend on the full dataset.
    criticality_pts = df["criticality"].map({"A": 35, "B": 20, "C": 8})
    availability_pts = (((.99 - df["availability_ratio"]).clip(lower=0) / .10).clip(upper=1)) * 30
    cost_max = df["total_maintenance_cost"].max(skipna=True)
    mttr_max = df["mttr_hours"].max(skipna=True)
    mtbf_max = df["mtbf_hours"].max(skipna=True)
    cost_pts = df["total_maintenance_cost"].fillna(0) / max(float(cost_max) if pd.notna(cost_max) else 0, 1) * 20
    mttr_pts = df["mttr_hours"].fillna(0) / max(float(mttr_max) if pd.notna(mttr_max) else 0, 1) * 10
    mtbf_pts = ((1 - df["mtbf_hours"].fillna(mtbf_max if pd.notna(mtbf_max) else 0) /
                 max(float(mtbf_max) if pd.notna(mtbf_max) else 0, 1)).clip(lower=0)) * 5
    if pd.isna(mtbf_max):
        mtbf_pts = pd.Series(0.0, index=df.index)
    if df["total_maintenance_cost"].isna().all():
        warnings.append("Custo ausente para todos os ativos: nenhum ponto de custo foi atribuído.")
    df["priority_score"] = (criticality_pts + availability_pts + cost_pts + mttr_pts + mtbf_pts).round(1)
    return df.sort_values("priority_score", ascending=False).reset_index(drop=True), warnings


def prepare_events(raw: pd.DataFrame, asset_names: list[str]) -> tuple[pd.DataFrame, list[str]]:
    required = {"asset_name", "failure_family", "maintenance_type"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError("CSV de eventos: colunas ausentes: " + ", ".join(missing))
    if raw.empty:
        raise ValueError("CSV de eventos vazio.")
    if len(raw) > 30_000:
        raise ValueError("Máximo de 30.000 eventos nesta demo.")
    df = raw.copy()
    df["asset_name"] = df["asset_name"].astype("string").str.strip()
    df["maintenance_type"] = df["maintenance_type"].astype("string").str.strip().str.upper()
    df["failure_family"] = df["failure_family"].astype("string").str.strip()
    if not df["maintenance_type"].isin(VALID_MAINTENANCE).all():
        raise ValueError("maintenance_type dos eventos deve ser CORR, PREV ou AMEL.")
    if df["asset_name"].isna().any() or (df["asset_name"].fillna("") == "").any():
        raise ValueError("Há eventos sem asset_name.")
    known = set(asset_names)
    unknown = sorted(set(df["asset_name"]) - known)
    if unknown:
        raise ValueError("Eventos contêm ativos não presentes nos KPIs: " + ", ".join(unknown[:5]))
    corr = df["maintenance_type"] == "CORR"
    if df.loc[corr, "failure_family"].isna().any() or (df.loc[corr, "failure_family"].fillna("") == "").any():
        raise ValueError("Cada evento CORR precisa de failure_family para calcular o Pareto.")
    df["failure_family"] = df["failure_family"].fillna("")
    df["failure_family"] = df["failure_family"].str.slice(0, 70)
    warnings = []
    if "downtime_hours" in df:
        try:
            df["downtime_hours"] = df["downtime_hours"].map(_parse_number)
        except ValueError as exc:
            raise ValueError("downtime_hours: " + str(exc)) from exc
        if (df["downtime_hours"].dropna() < 0).any():
            raise ValueError("downtime_hours não pode ser negativo.")
        if df["downtime_hours"].isna().any():
            warnings.append("Alguns eventos não têm downtime_hours; totais de parada podem ser incompletos.")
    if "event_date" in df:
        df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
        bad = int(df["event_date"].isna().sum())
        if bad:
            warnings.append(f"{bad} eventos sem data válida; excluídos apenas do gráfico temporal.")
    return df, warnings


def normalize_global_tables(extras: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = extras.get("pareto")
    m = extras.get("mix")
    if p is None or not {"family", "nb_pannes"}.issubset(p.columns):
        p = pd.DataFrame(columns=["failure_family", "count"])
    else:
        p = p[["family", "nb_pannes"]].rename(columns={"family": "failure_family", "nb_pannes": "count"})
        p["count"] = pd.to_numeric(p["count"], errors="coerce").fillna(0)
        p = p[p["count"] >= 0]
    if m is None or not {"maintenance_type", "nb_work_orders"}.issubset(m.columns):
        m = pd.DataFrame(columns=["maintenance_type", "count"])
    else:
        m = m[["maintenance_type", "nb_work_orders"]].rename(columns={"nb_work_orders": "count"})
        m["count"] = pd.to_numeric(m["count"], errors="coerce").fillna(0)
        m = m[m["count"] >= 0]
    return p, m


def event_analytics(events: pd.DataFrame | None, visible_names: list[str], extras: dict | None = None):
    """Return (pareto, mix, monthly, event_counts, scope_note)."""
    if events is not None:
        selected = events[events["asset_name"].isin(visible_names)]
        corr = selected[selected["maintenance_type"] == "CORR"]
        pareto = corr.groupby("failure_family").size().reset_index(name="count")
        mix = selected.groupby("maintenance_type").size().reset_index(name="count")
        count_by_asset = corr.groupby("asset_name").size().reset_index(name="corrective_count")
        if "event_date" in selected:
            dates = selected.dropna(subset=["event_date"]).copy()
            dates["month"] = dates["event_date"].dt.to_period("M").astype(str)
            month = dates.groupby("month").size().reset_index(name="count")
        else:
            month = pd.DataFrame(columns=["month", "count"])
        scope = "Ordens/eventos associados aos ativos filtrados; contagem não equivale ao tempo operacional."
    else:
        pareto, mix = normalize_global_tables(extras or {})
        month = pd.DataFrame(columns=["month", "count"])
        count_by_asset = pd.DataFrame(columns=["asset_name", "corrective_count"])
        scope = ("Totais globais das abas originais do Excel: não é possível filtrá-los por criticidade ou atribuí-los a um ativo."
                 if not pareto.empty or not mix.empty else
                 "Sem histórico de falhas. Envie um CSV de eventos para ver Pareto, mix e tendências.")
    if not pareto.empty:
        pareto = pareto.sort_values("count", ascending=False).reset_index(drop=True)
        total = pareto["count"].sum()
        pareto["cumulative_pct"] = (pareto["count"].cumsum() / total * 100).round(1) if total else 0
    return pareto, mix, month, count_by_asset, scope
