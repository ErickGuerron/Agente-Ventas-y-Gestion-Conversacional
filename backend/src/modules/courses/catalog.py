"""Official course catalog. Prices and promotions come only from data/courses.json."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "courses.json"


class Course(BaseModel):
    id: str
    nombre: str
    modalidad: str
    duracion_horas: int = Field(gt=0)
    precio_usd: float = Field(ge=0)
    descripcion: str
    temas: list[str]
    promociones_autorizadas: list[str] = []


def load_catalog(path: Path = CATALOG_PATH) -> list[Course]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Course.model_validate(item) for item in raw]
