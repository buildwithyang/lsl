from lsl.modules.material.api import router
from lsl.modules.material.extractor.factory import build_extractor
from lsl.modules.material.service import MaterialService

__all__ = [
    "MaterialService",
    "build_extractor",
    "router",
]
