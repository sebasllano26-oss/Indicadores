import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import Settings
from .models import Snapshot, TABLES
from .normalization import DataValidationError, normalize_tables, read_workbook, text


@dataclass(frozen=True)
class RepositoryState:
    snapshot: Snapshot | None = None
    error: str = ''
    revision: int = 0


class SheetRepository:
    """Una caché por proceso; el lock evita lecturas duplicadas entre sesiones."""

    def __init__(self, settings: Settings, fetcher=None, clock=time.monotonic):
        self.settings = settings
        self._fetcher = fetcher
        self._clock = clock
        self._lock = threading.Lock()
        self._last_attempt = None
        self.state = RepositoryState()

    def refresh(self, force=False):
        with self._lock:
            now = self._clock()
            cooldown = 4 if force else self.settings.refresh_seconds
            if self._last_attempt is not None and now - self._last_attempt < cooldown:
                return self.state
            self._last_attempt = now
            try:
                value = self._fetcher() if self._fetcher else self._fetch()
                snapshot = value if isinstance(value, Snapshot) else read_workbook(value)
                self.state = RepositoryState(snapshot, '', self.state.revision + 1)
            except Exception as exc:
                message = str(exc) if isinstance(exc, (DataValidationError, ValueError, RuntimeError)) else 'No se pudo leer Google Sheets. Revise la conexión y el acceso al libro.'
                self.state = RepositoryState(self.state.snapshot, message, self.state.revision + 1)
            return self.state

    def _fetch(self):
        if self.settings.source_mode == 'file':
            if not self.settings.local_workbook:
                raise ValueError('Defina LOCAL_WORKBOOK para leer un archivo local.')
            return Path(self.settings.local_workbook).read_bytes()
        if self.settings.source_mode == 'google':
            return self._fetch_authenticated()
        url = f'https://docs.google.com/spreadsheets/d/{self.settings.sheet_id}/export'
        response = self._get(requests.Session(), url, params={'format': 'xlsx'})
        if not response.content.startswith(b'PK'):
            raise ValueError('Sheets no devolvió un libro. Configure acceso autenticado o revise el permiso de lectura existente.')
        if len(response.content) > 25 * 1024 * 1024:
            raise ValueError('El libro supera los 25 MB; use la conexión de Google Sheets API.')
        return response.content

    @staticmethod
    def _get(session, url, **kwargs):
        for attempt in range(3):
            response = session.get(url, timeout=(10, 35), **kwargs)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(0.5 * 2 ** attempt)
                continue
            if response.status_code in (401, 403):
                raise ValueError('Google Sheets rechazó el acceso. Comparta el libro con la cuenta lectora o configure las credenciales.')
            response.raise_for_status()
            return response
        raise RuntimeError('Google Sheets no respondió después de los reintentos.')

    def _fetch_authenticated(self):
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.service_account import Credentials

        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        if self.settings.google_credentials_json:
            credentials = Credentials.from_service_account_info(json.loads(self.settings.google_credentials_json), scopes=scopes)
        elif self.settings.google_credentials_file:
            credentials, _ = google.auth.load_credentials_from_file(self.settings.google_credentials_file, scopes=scopes)
        else:
            credentials, _ = google.auth.default(scopes=scopes)
        session = AuthorizedSession(credentials)
        base = f'https://sheets.googleapis.com/v4/spreadsheets/{self.settings.sheet_id}'
        metadata = self._get(session, base, params={'fields': 'sheets.properties.title'}).json()
        titles = [s['properties']['title'] for s in metadata.get('sheets', []) if s['properties']['title'].strip().lower() in TABLES]
        if not titles:
            raise DataValidationError('No se encontraron las pestañas internas del sistema.')
        ranges = ["'" + title.replace("'", "''") + "'" for title in titles]
        values = self._get(session, base + '/values:batchGet', params={
            'ranges': ranges, 'valueRenderOption': 'UNFORMATTED_VALUE', 'dateTimeRenderOption': 'SERIAL_NUMBER',
        }).json()
        tables = {}
        for title, value_range in zip(titles, values.get('valueRanges', [])):
            matrix = value_range.get('values', [])
            headers = [text(v) for v in matrix[0]] if matrix else []
            if len([h for h in headers if h]) != len(set(h for h in headers if h)):
                raise DataValidationError(f'{title}: encabezado duplicado.')
            tables[title.strip().lower()] = [dict(zip(headers, list(row) + [None] * (len(headers) - len(row)))) for row in matrix[1:]]
        return normalize_tables(tables)
