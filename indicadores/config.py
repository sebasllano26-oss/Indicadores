import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SHEET = '1vSevS3HEHGnGEc4q3Gjd4874iQJqySkN1hnWFVKssaU'


@dataclass(frozen=True)
class Settings:
    sheet_id: str = DEFAULT_SHEET
    refresh_seconds: int = 60
    source_mode: str = 'public'
    local_workbook: str = ''
    google_credentials_file: str = ''
    google_credentials_json: str = ''
    gemini_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'

    @classmethod
    def from_env(cls):
        load_dotenv(APP_DIR / '.env', override=False)
        mode = os.getenv('SOURCE_MODE', 'public').lower()
        if mode not in ('public', 'google', 'file'):
            raise ValueError('SOURCE_MODE debe ser public, google o file.')
        return cls(
            sheet_id=os.getenv('GOOGLE_SHEET_ID', DEFAULT_SHEET),
            refresh_seconds=max(5, int(os.getenv('REFRESH_SECONDS', '60'))),
            source_mode=mode, local_workbook=os.getenv('LOCAL_WORKBOOK', ''),
            google_credentials_file=os.getenv('GOOGLE_APPLICATION_CREDENTIALS', ''),
            google_credentials_json=os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', ''),
            gemini_key=os.getenv('GEMINI_API_KEY', ''),
            gemini_model=os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'),
        )

    def sheet_url(self, table=''):
        base = f'https://docs.google.com/spreadsheets/d/{self.sheet_id}/edit'
        return base + ('#range=' + quote(table + '!A1', safe='!') if table else '')
