from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Axis-aligned bounding box in corner-point format, normalized to image size.

    This is a detection model's native output shape (xyxy), shared by any
    detector (face, object, etc.). Field order matters: callers zip model
    output onto `BoundingBox.model_fields.keys()` rather than instantiating
    this class directly.
    """

    xmin: float = Field(ge=0, le=1)
    ymin: float = Field(ge=0, le=1)
    xmax: float = Field(ge=0, le=1)
    ymax: float = Field(ge=0, le=1)
