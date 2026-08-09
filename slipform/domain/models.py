"""Lightweight domain models used as contracts between layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Colado:
    id: int | None
    silo_id: str
    mezcla_id: int
    fecha_hora_inicio: str
    operador: str = ""
    estado: str = "Activo"
    observaciones: str = ""


@dataclass(slots=True)
class ZonaColado:
    id: int | None
    colado_id: int
    zona_numero: int
    elevacion_inferior_cm: float
    elevacion_superior_cm: float
    hora_inicio_llenado: str
    hora_fin_llenado: str
    hora_referencia_madurez: str
    mezcla_id: int | None = None
    curva_id: int | None = None
    estado: str = "ZONA_EN_LLENADO"


@dataclass(slots=True)
class Lectura:
    id: int | None
    colado_id: int
    fecha_hora: str
    temperatura_concreto_c: float | None = None
    temperatura_ambiente_c: float | None = None
    humedad_relativa_pct: float | None = None
    origen: str = "manual"
    valido: bool = True
    motivo_invalidez: str = ""


@dataclass(slots=True)
class AvanceMolde:
    id: int | None
    colado_id: int
    fecha_hora: str
    avance_cm: float
    avance_acumulado_cm: float
    velocidad_real_cm_h: float | None = None
    origen: str = "manual"
    operador: str = ""
    observacion: str = ""


@dataclass(slots=True)
class EstadoMolde:
    colado_id: int
    estado_operativo: str
    avance_acumulado_cm: float
    velocidad_real_cm_h: float | None = None
    zona_en_liberacion: dict[str, Any] | None = None
    ventana_molde: dict[str, Any] = field(default_factory=dict)
    alertas: list[dict[str, Any]] = field(default_factory=list)
    recomendaciones: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AlarmaOperativa:
    id: int | None
    colado_id: int
    tipo: str
    severidad: str
    estado: str
    fecha_hora_inicio: str
    mensaje: str
    zona_colado_id: int | None = None


@dataclass(slots=True)
class DecisionOperador:
    id: int | None
    colado_id: int
    recomendacion_sistema: str
    decision_operador: str
    operador: str
    zona_colado_id: int | None = None
    avance_molde_id: int | None = None
    requiere_supervisor: bool = False
    supervisor: str = ""
    checklist_json: str = "{}"
    observacion: str = ""
