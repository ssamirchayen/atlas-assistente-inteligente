from __future__ import annotations

from datetime import datetime, timezone

from atlas.automation.engine import AutomationEngine
from atlas.connectors import ConnectorDecision
from atlas.internet.models import (
    SearchResult,
    SearchStatus,
    WebSearchResponse,
)
from atlas.planner.actions import Action
from atlas.planner.planner import Planner


class StubSearchService:
    def __init__(self, response: WebSearchResponse) -> None:
        self.response = response
        self.calls: list[object] = []

    def search(self, request: object, principal: object) -> WebSearchResponse:
        self.calls.append((request, principal))
        return self.response


def make_response() -> WebSearchResponse:
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    return WebSearchResponse(
        trace_id="trace-1",
        query="indústrias de Manaus",
        status=SearchStatus.SUCCESS,
        results=(
            SearchResult(
                citation_id=1,
                title="Polo Industrial de Manaus",
                url="https://example.com/pim",
                domain="example.com",
                snippet="Informações sobre o polo industrial.",
                source_name="Example",
                provider_ids=("source.one",),
                provider_rank=1,
                score=0.9,
                retrieved_at=now,
            ),
        ),
        providers=(),
        retrieved_at=now,
        connector_decision=ConnectorDecision.ALLOWED,
        reason="Pesquisa concluída.",
    )


def test_planner_routes_multisource_phrase_without_changing_google_flow() -> None:
    planner = object.__new__(Planner)

    internet = planner._plan_direct_automation(
        "pesquise na internet por indústrias de Manaus",
        "pesquise na internet por industrias de manaus",
    )
    google = planner._plan_direct_automation(
        "pesquise no Google carros usados",
        "pesquise no google carros usados",
    )

    assert internet == [
        Action(
            type="internet.search",
            parameters={
                "query": "industrias de manaus",
                "max_results": 5,
            },
        )
    ]
    assert google == [
        Action(
            type="browser.search",
            parameters={"query": "carros usados"},
        )
    ]


def test_automation_formats_ranked_results_with_citation() -> None:
    service = StubSearchService(make_response())
    engine = AutomationEngine(internet_search=service)

    result = engine.execute(
        Action(
            type="internet.search",
            parameters={"query": "indústrias de Manaus"},
        )
    )

    assert result.success is True
    assert "[1] Polo Industrial de Manaus" in result.message
    assert "https://example.com/pim" in result.message
    assert len(service.calls) == 1
