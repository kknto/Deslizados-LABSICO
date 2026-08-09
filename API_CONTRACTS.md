# Contratos Minimos De API

Los endpoints actuales deben conservar sus URLs. Toda respuesta de error debe usar JSON con `error`.

## Fechas Y Hora Local

- La operacion de campo usa hora local de Seybaplaya/Cancun.
- La interfaz debe enviar fechas locales tipo `2026-07-24T09:05` cuando la captura es manual.
- Si un gateway o navegador envia `Z` u offset, el backend lo convierte a hora local antes de guardar y calcular.
- No se deben mezclar timestamps UTC persistidos como hora local porque desplazan madurez, edad y velocidad.

## Salud, Schema Y Backups

```text
GET /api/health
GET /api/schema/version
GET /api/backups
GET /api/auditoria?limit=25
POST /api/backups
POST /api/demo/reset
```

Payload `POST /api/backups`:

```json
{ "motivo": "manual_ui" }
```

Payload `POST /api/demo/reset`:

```json
{ "operador": "Nombre", "motivo": "reset demo" }
```

## Colado

Payload minimo:

```json
{
  "silo_id": "Silo 1",
  "mezcla_id": 1,
  "curva_id": 1,
  "hora_colocacion_en_molde": "2026-07-24T09:00",
  "operador": "Operador"
}
```

Reglas:

- `silo_id` y `mezcla_id` son obligatorios.
- Las fechas capturadas deben estar en orden operativo.
- `es_demo` separa datos de entrenamiento.

## Lectura Global

Endpoint:

```text
POST /api/lecturas
POST /api/sensor-readings
POST /api/sensores/ingesta
```

Payload minimo:

```json
{
  "colado_id": 1,
  "fecha_hora": "2026-07-24T09:05",
  "temperatura_concreto_c": 28.5,
  "temperatura_ambiente_c": 31.0,
  "humedad_relativa_pct": 82,
  "origen": "manual"
}
```

Reglas:

- `origen` acepta `manual`, `sensor`, `importacion`, `estimado`.
- Temperatura de concreto: `-10` a `90 C`.
- Temperatura ambiente: `-20` a `70 C`.
- Humedad relativa: `0` a `100%`.
- Si no viene minuto, se calcula desde la hora base del colado.

## Lectura Por Zona

Endpoint:

```text
POST /api/lecturas-zona
POST /api/sensores/ingesta
```

Payload minimo:

```json
{
  "zona_colado_id": 1,
  "fecha_hora": "2026-07-24T09:05",
  "temperatura_concreto_c": 28.5,
  "origen": "sensor"
}
```

Si `POST /api/sensores/ingesta` recibe `zona_colado_id`, guarda lectura por zona; si no, guarda lectura global.

## Avance

Endpoint:

```text
POST /api/avances/registrar-5min
```

Payload minimo:

```json
{
  "colado_id": 1,
  "avance_cm": 2.5,
  "intervalo_minutos": 5,
  "fecha_hora": "2026-07-24T10:00",
  "operador": "Operador"
}
```

Reglas:

- avance, intervalo y velocidad deben ser mayores a cero.
- el backend crea zonas continuas cuando la corona del molde abre espacio superior.

## Decision SCADA

Endpoint:

```text
POST /api/scada/confirmar-avance
```

Payload minimo:

```json
{
  "colado_id": 1,
  "decision_operador": "AVANZAR",
  "registrar_avance": true,
  "avance_cm": 2.5,
  "intervalo_minutos": 5,
  "operador": "Operador",
  "checklist": {
    "no_desmorona": true,
    "no_se_pega": true,
    "acabado_aceptable": true,
    "sin_arrastre": true
  }
}
```

Si la decision contradice una alerta critica, la interfaz debe solicitar supervisor.

## Estado SCADA

Endpoint:

```text
GET /api/scada/estado?colado_id=1&as_of=2026-07-24T10:00
```

La respuesta incluye:

- `estado_scada`: texto corto para operador.
- `estado_molde`: estado tecnico del molde.
- `zona_proxima`: zona que se libera en el siguiente avance.
- `alarmas_activas`: alarmas reconocibles.
- `decisiones_recientes`: bitacora corta.
- `metricas`: madurez, edad, temperatura, avance y velocidad.
- `estado_molde.explicacion_operativa`: lectura corta tipo "Que Esta Pasando".

Alarmas operativas iniciales:

- `ZONA_MENOR_90`.
- `ZONA_MAYOR_105`.
- `FALTA_ZONA_SUPERIOR`.
- `VELOCIDAD_FUERA_OBJETIVO`.
- `SENSOR_VENCIDO`.
- `TEMPERATURA_FUERA_RANGO`.
- `ZONA_HORA_FUTURA`.
