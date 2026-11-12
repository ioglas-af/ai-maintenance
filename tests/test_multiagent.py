"""Offline tests for two distinct LLM roles, hand-off and fail-closed behavior."""
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import demo_assets, demo_events, prepare_assets, prepare_events, event_analytics
from agent_tools import MaintenanceTools
from multiagent import run_multiagent, build_handoff, MAX_HANDOFF_CHARS


def demo_tools():
    assets, _ = prepare_assets(demo_assets())
    events, _ = prepare_events(demo_events(), assets["asset_name"].tolist())
    pareto, mix, monthly, corrective, scope = event_analytics(events, assets["asset_name"].tolist())
    return MaintenanceTools(assets, pareto, mix, monthly, corrective, "Demonstração (dados fictícios)", scope)


class Types:
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


def fake_google(monkeypatch):
    google = ModuleType("google")
    google.genai = SimpleNamespace(types=Types, Client=lambda **k: None)
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", google.genai)


def response_call(name, args):
    return SimpleNamespace(
        function_calls=[SimpleNamespace(name=name, args=args)],
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=["function call"]))],
        text=None,
    )


def response_text(txt):
    return SimpleNamespace(
        function_calls=[],
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=["text"]))],
        text=txt,
    )


class MockModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        assert all(getattr(c, "role", "") in ("user", "model") for c in contents)
        self.calls.append((model, list(contents), config))
        return self.responses.pop(0)


def test_multiagent_uses_two_separate_model_roles_and_real_handoff(monkeypatch):
    fake_google(monkeypatch)
    model = MockModel([
        response_call("get_equipment_ranking", {"metric": "priority_score", "order": "highest", "limit": 1}),
        response_text("A Pump P-04 lidera o ranking com score 88,2."),
        response_text("Conclusão: priorizar verificação da Pump P-04 (score 88,2). Custos em u.m."),
    ])
    client = SimpleNamespace(models=model)
    result = run_multiagent(question="Qual equipamento priorizar?", tools=demo_tools(),
                            api_key="test-key", client=client)
    assert len(model.calls) == 3
    assert result.model_requests == 3
    assert len(result.tool_trace) == 1
    assert result.tool_trace[0]["result"]["assets"][0]["asset_name"] == "Pump P-04"
    assert len(result.workflow_trace) == 5
    assert [s["stage"] for s in result.workflow_trace] == [
        "Analista", "Analista", "Coordenador Python", "Coordenador Python", "Consultor"]
    assert result.workflow_trace[3]["event"] == "evidence_enrichment"
    assert result.coordinator_evidence[0]["function"] == "get_failure_analysis"
    assert "88,2" in result.answer
    analyst_config = model.calls[0][2]
    consultant_config = model.calls[2][2]
    assert analyst_config.tool_config.function_calling_config.mode == "ANY"
    assert not hasattr(consultant_config, "tools")
    assert "AGENTE CONSULTOR" in consultant_config.system_instruction
    consultant_input = model.calls[2][1][0].parts[0]["text"]
    assert "tool_evidence" in consultant_input
    assert '"priority_score": 88.2' in consultant_input
    assert '"data_source": "Demonstração (dados fictícios)"' in consultant_input
    assert '"analyst_summary": "A Pump P-04' in consultant_input


def test_multiagent_fails_without_real_tool_execution(monkeypatch):
    fake_google(monkeypatch)
    model = MockModel([response_text("Resposta sem consultar dados")])
    with pytest.raises(RuntimeError, match="não utilizou uma ferramenta"):
        run_multiagent(question="Qual o maior custo?", tools=demo_tools(),
                       api_key="test-key", client=SimpleNamespace(models=model))
    assert len(model.calls) == 1


def test_multiagent_fails_if_consultant_returns_nothing(monkeypatch):
    fake_google(monkeypatch)
    model = MockModel([
        response_call("get_dataset_overview", {}),
        response_text("Existem 10 ativos."),
        response_text(" "),
    ])
    with pytest.raises(RuntimeError, match="não retornou resposta"):
        run_multiagent(question="Resuma a base", tools=demo_tools(),
                       api_key="test-key", client=SimpleNamespace(models=model))


