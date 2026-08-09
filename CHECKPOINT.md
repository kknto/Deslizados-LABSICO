# Checkpoint Lite

Fecha: 2026-08-04.

Proyecto funcional: version Lite local Windows para control de deslizamiento en silos de concreto. Stack: Python stdlib HTTP + SQLite + HTML/CSS/JS + ECharts + Playwright. Servidor: `py -3 -m slipform.server`, URL normal `http://127.0.0.1:8010`.

## Despliegue Web Preparado

- Blueprint: `render.yaml`.
- Inicializador: `python -m slipform.cloud_init`, ejecutado como `preDeployCommand`.
- Base cloud: PostgreSQL administrado con `DATABASE_URL`.
- Health check: `/api/health`.
- No se versionan bases SQLite, respaldos ni evidencias reales.

## Alcance Actual

- UI visible: `Operador`, `Captura`, `Programa`, `Bitacora`, `Reporte`.
- Componentes moviles eliminados de esta copia Lite.
- Base activa: `data/slipform.sqlite`, regenerada limpia con curvas HRP.
- Bitacora incluye OCR experimental e importacion desde CSV revisado con backup previo y evidencia de imagenes originales.
- La importacion historica ya es configurable: primera zona fresca, zonas previas `existente_previo`, eventos como bitacora y avances desde `Deslizado` solo si el usuario lo activa.
- Respaldos previos:
  - `data/backups/pre_limpieza_lite_20260804_135444.sqlite`
  - `data/backups/pre_sqlite_limpia_lite_20260804_140737.sqlite`

## Reglas Operativas Confirmadas

- Cada olla equivale a una zona/capa de 30 cm y 5 m3.
- La madurez de cada zona inicia desde `hora_salida_planta` de su olla.
- Si el colado inicia en zona 2 o superior, las zonas previas se registran como existentes previas.
- El avance total mostrado en Operador incluye zonas previas.
- No se falsifica madurez Arrhenius; liberacion por criterio de campo se guarda como madurez operativa por inspeccion.
- Programa usa cilindros de campo con escenarios 4h, 5h y 6h.

## Estado De Limpieza

- Removidas las pestanas/paneles visibles fuera del Lite.
- Removidos assets y scripts moviles fuera del alcance Lite.
- `static/js/main.js` carga modulos web/Windows: estado, utilidades, graficas, `view-operator`, `view-capture`, `view-program`, `view-report` y `legacy-app`.
- `legacy-app.js` sigue como orquestador temporal mientras se extraen mas responsabilidades por vista.
- Endpoints internos heredados pueden permanecer si alimentan Operador, reportes, SQLite o compatibilidad con respaldos.
- `slipform/services/written_log_import.py` concentra plantillas CSV, vista previa, importacion, auditoria y adjuntos de evidencia para bitacoras manuscritas.
- `written_log_import.py` toma temperatura/revenimiento desde `ollas_deslizado.csv`; menciones en texto libre de eventos se muestran como advertencias y no se guardan como datos estructurados.
- `slipform/services/written_log_ocr.py` concentra OCR experimental; genera candidatos y no guarda directo a SQLite.

## Validacion Obligatoria

```powershell
py -3 -m slipform.devcheck
npm.cmd run test:ui
npm.cmd run test:a11y
```

## Siguiente Paso Sugerido

Continuar extrayendo Captura, Programa y Reporte desde `legacy-app.js` hacia sus modulos dedicados con pruebas por vista, sin cambiar contratos de API. Para bitacoras escritas, cualquier OCR futuro debe quedar como ayuda para llenar CSV, no como commit automatico a SQLite.
