# SeybaPlaya Deslizamiento Lite

Version local Windows del control de deslizamiento para Seybaplaya. La interfaz visible operativa queda reducida y ahora incluye una vista experimental separada para migracion historica:

- Operador
- Captura
- Programa
- Bitacora
- Reporte

La logica interna necesaria para calculos, SQLite, reportes y compatibilidad con respaldos antiguos se conserva aunque ya no exista una pestana visible de diagnostico SCADA.

## Inicio

Desde esta carpeta:

```powershell
py -3 -m slipform.server
```

Despues abrir:

```text
http://127.0.0.1:8010
```

Tambien se puede usar doble clic en `INICIAR_LITE.bat`.

## Despliegue Web

La version Lite puede publicarse en Render con el Blueprint incluido en `render.yaml`.

- El repositorio no debe incluir `data/slipform.sqlite`, respaldos ni evidencias reales.
- Render crea una base PostgreSQL administrada nueva y separada para este proyecto.
- Al arrancar, el servidor crea schema, proyecto base, configuracion de molde y curvas HRP con reintentos si PostgreSQL tarda en responder.
- La app en nube usa `DATABASE_URL`, `SLIPFORM_HOST` y `PORT` para arrancar correctamente.

Ver instrucciones completas en `DEPLOY_RENDER.md`.

## Flujo Operativo

1. `Captura`: crear colado, configurar arranque, registrar ollas, lecturas y receta de avance.
2. `Programa`: registrar cilindros de campo y escenarios 4h, 5h y 6h.
3. `Operador`: ver decision, zona a liberar, madurez, avance total, temporizador, zonas y bitacora.
4. `Bitacora`: OCR experimental, plantillas CSV, vista previa e importacion de bitacora escrita.
5. `Reporte`: datos generales, reportes, exportaciones, evidencia operativa y respaldo SQLite.

## Reglas Crticas Del Lite

- Cada olla equivale a una zona/capa de 30 cm y 5 m3.
- La madurez de cada zona inicia desde `hora_salida_planta` de su olla.
- Si el colado inicia en zona 2 o superior, las zonas previas se registran como existentes previas.
- El avance total mostrado en Operador incluye zonas previas.
- No se falsifica madurez Arrhenius. Si el operador libera por criterio de campo, se guarda como madurez operativa por inspeccion.
- Programa usa cilindros de campo con escenarios 4h, 5h y 6h.

## Archivos Clave

- `slipform/mold.py`: estado del molde, zonas, madurez y avance operativo.
- `slipform/repositories/schema.py`: schema SQLite local y seleccion de schema PostgreSQL para Render.
- `slipform/repositories/postgres_schema.py`: schema PostgreSQL para despliegue web.
- `slipform/repositories/schedule_repo.py`: programa por cilindros.
- `slipform/services/written_log_import.py`: plantillas CSV, vista previa e importacion validada de bitacora escrita.
- `static/index.html`: vistas visibles Lite.
- `static/js/main.js`: carga modular frontend.
- `static/js/view-operator.js`: renderizadores visibles de Operador.
- `static/js/legacy-app.js`: orquestador temporal mientras se extraen Captura, Programa y Reporte.
- `data/slipform.sqlite`: base SQLite limpia actual.

## Base SQLite

La base activa es `data/slipform.sqlite`. Antes de la limpieza se genero un respaldo fechado en `data/backups/`.

La base limpia conserva mezclas, curvas HRP y puntos de madurez importados desde `Curvas HRP.xlsx`, e inicia sin colados reales, avances, alarmas ni decisiones historicas.

En despliegues web, la base activa es PostgreSQL y se conecta mediante `DATABASE_URL`. Para migrar datos historicos a internet se debe usar el flujo de importacion de la app.

## Bitacora Escrita

Las hojas manuscritas se migran desde `Bitacora` con un flujo seguro: imagen original como evidencia, OCR experimental o transcripcion CSV revisable y confirmacion final. El boton `Crear Plantillas CSV` genera:

- `Bitacora_escrita/transcripcion/ollas_deslizado.csv`
- `Bitacora_escrita/transcripcion/eventos_deslizado.csv`

La vista permite configurar la `Primera zona fresca`. Si se indica 2 o superior, las zonas anteriores se crean como `existente_previo` y se suman al avance total visible de Operador. Opcionalmente puede activarse `Crear avances desde eventos Deslizado`; en ese modo los numeros detectados en `eventos_deslizado.csv` se interpretan como avance acumulado desde el inicio del deslizado. Si ya existen avances en el colado, la importacion de avances queda bloqueada por seguridad.

`ollas_deslizado.csv` es la fuente confiable para ollas, zonas, temperatura de llegada, revenimiento y madurez desde `hora_salida_planta`. Los datos de temperatura o revenimiento escritos en texto libre dentro de eventos solo se conservan como advertencia/trazabilidad; no sustituyen automaticamente al CSV estructurado.

El boton `Analizar Imagenes Automaticamente` intenta usar Tesseract local o el motor incluido en `runtime/tesseract` para generar CSV candidatos. Si el motor OCR no esta disponible o no produce filas confiables, la importacion automatica queda bloqueada y se debe usar transcripcion manual. La vista previa normaliza horarios con fecha base, detecta cruces de medianoche, marca errores por fila y bloquea el guardado si falta una hora requerida. La importacion crea un backup SQLite antes de escribir datos y no borra registros existentes.

## Validacion

```powershell
py -3 -m slipform.devcheck
npm.cmd run test:ui
npm.cmd run test:a11y
```
