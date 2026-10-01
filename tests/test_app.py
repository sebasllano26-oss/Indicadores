from indicadores.config import Settings
from indicadores.copilot import answer_question, build_context
from indicadores.domain import Period
from indicadores.normalization import normalize_tables
from indicadores.presentation import VIEW_LABELS, safe_link, table_for_view

import pytest
import importlib.util
from pathlib import Path


def source():
    return normalize_tables({'registros': [
        {'id_registro': 'R1', 'nombre_proyecto': 'Visible 2026', 'fecha_inicio': '2026-02-09', 'objetivos': ''},
        {'id_registro': 'R2', 'nombre_proyecto': 'Anterior 2025', 'fecha_inicio': '2025-02-09'},
    ], 'indicadores': [{'id_indicador': 'I1', 'nombre': 'Gestiones', 'numerador': '{"op":"CONTAR"}',
                        'periodicidad': 'ANUAL', 'modo': 'META'}],
       'cierres': [{'id_cierre': 'C1', 'id_indicador': 'I1', 'anio': 2026, 'periodo': 'T1',
                   'valor': 8, 'meta': 10, 'cumplimiento': 0.8, 'banda': 'RIESGO'}]})


def test_eight_views_are_available_and_tables_are_filter_driven():
    assert len(VIEW_LABELS) == 8
    frame = table_for_view('registros', source(), Period(2026))
    assert frame['Proyecto o gestión'].tolist() == ['Visible 2026']
    assert table_for_view('registros', source(), Period(2024)).empty


def test_indicator_missing_target_has_explicit_state():
    frame = table_for_view('indicadores', source(), Period(2026))
    assert frame['Estado'].tolist() == ['Falta la meta']
    assert frame['Cumplimiento (%)'].isna().all()


def test_closures_use_saved_result_not_current_calculation():
    frame = table_for_view('cierres', source(), Period(2026))
    assert frame['Resultado'].tolist() == [8]
    assert frame['Cumplimiento (%)'].tolist() == [80]


def test_unsafe_sheet_links_are_never_clickable():
    assert 'href=' not in str(safe_link('javascript:alert(1)', 'Abrir'))
    assert 'href=' not in str(safe_link('data:text/html,hello', 'Abrir'))
    assert 'https://example.org' in str(safe_link('https://example.org', 'Abrir'))


def test_copilot_uses_filtered_context_and_excludes_other_years():
    context = build_context(source(), Period(2026), {})
    assert len(context['registros']) == 1
    assert context['registros'][0]['nombre_proyecto'] == 'Visible 2026'
    assert context['resumen']['total'] == 1


def test_copilot_without_key_reports_unavailability_without_provider_call():
    with pytest.raises(RuntimeError, match='Gemini'):
        answer_question(Settings(), source(), Period(2026), {}, '¿Cuál es el avance?')


def test_application_contains_accessible_navigation_and_filters():
    spec = importlib.util.spec_from_file_location('shiny_app_test', Path(__file__).parents[1] / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    html = str(module.app_ui)
    for label in VIEW_LABELS.values():
        assert label in html
    assert 'id="year"' in html
    assert 'id="period"' in html
    assert 'id="refresh"' in html
    assert 'Comfamiliar Risaralda' in html
