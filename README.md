# Sistema De Prediccion Para Encofrado Deslizante Lite

Esta carpeta contiene la version Lite local Windows para Seybaplaya. La documentacion principal esta en `README_LITE.md`.

## Alcance

- Interfaz visible: `Operador`, `Captura`, `Programa` y `Reporte`.
- Persistencia local: `data/slipform.sqlite`.
- Curvas HRP importadas desde `Curvas HRP.xlsx`.
- Solo Windows local.

## Inicio Rapido

```powershell
py -3 -m slipform.server
```

Abrir:

```text
http://127.0.0.1:8010
```

## Validacion

```powershell
py -3 -m slipform.devcheck
npm.cmd run test:ui
npm.cmd run test:a11y
```

## Documentos

- `README_LITE.md`: uso y reglas operativas.
- `ARCHITECTURE.md`: estructura interna.
- `DISTRIBUCION.md`: paquete Windows.
- `UX_UI_QUALITY.md`: criterios UI y accesibilidad.
