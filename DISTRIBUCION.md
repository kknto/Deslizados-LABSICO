# Distribucion Windows Lite

La distribucion del Lite es solo Windows local mediante ZIP portable o ejecucion directa de la carpeta.

## Contenido Del ZIP

El builder genera un archivo en `dist/` con nombre similar a:

```text
SeybaPlaya-Deslizamiento-Portable-YYYYMMDD_HHMM.zip
```

Incluye:

- `INICIAR_PROGRAMA.bat`
- `DIAGNOSTICO.bat`
- `RESPALDAR_DATOS.bat`
- `LEEME_PRIMERO.txt`
- `launcher.py`
- `runtime/python/`
- `runtime/tesseract/` cuando Tesseract OCR esta instalado en el equipo que genera el paquete.
- `slipform/`
- `static/`
- `data/slipform.sqlite`
- `data/backups/`
- `Bitacora_escrita/` si contiene imagenes historicas o plantillas de transcripcion.
- `README_LITE.md`, `ARCHITECTURE.md`, `DISTRIBUCION.md`, `UX_UI_QUALITY.md`
- `Curvas HRP.xlsx` y `Prediccion_Arrhenius_Campo.xlsx`

No incluye componentes moviles.

## Distribucion Web

Para GitHub/Render se distribuye solo el codigo, estaticos, documentacion y archivos Excel de referencia. No se suben:

- `data/slipform.sqlite`
- `data/backups/`
- `Bitacora_escrita/`
- `reports/` generados
- `node_modules/`

Render crea su propia SQLite limpia durante el arranque del servidor y la conserva en el disco persistente `/var/data`.

## Generar Paquete

Desde la carpeta del proyecto:

```powershell
py -3 tools\build_portable_package.py
```

Para carpeta sin ZIP:

```powershell
py -3 tools\build_portable_package.py --no-zip
```

## Probar Antes De Entregar

1. Ejecutar `py -3 -m slipform.devcheck`.
2. Ejecutar `npm.cmd run test:ui`.
3. Ejecutar `npm.cmd run test:a11y`.
4. Descomprimir el ZIP en una carpeta temporal.
5. Dar doble clic en `INICIAR_PROGRAMA.bat`.
6. Confirmar que abre `http://127.0.0.1:8010` u otro puerto mostrado.
7. Confirmar visualmente `Operador`, `Captura`, `Programa`, `Bitacora` y `Reporte`.
8. Crear un backup desde `Reporte`.
9. En `Bitacora`, crear plantillas de bitacora escrita y confirmar que la vista previa puede leer CSV de prueba.
10. Probar una importacion historica con `Primera zona fresca` y, si aplica, activar `Crear avances desde eventos Deslizado` para revisar el total visible estimado antes de confirmar.

## Reglas Para Usuario Final

- No borrar `data/`.
- No cerrar la ventana negra mientras se usa el sistema.
- Usar `Operador` para trabajo diario.
- Usar `Captura` para colado, ollas, lecturas y receta.
- Usar `Programa` para cilindros 4h/5h/6h.
- Usar `Bitacora` para OCR experimental o importacion de bitacora escrita desde CSV revisado.
- En Bitacora, `ollas_deslizado.csv` es la fuente confiable para temperatura y revenimiento; `eventos_deslizado.csv` puede crear avances solo si el usuario lo activa.
- Usar `Reporte` para exportaciones y respaldos.
- Si el navegador muestra `Sin conexion`, revisar que el servidor siga abierto.
- El OCR automatico funciona con Tesseract incluido en el ZIP o instalado en Windows.

El paquete es local y monousuario. Para varios equipos o acceso remoto se requiere una arquitectura central.
