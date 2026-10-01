from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from openpyxl import Workbook

from indicadores.config import Settings
from indicadores.repository import SheetRepository


def workbook(ids):
    wb = Workbook()
    ws = wb.active
    ws.title = 'registros'
    ws.append(['id_registro', 'fecha_inicio', 'nombre_proyecto'])
    for identifier in ids:
        ws.append([identifier, '2026-02-09', 'Proyecto ' + identifier])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_shared_cache_reads_once_for_multiple_consumers():
    calls = []
    def fetch():
        calls.append(1)
        return workbook(['R1'])
    repo = SheetRepository(Settings(refresh_seconds=60), fetcher=fetch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.refresh(), range(2)))
    assert len(calls) == 1
    assert results[0].snapshot.fingerprint == results[1].snapshot.fingerprint


def test_failure_keeps_last_valid_snapshot_and_recovers_additions_changes_deletions():
    time = [0]
    response = [workbook(['R1'])]
    def fetch():
        if isinstance(response[0], Exception):
            raise response[0]
        return response[0]
    repo = SheetRepository(Settings(refresh_seconds=60), fetcher=fetch, clock=lambda: time[0])
    first = repo.refresh()
    time[0] = 61
    response[0] = RuntimeError('Sin conexión')
    failed = repo.refresh()
    assert failed.error
    assert failed.snapshot == first.snapshot
    assert failed.snapshot.loaded_at == first.snapshot.loaded_at
    time[0] = 122
    response[0] = workbook(['R2', 'R3'])
    recovered = repo.refresh()
    assert not recovered.error
    assert [r['id_registro'] for r in recovered.snapshot.rows('registros')] == ['R2', 'R3']
    assert recovered.snapshot.fingerprint != first.snapshot.fingerprint


def test_first_failure_exposes_error_without_fabricated_records():
    def fetch():
        raise RuntimeError('Fuente no disponible')
    state = SheetRepository(Settings(), fetcher=fetch).refresh()
    assert state.snapshot is None
    assert state.error


def test_manual_refresh_is_throttled_but_observes_edits_after_cooldown():
    time = [0]
    calls = []
    def fetch():
        calls.append(1)
        return workbook(['R1'])
    repo = SheetRepository(Settings(), fetcher=fetch, clock=lambda: time[0])
    repo.refresh()
    repo.refresh(force=True)
    assert len(calls) == 1
    time[0] = 5
    repo.refresh(force=True)
    assert len(calls) == 2


def test_invalid_snapshot_is_not_promoted_over_valid_data():
    time = [0]
    response = [workbook(['R1'])]
    repo = SheetRepository(Settings(), fetcher=lambda: response[0], clock=lambda: time[0])
    first = repo.refresh()
    time[0] = 61
    response[0] = workbook(['R1', 'R1'])
    invalid = repo.refresh()
    assert 'duplicado' in invalid.error
    assert invalid.snapshot == first.snapshot
