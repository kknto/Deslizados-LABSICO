# UX/UI Quality Checklist Lite

## Objetivo

Mantener una interfaz simple para obra con decision rapida, trazabilidad clara, accesibilidad practica WCAG 2.2 AA y uso confiable en laptop, tablet o movil.

## Criterios Base

- La navegacion visible debe tener `Operador`, `Captura`, `Programa`, `Bitacora` y `Reporte`. `Bitacora` queda separada como flujo experimental de migracion historica.
- Operador debe responder rapido: puedo avanzar, que zona libero, madurez, temperatura, avance total y accion principal.
- Toda accion critica debe tener texto visible y confirmacion cuando modifique avance o criterio de campo.
- Los controles tactiles deben medir al menos 44 x 44 px.
- Los estados operativos deben usar terminologia consistente: `NO AVANZAR`, `PREPARARSE`, `AVANZAR`, `RIESGO`, `SIN DATOS`.
- Formularios deben tener labels visibles, errores junto al campo y foco al primer campo invalido.
- Tabs deben operar con mouse, tactil y teclado.
- Graficas visibles deben tener resumen textual y estado vacio claro.

## Revision Por Vista

- Operador: decision, zona, madurez, temperatura, avance total incluyendo zonas previas, temporizador, checklist, bitacora y tendencia viva.
- Captura: colado, arranque con zona previa, ollas de 5 m3/30 cm, lecturas, receta y tabla de descargas.
- Programa: cilindros de campo con escenarios 4h, 5h y 6h, historial y receta sugerida.
- Bitacora: OCR experimental, plantillas CSV, primera zona fresca, avances opcionales desde eventos, vista previa, errores/advertencias e importacion confirmada.
- Reporte: datos de proyecto, semaforo simplificado, lecturas recientes, exportaciones, evidencia y backup SQLite.

## Bitacora Escrita

- El usuario debe poder crear plantillas CSV desde Bitacora.
- El usuario puede probar OCR automatico, pero el sistema debe bloquear importacion si no hay motor OCR o candidatos importables.
- La vista previa debe mostrar conteos, errores y advertencias antes de habilitar la importacion.
- La vista previa debe mostrar zonas previas, avances detectados y avance total visible estimado cuando se active la creacion de avances desde eventos.
- Si ya existen avances del molde, la UI debe comunicar que la importacion de avances queda bloqueada por seguridad.
- La confirmacion final debe avisar que se crea backup SQLite.
- Las imagenes fuente deben quedar en la evidencia y en el ZIP de entrega.

## Pruebas Requeridas

```powershell
py -3 -m slipform.devcheck
npm.cmd run test:ui
npm.cmd run test:a11y
```

Verificacion manual final:

- Abrir `http://127.0.0.1:8010`.
- Confirmar las cinco pestanas visibles.
- Revisar consola sin errores.
- Probar desktop, tablet y movil.
- Confirmar `/api/health`.
