"""跨模块契约(纯类型,零依赖)。三方(apps/agent/services)共享的词汇表。"""

from platform_contracts.dto import HealthReport, HealthStatus, JobRef, JobStatus
from platform_contracts.errors import (
    HTTP_STATUS,
    ErrorBody,
    ErrorEnvelope,
    ErrorSuffix,
    ServiceError,
    make_code,
)
from platform_contracts.events import (
    LOCAL_USER,
    ActorKind,
    ActorRef,
    DomainEvent,
    Event,
    RuntimeEvent,
    new_trace_id,
)
from platform_contracts.version import ENVELOPE_VERSION, PROTOCOL_VERSION

__all__ = [
    "ENVELOPE_VERSION",
    "HTTP_STATUS",
    "LOCAL_USER",
    "PROTOCOL_VERSION",
    "ActorKind",
    "ActorRef",
    "DomainEvent",
    "ErrorBody",
    "ErrorEnvelope",
    "ErrorSuffix",
    "Event",
    "HealthReport",
    "HealthStatus",
    "JobRef",
    "JobStatus",
    "RuntimeEvent",
    "ServiceError",
    "make_code",
    "new_trace_id",
]
