"""Schema de `GET /status`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.robot import ConnectionState


class StatusResponse(BaseModel):
    connected: bool = Field(
        description="Há conexão WebRTC viva e canal de dados validado. É o que "
        "decide se os comandos são aceitos ou levam `503`."
    )
    state: ConnectionState = Field(
        description="Último estado publicado no tópico `connection`."
    )
    since: datetime = Field(
        description="Momento (UTC) da última transição de `state`."
    )
    battery_percent: int | None = Field(
        default=None,
        description="Carga em %, do cache de `rt/lf/lowstate`. `null` se ainda "
        "não chegou estado ou se o campo não foi reconhecido.",
    )
    mode: int | None = Field(
        default=None, description="Modo atual, do cache de `rt/sportmodestate`."
    )
    sport_state_age_s: float | None = Field(
        default=None,
        description="Há quantos segundos chegou o último `rt/sportmodestate`.",
    )
    low_state_age_s: float | None = Field(
        default=None,
        description="Há quantos segundos chegou o último `rt/lf/lowstate`.",
    )
    raw: dict[str, Any] | None = Field(
        default=None,
        description="Payloads crus em cache. Presente para permitir fixar a "
        "extração de `battery_percent`/`mode` na validação com o robô ligado.",
    )
