from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo('America/Bogota')
TABLES = (
    'objetivos_corporativos', 'objetivos_area', 'indicadores', 'metas',
    'registros', 'evidencias', 'catalogos', 'cierres', 'contratos', 'rastreo_convocatorias',
)
PRIMARY_KEYS = {
    'objetivos_corporativos': 'codigo', 'objetivos_area': 'id_objetivo',
    'indicadores': 'id_indicador', 'metas': 'id_meta', 'registros': 'id_registro',
    'evidencias': 'id_evidencia', 'cierres': 'id_cierre', 'contratos': 'id_contrato',
    'rastreo_convocatorias': 'id_rastreo',
}


@dataclass(frozen=True)
class Issue:
    table: str
    row: int
    field: str
    message: str
    severity: str = 'ADVERTENCIA'


@dataclass(frozen=True)
class Snapshot:
    tables: dict[str, list[dict]] = field(default_factory=dict)
    issues: tuple[Issue, ...] = ()
    fingerprint: str = ''
    loaded_at: datetime = field(default_factory=lambda: datetime.now(BOGOTA))

    def rows(self, table: str) -> list[dict]:
        return self.tables.get(table, [])

    @property
    def missing_tables(self) -> tuple[str, ...]:
        return tuple(name for name in TABLES if name not in self.tables)
