# Despliegue En Render

Este proyecto incluye `render.yaml` para crear el servicio web desde un Blueprint de Render.

## Que Se Crea

- Servicio web Python `deslizados-labsico`.
- Base PostgreSQL administrada `deslizados-labsico-db`.
- `DATABASE_URL` conectado desde la base al servicio web.
- Inicializacion idempotente al arrancar el servidor, con reintentos si PostgreSQL tarda en aceptar conexiones.

## Base De Datos

No se sube `data/slipform.sqlite` al repositorio para evitar publicar datos reales. En Render, PostgreSQL es la base activa; el primer arranque crea schema, proyecto base, configuracion de molde y curvas HRP importadas desde `Curvas HRP.xlsx`.

Si despues necesitas llevar datos historicos a internet, usa los flujos de importacion de la app. Los respaldos de produccion se gestionan desde Render Postgres.

## Pasos Minimos En Render

1. Crear un nuevo Blueprint.
2. Conectar el repositorio `kknto/Deslizados-LABSICO`.
3. Render detecta `render.yaml` y crea el servicio web mas la base PostgreSQL.
4. Abrir la URL publica cuando el estado quede `Live`.
5. Verificar `/api/health`.

## Notas De Escalabilidad

SQLite se conserva para Windows local/portable. Render usa PostgreSQL desde el inicio para evitar migraciones futuras con datos reales.
