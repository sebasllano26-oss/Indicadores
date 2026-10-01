# Indicadores · Shiny for Python

Portal de relacionamiento estratégico de Comfamiliar Risaralda. El equipo captura los datos en [Google Sheets](https://docs.google.com/spreadsheets/d/1vSevS3HEHGnGEc4q3Gjd4874iQJqySkN1hnWFVKssaU/edit); Python calcula los resultados y Shiny actualiza las vistas. Los cambios en la hoja no requieren publicar nuevamente el código.

La interfaz usa navegación por secciones, filtros desplegables, un resumen de cuatro cifras y gráficos interactivos. Las cifras monetarias del resumen se abrevian en millones (`M`); debajo se conserva el importe completo en COP. Las tablas permiten ordenar columnas, habilitar sus filtros y descargar el CSV. El diseño se adapta a móvil con un menú desplegable. La fuente Inter y los iconos se sirven desde la app; la licencia de Inter está incluida en `www/fonts/OFL.txt`.

## Ejecutar en Windows

Requiere Python 3.12. Desde esta carpeta:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m shiny run --host 127.0.0.1 --port 8000 app.py
```

Abrir <http://127.0.0.1:8000>. También puede ejecutarse `./iniciar.ps1` cuando la política local permita scripts; `./iniciar.ps1 -Install` instala las dependencias antes de iniciar. Para otros sistemas, usar los comandos equivalentes de Python 3.12 y `.venv/bin/python`.

## Conexión con Sheets

La app usa por defecto la hoja autorizada, mediante su exportación XLSX de lectura, accesible sin autenticación al verificarla el 1 de octubre de 2026. No se modificaron sus permisos. Se consulta cada 60 segundos mientras el proceso esté activo; «Actualizar» permite una lectura anticipada, con un intervalo mínimo de 4 segundos. La caché se comparte entre las sesiones de cada proceso.

Las lecturas incorporan altas, cambios y bajas. Si falla la conexión o el libro es inválido, la app conserva los últimos datos válidos y muestra el error y la hora de esa lectura. El servidor suspendido o una exportación demorada por Google pueden retrasar la actualización.

Copiar `.env.example` a `.env` para cambiar la configuración local. En el alojamiento, guardar estas variables como configuración del servidor:

| Variable | Uso |
| --- | --- |
| `GOOGLE_SHEET_ID` | ID del libro; predeterminado: el enlace autorizado |
| `SOURCE_MODE` | `public` para la exportación actual; `google` para Sheets API autenticada; `file` para una fuente local explícita |
| `REFRESH_SECONDS` | Intervalo de consulta; 60 por defecto, mínimo 5 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON de una cuenta de servicio; se lee desde una variable secreta |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta a un archivo de credenciales; alternativa local al JSON |
| `LOCAL_WORKBOOK` | Ruta del libro, únicamente en modo `file` |
| `GEMINI_API_KEY` | Clave opcional del copiloto |
| `GEMINI_MODEL` | Modelo disponible en la cuenta; configurable |

Para una hoja privada, habilitar Google Sheets API en el proyecto correspondiente, configurar `SOURCE_MODE=google`, proporcionar la credencial de una cuenta de servicio y compartir el libro con esa cuenta como lectora. La app solicita únicamente `spreadsheets.readonly`. La conexión autenticada requiere una credencial real y aún no se verificó contra una cuenta privada.

No subir `.env`, credenciales, el entorno virtual ni copias del libro al repositorio.

## Alimentar el sistema

Se leen las diez pestañas internas: `objetivos_corporativos`, `objetivos_area`, `indicadores`, `metas`, `registros`, `evidencias`, `catalogos`, `cierres`, `contratos` y `rastreo_convocatorias`. Las hojas del formato original se ignoran para evitar duplicar los registros ya importados. Conservar nombres de pestañas, encabezados e IDs únicos.

1. Registrar las gestiones en `registros`, con fecha de inicio y los IDs de `objetivos_area` en `objetivos` (varios se separan con coma).
2. Mantener las definiciones de `indicadores`. Sus operaciones declarativas son `CONTAR`, `SUMAR` y `FIJO`, con filtros opcionales. Las fórmulas inválidas se muestran como errores.
3. Completar `meta` en `indicadores` o una meta específica en `metas`, identificada por indicador, año y período (`ANUAL`, `T1`…`T4`, `S1`…`S2`). Una base positiva en `denominador` habilita el cálculo con base manual.
4. Actualizar contratos, convocatorias y evidencias en sus pestañas; guardar los resultados históricos en `cierres`. Los cierres mostrados son los guardados en la hoja; no se recalculan ni se escriben desde la app.
5. Consultar los resultados o pulsar «Actualizar». «Configuración y parámetros» abre cada pestaña de Sheets para editarla.

La hoja observada el 1 de octubre de 2026 contiene 55 gestiones, 4 indicadores, 2 contratos y 2 convocatorias. Los 55 registros no tienen objetivos asignados y los 4 indicadores no tienen metas; por eso el cumplimiento aparece pendiente. No hay metas específicas, evidencias ni cierres guardados en esa lectura. La app no inventa datos faltantes.

## Vistas y alcance

Análisis estratégico, indicadores, alertas tempranas, registros, contratación y compras, radar de convocatorias, cierres y auditoría, configuración y parámetros. Incluye filtros, gráficos interactivos, tablas, descarga CSV, detalle de registros y checklist contractual de 24 fases. La captura y las modificaciones se realizan en Sheets.

Contratos y convocatorias se consultan por año, responsable y búsqueda. Se conservan los registros sin fecha para que puedan corregirse; los filtros de período, área, estado de gestión y objetivo corresponden a las gestiones e indicadores.

El copiloto requiere una clave Gemini. Sin ella se muestra «Copiloto no disponible». Cuando se configura, las preguntas envían al proveedor el contexto de la consulta filtrada, hasta 80 registros y sus resultados; el contexto incluye la cantidad de registros cuyo detalle se omitió. No se verificó una respuesta del proveedor porque no hay una clave configurada.

## Publicar desde GitHub

El repositorio previsto es [sebasllano26-oss/Indicadores](https://github.com/sebasllano26-oss/Indicadores), rama `main`. Esta carpeta es la raíz del proyecto que se publica: contiene `app.py`, `requirements.txt`, `indicadores/` y `www/`. Los archivos Apps Script y React originales permanecen en la carpeta de trabajo anterior.

En [Posit Connect Cloud](https://connect.posit.cloud/), con una cuenta autenticada:

1. Crear contenido de tipo Shiny for Python e importar ese repositorio y la rama `main`.
2. Elegir `app.py` como archivo principal y Python 3.12. Las dependencias están fijadas en `requirements.txt` a las versiones verificadas.
3. Configurar, si se necesitan, las variables de entorno; las claves van como secretos. Para la hoja actual basta la configuración predeterminada.
4. Revisar la audiencia y las opciones de acceso del contenido, publicar y comprobar los registros de despliegue y la conexión a la hoja.

El acceso al sitio depende del alojamiento. La app no incorpora autenticación propia. La publicación requiere una cuenta Posit y acceso de esa cuenta al repositorio; subir el código a GitHub no publica automáticamente la app. [Guía oficial de Shiny for Python en Connect Cloud](https://docs.posit.co/connect-cloud/how-to/python/shiny-python.html).

También puede desplegarse por CLI en un servidor Shiny compatible sin usar un repositorio. [Opciones oficiales de despliegue](https://shiny.posit.co/py/get-started/deploy-cloud.html).

## Verificación

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe -m pytest tests -q
# Con la app local activa en el puerto 8000:
.venv/Scripts/python.exe -m pytest tests -q --live --ui
```

`--live` lee la hoja real sin modificarla y compara conteos y sumas con una lectura independiente. `--ui` verifica las ocho vistas, filtros, detalles, actualización y diseño móvil; además, abre dos sesiones contra un libro temporal y comprueba altas, cambios, bajas, conservación ante errores y recuperación. Los archivos temporales y las capturas no se publican.
