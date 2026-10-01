import asyncio
from dataclasses import replace
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from indicadores.config import APP_DIR, Settings
from indicadores.copilot import answer_question
from indicadores.domain import CHECKLIST, Period, alerts, analysis_summary, contract_progress, distribution, evaluate_all, filter_records
from indicadores.models import BOGOTA, Snapshot
from indicadores.normalization import text
from indicadores.presentation import (
    CONFIG_LABELS, VIEW_LABELS, VIEW_TABLE, badge, empty_state, field_list, metric,
    money, note, number, operational_rows, percent, safe_link, section_header, table_for_view,
)
from indicadores.repository import SheetRepository

settings = Settings.from_env()
repository = SheetRepository(settings)
refresh_signal = reactive.Value(0)
YEAR = datetime.now(BOGOTA).year
PERIOD_CHOICES = {'ANUAL': 'Año completo', **{f'T{i}': f'Trimestre {i}' for i in range(1, 5)},
                  **{f'S{i}': f'Semestre {i}' for i in range(1, 3)},
                  **{f'M{i}': name for i, name in enumerate(('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'), 1)}}

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.tags.div(ui.tags.img(src='logo.jpg', alt='Comfamiliar Risaralda', class_='brand-logo'), class_='brand'),
        ui.tags.div('RELACIONAMIENTO', class_='sidebar-eyebrow'),
        ui.tags.h1('Gestión estratégica', class_='sidebar-title'),
        ui.input_radio_buttons('view', None, VIEW_LABELS, selected='analisis'),
        ui.tags.div(
            ui.input_select('year', 'Año de consulta', {str(YEAR): str(YEAR)}, selected=str(YEAR)),
            ui.input_select('period', 'Período', PERIOD_CHOICES, selected='ANUAL'),
            class_='sidebar-period',
        ),
        ui.tags.div('Los datos se registran en la hoja compartida.', class_='sidebar-note'),
        width=270, open='desktop', id='navigation',
    ),
    ui.include_css(APP_DIR / 'www' / 'app.css'),
    ui.tags.a('Ir al contenido', href='#main-content', class_='skip-link'),
    ui.tags.main(
        ui.tags.div(
            ui.tags.div(ui.tags.span('COMFAMILIAR RISARALDA', class_='eyebrow'), ui.tags.p('Portal de relacionamiento estratégico', class_='portal-name')),
            ui.tags.div(
                ui.input_action_button('open_copilot', 'Copiloto', class_='btn-outline-primary'),
                ui.tags.a('Abrir Google Sheets', href=settings.sheet_url(), target='_blank', rel='noopener noreferrer', class_='action-link'),
                ui.input_action_button('refresh', 'Actualizar', class_='btn-primary'), class_='header-actions',
            ), class_='topbar',
        ),
        ui.output_ui('source_status'),
        ui.tags.div(
            ui.input_select('area', 'Área beneficiaria', {'': 'Todas las áreas'}),
            ui.input_select('responsible', 'Responsable', {'': 'Todos los responsables'}),
            ui.input_select('state', 'Estado de gestión', {'': 'Todos los estados'}),
            ui.input_select('objective', 'Objetivo estratégico', {'': 'Todos los objetivos'}),
            ui.input_text('search', 'Buscar', placeholder='Proyecto, entidad o palabra clave'),
            ui.input_action_button('clear_filters', 'Limpiar filtros', class_='btn-outline-secondary'),
            class_='filter-panel',
        ),
        ui.output_ui('view_body'),
        ui.tags.footer('Relacionamiento Estratégico · Comfamiliar Risaralda', class_='app-footer'),
        id='main-content', class_='workspace',
    ),
    title=None, window_title='Relacionamiento Estratégico · Comfamiliar Risaralda', lang='es',
)


