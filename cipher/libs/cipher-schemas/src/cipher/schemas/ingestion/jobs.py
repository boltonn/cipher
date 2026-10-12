"""Job schemas - used by workflows, backend, and CLI."""

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas._base.common import ModelDevice


class JobStatus(StrEnum):
    """Job status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SetfitCVJobRequest(BaseModel):
    """Request to spawn a SetfitCV embedding job."""

    model_dir: str = Field(description="Path to model directory")
    dataset_name: str = Field(description="Dataset name")
    path: str = Field(description="Path to images")
    batch_size: int = Field(default=32, description="Batch size")
    device: ModelDevice = Field(default=ModelDevice.CPU, description="Device (CPU/CUDA)")
    log_path: str | None = Field(default=None, description="Path to log file")


class JobResponse(BaseModel):
    """Response from job spawn endpoint."""

    pid: int = Field(description="Process ID")
    status: str = Field(description="Job status")
