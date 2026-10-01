from collections import defaultdict
from urllib.parse import urlparse

import pandas as pd
from shiny import ui

from .domain import BAND_LABELS, Period, alerts, analysis_summary, contract_progress, evaluate_all, filter_records, values_list
from .normalization import parse_date, text
from .icons import icon

VIEW_LABELS = {
    'analisis': 'Análisis estratégico', 'indicadores': 'Indicadores estratégicos',
    'alertas': 'Alertas tempranas', 'registros': 'Registros de gestión',
    'contratacion': 'Contratación y compras', 'radar': 'Radar de convocatorias',
    'cierres': 'Cierres y auditoría', 'configuracion': 'Configuración y parámetros',
}
VIEW_TABLE = {'registros': 'registros', 'indicadores': 'indicadores', 'analisis': 'registros',
              'contratacion': 'contratos', 'radar': 'rastreo_convocatorias', 'cierres': 'cierres'}
CONFIG_LABELS = {'objetivos_area': 'Objetivos del área', 'objetivos_corporativos': 'Objetivos corporativos',
                 'indicadores': 'Definiciones de indicadores', 'metas': 'Metas por período', 'catalogos': 'Catálogos y parámetros'}


def safe_link(value, label='Abrir enlace'):
    parsed = urlparse(text(value))
    if parsed.scheme in ('https', 'http') and parsed.netloc:
        return ui.tags.a(label, href=text(value), target='_blank', rel='noopener noreferrer', class_='text-link')
    return ui.tags.span('Enlace no disponible', class_='muted')


def number(value, decimals=0):
    if value is None:
        return 'Sin dato'
    return f'{value:,.{decimals}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def money(value):
    return '$ ' + number(value) if value is not None else 'Sin dato'


def compact_money(value):
    if value is None:
        return 'Sin dato'
    return '$ ' + number(value / 1_000_000, 1) + ' M' if abs(value) >= 1_000_000 else money(value)


def percent(value):
    return number(value * 100, 1) + ' %' if value is not None else 'Sin evaluación'


def frame(rows, columns):
    return pd.DataFrame(rows, columns=columns)


