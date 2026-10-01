import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from .models import BOGOTA, Snapshot
from .normalization import normalize_name, parse_date, parse_number, text

PERIOD_PREFIX = {'TRIMESTRAL': 'T', 'SEMESTRAL': 'S', 'MENSUAL': 'M'}
BAND_LABELS = {'CRITICO': 'Incumplida', 'RIESGO': 'En riesgo', 'CUMPLIDA': 'Cumplida',
               'SOBRECUMPLIDA': 'Sobrecumplida', 'SIN_DATOS': 'Sin evaluación'}


@dataclass(frozen=True)
class Period:
    year: int
    kind: str = 'ANUAL'
    number: int | None = None

    @property
    def key(self):
        return 'ANUAL' if self.kind == 'ANUAL' else f'{PERIOD_PREFIX[self.kind]}{self.number}'

    @property
    def label(self):
        return f'Año {self.year}' if self.kind == 'ANUAL' else f'{self.key} · {self.year}'

    @classmethod
    def from_key(cls, year, key='ANUAL'):
        if key == 'ANUAL':
            return cls(int(year))
        kinds = {'T': ('TRIMESTRAL', 4), 'S': ('SEMESTRAL', 2), 'M': ('MENSUAL', 12)}
        if key[:1] not in kinds or not key[1:].isdigit():
            raise ValueError('Período inválido')
        kind, maximum = kinds[key[0]]
        number = int(key[1:])
        if not 1 <= number <= maximum:
            raise ValueError('Período fuera de rango')
        return cls(int(year), kind, number)


def values_list(value):
    if isinstance(value, list):
        return [text(v) for v in value if text(v)]
    return [part.strip() for part in re.split(r'[,;]', text(value)) if part.strip()]


