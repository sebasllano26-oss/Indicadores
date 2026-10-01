import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_addoption(parser):
    parser.addoption('--live', action='store_true', help='Consultar la Google Sheets real, sin modificarla.')
    parser.addoption('--ui', action='store_true', help='Verificar la app local con Playwright en el puerto 8000.')
