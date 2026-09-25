"""Integração de consulta com o contrato Atlas do Nexyra CRM."""

from .client import (
    NexyraActionPreview,
    NexyraActionRequest,
    NexyraClient,
    NexyraConfig,
    NexyraError,
)
from .commands import (
    NexyraPendingAction,
    execute_pending_action,
    format_action_preview,
    parse_action_request,
    prepare_action,
)
from .connector import NexyraConnector

__all__ = [
    "NexyraActionPreview",
    "NexyraActionRequest",
    "NexyraClient",
    "NexyraConfig",
    "NexyraConnector",
    "NexyraError",
    "NexyraPendingAction",
    "execute_pending_action",
    "format_action_preview",
    "parse_action_request",
    "prepare_action",
]