def record_period(row):
    try:
        dt = parse_date(row.get('fecha_inicio'))
    except ValueError:
        dt = None
    quarters = []
    for part in values_list(row.get('trimestre_reporte')):
        digits = re.sub(r'\D', '', part)
        if digits and 1 <= int(digits) <= 4:
            quarters.append(int(digits))
    if not quarters and dt:
        quarters = [(dt.month - 1) // 3 + 1]
    return dt, set(quarters)


def in_period(row, period):
    dt, quarters = record_period(row)
    if not dt or dt.year != period.year:
        return False
    if period.kind == 'ANUAL':
        return True
    if period.kind == 'MENSUAL':
        return dt.month == period.number
    if period.kind == 'TRIMESTRAL':
        return period.number in quarters
    return period.number in {(q + 1) // 2 for q in quarters}


def filter_records(rows, period, filters=None):
    filters = filters or {}
    selected = []
    for row in rows:
        if not in_period(row, period):
            continue
        passes = True
        for field, wanted in filters.items():
            if not wanted:
                continue
            if field == 'texto':
                haystack = ' '.join(text(v) for k, v in row.items() if not k.startswith('_'))
                passes = normalize_name(wanted) in normalize_name(haystack)
            elif field in ('objetivo', 'objetivos'):
                passes = bool({v.upper() for v in values_list(wanted)} & {v.upper() for v in values_list(row.get('objetivos'))})
            else:
                passes = text(row.get(field)).upper() in {v.upper() for v in values_list(wanted)}
            if not passes:
                break
        if passes:
            selected.append(row)
    return selected


def indicator_period(ind, selected):
    frequency = text(ind.get('periodicidad')) or 'ANUAL'
    if selected.kind == 'ANUAL' or frequency == 'ANUAL':
        return Period(selected.year)
    quarter = selected.number
    if selected.kind == 'MENSUAL':
        quarter = (selected.number - 1) // 3 + 1
    if selected.kind == 'SEMESTRAL':
        quarter = selected.number * 2
    if frequency == 'SEMESTRAL':
        return Period(selected.year, 'SEMESTRAL', (quarter + 1) // 2)
    return Period(selected.year, 'TRIMESTRAL', quarter)


def parameters(snapshot):
    result = {'banda_riesgo': 0.7, 'banda_sobre': 1.2, 'dias_aviso_cierre': 15, 'dias_sin_avance': 60}
    for row in snapshot.rows('catalogos'):
        category = text(row.get('categoria'))
        if category.startswith('config_') and text(row.get('estado')).upper() != 'INACTIVO':
            try:
                value = parse_number(row.get('valor'))
                if value is not None:
                    result[category[7:]] = value
            except ValueError:
                continue
    return result


def safe_sum(rows, field):
    if any(r.get(field) is None or field in r.get('_invalid_fields', []) for r in rows):
        return None
    return sum(parse_number(r.get(field)) or 0 for r in rows)


def operand(spec, rows):
    if not spec:
        return 0
    try:
        definition = json.loads(spec) if isinstance(spec, str) else spec
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError('La fórmula debe ser una especificación JSON válida.') from exc
    if not isinstance(definition, dict) or definition.get('op', 'CONTAR').upper() not in ('CONTAR', 'SUMAR', 'FIJO'):
        raise ValueError('Operación de indicador inválida.')
    op = definition.get('op', 'CONTAR').upper()
    if op == 'FIJO':
        value = parse_number(definition.get('valor'))
        if value is None:
            raise ValueError('La operación FIJO necesita un valor.')
        return value
    filters = definition.get('filtro', {})
    if not isinstance(filters, dict):
        raise ValueError('El filtro de la fórmula debe ser un objeto.')
    selected = []
    for row in rows:
        include = True
        for field, wanted in filters.items():
            if wanted in ('', None):
                continue
            expected = {text(v).upper() for v in (wanted if isinstance(wanted, list) else [wanted])}
            actual = {v.upper() for v in values_list(row.get(field))} if field == 'objetivos' else {text(row.get(field)).upper()}
            if not expected & actual:
                include = False
                break
        if include:
            selected.append(row)
    if op == 'CONTAR':
        return len(selected)
    field = definition.get('campo')
    if not isinstance(field, str) or not field:
        raise ValueError('La operación SUMAR necesita un campo.')
    result = safe_sum(selected, field)
    if result is None:
        raise ValueError(f'Hay datos faltantes o inválidos en {field}.')
    return result


def evaluate_indicator(ind, period, rows, metas, params=None):
    params = params or {}
    base_result = {'id_indicador': ind.get('id_indicador'), 'id_objetivo': ind.get('id_objetivo'),
                   'nombre': ind.get('nombre'), 'codigo': ind.get('codigo'), 'formula': ind.get('formula_texto', ''),
                   'periodo': period.key, 'anio': period.year, 'periodicidad': ind.get('periodicidad', 'ANUAL'),
                   'unidad': ind.get('unidad', 'CONTEO'), 'error': '', 'sinMeta': False, 'sinBase': False}
    own = next((m for m in metas if m.get('id_indicador') == ind.get('id_indicador')
                and text(m.get('anio')) == str(period.year) and text(m.get('periodo')).upper() == period.key), {})
    try:
        target = parse_number(own.get('valor'))
        if target is None or target <= 0:
            target = parse_number(ind.get('meta'))
        target = target if target is not None and target > 0 else None
        base = parse_number(own.get('denominador'))
        base = base if base is not None and base > 0 else None
        mode = text(ind.get('modo')).upper()
        if mode not in ('META', 'RAZON'):
            mode = 'RAZON' if text(ind.get('denominador')) else 'META'
        numerator = operand(ind.get('numerador'), filter_records(rows, period))
        denominator = target
        value = numerator
        if base:
            mode, denominator, value = 'BASE', base, numerator / base
        elif mode == 'RAZON':
            denominator = operand(ind.get('denominador'), filter_records(rows, period)) if text(ind.get('denominador')) else None
            value = numerator if denominator is None else (numerator / denominator if denominator else None)
        compliance = value / target if value is not None and target else None
        risk, over = params.get('banda_riesgo', 0.7), params.get('banda_sobre', 1.2)
        band = 'SIN_DATOS' if compliance is None else 'SOBRECUMPLIDA' if compliance + 1e-12 >= over else 'CUMPLIDA' if compliance >= 1 else 'RIESGO' if compliance >= risk else 'CRITICO'
        base_result.update(modo=mode, numerador=numerator, denominador=denominator, valor=value, meta=target,
                           cumplimiento=compliance, banda=band, base=base, metaPropia=bool(own.get('valor')),
                           sinMeta=target is None, sinBase=mode == 'RAZON' and denominator == 0)
    except (ValueError, TypeError, AttributeError) as exc:
        base_result.update(error=str(exc), numerador=None, denominador=None, valor=None, meta=None,
                           cumplimiento=None, banda='SIN_DATOS', modo=text(ind.get('modo')), base=None)
    base_result['etiquetaBanda'] = 'Falta la meta' if base_result['sinMeta'] else BAND_LABELS[base_result['banda']]
    return base_result


def evaluate_all(snapshot, selected, filters=None):
    rows = filter_records(snapshot.rows('registros'), Period(selected.year), filters)
    results = []
    params = parameters(snapshot)
    for ind in sorted(snapshot.rows('indicadores'), key=lambda r: r.get('orden') or 0):
        if text(ind.get('estado')).upper() == 'INACTIVO':
            continue
        period = indicator_period(ind, selected)
        result = evaluate_indicator(ind, period, rows, snapshot.rows('metas'), params)
        frequency = text(ind.get('periodicidad')) or 'ANUAL'
        count = 4 if frequency == 'TRIMESTRAL' else 2 if frequency == 'SEMESTRAL' else 1
        result['serie'] = [evaluate_indicator(ind, Period(selected.year, frequency, n if count > 1 else None),
                                                rows, snapshot.rows('metas'), params) for n in range(1, count + 1)]
        results.append(result)
    return results


def analysis_summary(rows):
    summary = {'total': len(rows), 'finalizados': 0, 'en_avance': 0, 'cancelados': 0,
               'aprobados': 0, 'clasificados': 0}
    for row in rows:
        state = text(row.get('estado_ejecucion')).upper()
        summary['finalizados'] += state in ('FINALIZADA', 'FINALIZADO', 'APROBADO')
        summary['en_avance'] += state in ('EN_AVANCE', 'AVANCE', 'EN PROCESO', 'ENVIADO')
        summary['cancelados'] += state in ('CANCELADA', 'CANCELADO')
        summary['aprobados'] += text(row.get('resultado')).upper() == 'APROBADO' or state == 'APROBADO'
        summary['clasificados'] += bool(values_list(row.get('objetivos')))
    summary['sin_clasificar'] = summary['total'] - summary['clasificados']
    for field, key in [('recursos_gestionados', 'gestionados'), ('recursos_asignados', 'asignados'),
                       ('recursos_institucionales', 'institucionales')]:
        summary[key] = safe_sum(rows, field)
    resolved = [r for r in rows if text(r.get('resultado')).upper() in ('APROBADO', 'NEGADO')]
    requested, assigned = safe_sum(resolved, 'recursos_gestionados'), safe_sum(resolved, 'recursos_asignados')
    summary['tasa_aprobacion'] = assigned / requested if requested and assigned is not None else None
    return summary


CHECKLIST = (
    ('chk_01_estudio_previo', 'Estudio previo'), ('chk_02_firma_estudio', 'Firma del estudio previo'),
    ('chk_03_cdp', 'Disponibilidad presupuestal CDP'), ('chk_04_consejo', 'Autorización del Consejo'),
    ('chk_05_procedimiento', 'Procedimiento especial'), ('chk_06_expediente', 'Remisión del expediente'),
    ('chk_07_invitacion', 'Invitación a ofertar'), ('chk_08_ofertas', 'Recepción de ofertas'),
    ('chk_09_habilitantes', 'Requisitos habilitantes'), ('chk_10_sarlaft', 'Riesgos y SARLAFT'),
    ('chk_11_comparativo', 'Análisis comparativo'), ('chk_12_aval_subdirector', 'Aval de Subdirección'),
    ('chk_13_discrepancias', 'Resolución de discrepancias'), ('chk_14_comunicacion', 'Intención de legalización'),
    ('chk_15_minuta', 'Minuta contractual'), ('chk_16_firma_contrato', 'Firma del contrato'),
    ('chk_17_rp', 'Registro presupuestal e inicio'), ('chk_18_supervisor', 'Supervisor o interventor'),
    ('chk_19_polizas', 'Pólizas y garantías'), ('chk_20_pagos', 'Informes y pagos'),
    ('chk_21_modificatorios', 'Otrosí y prórrogas'), ('chk_22_recibo_final', 'Informe final y recibo'),
    ('chk_23_liquidacion', 'Liquidación del contrato'), ('chk_24_garantias_post', 'Garantías posteriores'),
)


def contract_progress(row):
    done = pending = na = blank = 0
    for field, _ in CHECKLIST:
        value = normalize_name(row.get(field)).replace('_', ' ')
        if value in ('na', 'n/a', 'no aplica', 'no aplicable'):
            na += 1
        elif not value:
            blank += 1
        elif 'pendient' in value or value == 'pte':
            pending += 1
        else:
            done += 1
    applicable = 24 - na
    return {'total': 24, 'cumplidos': done, 'pendientes': pending, 'no_aplica': na, 'sin_registrar': blank,
            'aplicables': applicable, 'porcentaje': math.floor(done / applicable * 100 + 0.5) if applicable else 100}


def alerts(snapshot, period, filters=None, today=None):
    today = today or datetime.now(BOGOTA).date()
    rows = filter_records(snapshot.rows('registros'), period, filters)
    cfg = parameters(snapshot)
    result = []

    def add(identifier, level, title, detail, selected, destination='registros'):
        if selected:
            result.append({'id': identifier, 'nivel': level, 'titulo': title, 'detalle': detail,
                           'cantidad': len(selected), 'ids': [r.get('id_registro') for r in selected], 'destino': destination})

    add('SIN_ESTADO', 'CRITICO', 'Registros sin estado', 'Complete el estado de ejecución en Sheets.',
        [r for r in rows if not text(r.get('estado_ejecucion'))])
    add('SIN_RESULTADO', 'CRITICO', 'Resultados pendientes', 'Complete el resultado de la gestión en Sheets.',
        [r for r in rows if text(r.get('resultado')).upper() in ('', 'PENDIENTE')])
    add('SIN_OBJETIVO', 'CRITICO', 'Registros sin objetivo estratégico', 'Clasifique cada registro para que alimente los indicadores.',
        [r for r in rows if not values_list(r.get('objetivos'))])
    add('SIN_RESPONSABLE', 'ADVERTENCIA', 'Registros sin responsable', 'Asigne un responsable para el seguimiento.',
        [r for r in rows if not text(r.get('responsable'))])
    with_evidence = {e.get('id_registro') for e in snapshot.rows('evidencias')}
    add('SIN_EVIDENCIA', 'ADVERTENCIA', 'Registros sin soporte', 'Agregue una carpeta o una evidencia vinculada.',
        [r for r in rows if r.get('id_registro') not in with_evidence and not text(r.get('carpeta_url'))])
    add('APROBADO_SIN_MONTO', 'CRITICO', 'Aprobaciones sin monto asignado', 'Revise el valor de los recursos asignados.',
        [r for r in rows if text(r.get('resultado')).upper() == 'APROBADO' and not r.get('recursos_asignados')])
    opened = [r for r in rows if text(r.get('estado_ejecucion')).upper() not in ('FINALIZADA', 'CANCELADA')]
    due, expired, stopped = [], [], []
    for row in opened:
        end = parse_date(row.get('fecha_cierre'))
        if end and 0 <= (end - today).days <= cfg['dias_aviso_cierre']:
            due.append(row)
        elif end and end < today:
            expired.append(row)
        reference = parse_date(row.get('actualizado_en')) or parse_date(row.get('fecha_inicio'))
        if reference and (today - reference).days >= cfg['dias_sin_avance']:
            stopped.append(row)
    add('POR_VENCER', 'CRITICO', 'Cierres próximos', f"Cierran en los próximos {cfg['dias_aviso_cierre']:g} días.", due)
    add('VENCIDO', 'CRITICO', 'Fechas de cierre vencidas', 'La gestión sigue abierta después de su fecha de cierre.', expired)
    add('SIN_AVANCE', 'ADVERTENCIA', 'Gestiones sin movimiento', f"Sin actualización durante {cfg['dias_sin_avance']:g} días o más.", stopped)
    evaluated = evaluate_all(snapshot, period, filters)
    for identifier, level, title, condition in [
        ('SIN_META', 'ADVERTENCIA', 'Indicadores sin meta', lambda r: r['sinMeta']),
        ('SIN_BASE', 'ADVERTENCIA', 'Indicadores sin base de cálculo', lambda r: r['sinBase']),
        ('FORMULA_INVALIDA', 'CRITICO', 'Indicadores con fórmula inválida', lambda r: bool(r['error'])),
        ('META_INCUMPLIDA', 'CRITICO', 'Indicadores por debajo de la meta', lambda r: r['banda'] == 'CRITICO'),
        ('META_RIESGO', 'ADVERTENCIA', 'Indicadores en riesgo', lambda r: r['banda'] == 'RIESGO'),
        ('META_DESACTUALIZADA', 'INFORMACION', 'Metas superadas más del doble', lambda r: r['cumplimiento'] is not None and r['cumplimiento'] >= 2),
    ]:
        selected = [r for r in evaluated if condition(r)]
        add(identifier, level, title, ' · '.join(text(r['nombre']) for r in selected), selected, 'indicadores')
    return sorted(result, key=lambda a: ({'CRITICO': 0, 'ADVERTENCIA': 1, 'INFORMACION': 2}[a['nivel']], -a['cantidad']))


def distribution(rows, field):
    return Counter(text(r.get(field)) or 'Sin registrar' for r in rows)
