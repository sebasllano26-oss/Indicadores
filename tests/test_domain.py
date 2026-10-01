import json
from datetime import date

import pytest

from indicadores.domain import Period, alerts, analysis_summary, contract_progress, evaluate_indicator, filter_records, indicator_period
from indicadores.normalization import normalize_tables


def record(identifier='R1', **kwargs):
    return {'id_registro': identifier, 'fecha_inicio': '2026-02-09', 'objetivos': 'OBJ-1',
            'recursos_gestionados': 100, 'recursos_asignados': 80, 'recursos_institucionales': 0, **kwargs}


def indicator(**kwargs):
    return {'id_indicador': 'IND-1', 'id_objetivo': 'OBJ-1', 'nombre': 'Gestiones', 'modo': 'META',
            'numerador': json.dumps({'op': 'CONTAR', 'filtro': {'objetivos': 'OBJ-1'}}),
            'meta': 30, 'periodicidad': 'TRIMESTRAL', **kwargs}


def test_period_multiple_quarters_do_not_duplicate_annual_records():
    rows = [record(trimestre_reporte='1,3')]
    assert len(filter_records(rows, Period(2026, 'TRIMESTRAL', 1))) == 1
    assert len(filter_records(rows, Period(2026, 'TRIMESTRAL', 2))) == 0
    assert len(filter_records(rows, Period(2026, 'TRIMESTRAL', 3))) == 1
    assert len(filter_records(rows, Period(2026, 'ANUAL'))) == 1
    assert len(filter_records(rows, Period(2026, 'MENSUAL', 2))) == 1


def test_period_respects_indicator_frequency():
    assert indicator_period(indicator(periodicidad='SEMESTRAL'), Period(2026, 'TRIMESTRAL', 3)) == Period(2026, 'SEMESTRAL', 2)
    assert indicator_period(indicator(), Period(2026, 'SEMESTRAL', 1)) == Period(2026, 'TRIMESTRAL', 2)


def test_indicator_target_mode_counts_and_compares():
    rows = [record(str(i)) for i in range(24)]
    result = evaluate_indicator(indicator(), Period(2026, 'TRIMESTRAL', 1), rows, [])
    assert result['numerador'] == 24
    assert result['cumplimiento'] == 0.8
    assert result['banda'] == 'RIESGO'


def test_indicator_manual_base_overrides_mode_and_period_target_overrides_default():
    rows = [record(str(i)) for i in range(24)]
    metas = [{'id_indicador': 'IND-1', 'anio': 2026, 'periodo': 'T1', 'valor': 0.8, 'denominador': 25}]
    result = evaluate_indicator(indicator(), Period(2026, 'TRIMESTRAL', 1), rows, metas)
    assert result['modo'] == 'BASE'
    assert result['valor'] == 0.96
    assert result['cumplimiento'] == pytest.approx(1.2)
    assert result['banda'] == 'SOBRECUMPLIDA'


def test_indicator_ratio_and_zero_denominator():
    ind = indicator(modo='RAZON', meta=0.8, numerador=json.dumps({'op': 'SUMAR', 'campo': 'recursos_asignados'}),
                    denominador=json.dumps({'op': 'SUMAR', 'campo': 'recursos_gestionados'}))
    assert evaluate_indicator(ind, Period(2026), [record()], [])['cumplimiento'] == 1
    result = evaluate_indicator(ind, Period(2026), [record(recursos_gestionados=0)], [])
    assert result['sinBase']
    assert result['cumplimiento'] is None


def test_indicator_missing_target_does_not_claim_success():
    result = evaluate_indicator(indicator(meta=None), Period(2026), [record()], [])
    assert result['sinMeta']
    assert result['cumplimiento'] is None
    assert result['banda'] == 'SIN_DATOS'


def test_indicator_fixed_operand_and_configurable_threshold_boundary():
    ind = indicator(numerador=json.dumps({'op': 'FIJO', 'valor': 21}))
    assert evaluate_indicator(ind, Period(2026), [], [], {'banda_riesgo': 0.7})['banda'] == 'RIESGO'
    assert evaluate_indicator(ind, Period(2026), [], [], {'banda_riesgo': 0.71})['banda'] == 'CRITICO'


def test_indicator_invalid_spec_is_exposed_and_other_rows_remain_available():
    result = evaluate_indicator(indicator(numerador='__import__("os")'), Period(2026), [], [])
    assert result['error']
    assert result['cumplimiento'] is None


def test_indicator_invalid_amount_is_not_a_false_zero_sum():
    rows = [record(recursos_asignados=None, _invalid_fields=['recursos_asignados'])]
    ind = indicator(numerador=json.dumps({'op': 'SUMAR', 'campo': 'recursos_asignados'}))
    assert evaluate_indicator(ind, Period(2026), rows, [])['error']


def test_analysis_uses_unique_source_rows_and_preserves_unknown_amounts():
    rows = [record(trimestre_reporte='1,3')]
    assert analysis_summary(filter_records(rows, Period(2026)))['gestionados'] == 100
    assert analysis_summary([record(recursos_asignados=None)])['asignados'] is None


def test_contract_excludes_not_applicable_and_reports_blank_phases():
    result = contract_progress({'chk_01_estudio_previo': 'Cumplido', 'chk_02_firma_estudio': 'No aplica'})
    assert result['aplicables'] == 23
    assert result['cumplidos'] == 1
    assert result['sin_registrar'] == 22
    assert result['porcentaje'] == 4


def test_alerts_include_missing_classification_missing_target_and_deadline():
    snapshot = normalize_tables({'registros': [record(objetivos='', estado_ejecucion='EN_AVANCE',
                                                   fecha_cierre='2026-10-05', resultado='PENDIENTE')],
                                 'indicadores': [indicator(meta=None)], 'metas': []})
    found = {a['id']: a for a in alerts(snapshot, Period(2026), today=date(2026, 10, 1))}
    assert found['SIN_OBJETIVO']['cantidad'] == 1
    assert found['SIN_META']['cantidad'] == 1
    assert found['POR_VENCER']['cantidad'] == 1


def test_period_filters_match_multiple_objectives_and_text():
    rows = [record(objetivos='OBJ-1,OBJ-2', nombre_proyecto='Programa de bienestar')]
    assert len(filter_records(rows, Period(2026), {'objetivo': 'OBJ-2', 'texto': 'BIENESTAR'})) == 1
    assert filter_records(rows, Period(2025)) == []
