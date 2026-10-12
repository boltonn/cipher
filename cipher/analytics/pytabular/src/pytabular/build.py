"""Build detectors by name: `header`, `validators`, `gliner`, `nerd`, `llm` (model ones by URL or local dir)."""

from dataclasses import dataclass

from cipher.schemas._base.common import ModelDevice
from pytabular.detectors import Detector
from pytabular.detectors.header_lexicon import HeaderLexiconDetector
from pytabular.detectors.validators import ValidatorDetector

DETECTOR_NAMES = ("header", "validators", "gliner", "nerd", "llm")


@dataclass(slots=True)
class ModelEndpoints:
    gliner_url: str | None = None
    gliner_model_dir: str | None = None
    nerd_url: str | None = None
    nerd_model_dir: str | None = None
    llm_model: str | None = None
    device: ModelDevice = ModelDevice.CPU


def build_detectors(names: list[str], *, endpoints: ModelEndpoints | None = None) -> list[Detector]:
    """Detectors in cascade order (cheap first, whatever order `names` gives)."""
    endpoints = endpoints or ModelEndpoints()
    unknown = set(names) - set(DETECTOR_NAMES)
    if unknown:
        raise ValueError(f"Unknown detectors {sorted(unknown)}; choose from {DETECTOR_NAMES}")
    detectors: list[Detector] = []
    for name in sorted(names, key=DETECTOR_NAMES.index):
        match name:
            case "header":
                detectors.append(HeaderLexiconDetector())
            case "validators":
                detectors.append(ValidatorDetector())
            case "gliner":
                from pytabular.detectors.models import GlinerDetector

                if endpoints.gliner_url:
                    detectors.append(GlinerDetector.from_url(endpoints.gliner_url))
                elif endpoints.gliner_model_dir:
                    detectors.append(GlinerDetector.from_model_dir(endpoints.gliner_model_dir, device=endpoints.device))
                else:
                    raise ValueError("the gliner detector needs a URL or a model dir")
            case "nerd":
                from pytabular.detectors.models import NerdDetector

                if endpoints.nerd_url:
                    detectors.append(NerdDetector.from_url(endpoints.nerd_url))
                elif endpoints.nerd_model_dir:
                    detectors.append(NerdDetector.from_model_dir(endpoints.nerd_model_dir, device=endpoints.device))
                else:
                    raise ValueError("the nerd detector needs a URL or a model dir")
            case "llm":
                from pytabular.detectors.llm import LlmDetector

                detectors.append(LlmDetector(model=endpoints.llm_model))
    return detectors
