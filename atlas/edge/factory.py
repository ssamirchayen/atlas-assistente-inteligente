"""Default local composition for the Sprint 23 Atlas Edge agent."""

from __future__ import annotations

from atlas.core.config import (
    DATA_DIR,
    EDGE_AUDIT_MAX_EVENTS,
    EDGE_AUDIT_RETENTION_DAYS,
    EDGE_EXECUTION_ENABLED,
    EDGE_MAX_ACTIVE_ONBOARDINGS,
    EDGE_MAX_ONBOARDINGS,
    EDGE_MAX_TASKS,
    PROVISIONING_COMMAND_TIMEOUT,
    PROVISIONING_DRY_RUN,
    PROVISIONING_MAX_STEPS,
    PROVISIONING_WORKSPACE,
)
from atlas.edge.agent import ITProvisioningAgent
from atlas.edge.audit import SqliteEdgeAuditTrail
from atlas.edge.execution import EdgeExecutionService
from atlas.edge.governance import EdgePolicyEngine, build_edge_policy
from atlas.edge.governed_service import GovernedEdgeService
from atlas.edge.onboarding_service import EmployeeOnboardingService
from atlas.edge.onboarding_store import EmployeeOnboardingStore
from atlas.edge.profile_service import EdgeProfileService
from atlas.edge.profiles import EmployeeProfileCatalog
from atlas.edge.storage import EdgeStateStore
from atlas.edge.task_queue import EdgeTaskQueue, EdgeTaskStore
from atlas.provisioning.executor import ProvisioningExecutor
from atlas.provisioning.factory import build_provisioning_profiles
from atlas.provisioning.inventory import DeviceInventoryCollector
from atlas.provisioning.planner import ProvisioningPlanner


def build_default_edge_agent() -> ITProvisioningAgent:
    return ITProvisioningAgent(
        store=EdgeStateStore(DATA_DIR / "edge" / "device.json"),
        collector=DeviceInventoryCollector(
            timeout=PROVISIONING_COMMAND_TIMEOUT,
        ),
    )


def build_default_edge_profile_service() -> EdgeProfileService:
    """Compose read-only planning over the enrolled local agent."""

    return EdgeProfileService(
        agent=build_default_edge_agent(),
        collector=DeviceInventoryCollector(
            timeout=PROVISIONING_COMMAND_TIMEOUT,
        ),
        planner=ProvisioningPlanner(),
        catalog=EmployeeProfileCatalog(build_provisioning_profiles()),
    )


def build_default_edge_execution_service() -> EdgeExecutionService:
    """Compose persistent supervised execution with fail-safe defaults."""

    agent = build_default_edge_agent()
    collector = DeviceInventoryCollector(
        timeout=PROVISIONING_COMMAND_TIMEOUT,
    )
    planner = ProvisioningPlanner()
    catalog = EmployeeProfileCatalog(build_provisioning_profiles())
    profile_service = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=planner,
        catalog=catalog,
    )
    queue = EdgeTaskQueue(
        EdgeTaskStore(DATA_DIR / "edge" / "tasks.json"),
        max_tasks=EDGE_MAX_TASKS,
    )
    executor = ProvisioningExecutor(
        PROVISIONING_WORKSPACE,
        command_timeout=PROVISIONING_COMMAND_TIMEOUT,
        dry_run=PROVISIONING_DRY_RUN or not EDGE_EXECUTION_ENABLED,
    )
    return EdgeExecutionService(
        agent=agent,
        profile_service=profile_service,
        queue=queue,
        catalog=catalog,
        collector=collector,
        planner=planner,
        executor=executor,
    )


def build_default_governed_edge_service() -> GovernedEdgeService:
    """Compose the production facade with RBAC, tenancy and persistent audit."""

    agent = build_default_edge_agent()
    collector = DeviceInventoryCollector(
        timeout=PROVISIONING_COMMAND_TIMEOUT,
    )
    planner = ProvisioningPlanner()
    profile_items = build_provisioning_profiles()
    catalog = EmployeeProfileCatalog(profile_items)
    profile_service = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=planner,
        catalog=catalog,
    )
    queue = EdgeTaskQueue(
        EdgeTaskStore(DATA_DIR / "edge" / "tasks.json"),
        max_tasks=EDGE_MAX_TASKS,
    )
    executor = ProvisioningExecutor(
        PROVISIONING_WORKSPACE,
        command_timeout=PROVISIONING_COMMAND_TIMEOUT,
        dry_run=PROVISIONING_DRY_RUN or not EDGE_EXECUTION_ENABLED,
    )
    execution_service = EdgeExecutionService(
        agent=agent,
        profile_service=profile_service,
        queue=queue,
        catalog=catalog,
        collector=collector,
        planner=planner,
        executor=executor,
    )
    enrollment = agent.state.enrollment
    policies = ()
    if enrollment is not None:
        policies = (
            build_edge_policy(
                enrollment.organization_id,
                profile_items,
                max_steps=PROVISIONING_MAX_STEPS,
                allow_real_execution=(
                    EDGE_EXECUTION_ENABLED and not PROVISIONING_DRY_RUN
                ),
            ),
        )
    return GovernedEdgeService(
        agent=agent,
        profile_service=profile_service,
        execution_service=execution_service,
        policy=EdgePolicyEngine(policies),
        audit=SqliteEdgeAuditTrail(
            DATA_DIR / "edge" / "audit.db",
            retention_days=EDGE_AUDIT_RETENTION_DAYS,
            max_events=EDGE_AUDIT_MAX_EVENTS,
        ),
    )


def build_default_edge_onboarding_service() -> EmployeeOnboardingService:
    """Compose the persistent end-to-end employee onboarding workflow."""

    return EmployeeOnboardingService(
        governed=build_default_governed_edge_service(),
        store=EmployeeOnboardingStore(
            DATA_DIR / "edge" / "onboardings.json",
            max_records=EDGE_MAX_ONBOARDINGS,
        ),
        max_active=EDGE_MAX_ACTIVE_ONBOARDINGS,
    )