def table_for_view(view, snapshot, period, filters=None, config_section='objetivos_area'):
    filters = filters or {}
    records = filter_records(snapshot.rows('registros'), period, filters)
    if view == 'registros':
        fields = [('consecutivo', 'No.'), ('nombre_proyecto', 'Proyecto o gestión'), ('fecha_inicio', 'Inicio'),
                  ('estado_ejecucion', 'Estado'), ('responsable', 'Responsable'), ('area_beneficiaria', 'Área'),
                  ('resultado', 'Resultado'), ('objetivos', 'Objetivos'), ('recursos_gestionados', 'Solicitados (COP)'),
                  ('recursos_asignados', 'Asignados (COP)'), ('recursos_institucionales', 'Aporte (COP)')]
        return frame([{label: r.get(field, '') for field, label in fields} for r in records], [l for _, l in fields])
    if view == 'analisis':
        groups = defaultdict(list)
        for row in records:
            groups[text(row.get('area_beneficiaria')) or 'Sin área'].append(row)
        result = []
        for area, rows in sorted(groups.items(), key=lambda x: -len(x[1])):
            summary = analysis_summary(rows)
            result.append({'Área': area, 'Registros': summary['total'], 'Finalizados': summary['finalizados'],
                           'Solicitados (COP)': summary['gestionados'], 'Asignados (COP)': summary['asignados']})
        return frame(result, ['Área', 'Registros', 'Finalizados', 'Solicitados (COP)', 'Asignados (COP)'])
    if view == 'indicadores':
        objectives = {r['id_objetivo']: r.get('nombre', '') for r in snapshot.rows('objetivos_area')}
        return frame([{'Indicador': r['nombre'], 'Objetivo': objectives.get(r['id_objetivo'], r['id_objetivo']),
                       'Período': r['periodo'], 'Resultado': r['valor'], 'Meta': r['meta'],
                       'Cumplimiento (%)': r['cumplimiento'] * 100 if r['cumplimiento'] is not None else None,
                       'Estado': r['error'] or r['etiquetaBanda']} for r in evaluate_all(snapshot, period, filters)],
                     ['Indicador', 'Objetivo', 'Período', 'Resultado', 'Meta', 'Cumplimiento (%)', 'Estado'])
    if view == 'alertas':
        return frame([{'Nivel': a['nivel'], 'Alerta': a['titulo'], 'Cantidad': a['cantidad'], 'Detalle': a['detalle']}
                      for a in alerts(snapshot, period, filters)], ['Nivel', 'Alerta', 'Cantidad', 'Detalle'])
    if view == 'contratacion':
        rows = operational_rows(snapshot.rows('contratos'), period, filters, 'fecha_inicio')
        return frame([{'Contrato': r.get('codigo_contrato'), 'Objeto': r.get('objeto'), 'Contratista': r.get('contratista'),
                       'Responsable': r.get('responsable'), 'Cuantía (COP)': r.get('cuantia'),
                       'Estado': r.get('estado_general'), 'Avance (%)': contract_progress(r)['porcentaje'],
                       'Fases sin registrar': contract_progress(r)['sin_registrar']} for r in rows],
                     ['Contrato', 'Objeto', 'Contratista', 'Responsable', 'Cuantía (COP)', 'Estado', 'Avance (%)', 'Fases sin registrar'])
    if view == 'radar':
        rows = operational_rows(snapshot.rows('rastreo_convocatorias'), period, filters, 'fecha_busqueda')
        return frame([{'Convocatoria': r.get('nombre_convocatoria'), 'Estado': r.get('estado'),
                       'Área de interés': r.get('area_interes'), 'Fecha de búsqueda': r.get('fecha_busqueda'),
                       'Observaciones': r.get('observaciones')} for r in rows],
                     ['Convocatoria', 'Estado', 'Área de interés', 'Fecha de búsqueda', 'Observaciones'])
    if view == 'cierres':
        names = {r['id_indicador']: r.get('nombre') for r in snapshot.rows('indicadores')}
        rows = [r for r in snapshot.rows('cierres') if r.get('anio') == period.year
                and (period.kind == 'ANUAL' or r.get('periodo') == period.key)]
        return frame([{'Indicador': names.get(r.get('id_indicador'), r.get('id_indicador')), 'Período': r.get('periodo'),
                       'Numerador': r.get('numerador'), 'Base': r.get('denominador'), 'Resultado': r.get('valor'),
                       'Meta': r.get('meta'), 'Cumplimiento (%)': r['cumplimiento'] * 100 if r.get('cumplimiento') is not None else None,
                       'Estado': BAND_LABELS.get(r.get('banda'), r.get('banda')), 'Cerrado por': r.get('cerrado_por'),
                       'Fecha': r.get('cerrado_en')} for r in rows],
                     ['Indicador', 'Período', 'Numerador', 'Base', 'Resultado', 'Meta', 'Cumplimiento (%)', 'Estado', 'Cerrado por', 'Fecha'])
    fields = {
        'objetivos_area': [('id_objetivo', 'Objetivo'), ('nombre', 'Nombre'), ('descripcion', 'Descripción'), ('corp_codigos', 'Objetivos corporativos'), ('estado', 'Estado')],
        'objetivos_corporativos': [('codigo', 'Código'), ('nombre', 'Nombre'), ('descripcion', 'Descripción'), ('estado', 'Estado')],
        'indicadores': [('codigo', 'Código'), ('nombre', 'Indicador'), ('formula_texto', 'Fórmula'), ('meta', 'Meta general'), ('periodicidad', 'Periodicidad'), ('estado', 'Estado')],
        'metas': [('id_indicador', 'Indicador'), ('anio', 'Año'), ('periodo', 'Período'), ('valor', 'Meta'), ('denominador', 'Base'), ('nota', 'Nota')],
        'catalogos': [('categoria', 'Categoría'), ('valor', 'Valor'), ('orden', 'Orden'), ('estado', 'Estado')],
    }.get(config_section, [])
    return frame([{label: r.get(field) for field, label in fields} for r in snapshot.rows(config_section)], [l for _, l in fields])


def operational_rows(rows, period, filters, date_field):
    result = []
    for row in rows:
        dt = parse_date(row.get(date_field))
        if dt and dt.year != period.year:
            continue
        if filters.get('texto') and text(filters['texto']).lower() not in ' '.join(text(v) for v in row.values()).lower():
            continue
        if filters.get('responsable') and row.get('responsable') != filters['responsable']:
            continue
        result.append(row)
    return result


def badge(label, tone='neutral'):
    return ui.tags.span(label, class_=f'badge-status {tone}')


def metric(label, value, detail='', tone='', symbol='analisis'):
    return ui.tags.div(
        ui.tags.div(ui.tags.span(label, class_='metric-label'),
                    ui.tags.span(icon(symbol), class_='metric-icon'), class_='metric-top'),
        ui.tags.div(value, class_='metric-value'),
        ui.tags.div(detail, class_='metric-detail'), class_=f'metric-card {tone}')


def section_header(title, detail=''):
    return ui.tags.div(ui.tags.h2(title), ui.tags.p(detail, class_='muted') if detail else None, class_='section-heading')


def note(message, tone='info'):
    return ui.tags.div(icon('info', 17), ui.tags.div(message), class_=f'notice {tone}', role='status')


def empty_state(title, detail, link=None):
    return ui.tags.div(ui.tags.span(icon('registros', 24), class_='empty-icon'),
                       ui.tags.h3(title), ui.tags.p(detail), link, class_='empty-state')


def field_list(row, fields):
    return ui.tags.dl(*[ui.TagList(ui.tags.dt(label), ui.tags.dd(text(row.get(field)) or 'Sin dato'))
                        for field, label in fields], class_='detail-list')
