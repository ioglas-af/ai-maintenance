"""Offline tests for numeric grounding, permissions and tool execution."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import demo_assets, demo_events, prepare_assets, prepare_events, event_analytics
from agent_tools import MaintenanceTools
from agent_gemini import run_agent


def demo_tools():
    ranked, _ = prepare_assets(demo_assets())
    events, _ = prepare_events(demo_events(), ranked["asset_name"].tolist())
    pareto, mix, monthly, corrected, scope = event_analytics(events, ranked["asset_name"].tolist())
    return MaintenanceTools(ranked, pareto, mix, monthly, corrected, "Demonstração (dados fictícios)", scope)


def test_agent_uses_validated_ranking():
    tools = demo_tools()
    top = tools.get_equipment_ranking("priority_score", "highest", 2)
    assert top["assets"][0]["asset_name"] == "Pump P-04"
    assert top["assets"][0]["priority_score"] == 88.2
    low = tools.get_equipment_ranking("total_maintenance_cost", "lowest", 1)
    assert low["assets"][0]["asset_name"] == "Steam Valve V-08"
    assert low["assets"][0]["total_maintenance_cost"] == 1300
    assert tools.get_equipment_ranking("roi")["error"] == "Metric not allowed"
    assert "error" in tools.get_equipment_ranking("priority_score", limit=999)


def test_agent_scope_no_leakage():
    tools = demo_tools()
    only_a = tools.assets[tools.assets["criticality"] == "A"].copy()
    scoped = MaintenanceTools(only_a, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                              pd.DataFrame(), "Arquivo CSV", "Sem histórico enviado")
    lowest = scoped.get_equipment_ranking("total_maintenance_cost", "lowest", 10)
    assert all(r["criticality"] == "A" for r in lowest["assets"])
    assert scoped.get_failure_analysis()["has_family_breakdown"] is False
    assert scoped.get_equipment_details("Steam Valve V-08")["error"].startswith("Equipment not found")
    assert scoped.get_equipment_details("Pump P-04")["corrective_order_count"] is None


def test_agent_invoke_denies_unknown_tools_and_args():
    tools = demo_tools()
    assert "error" in tools.invoke("exec", {"code": "import os"})
    assert "error" in tools.invoke("get_equipment_ranking", {"metric": "priority_score", "shell": "whoami"})
    assert "error" in tools.invoke("get_dataset_overview", {"unexpected": 3})
    assert "error" in tools.invoke("get_equipment_details", {"asset_name": "foo", "unexpected": "bar"})


def test_agent_history_contains_recorded_types_not_root_causes():
    tools = demo_tools()
    hist = tools.get_failure_analysis()
    assert hist["has_family_breakdown"] is True
    assert len(hist["failure_family_counts"]) > 0
    assert "root causes" in hist["note"]
    assert hist["history_scope"]


class FakeTypes:
    class Obj:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    FunctionDeclaration = Obj
    Tool = Obj
    GenerateContentConfig = Obj
    ToolConfig = Obj
    FunctionCallingConfig = Obj
    AutomaticFunctionCallingConfig = Obj

    @staticmethod
    def Content(**kwargs): return SimpleNamespace(**kwargs)

    class Part:
        @staticmethod
        def from_text(text): return {"text": text}
        @staticmethod
        def from_function_response(name, response): return {"name": name, "response": response}


class FakeModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def generate_content(self, *, model, contents, config):
        # Regression guard: Gemini rejects unsupported role="tool" on this API.
        assert all(getattr(item, "role", "") in {"user", "model"} for item in contents)
        self.requests.append({"model": model, "contents": list(contents), "mode":
                              config.tool_config.function_calling_config.mode})
        return self.replies.pop(0)


def response_with_call(name, args):
    return SimpleNamespace(
        function_calls=[SimpleNamespace(name=name, args=args)],
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=["call"]))],
        text=None,
    )


def response_with_text(text):
    return SimpleNamespace(function_calls=None,
                           candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=["text"]))],
                           text=text)


def test_manual_function_calling_records_real_executions(monkeypatch):
    fake_google = ModuleType("google")
    fake_google.genai = SimpleNamespace(Client=lambda **kwargs: None, types=FakeTypes)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_google.genai)
    fake = FakeModel([
        response_with_call("get_equipment_ranking", {"metric": "total_maintenance_cost", "order": "highest", "limit": 1}),
        response_with_call("get_equipment_details", {"asset_name": "Pump P-04"}),
        response_with_text("Pump P-04 custa 18.300 u.m. e tem disponibilidade de 92,7%."),
    ])
    client = SimpleNamespace(models=fake)
    result = run_agent(question="Qual o maior custo e sua confiabilidade?", tools=demo_tools(),
                       api_key="not-a-real-key", client=client)
    assert len(result.trace) == 2
    assert result.trace[0]["result"]["assets"][0]["total_maintenance_cost"] == 18300
    assert result.trace[1]["tool"] == "get_equipment_details"
    assert result.model_requests == 3
    assert [r["mode"] for r in fake.requests] == ["ANY", "AUTO", "AUTO"]
    assert "18.300" in result.answer
    tool_content = fake.requests[-1]["contents"][-1]
    assert tool_content.role == "user"
    assert tool_content.parts[0]["name"] == "get_equipment_details"


def test_requires_tool_call(monkeypatch):
    fake_google = ModuleType("google")
    fake_google.genai = SimpleNamespace(Client=lambda **kwargs: None, types=FakeTypes)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_google.genai)
    client = SimpleNamespace(models=FakeModel([response_with_text("inventei")]))
    with pytest.raises(RuntimeError, match="não utilizou uma ferramenta"):
        run_agent(question="qual o custo?", tools=demo_tools(), api_key="x", client=client)


def test_asset_history_is_scoped_and_grounded_in_events():
    assets, _ = prepare_assets(demo_assets())
    events, _ = prepare_events(demo_events(), assets["asset_name"].tolist())
    pareto, mix, monthly, corrected, scope = event_analytics(events, assets["asset_name"].tolist())
    tools = MaintenanceTools(assets, pareto, mix, monthly, corrected,
                             "Synthetic", scope, events=events)
    record = tools.invoke("get_equipment_failure_history", {"asset_name": "Pump P-04"})
    assert record["asset_name"] == "Pump P-04"
    raw = events[events["asset_name"] == "Pump P-04"]
    assert record["recorded_event_count"] == len(raw)
    assert record["recorded_corrective_count"] == len(raw[raw["maintenance_type"] == "CORR"])
    assert {r["failure_family"]: r["count"] for r in record["family_counts"]} == (
        raw[raw["maintenance_type"] == "CORR"].groupby("failure_family").size().to_dict())
    assert "error" in tools.invoke("get_equipment_failure_history", {"asset_name": "Pump P-04", "code": "bad"})
    assert "error" in tools.invoke("get_equipment_failure_history", {"asset_name": "Unknown"})
    # The active criticality filter must prevent reading excluded machines.
    only_a = assets[assets["criticality"] == "A"]
    scoped = MaintenanceTools(only_a, pareto, mix, monthly, corrected,
                              "Synthetic", scope, events=events)
    assert "error" in scoped.get_equipment_failure_history("Steam Valve V-08")
