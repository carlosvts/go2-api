"""Testes do estado da conexão publicado aos consumidores."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_robot
from app.main import create_app
from app.robot import ConnectionState, RobotConnection


def _escutar(robot: RobotConnection) -> list[dict[str, str]]:
    recebidas: list[dict[str, str]] = []
    robot.subscribe_connection(recebidas.append)
    return recebidas


def _usar_conexao(monkeypatch: pytest.MonkeyPatch, conn) -> None:
    monkeypatch.setattr(
        "app.robot.UnitreeWebRTCConnection", lambda *args, **kwargs: conn
    )


# ─── Transições ────────────────────────────────────────────────────────────


async def test_estado_inicial_e_disconnected(offline_robot: RobotConnection) -> None:
    assert offline_robot.connection_state is ConnectionState.disconnected


async def test_connect_publica_connected(
    settings: Settings, fake_conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    _usar_conexao(monkeypatch, fake_conn)
    robot = RobotConnection(settings)
    recebidas = _escutar(robot)

    await robot.connect()

    assert recebidas == [{"state": "connected", "reason": "connected"}]
    assert robot.connection_state is ConnectionState.connected


async def test_connect_que_falha_mantem_disconnected(
    settings: Settings, fake_conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def falha() -> None:
        raise ConnectionError("robô desligado")

    fake_conn.connect = falha
    _usar_conexao(monkeypatch, fake_conn)
    robot = RobotConnection(settings)
    recebidas = _escutar(robot)

    with pytest.raises(ConnectionError):
        await robot.connect()

    assert robot.connection_state is ConnectionState.disconnected
    assert recebidas == []


@pytest.mark.parametrize("pc_state", ["failed", "closed", "disconnected"])
async def test_queda_do_pc_publica_disconnected(
    connected_robot: RobotConnection, fake_conn, pc_state: str
) -> None:
    recebidas = _escutar(connected_robot)

    fake_conn.pc.set_state(pc_state)

    assert recebidas == [{"state": "disconnected", "reason": pc_state}]
    assert connected_robot.connection_state is ConnectionState.disconnected


async def test_eventos_repetidos_publicam_uma_vez(
    connected_robot: RobotConnection, fake_conn
) -> None:
    recebidas = _escutar(connected_robot)

    fake_conn.pc.set_state("failed")
    fake_conn.pc.set_state("failed")
    fake_conn.pc.set_state("closed")  # mesmo estado publicado, outro motivo

    assert recebidas == [{"state": "disconnected", "reason": "failed"}]


async def test_estados_transitorios_nao_publicam(
    connected_robot: RobotConnection, fake_conn
) -> None:
    recebidas = _escutar(connected_robot)

    fake_conn.pc.set_state("connecting")
    fake_conn.pc.set_state("new")

    assert recebidas == []


async def test_volta_para_connected_publica_de_novo(
    connected_robot: RobotConnection, fake_conn
) -> None:
    recebidas = _escutar(connected_robot)

    fake_conn.pc.set_state("disconnected")
    fake_conn.pc.set_state("connected")

    assert [m["state"] for m in recebidas] == ["disconnected", "connected"]


async def test_disconnect_publica_disconnected(
    connected_robot: RobotConnection,
) -> None:
    recebidas = _escutar(connected_robot)

    await connected_robot.disconnect()

    assert recebidas == [{"state": "disconnected", "reason": "closed"}]


async def test_listener_com_erro_nao_derruba_os_outros(
    connected_robot: RobotConnection, fake_conn
) -> None:
    def quebra(_: dict[str, str]) -> None:
        raise RuntimeError

    connected_robot.subscribe_connection(quebra)
    recebidas = _escutar(connected_robot)

    fake_conn.pc.set_state("failed")

    assert len(recebidas) == 1


async def test_since_muda_so_na_transicao(
    connected_robot: RobotConnection, fake_conn
) -> None:
    fake_conn.pc.set_state("failed")
    since = connected_robot.connection_since

    fake_conn.pc.set_state("failed")

    assert connected_robot.connection_since == since


# ─── /status ───────────────────────────────────────────────────────────────


@pytest.fixture
def client_for(settings: Settings) -> Iterator[Callable[[RobotConnection], TestClient]]:
    def _make(robot: RobotConnection) -> TestClient:
        app = create_app(settings)
        app.dependency_overrides[get_robot] = lambda: robot
        return TestClient(app)

    yield _make


async def test_status_reflete_estado_conectado(
    connected_robot: RobotConnection, client_for
) -> None:
    corpo = client_for(connected_robot).get("/status").json()

    assert corpo["connected"] is True
    assert corpo["state"] == "connected"
    assert datetime.fromisoformat(corpo["since"]) == connected_robot.connection_since


async def test_status_apos_queda_responde_200_disconnected(
    connected_robot: RobotConnection, fake_conn, client_for
) -> None:
    fake_conn.pc.set_state("failed")
    fake_conn.isConnected = False

    resposta = client_for(connected_robot).get("/status")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["connected"] is False
    assert corpo["state"] == "disconnected"


def test_status_robo_desligado_na_subida_responde_disconnected(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem override: a app sobe, o `connect()` falha e `/status` segue 200."""

    class Inacessivel:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def connect(self) -> None:
            raise ConnectionError("robô desligado")

    monkeypatch.setattr("app.robot.UnitreeWebRTCConnection", Inacessivel)
    app = create_app(settings.model_copy(update={"connect_on_startup": True}))

    with TestClient(app) as client:
        resposta = client.get("/status")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["connected"] is False
    assert corpo["state"] == "disconnected"
    assert corpo["since"] is not None
