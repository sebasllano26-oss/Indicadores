import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook

from .models import Issue, PRIMARY_KEYS, Snapshot, TABLES


class DataValidationError(ValueError):
    pass


def text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_name(value) -> str:
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text(value).lower())
                           if not unicodedata.combining(c)).split())


def parse_number(value) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        s = text(value).replace('$', '').replace('COP', '').replace(' ', '').replace('\u00a0', '')
        percent = s.endswith('%')
        if percent:
            s = s[:-1]
        if ',' in s and '.' in s:
            decimal, thousands = (',', '.') if s.rfind(',') > s.rfind('.') else ('.', ',')
            parts = s.split(decimal)
            if len(parts) != 2 or not re.fullmatch(r'[+-]?\d{1,3}(' + re.escape(thousands) + r'\d{3})*', parts[0]):
                raise ValueError('Formato numérico inválido')
            s = parts[0].replace(thousands, '') + '.' + parts[1]
        elif s.count(',') > 1 or s.count('.') > 1:
            separator = ',' if ',' in s else '.'
            if not re.fullmatch(r'[+-]?\d{1,3}(' + re.escape(separator) + r'\d{3})+', s):
                raise ValueError('Formato numérico inválido')
            s = s.replace(separator, '')
        elif ',' in s:
            s = s.replace(',', '.')
        elif re.fullmatch(r'[+-]?\d{1,3}\.\d{3}', s):
            s = s.replace('.', '')
        try:
            number = float(s)
        except (ValueError, TypeError) as exc:
            raise ValueError('Formato numérico inválido') from exc
        if percent:
            number /= 100
    if not math.isfinite(number):
        raise ValueError('El número debe ser finito')
    return number


def parse_date(value) -> date | None:
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (float, int)):
        if not 1 <= value <= 100000:
            raise ValueError('Fecha serial fuera de rango')
        return (datetime(1899, 12, 30) + timedelta(days=value)).date()
    s = text(value)
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).date()
    except ValueError:
        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d/%m/%Y %H:%M', '%Y/%m/%d'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    raise ValueError('Fecha inválida; use AAAA-MM-DD o DD/MM/AAAA')


NUMBER_FIELDS = {
    'recursos_gestionados', 'recursos_asignados', 'recursos_institucionales',
    'cantidad', 'cuantia', 'meta', 'valor', 'cumplimiento', 'orden', 'anio',
}
DATE_FIELDS = {'fecha_digitacion', 'fecha_inicio', 'fecha_cierre', 'fecha_fin', 'fecha_busqueda',
               'fecha', 'creado_en', 'actualizado_en', 'actualizado_por_fecha', 'cerrado_en'}


def normalize_tables(tables: dict[str, list[dict]]) -> Snapshot:
    normalized = {}
    issues = []
    for name in TABLES:
        if name not in tables:
            continue
        rows, seen = [], set()
        for index, source in enumerate(tables[name], start=2):
            if not any(value is not None and value != '' for value in source.values()):
                continue
            row = {}
            invalid = []
            for field, value in source.items():
                if not field:
                    continue
                is_number = (field in NUMBER_FIELDS and not (name == 'catalogos' and field == 'valor')) or (name in ('metas', 'cierres') and field in ('numerador', 'denominador'))
                is_date = field in DATE_FIELDS or field.startswith('fec_')
                try:
                    if is_number:
                        row[field] = parse_number(value)
                    elif is_date:
                        parsed = parse_date(value)
                        row[field] = parsed.isoformat() if parsed else ''
                    else:
                        row[field] = text(value)
                except ValueError as exc:
                    row[field] = None if is_number else ''
                    invalid.append(field)
                    issues.append(Issue(name, index, field, str(exc), 'CRITICO'))
            pk = PRIMARY_KEYS.get(name)
            if pk:
                identifier = row.get(pk)
                if not identifier:
                    raise DataValidationError(f'{name}, fila {index}: falta el identificador {pk}.')
                if identifier in seen:
                    raise DataValidationError(f'{name}, fila {index}: identificador duplicado {identifier}.')
                seen.add(identifier)
            row['_fila'] = index
            row['_invalid_fields'] = invalid
            rows.append(row)
        normalized[name] = rows
    references = [('indicadores', 'id_objetivo', 'objetivos_area', 'id_objetivo'),
                  ('metas', 'id_indicador', 'indicadores', 'id_indicador'),
                  ('cierres', 'id_indicador', 'indicadores', 'id_indicador'),
                  ('evidencias', 'id_registro', 'registros', 'id_registro')]
    for name, field, target, target_key in references:
        allowed = {r.get(target_key) for r in normalized.get(target, [])}
        for row in normalized.get(name, []):
            if row.get(field) and target in normalized and row[field] not in allowed:
                issues.append(Issue(name, row['_fila'], field, f'Referencia inexistente en {target}', 'CRITICO'))
    meta_keys = set()
    for row in normalized.get('metas', []):
        key = (row.get('id_indicador'), row.get('anio'), row.get('periodo'))
        if key in meta_keys:
            raise DataValidationError('metas: período duplicado para un mismo indicador y año.')
        meta_keys.add(key)
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str)
    return Snapshot(normalized, tuple(issues), hashlib.sha256(payload.encode()).hexdigest())


def read_workbook(data: bytes) -> Snapshot:
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise DataValidationError('La respuesta no es un libro XLSX válido.') from exc
    tables = {}
    try:
        for ws in wb:
            name = normalize_name(ws.title)
            if name not in TABLES:
                continue
            rows = iter(ws.values)
            headers = [text(value) for value in next(rows, ())]
            populated = [h for h in headers if h]
            if len(populated) != len(set(populated)):
                raise DataValidationError(f'{name}: encabezado duplicado.')
            if name in PRIMARY_KEYS and PRIMARY_KEYS[name] not in headers:
                raise DataValidationError(f'{name}: falta la columna identificador {PRIMARY_KEYS[name]}.')
            tables[name] = [dict(zip(headers, row)) for row in rows if any(v is not None and v != '' for v in row)]
    finally:
        wb.close()
    if not tables:
        raise DataValidationError('No se encontraron las tablas del sistema. Use las pestañas internas de la hoja compartida.')
    return normalize_tables(tables)