def server(input, output, session):
    state = reactive.Value(repository.state)
    data = reactive.Value(repository.state.snapshot)
    alert_ids = reactive.Value(None)

    def optional_input(identifier, default=''):
        try:
            return input[identifier]() or default
        except Exception:
            return default

    @reactive.effect
    async def synchronize():
        refresh_signal.get()
        reactive.invalidate_later(1)
        updated = await asyncio.to_thread(repository.refresh)
        with reactive.isolate():
            old_state, old_data = state.get(), data.get()
        if updated.revision != old_state.revision:
            state.set(updated)
            if updated.snapshot and (old_data is None or old_data.fingerprint != updated.snapshot.fingerprint):
                data.set(updated.snapshot)

    @reactive.effect
    @reactive.event(input.refresh)
    async def refresh_now():
        ui.update_action_button('refresh', label='Actualizando…', disabled=True)
        try:
            await asyncio.to_thread(repository.refresh, True)
            refresh_signal.set(refresh_signal.get() + 1)
        finally:
            ui.update_action_button('refresh', label='Actualizar', disabled=False)

    @reactive.calc
    def selected_period():
        return Period.from_key(input.year(), input.period())

    @reactive.calc
    def filters():
        return {'area_beneficiaria': input.area(), 'responsable': input.responsible(),
                'estado_ejecucion': input.state(), 'objetivo': input.objective(), 'texto': input.search().strip()}

    @reactive.calc
    def snapshot():
        value = data.get() or Snapshot()
        ids = alert_ids.get()
        if ids is not None and input.view() == 'registros':
            value = replace(value, tables={**value.tables, 'registros': [r for r in value.rows('registros') if r['id_registro'] in ids]})
        return value

    @reactive.calc
    def records():
        return filter_records(snapshot().rows('registros'), selected_period(), filters())

    @reactive.effect
    def update_options():
        source = data.get()
        if source is None:
            return
        years = {YEAR}
        for row in source.rows('registros'):
            if row.get('fecha_inicio'):
                years.add(int(row['fecha_inicio'][:4]))
        for row in source.rows('cierres') + source.rows('metas'):
            if row.get('anio'):
                years.add(int(row['anio']))
        ui.update_select('year', choices={str(y): str(y) for y in sorted(years, reverse=True)}, selected=input.year())
        annual = filter_records(source.rows('registros'), Period(int(input.year())))
        for identifier, field, all_label in [('area', 'area_beneficiaria', 'Todas las áreas'),
                                             ('responsible', 'responsable', 'Todos los responsables'),
                                             ('state', 'estado_ejecucion', 'Todos los estados')]:
            values = sorted({text(r.get(field)) for r in annual if text(r.get(field))})
            selected = optional_input(identifier)
            ui.update_select(identifier, choices={'': all_label, **{v: v.replace('_', ' ') for v in values}},
                             selected=selected if selected in values else '')
        goals = {r['id_objetivo']: text(r.get('nombre')) for r in source.rows('objetivos_area') if r.get('estado') != 'INACTIVO'}
        ui.update_select('objective', choices={'': 'Todos los objetivos', **goals}, selected=input.objective() if input.objective() in goals else '')

    @reactive.effect
    @reactive.event(input.clear_filters)
    def clear_filters():
        for identifier in ('area', 'responsible', 'state', 'objective'):
            ui.update_select(identifier, selected='')
        ui.update_text('search', value='')
        alert_ids.set(None)

    @reactive.effect
    @reactive.event(input.view)
    def leave_alert_filter():
        if input.view() != 'registros':
            alert_ids.set(None)

    @render.ui
    def source_status():
        current = state.get()
        if current.snapshot is None:
            return note(current.error or 'Conectando con Google Sheets…', 'warning' if current.error else 'info')
        stamp = current.snapshot.loaded_at.strftime('%d/%m/%Y %H:%M:%S')
        if current.error:
            return note(f'No se pudo actualizar: {current.error} Última lectura válida: {stamp}.', 'warning')
        source_name = 'Archivo local' if settings.source_mode == 'file' else 'Google Sheets'
        return ui.tags.div(badge('Conectado', 'success'), ui.tags.span(source_name),
                           ui.tags.span(f'Última lectura: {stamp}', class_='sync-time'),
                           ui.tags.span(f'Consulta cada {settings.refresh_seconds} s', class_='muted'), class_='sync-bar')

    def grid_panel(title='Detalle de la consulta'):
        return ui.card(ui.card_header(ui.tags.span(title), ui.download_button('download_csv', 'Descargar CSV', class_='btn-sm btn-outline-secondary')),
                       ui.output_data_frame('main_table'), class_='table-card')

    @render.ui
    def view_body():
        view = input.view()
        headings = section_header(VIEW_LABELS[view])
        common = [headings, ui.output_ui('view_notice')]
        if view == 'analisis':
            return ui.TagList(*common, ui.output_ui('metrics'),
                ui.tags.div(ui.card(ui.card_header('Gestiones por área'), output_widget('primary_chart')),
                            ui.card(ui.card_header('Evolución mensual'), output_widget('secondary_chart')), class_='chart-grid'), grid_panel('Detalle por área'))
        if view == 'indicadores':
            return ui.TagList(*common, ui.output_ui('indicator_cards'), ui.output_ui('indicator_controls'),
                              ui.card(ui.card_header('Serie del indicador'), output_widget('secondary_chart')), grid_panel('Resultados por objetivo'))
        if view == 'alertas':
            return ui.TagList(*common, ui.output_ui('metrics'), ui.output_ui('alert_cards'), grid_panel('Alertas del período'))
        if view == 'registros':
            return ui.TagList(*common, ui.output_ui('metrics'), grid_panel('Bitácora de gestión'),
                              ui.card(ui.card_header('Detalle del registro'), ui.output_ui('record_controls'), ui.output_ui('record_detail')))
        if view == 'contratacion':
            return ui.TagList(*common, ui.output_ui('metrics'), grid_panel('Seguimiento contractual'),
                              ui.card(ui.card_header('Lista de chequeo de 24 fases'), ui.output_ui('contract_controls'), ui.output_ui('contract_detail')))
        if view == 'radar':
            return ui.TagList(*common, ui.output_ui('metrics'), grid_panel('Oportunidades identificadas'), ui.output_ui('radar_links'))
        if view == 'cierres':
            return ui.TagList(*common, note('Estos resultados corresponden al cierre guardado de cada período.'), grid_panel('Histórico de cierres'))
        return ui.TagList(*common,
            note('Edite los objetivos, metas y parámetros en Google Sheets. La app incorporará los cambios en la siguiente lectura.'),
            ui.input_select('config_section', 'Consultar configuración', CONFIG_LABELS),
            ui.output_ui('config_link'), grid_panel('Configuración de la hoja'),
            ui.accordion(ui.accordion_panel('Cómo alimentar los indicadores',
                ui.tags.ol(ui.tags.li('Registre la gestión en la pestaña registros, con su fecha de inicio y estado.'),
                           ui.tags.li('Complete objetivos con el identificador del objetivo; puede separar varios por coma.'),
                           ui.tags.li('En metas, indique el indicador, año, período (T1–T4, S1–S2 o ANUAL) y valor objetivo.'),
                           ui.tags.li('Si corresponde, complete denominador con la base manual del período.'),
                           ui.tags.li('Conserve el identificador de cada fila al editar y agregue identificadores únicos para nuevas filas.')))))

    @render.ui
    def view_notice():
        source, period, view = snapshot(), selected_period(), input.view()
        if data.get() is None:
            return note('La consulta se mostrará cuando termine la lectura de la hoja.')
        notices = [ui.tags.div(period.label, class_='period-caption')]
        table = VIEW_TABLE.get(view, optional_input('config_section', 'objetivos_area'))
        if view not in ('alertas',) and table not in source.tables:
            notices.append(note(f'Falta la pestaña {table} en la fuente.', 'warning'))
        if source.issues:
            notices.append(note(f'Hay {len(source.issues)} campos con datos inválidos. Revise el detalle de calidad.', 'warning'))
            notices.append(ui.accordion(ui.accordion_panel('Detalle de calidad',
                *[ui.tags.p(f'{i.table}, fila {i.row}, {i.field}: {i.message}') for i in source.issues])))
        if view in ('analisis', 'indicadores', 'registros'):
            unclassified = analysis_summary(records())['sin_clasificar']
            if unclassified:
                notices.append(note(f'{unclassified} registros de esta consulta no tienen objetivo asignado. Complete su clasificación en Sheets.', 'warning'))
        if view in ('contratacion', 'radar'):
            notices.append(ui.tags.p('Estas secciones usan el año, responsable y búsqueda. Los registros sin fecha permanecen visibles.', class_='muted'))
        if view == 'registros' and alert_ids.get() is not None:
            notices.append(note('Se muestran los registros de la alerta seleccionada. Use Limpiar filtros para volver a la bitácora completa.'))
        if view in ('registros', 'cierres', 'radar', 'contratacion') and table_for_view(view, source, period, filters()).empty:
            notices.append(empty_state('No hay datos para esta consulta',
                'Ajuste los filtros o registre los datos en la hoja compartida.', safe_link(settings.sheet_url(table), 'Abrir la pestaña en Sheets')))
        return ui.TagList(*notices)

    @render.ui
    def metrics():
        view, source, period = input.view(), snapshot(), selected_period()
        summary = analysis_summary(records())
        if view == 'contratacion':
            rows = operational_rows(source.rows('contratos'), period, filters(), 'fecha_inicio')
            total = sum(r.get('cuantia') or 0 for r in rows)
            blocks = [metric('Contratos', number(len(rows))), metric('Cuantía registrada', money(total), 'COP'),
                      metric('Fases cumplidas', number(sum(contract_progress(r)['cumplidos'] for r in rows))),
                      metric('Fases sin registrar', number(sum(contract_progress(r)['sin_registrar'] for r in rows)), tone='attention')]
        elif view == 'radar':
            rows = operational_rows(source.rows('rastreo_convocatorias'), period, filters(), 'fecha_busqueda')
            counts = distribution(rows, 'estado')
            blocks = [metric('Oportunidades', number(len(rows))), metric('Detectadas', number(counts['DETECTADA'])),
                      metric('En revisión', number(counts['EN_REVISION'])), metric('Postuladas', number(counts['POSTULADA']))]
        elif view == 'alertas':
            current = alerts(source, period, filters())
            blocks = [metric('Reglas con hallazgos', number(len(current))),
                      metric('Críticas', number(sum(a['nivel'] == 'CRITICO' for a in current)), tone='attention'),
                      metric('Advertencias', number(sum(a['nivel'] == 'ADVERTENCIA' for a in current))),
                      metric('Información', number(sum(a['nivel'] == 'INFORMACION' for a in current)))]
        else:
            blocks = [metric('Gestiones registradas', number(summary['total']), period.label),
                      metric('Recursos solicitados', money(summary['gestionados']), 'COP'),
                      metric('Recursos asignados', money(summary['asignados']), 'COP'),
                      metric('Gestiones finalizadas', number(summary['finalizados']), f"{summary['en_avance']} en avance")]
        return ui.tags.div(*blocks, class_='metric-grid')

    @render.data_frame
    def main_table():
        current = table_for_view(input.view(), snapshot(), selected_period(), filters(), optional_input('config_section', 'objetivos_area'))
        return render.DataGrid(current, filters=True, width='100%', height='440px', summary='{start}–{end} de {total} filas')

    @render.download(filename=lambda: f'relacionamiento_{input.view()}_{input.year()}.csv')
    def download_csv():
        current = table_for_view(input.view(), snapshot(), selected_period(), filters(), optional_input('config_section', 'objetivos_area'))
        yield '\ufeff' + current.to_csv(index=False)

    def chart_layout(figure, x_title='', y_title='Registros'):
        figure.update_layout(template='plotly_white', height=310, margin=dict(l=20, r=20, t=30, b=45),
                             font=dict(family='Arial, sans-serif', color='#24324b'),
                             paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                             xaxis_title=x_title, yaxis_title=y_title, legend=dict(orientation='h', y=1.12))
        return figure

    @render_plotly
    def primary_chart():
        counts = distribution(records(), 'area_beneficiaria')
        selected = sorted(counts.items(), key=lambda x: x[1])[-10:]
        figure = go.Figure()
        if selected:
            figure.add_bar(x=[c for _, c in selected], y=[a for a, _ in selected], orientation='h',
                           marker_color='#294894', text=[c for _, c in selected], textposition='outside',
                           hovertemplate='%{y}: %{x} registros<extra></extra>')
            chart_layout(figure, 'Registros', '')
            figure.update_layout(margin=dict(l=20, r=35, t=20, b=40))
            figure.update_yaxes(automargin=True)
        else:
            figure.add_annotation(text='No hay registros para los filtros seleccionados', showarrow=False)
            chart_layout(figure)
        return figure

    @render_plotly
    def secondary_chart():
        figure = go.Figure()
        if input.view() == 'indicadores':
            evaluated = evaluate_all(snapshot(), selected_period(), filters())
            current = next((r for r in evaluated if r['id_indicador'] == optional_input('indicator_id')), evaluated[0] if evaluated else None)
            if current:
                series = current['serie']
                figure.add_bar(name='Resultado', x=[r['periodo'] for r in series], y=[r['valor'] for r in series], marker_color='#294894')
                if any(r['meta'] is not None for r in series):
                    figure.add_scatter(name='Meta', x=[r['periodo'] for r in series], y=[r['meta'] for r in series],
                                       mode='lines+markers', line=dict(color='#9e8500', dash='dot'))
                chart_layout(figure, 'Período', 'Proporción' if current['modo'] in ('RAZON', 'BASE') else 'Resultado')
            else:
                figure.add_annotation(text='No hay indicadores configurados', showarrow=False)
                chart_layout(figure)
        else:
            source = filter_records(snapshot().rows('registros'), Period(selected_period().year), filters())
            values = [len(filter_records(source, Period(selected_period().year, 'MENSUAL', month))) for month in range(1, 13)]
            figure.add_scatter(x=['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'],
                               y=values, mode='lines+markers', fill='tozeroy', line=dict(color='#294894', width=3),
                               fillcolor='rgba(41,72,148,.08)', hovertemplate='%{x}: %{y} registros<extra></extra>')
            chart_layout(figure, 'Mes de inicio')
        return figure

    @render.ui
    def indicator_cards():
        rows = evaluate_all(snapshot(), selected_period(), filters())
        cards = []
        for row in rows:
            state_label = row['error'] or row['etiquetaBanda']
            tone = 'warning' if row['sinMeta'] or row['sinBase'] or row['error'] else 'success' if row['banda'] in ('CUMPLIDA', 'SOBRECUMPLIDA') else 'warning'
            value = percent(row['valor']) if row['modo'] in ('BASE', 'RAZON') else number(row['valor'])
            cards.append(ui.tags.div(ui.tags.div(ui.tags.span(row['periodo'], class_='eyebrow'), badge(state_label, tone), class_='indicator-top'),
                ui.tags.h3(text(row['nombre'])), ui.tags.p(text(row['formula']), class_='muted'),
                ui.tags.div(ui.tags.div(value, class_='indicator-value'), ui.tags.span('Resultado registrado', class_='muted')),
                ui.tags.div(ui.tags.span('Meta: ' + (percent(row['meta']) if row['modo'] in ('BASE', 'RAZON') else number(row['meta']))),
                            ui.tags.span('Cumplimiento: ' + percent(row['cumplimiento'])), class_='indicator-footer'), class_='indicator-card'))
        return ui.tags.div(*cards, class_='indicator-grid') if cards else empty_state('Sin indicadores', 'Configure los indicadores en la hoja.')

    @render.ui
    def indicator_controls():
        rows = evaluate_all(snapshot(), selected_period(), filters())
        choices = {r['id_indicador']: text(r['nombre']) for r in rows}
        with reactive.isolate():
            selected = optional_input('indicator_id')
        return ui.input_select('indicator_id', 'Indicador para consultar la serie', choices, selected=selected if selected in choices else next(iter(choices), None))

    @render.ui
    def alert_cards():
        current = alerts(snapshot(), selected_period(), filters())
        if not current:
            return empty_state('Sin alertas para esta consulta', 'No se detectaron hallazgos en las reglas evaluadas.')
        choices = {a['id']: a['titulo'] for a in current}
        return ui.TagList(ui.tags.div(*[
            ui.tags.div(ui.tags.div(badge(a['nivel'].capitalize(), 'warning' if a['nivel'] != 'INFORMACION' else 'neutral'),
                                    ui.tags.strong(str(a['cantidad']), class_='alert-count'), class_='indicator-top'),
                        ui.tags.h3(a['titulo']), ui.tags.p(a['detalle'], class_='muted'), class_='alert-card') for a in current], class_='alert-grid'),
            ui.tags.div(ui.input_select('alert_choice', 'Revisar una alerta', choices),
                        ui.input_action_button('open_alert', 'Ver registros o indicadores', class_='btn-primary'), class_='alert-action'))

    @reactive.effect
    @reactive.event(input.open_alert)
    def open_alert():
        selected = next((a for a in alerts(snapshot(), selected_period(), filters()) if a['id'] == optional_input('alert_choice')), None)
        if selected:
            alert_ids.set(set(selected['ids']) if selected['destino'] == 'registros' else None)
            ui.update_radio_buttons('view', selected=selected['destino'])

    @render.ui
    def record_controls():
        choices = {r['id_registro']: f"{text(r.get('consecutivo'))} · {text(r.get('nombre_proyecto') or r.get('nombre_gestion'))}" for r in records()}
        with reactive.isolate():
            selected = optional_input('record_id')
        return ui.input_select('record_id', 'Seleccionar un registro', choices, selected=selected if selected in choices else next(iter(choices), None))

    @render.ui
    def record_detail():
        row = next((r for r in records() if r['id_registro'] == optional_input('record_id')), None)
        if row is None:
            return ui.tags.p('Seleccione un registro de la consulta.', class_='muted')
        evidence = [e for e in snapshot().rows('evidencias') if e.get('id_registro') == row['id_registro']]
        return ui.TagList(ui.tags.h3(text(row.get('nombre_proyecto') or row.get('nombre_gestion'))),
            field_list(row, [('fecha_inicio', 'Inicio'), ('fecha_cierre', 'Cierre'), ('responsable', 'Responsable'),
                             ('entidad', 'Entidad'), ('objetivos', 'Objetivos'), ('actividades', 'Actividades'), ('logros', 'Logros'),
                             ('alertas', 'Alertas identificadas'), ('riesgos', 'Riesgos'), ('acciones_mejora', 'Acciones de mejora'), ('observaciones', 'Observaciones')]),
            ui.tags.div(metric('Recursos solicitados', money(row.get('recursos_gestionados'))),
                        metric('Recursos asignados', money(row.get('recursos_asignados'))), class_='detail-resources'),
            safe_link(row.get('carpeta_url'), 'Abrir carpeta de soportes'),
            *[ui.tags.p(safe_link(e.get('url'), text(e.get('nombre')) or 'Abrir evidencia')) for e in evidence],
            ui.tags.p(safe_link(settings.sheet_url('registros'), 'Editar la bitácora en Sheets')))

    @render.ui
    def contract_controls():
        rows = operational_rows(snapshot().rows('contratos'), selected_period(), filters(), 'fecha_inicio')
        choices = {r['id_contrato']: text(r.get('codigo_contrato')) + ' · ' + text(r.get('contratista')) for r in rows}
        with reactive.isolate():
            selected = optional_input('contract_id')
        return ui.input_select('contract_id', 'Seleccionar un contrato', choices, selected=selected if selected in choices else next(iter(choices), None))

    @render.ui
    def contract_detail():
        rows = operational_rows(snapshot().rows('contratos'), selected_period(), filters(), 'fecha_inicio')
        row = next((r for r in rows if r['id_contrato'] == optional_input('contract_id')), None)
        if row is None:
            return ui.tags.p('Seleccione un contrato.', class_='muted')
        progress = contract_progress(row)
        phases = []
        for index, (field, label) in enumerate(CHECKLIST, 1):
            detail_fields = [k for k in row if k.startswith((f'fec_{index:02d}_', f'det_{index:02d}_'))]
            details = ' · '.join(text(row[k]) for k in detail_fields if row[k])
            phases.append(ui.tags.tr(ui.tags.td(f'{index:02d}'), ui.tags.td(label), ui.tags.td(text(row.get(field)) or 'Sin registrar'), ui.tags.td(details)))
        return ui.TagList(ui.tags.h3(text(row.get('objeto'))),
            ui.tags.p(f"{progress['cumplidos']} de {progress['aplicables']} fases aplicables cumplidas · {progress['porcentaje']} %"),
            ui.tags.div(ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(v) for v in ('Fase', 'Actividad', 'Estado', 'Fecha o detalle')])),
                                     ui.tags.tbody(*phases), class_='checklist-table'), class_='table-scroll'),
            ui.tags.p(safe_link(row.get('carpeta_url'), 'Abrir expediente contractual')),
            ui.tags.p(safe_link(settings.sheet_url('contratos'), 'Actualizar seguimiento en Sheets')))

    @render.ui
    def radar_links():
        rows = operational_rows(snapshot().rows('rastreo_convocatorias'), selected_period(), filters(), 'fecha_busqueda')
        return ui.tags.div(*[ui.tags.div(badge(text(r.get('estado')).replace('_', ' ')), ui.tags.h3(text(r.get('nombre_convocatoria'))),
                                        ui.tags.p(text(r.get('observaciones'))), safe_link(r.get('url'), 'Consultar convocatoria'), class_='radar-card') for r in rows], class_='radar-grid')

    @render.ui
    def config_link():
        return safe_link(settings.sheet_url(optional_input('config_section', 'objetivos_area')), 'Editar esta configuración en Google Sheets')

    @reactive.extended_task
    async def ask_copilot(source, period, applied_filters, question):
        return await asyncio.to_thread(answer_question, settings, source, period, applied_filters, question)

    @reactive.effect
    @reactive.event(input.open_copilot)
    def open_copilot():
        body = [note('El copiloto utiliza los datos de los filtros actuales y responde mediante Gemini.')]
        if not settings.gemini_key:
            body.append(empty_state('Copiloto no disponible', 'La cuenta de Gemini aún no está configurada para esta aplicación.'))
        else:
            body.extend([ui.input_text_area('copilot_question', 'Pregunta', placeholder='¿Qué gestiones requieren atención?', rows=3),
                         ui.input_action_button('ask_copilot', 'Consultar', class_='btn-primary'), ui.output_text_verbatim('copilot_answer')])
        ui.modal_show(ui.modal(*body, title='Copiloto estratégico', easy_close=True, footer=ui.modal_button('Cerrar'), size='l'))

    @reactive.effect
    @reactive.event(input.ask_copilot)
    def send_question():
        if data.get() is None:
            ui.notification_show('Espere a que se carguen los datos.', type='warning')
            return
        question = optional_input('copilot_question')
        if not question.strip():
            ui.notification_show('Escriba una pregunta.', type='warning')
            return
        ask_copilot(snapshot(), selected_period(), filters(), question)

    @render.text
    def copilot_answer():
        return ask_copilot.result()


app = App(app_ui, server, static_assets=APP_DIR / 'www')
