from atlas.benchmark.retail_office_simulation import (
    OfficeScenario,
    OfficeSimulationEngine,
    RetailScenario,
    RetailSimulationEngine,
    office_dashboard_payload,
    retail_dashboard_payload,
)


def test_retail_scenario_and_simulation_reduce_human_work():
    scenario = RetailScenario.from_dict({})
    result = RetailSimulationEngine().simulate(scenario)
    assert result.business.human_hours_liberated > 0
    assert result.business.atlas_human_hours < result.business.manual_human_hours
    assert result.exception_response_reduction_pct > 0


def test_retail_event_generation_is_deterministic_and_synthetic():
    scenario = RetailScenario.from_dict({})
    first = RetailSimulationEngine.generate_events(scenario, seed=27, count=20)
    second = RetailSimulationEngine.generate_events(scenario, seed=27, count=20)
    assert first == second
    assert len(first) == 20
    assert all(event.event_id.startswith("RT-SIM-") for event in first)


def test_retail_frontend_payload_contract():
    result = RetailSimulationEngine().simulate(RetailScenario.from_dict({}))
    payload = retail_dashboard_payload(result)
    assert payload["schema_version"] == "1.0"
    assert payload["kind"] == "retail_simulation"
    assert payload["frontend"]["ready"] is True


def test_office_scenario_and_simulation_reduce_human_work():
    scenario = OfficeScenario.from_dict({})
    result = OfficeSimulationEngine().simulate(scenario)
    assert result.business.human_hours_liberated > 0
    assert result.first_action_reduction_pct > 0
    assert result.atlas_on_time_pct >= result.manual_on_time_pct


def test_office_task_generation_is_deterministic_and_synthetic():
    scenario = OfficeScenario.from_dict({})
    first = OfficeSimulationEngine.generate_tasks(scenario, seed=27, count=20)
    second = OfficeSimulationEngine.generate_tasks(scenario, seed=27, count=20)
    assert first == second
    assert len(first) == 20
    assert all(task.task_id.startswith("OF-SIM-") for task in first)


def test_office_frontend_payload_contract():
    result = OfficeSimulationEngine().simulate(OfficeScenario.from_dict({}))
    payload = office_dashboard_payload(result)
    assert payload["schema_version"] == "1.0"
    assert payload["kind"] == "office_simulation"
    assert payload["frontend"]["ready"] is True
