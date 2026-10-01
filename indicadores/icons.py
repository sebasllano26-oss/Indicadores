"""Iconos de interfaz: SVG locales, decorativos y sin dependencias de red."""
from shiny import ui


PATHS = {
    'analisis': '<path d="M4 19V5m0 14h16M8 14l4-5 4 3 4-7"/>',
    'indicadores': '<rect x="3" y="12" width="4" height="8" rx="1"/><rect x="10" y="8" width="4" height="12" rx="1"/><rect x="17" y="3" width="4" height="17" rx="1"/>',
    'alertas': '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    'registros': '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M8 12h8m-8 4h5"/>',
    'contratacion': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12a22 22 0 0 0 18 0m-9-1v4"/>',
    'radar': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 7-7"/><circle cx="12" cy="12" r="1"/>',
    'cierres': '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 10h16m-12 5 3 3 5-5"/>',
    'configuracion': '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor" stroke="none"/><circle cx="15" cy="17" r="3" fill="currentColor" stroke="none"/>',
    'refresh': '<path d="M20 7v5h-5M4 17v-5h5M6.1 6.1a8 8 0 0 1 13 2M4.9 15.9a8 8 0 0 0 13 2"/>',
    'sheet': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 12h8m-8 4h8m-4-4v8"/>',
    'sparkles': '<path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4ZM20 2v4m-2-2h4"/>',
    'filter': '<path d="M4 5h16l-6 7v7l-4 2v-9Z"/>',
    'arrow': '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'wallet': '<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 8h18m-5 4h5v5h-5a2.5 2.5 0 0 1 0-5"/>',
    'coins': '<ellipse cx="9" cy="6" rx="6" ry="3"/><path d="M3 6v5c0 4 12 4 12 0V6m-12 5v5c0 4 12 4 12 0m3-6c4 0 4 5 0 5m0-1c4 0 4 5 0 5"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
    'download': '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
}


def icon(name, size=18):
    return ui.HTML(f'<svg class="app-icon" width="{size}" height="{size}" viewBox="0 0 24 24" '
                   'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
                   'stroke-linejoin="round" aria-hidden="true" focusable="false">'
                   + PATHS.get(name, PATHS['info']) + '</svg>')