def test_handoff_contains_history_scope_and_no_fabricated_history():
    t = demo_tools()
    no_history = MaintenanceTools(t.assets, t.pareto.iloc[:0], t.mix.iloc[:0],
                                  t.monthly.iloc[:0], t.corrective_by_asset.iloc[:0],
                                  "CSV importado", "Sem histórico enviado")
    evidence = no_history.get_failure_analysis()
    handoff = build_handoff("Que falhas aparecem?", no_history,
                            "Não existem dados suficientes de falha.",
                            [{"tool": "get_failure_analysis", "arguments": {}, "result": evidence}])
    assert handoff["history_scope"] == "Sem histórico enviado"
    assert handoff["tool_evidence"][0]["result"]["has_family_breakdown"] is False
    assert json.dumps(handoff)


def test_handoff_rejects_missing_trace_or_excessive_size():
    t = demo_tools()
    with pytest.raises(RuntimeError, match="não executou"):
        build_handoff("Q", t, "A", [])
    with pytest.raises(RuntimeError, match="limite seguro"):
        build_handoff("Q", t, "X" * MAX_HANDOFF_CHARS,
                      [{"tool": "get_dataset_overview", "arguments": {}, "result": {}}])


def test_multiagent_requires_key_without_client():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        run_multiagent(question="Q", tools=demo_tools(), api_key="")


def test_coordinator_uses_per_equipment_history_when_csv_events_exist(monkeypatch):
    """The analyst can rank, coordinator must hand off exact per-asset event families."""
    fake_google(monkeypatch)
    source = Path(__file__).resolve().parents[1]
    import pandas as pd
    raw_assets = pd.read_csv(source / "data" / "cenario2_indicadores.csv")
    raw_events = pd.read_csv(source / "data" / "cenario2_eventos.csv")
    assets, _ = prepare_assets(raw_assets)
    events, _ = prepare_events(raw_events, assets["asset_name"].tolist())
    pareto, mix, monthly, corrective, scope = event_analytics(events, assets["asset_name"].tolist())
    assert len(assets) == 14
    assert len(events) == 90
    tools = MaintenanceTools(assets, pareto, mix, monthly, corrective,
                             "CSV de teste", scope, events=events)
    model = MockModel([
        response_call("get_equipment_ranking", {"metric": "priority_score", "order": "highest", "limit": 2}),
        response_text("Resumo do analista: maior prioridade para os dois primeiros."),
        response_text("Conclusão: priorizar verificações dos ativos com maiores scores."),
    ])
    result = run_multiagent(question="Quais manutenções investigar?", tools=tools,
                            api_key="mock", client=SimpleNamespace(models=model))
    assert result.model_requests == 3
    assert any(e["function"] == "get_equipment_failure_history" for e in result.coordinator_evidence)
    for evidence in result.coordinator_evidence:
        if evidence["function"] == "get_equipment_failure_history":
            name = evidence["arguments"]["asset_name"]
            expected = (events[(events["asset_name"] == name) &
                               (events["maintenance_type"] == "CORR")]
                        .groupby("failure_family").size().to_dict())
            actual = {r["failure_family"]: r["count"] for r in evidence["result"]["family_counts"]}
            assert actual == expected
    payload = model.calls[-1][1][0].parts[0]["text"]
    assert "coordinator_evidence" in payload
    assert "get_equipment_failure_history" in payload


def test_no_asset_history_is_not_invented_from_global_pareto():
    tools = demo_tools()
    assert tools.events is None
    assert tools.get_equipment_failure_history("Pump P-04")["has_asset_history"] is False
    from multiagent import collect_coordinator_evidence
    evidence = collect_coordinator_evidence(tools, [
        {"tool": "get_equipment_ranking", "arguments": {},
         "result": tools.get_equipment_ranking("priority_score", limit=1)}
    ])
    assert all(e["function"] != "get_equipment_failure_history" for e in evidence)
