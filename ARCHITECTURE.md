# Arquitectura Lite

El proyecto Lite es una app local Windows para operar el deslizamiento con una UI reducida: `Operador`, `Captura`, `Programa`, `Bitacora` y `Reporte`. `Bitacora` es una vista separada para migracion historica y OCR experimental.

## Estructura

```text
slipform/
  domain/          Reglas puras y modelos de negocio.
  repositories/    SQLite, migraciones y consultas por agregado.
  services/        Casos de uso de colados, molde, programa, reportes y soporte.
  http/            Rutas HTTP, handlers y respuestas.
  reports/         HTML, CSV y paquetes de exportacion.
  db.py            Fachada de compatibilidad.
  cloud_init.py    Inicializacion idempotente para despliegues web.
  server.py        Entrada de servidor local.

static/
  index.html       Vistas Lite visibles.
  js/main.js       Orden de carga web/Windows.
  js/view-operator.js
  js/view-capture.js
  js/view-program.js
  js/view-report.js
  js/legacy-app.js Orquestador temporal.
  css/             Estilos compartidos y especificos.

data/
  slipform.sqlite  Base local activa.
  backups/         Respaldos SQLite.

Bitacora_escrita/
  transcripcion/   Plantillas CSV para importar hojas manuscritas.
```

## Fronteras

- La UI no expone Inicio, SCADA, Zonas, Tendencias, Eventos, Evidencia, Sensores, Diagnostico ni Calibracion como pestanas.
- `Bitacora` es una excepcion explicita para migrar informacion historica; no participa en la operacion diaria.
- Los endpoints historicos que todavia alimentan Operador, reportes o compatibilidad pueden permanecer internos.
- No se eliminan columnas legacy durante esta limpieza para poder abrir respaldos anteriores.
- Android no forma parte del Lite.

## Modulos Backend

```text
repositories/audit_repo.py        Schema version, conteos, auditoria y limpieza demo.
repositories/avances_repo.py      Avances del molde y receta activa.
repositories/catalog_repo.py      Mezclas, curvas HRP y bootstrap.
repositories/colados_repo.py      Crear, editar, listar y eliminar colados.
repositories/descargas_repo.py    Descargas de olla.
repositories/events_repo.py       Eventos operativos y predicciones guardadas.
repositories/evidencia_repo.py    Evidencia usada por reportes.
repositories/lecturas_repo.py     Lecturas generales y por zona.
repositories/mold_config_repo.py  Configuracion fisica del molde.
repositories/project_repo.py      Datos generales del proyecto.
repositories/scada_repo.py        Decisiones, alarmas y turnos internos.
repositories/schedule_repo.py     Programa por cilindros 4h/5h/6h.
repositories/schema.py            Schema SQLite y migraciones compatibles.
repositories/zonas_repo.py        Zonas de 30 cm y continuidad.
services/written_log_import.py    Importacion segura de bitacora escrita desde CSV revisado.
services/written_log_ocr.py       OCR experimental; genera candidatos, nunca escribe directo a SQLite.
```

## Flujo De Datos

1. Captura registra colado, arranque, olla, lectura o receta.
2. Los handlers HTTP validan payloads y llaman servicios.
3. Los servicios calculan madurez, avance, estado de molde y programa.
4. SQLite guarda la operacion local.
5. Operador consume estado de molde, tendencias visibles, zonas, bitacora y programa.
6. Reporte genera HTML, CSV, ZIP de evidencia y backups.
7. Bitacora puede generar candidatos OCR o importar CSV revisado; antes del commit crea backup, registra auditoria y adjunta imagenes originales como evidencia.
8. En importaciones historicas, `ollas_deslizado.csv` crea/actualiza ollas y zonas con temperatura, revenimiento y madurez desde `hora_salida_planta`. `eventos_deslizado.csv` siempre entra como bitacora historica y solo crea avances del molde si el usuario activa esa opcion.

## Convenciones

- SQLite es la fuente local de verdad.
- En nube, `SLIPFORM_DB_PATH` define la ruta de SQLite. Render usa `/var/data/slipform.sqlite` sobre disco persistente.
- La base SQLite no se versiona en GitHub; `slipform.cloud_init` crea schema y curvas al arrancar si la base esta vacia.
- Toda conexion debe habilitar `PRAGMA foreign_keys=ON` y cerrarse correctamente.
- Las URLs publicas usadas por las vistas Lite no deben cambiar sin prueba de contrato.
- `legacy-app.js` se mantiene como orquestador temporal; nuevas responsabilidades visibles deben moverse gradualmente a `view-operator`, `view-capture`, `view-program` y `view-report`.
- `static/sw.js` debe versionarse cuando cambie cualquier asset cacheado.
- `py -3 -m slipform.devcheck` es validacion obligatoria antes de entregar.
- No se importa OCR directo a SQLite; las hojas manuscritas pasan por CSV revisable y vista previa.
- Si la primera zona fresca es 2 o superior, la importacion historica crea las zonas previas como `existente_previo`; no calcula madurez Arrhenius para ellas y el avance visible de Operador suma esas zonas previas.
- Los avances importados desde eventos `Deslizado` se interpretan como avance acumulado desde el inicio del deslizado y se bloquean si el colado ya tiene avances guardados.
- El OCR busca Tesseract en PATH, `runtime/tesseract`, `tools/tesseract` y rutas estandar de Windows.

## Despliegue Web

- `render.yaml` define el servicio Python, disco persistente, health check y comandos de arranque.
- `startCommand` ejecuta `python -m slipform.server`.
- El servidor toma `PORT` y `SLIPFORM_HOST` del entorno cuando existen, preservando `127.0.0.1:8010` para uso local.
- SQLite en Render es adecuada para una sola instancia. Para multiples instancias o alta concurrencia, la ruta futura es PostgreSQL.

## Agregar Funcionalidad

1. Ubicar la regla en `domain/` o `services/`.
2. Persistir con un repositorio claro, sin SQL disperso en handlers.
3. Exponer ruta en `http/routes.py` y handler correspondiente.
4. Agregar prueba de contrato o unidad.
5. Actualizar documentacion si cambia el flujo visible.
