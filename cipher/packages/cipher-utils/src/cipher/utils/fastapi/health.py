from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ServiceHealthStatus(StrEnum):
    OK = "OK"
    PENDING = "PENDING"
    ERROR = "ERROR"


class ServiceHealth(BaseModel):
    status: ServiceHealthStatus = ServiceHealthStatus.PENDING
    model_config = ConfigDict(use_enum_values=True)


service_health = ServiceHealth()
