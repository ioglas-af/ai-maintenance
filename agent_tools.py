"""Read-only maintenance tools for Gemini function calling.

All numerical answers come from validated Pandas tables. The language model
chooses a tool, but cannot execute arbitrary Python or modify files.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

ALLOWED_METRICS = {
    "priority_score", "total_maintenance_cost", "availability_ratio",
    "mtbf_hours", "mttr_hours",
}
COLUMNS = [
    "asset_name", "criticality", "priority_score", "availability_ratio",
    "mtbf_hours", "mttr_hours", "total_maintenance_cost",
]


def clean(value: Any) -> Any:
    """Convert pandas/numpy scalars to safe, JSON-compatible primitives."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)) or hasattr(value, "item"):
        value = value.item() if hasattr(value, "item") else value
        if isinstance(value, (int, float)):
            return None if not math.isfinite(float(value)) else value
    if pd.isna(value):
        return None
    return str(value)


class MaintenanceTools:
    """Functions exposed to the model; operate only on the current user filter."""

    def __init__(
        self,
        assets: pd.DataFrame,
        pareto: pd.DataFrame,
        mix: pd.DataFrame,
        monthly: pd.DataFrame,
        corrective_by_asset: pd.DataFrame,
        source: str,
        history_scope: str,
        events: pd.DataFrame | None = None,
    ):
        self.assets = assets.copy()
        self.pareto = pareto.copy()
        self.mix = mix.copy()
        self.monthly = monthly.copy()
        self.corrective_by_asset = corrective_by_asset.copy()
        self.source = str(source)[:250]
        self.history_scope = str(history_scope)[:400]
        # Optional validated work-order history, restricted to visible equipment.
        # Never infer event families for individual assets from global Excel totals.
        self.events = (events[events["asset_name"].isin(self.assets["asset_name"])].copy()
                       if events is not None else None)

    def get_dataset_overview(self) -> dict:
        """Return total equipment, mean availability, total recorded costs and scope."""
        df = self.assets
        return clean({
            "source": self.source,
            "asset_scope": "Only currently selected criticality filters",
            "asset_count": len(df),
            "criticality_counts": df["criticality"].value_counts().to_dict(),
            "mean_availability_ratio": float(df["availability_ratio"].mean()),
            "total_maintenance_cost_um": float(df["total_maintenance_cost"].sum(min_count=1)),
            "cost_unit": "u.m. (currency unspecified)",
            "priority_score_type": "illustrative heuristic, not a failure prediction",
            "kpi_scope": "MTBF/MTTR/availability imported; not recalculated from work orders",
            "failure_history_scope": self.history_scope,
        })

    def get_equipment_ranking(self, metric: str, order: str = "highest", limit: int = 5) -> dict:
        """Rank equipment by one numeric KPI or priority score.

        Args:
            metric: One of priority_score, total_maintenance_cost,
                availability_ratio, mtbf_hours, mttr_hours.
            order: highest or lowest.
            limit: Number of equipment, between 1 and 10.
        """
        if not isinstance(metric, str) or metric not in ALLOWED_METRICS:
            return {"error": "Metric not allowed", "allowed_metrics": sorted(ALLOWED_METRICS)}
        if order not in ("highest", "lowest"):
            return {"error": "Order must be highest or lowest"}
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            return {"error": "limit must be integer from 1 to 10"}
        valid = self.assets.dropna(subset=[metric])
        ranked = valid.sort_values(metric, ascending=order == "lowest").head(limit)
        return clean({
            "metric": metric, "order": order, "returned": len(ranked),
            "all_assets_considered": len(valid),
            "cost_unit": "u.m.",
            "assets": ranked[COLUMNS].to_dict("records"),
        })

    def get_equipment_details(self, asset_name: str) -> dict:
        """Return validated KPIs for one equipment by exact case-insensitive name."""
        if not isinstance(asset_name, str) or len(asset_name) > 100:
            return {"error": "Equipment name must be a string with at most 100 characters"}
        found = self.assets[
            self.assets["asset_name"].astype(str).str.casefold() == asset_name.strip().casefold()
        ]
        if found.empty:
            return {"error": "Equipment not found in current filters", "available_names":
                    self.assets["asset_name"].astype(str).head(15).tolist()}
        row = clean(found.iloc[0][COLUMNS].to_dict())
        if not self.corrective_by_asset.empty:
            subset = self.corrective_by_asset[
                self.corrective_by_asset["asset_name"] == found.iloc[0]["asset_name"]
            ]
            row["corrective_order_count"] = int(subset["corrective_count"].iloc[0]) if not subset.empty else 0
            row["corrective_order_count_scope"] = self.history_scope
        else:
            row["corrective_order_count"] = None
        row["cost_unit"] = "u.m."
        row["reliability_kpi_origin"] = "imported (not recomputed from events)"
        return row

    def get_failure_analysis(self) -> dict:
        """Return the available failure family Pareto and preventive/corrective mix.

        Do NOT infer root causes or per-machine failures when only global Excel
        aggregates are available. Empty arrays mean no such data were provided.
        """
        return clean({
            "history_scope": self.history_scope,
            "has_family_breakdown": not self.pareto.empty,
            "failure_family_counts": self.pareto[
                ["failure_family", "count", "cumulative_pct"]
            ].head(15).to_dict("records") if not self.pareto.empty else [],
            "maintenance_mix": self.mix[["maintenance_type", "count"]].head(10).to_dict("records")
            if not self.mix.empty else [],
            "monthly_intervention_counts": self.monthly[["month", "count"]].tail(12).to_dict("records")
            if not self.monthly.empty else [],
            "corrective_orders_by_asset": self.corrective_by_asset.sort_values(
                "corrective_count", ascending=False
            ).head(10).to_dict("records") if not self.corrective_by_asset.empty else [],
            "note": "Work-order event counts do not prove root causes or change imported MTBF/MTTR.",
        })

    def get_equipment_failure_history(self, asset_name: str) -> dict:
        """Return actual recorded failure families for one visible asset, if available.

        Global Pareto aggregates are NOT a substitute for per-equipment records.
        """
        if not isinstance(asset_name, str) or len(asset_name) > 100:
            return {"error": "Equipment name must be a string with at most 100 characters"}
        found = self.assets[
            self.assets["asset_name"].astype(str).str.casefold() == asset_name.strip().casefold()
        ]
        if found.empty:
            return {"error": "Equipment not found in current filters"}
        canonical_name = str(found.iloc[0]["asset_name"])
        if self.events is None:
            return clean({
                "asset_name": canonical_name, "has_asset_history": False,
                "history_scope": self.history_scope,
                "note": "No per-asset events available. Global Pareto cannot be assigned to this equipment.",
            })
        rows = self.events[self.events["asset_name"] == canonical_name]
        corr = rows[rows["maintenance_type"] == "CORR"]
        family_counts = (corr.groupby("failure_family").size()
                         .sort_values(ascending=False).head(10))
        mix = rows.groupby("maintenance_type").size().to_dict()
        result = {
            "asset_name": canonical_name,
            "has_asset_history": not rows.empty,
            "has_recorded_corrective_families": not family_counts.empty,
            "recorded_event_count": len(rows),
            "recorded_corrective_count": len(corr),
            "family_counts": [
                {"failure_family": str(f), "count": int(c)}
                for f, c in family_counts.items()
            ],
            "maintenance_mix": {str(k): int(v) for k, v in mix.items()},
            "history_scope": self.history_scope,
            "note": "Recorded categories are not confirmed root causes; counts are not failure-rate estimates.",
        }
        return clean(result)

    def invoke(self, name: str, args: dict) -> dict:
        """Explicit allowlist: no eval(), arbitrary imports, network or write actions."""
        if not isinstance(args, dict):
            return {"error": "Tool arguments must be an object"}
        if name == "get_dataset_overview":
            return self.get_dataset_overview() if not args else {"error": "No arguments expected"}
        if name == "get_equipment_ranking":
            if set(args) - {"metric", "order", "limit"}:
                return {"error": "Unrecognized ranking argument"}
            return self.get_equipment_ranking(**args)
        if name == "get_equipment_details":
            if set(args) != {"asset_name"}:
                return {"error": "Provide asset_name only"}
            return self.get_equipment_details(**args)
        if name == "get_failure_analysis":
            return self.get_failure_analysis() if not args else {"error": "No arguments expected"}
        if name == "get_equipment_failure_history":
            if set(args) != {"asset_name"}:
                return {"error": "Provide asset_name only"}
            return self.get_equipment_failure_history(**args)
        return {"error": "Unknown tool", "name": str(name)[:80]}
