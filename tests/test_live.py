from io import BytesIO

import pytest
import requests
from openpyxl import load_workbook

from indicadores.config import Settings
from indicadores.domain import Period, analysis_summary, evaluate_all
from indicadores.repository import SheetRepository


def test_live_sheet_matches_independent_counts_and_amounts(request):
    if not request.config.getoption('--live'):
        pytest.skip('La prueba de integración real requiere --live.')
    settings = Settings()
    state = SheetRepository(settings).refresh()
    assert not state.error, state.error
    snapshot = state.snapshot
    assert not snapshot.missing_tables
    data = requests.get(f'https://docs.google.com/spreadsheets/d/{settings.sheet_id}/export?format=xlsx', timeout=40).content
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    source = list(wb['registros'].values)
    records = [dict(zip(source[0], row)) for row in source[1:] if row[0]]
    assert len(snapshot.rows('registros')) == len(records)
    summary = analysis_summary(snapshot.rows('registros'))
    for key, field in [('gestionados', 'recursos_gestionados'), ('asignados', 'recursos_asignados'),
                       ('institucionales', 'recursos_institucionales')]:
        assert summary[key] == pytest.approx(sum(float(r.get(field) or 0) for r in records))
    year = int(str(records[0]['fecha_inicio'])[:4])
    results = evaluate_all(snapshot, Period(year))
    assert len(results) == len(snapshot.rows('indicadores'))
    assert all(not r['error'] for r in results)
    wb.close()
