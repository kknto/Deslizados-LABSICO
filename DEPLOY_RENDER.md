# Despliegue En Render

Este proyecto incluye `render.yaml` para crear el servicio web desde un Blueprint de Render.

## Que Se Crea

- Servicio web Python `deslizados-labsico`.
- Disco persistente de 1 GB montado en `/var/data`.
- SQLite activa en `/var/data/slipform.sqlite`.
- Inicializacion previa al despliegue con `python -m slipform.cloud_init`.

## Base De Datos

No se sube `data/slipform.sqlite` al repositorio para evitar publicar datos reales. En Render, la primera ejecucion crea una SQLite nueva con schema, proyecto base, configuracion de molde y curvas HRP importadas desde `Curvas HRP.xlsx`.

Si despues necesitas llevar datos historicos a internet, usa la exportacion/importacion de respaldo desde la app, no reemplaces archivos dentro del repositorio.

## Pasos Minimos En Render

1. Crear un nuevo Blueprint.
2. Conectar el repositorio `kknto/Deslizados-LABSICO`.
3. Render detecta `render.yaml` y crea el servicio.
4. Abrir la URL publica cuando el estado quede `Live`.
5. Verificar `/api/health`.

## Notas De Escalabilidad

SQLite con disco persistente es adecuado para una instancia web sencilla y pocos usuarios. Si el sistema va a operar con varios usuarios simultaneos o mas de una instancia, el siguiente paso tecnico debe ser migrar la capa de repositorios a PostgreSQL.
