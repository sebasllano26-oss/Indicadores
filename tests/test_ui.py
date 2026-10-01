from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect


def test_live_ui_views_filters_and_mobile_layout(request):
    if not request.config.getoption('--ui'):
        pytest.skip('La verificación de navegador requiere --ui y la app local en el puerto 8000.')
    screenshots = Path(__file__).resolve().parents[1] / 'test-results'
    screenshots.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = page.goto('http://127.0.0.1:8000', wait_until='domcontentloaded')
        assert response.status == 200
        expect(page.locator('#source_status')).to_contain_text('Conectado', timeout=45000)
        expect(page.get_by_role('heading', name='Análisis estratégico', exact=True)).to_be_visible()
        expect(page.locator('.metric-value').first).not_to_have_text('0')
        page.locator('.js-plotly-plot').first.wait_for(timeout=20000)
        page.screenshot(path=str(screenshots / 'desktop.png'), full_page=True)
        for route, title in [
            ('indicadores', 'Indicadores estratégicos'), ('alertas', 'Alertas tempranas'),
            ('registros', 'Registros de gestión'), ('contratacion', 'Contratación y compras'),
            ('radar', 'Radar de convocatorias'), ('cierres', 'Cierres y auditoría'),
            ('configuracion', 'Configuración y parámetros'),
        ]:
            page.locator(f'.sidebar label:has(input[value="{route}"])').click()
            expect(page.get_by_role('heading', name=title, exact=True)).to_be_visible(timeout=10000)
            if route == 'indicadores':
                expect(page.locator('.indicator-card')).to_have_count(4)
                expect(page.locator('.indicator-card').first).to_contain_text('Falta la meta')
                page.screenshot(path=str(screenshots / 'indicadores.png'), full_page=True)
            if route == 'registros':
                expect(page.locator('#record_id')).to_be_visible()
                expect(page.locator('#record_detail h3')).not_to_be_empty(timeout=10000)
                page.locator('#search').fill('zz-no-existe-zz')
                expect(page.locator('#view_notice')).to_contain_text('No hay datos para esta consulta', timeout=10000)
                page.locator('#clear_filters').click()
                expect(page.locator('#record_detail h3')).not_to_be_empty(timeout=10000)
            if route == 'contratacion':
                expect(page.locator('.checklist-table tbody tr')).to_have_count(24)
                page.screenshot(path=str(screenshots / 'contratos.png'), full_page=True)
            if route == 'radar':
                expect(page.locator('.radar-card a').first).to_have_attribute('href', 'https://www.soyhenry.com/curso-data-analytics')
            if route == 'cierres':
                expect(page.locator('#view_notice')).to_contain_text('No hay datos para esta consulta')
            if route == 'configuracion':
                page.locator('#config_section').select_option('metas')
                expect(page.locator('#config_link a')).to_have_attribute('href', 'https://docs.google.com/spreadsheets/d/1vSevS3HEHGnGEc4q3Gjd4874iQJqySkN1hnWFVKssaU/edit#range=metas!A1')
        page.locator('#open_copilot').click()
        expect(page.get_by_role('heading', name='Copiloto estratégico')).to_be_visible()
        expect(page.get_by_role('heading', name='Copiloto no disponible')).to_be_visible()
        page.get_by_role('button', name='Cerrar', exact=True).click()
        page.locator('.sidebar label:has(input[value="analisis"])').click()
        page.locator('#refresh').click()
        expect(page.locator('#refresh')).to_have_text('Actualizar', timeout=45000)
        mobile = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=1)
        mobile.on('pageerror', lambda error: errors.append(str(error)))
        mobile.goto('http://127.0.0.1:8000', wait_until='domcontentloaded')
        expect(mobile.locator('#source_status')).to_contain_text('Conectado', timeout=45000)
        expect(mobile.get_by_role('heading', name='Análisis estratégico', exact=True)).to_be_visible()
        expect(mobile.locator('.metric-value').first).not_to_have_text('0')
        mobile.locator('.js-plotly-plot').first.wait_for(timeout=20000)
        mobile.screenshot(path=str(screenshots / 'mobile.png'), full_page=True)
        assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        assert not errors, errors
        browser.close()
