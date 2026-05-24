import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Asegurar que el directorio raíz esté en el PATH para importar de src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Evitar llamadas reales a base de datos y clientes en la importación de main
with patch("src.database.engine"), \
     patch("src.database.SessionLocal"), \
     patch("src.client.OpenWAClient"):
    from src.main import app, procesar_mensaje_asincrono, MENU_PRINCIPAL, MENU_CATALOGO, RESPUESTA_TEC


@pytest.fixture
def client():
    """
    Cliente de pruebas de FastAPI con mocks aplicados a las llamadas del startup.
    """
    # Mockear las llamadas asíncronas hechas en startup_event de src/main
    mock_conn = AsyncMock()
    mock_engine_begin = MagicMock()
    mock_engine_begin.__aenter__.return_value = mock_conn

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"name": "default", "id": "uuid-mock-session-123"}]

    with patch("src.main.engine.begin", return_value=mock_engine_begin), \
         patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_response)):
        with TestClient(app) as test_client:
            yield test_client


def test_root_endpoint(client):
    """
    Verifica que el endpoint raíz '/' retorne la salud del servicio correctamente.
    """
    response = client.get("/")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "healthy"
    assert json_data["service"] == "WhatsApp Automation Backend"


def test_receive_webhook_ignored_event(client):
    """
    Verifica que eventos no relacionados a mensajes (ej. 'session.status') sean ignorados.
    """
    payload = {
        "event": "session.status",
        "session": "default",
        "data": {"status": "connected"}
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "ignored"
    assert json_data["event"] == "session.status"


def test_receive_webhook_empty_data(client):
    """
    Verifica que eventos de mensaje pero con 'data' vacío lancen un error 400.
    """
    payload = {
        "event": "message.received",
        "session": "default",
        "data": None
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 400
    assert "Data vacía en evento de mensaje" in response.json()["detail"]


def test_receive_webhook_success(client):
    """
    Verifica que un mensaje válido sea aceptado y encolado en BackgroundTasks.
    """
    payload = {
        "event": "message.received",
        "session": "default",
        "data": {
            "from": "34600000000@c.us",
            "body": "Hola",
            "sender": {"pushname": "Test User"}
        }
    }
    # Mockear procesar_mensaje_asincrono para que no intente ejecutar lógica asíncrona real de DB aquí
    with patch("src.main.procesar_mensaje_asincrono") as mock_process:
        response = client.post("/webhook", json=payload)
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "accepted"
        assert "cola para procesamiento" in json_data["message"]


@pytest.mark.asyncio
async def test_procesar_mensaje_ping():
    """
    Prueba que el comando 'ping' sea procesado y retorne una respuesta Pong.
    """
    data = {
        "from": "34600000000@c.us",
        "body": "ping",
        "sender": {"pushname": "Usuario Test"}
    }

    # 1. Crear Mocks para la sesión de base de datos
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    
    # Mockear UserSession
    mock_user_session = MagicMock()
    mock_user_session.chat_id = "34600000000@c.us"
    mock_user_session.current_state = "idle"

    # Configurar el retorno de execute() para UserSession
    mock_session_result = MagicMock()
    mock_session_result.scalar_one_or_none.return_value = mock_user_session

    # Configurar el retorno de execute() para MessageHistory
    mock_history_result = MagicMock()
    mock_history_result.scalars().all.return_value = []

    # Registrar retornos secuenciales de db.execute()
    # Primera llamada: Buscar sesión
    # Segunda llamada: Cargar historial de mensajes
    mock_db.execute.side_effect = [mock_session_result, mock_history_result]

    # Crear mock de SessionLocal context manager
    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Mockear openwa_client y sus métodos de envío
    mock_openwa = AsyncMock()

    with patch("src.main.SessionLocal", mock_session_local), \
         patch("src.main.openwa_client", mock_openwa):
        
        await procesar_mensaje_asincrono(data)

        # Verificar que se envió la respuesta Pong a través de openwa_client
        mock_openwa.send_text_message.assert_called_once()
        called_args = mock_openwa.send_text_message.call_args[1]
        assert called_args["chat_id"] == "34600000000@c.us"
        assert "Pong!" in called_args["text"]


@pytest.mark.asyncio
async def test_procesar_mensaje_menu_principal():
    """
    Prueba que el comando 'menu' retorne el menú principal y actualice el estado a 'main_menu'.
    """
    data = {
        "from": "34600000000@c.us",
        "body": "menu",
        "sender": {"pushname": "Usuario Test"}
    }

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    
    # Mockear UserSession
    mock_user_session = MagicMock()
    mock_user_session.chat_id = "34600000000@c.us"
    mock_user_session.current_state = "idle"

    mock_session_result = MagicMock()
    mock_session_result.scalar_one_or_none.return_value = mock_user_session

    mock_history_result = MagicMock()
    mock_history_result.scalars().all.return_value = []

    mock_db.execute.side_effect = [mock_session_result, mock_history_result]

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    mock_openwa = AsyncMock()

    with patch("src.main.SessionLocal", mock_session_local), \
         patch("src.main.openwa_client", mock_openwa):
        
        await procesar_mensaje_asincrono(data)

        # Verificar que se actualizó el estado a 'main_menu' en el objeto de sesión
        assert mock_user_session.current_state == "main_menu"
        
        # Verificar que se envió el menú principal
        mock_openwa.send_text_message.assert_called_once()
        called_args = mock_openwa.send_text_message.call_args[1]
        assert "Bienvenido a nuestro asistente virtual" in called_args["text"]


@pytest.mark.asyncio
async def test_procesar_navegacion_menu():
    """
    Prueba que estando en estado 'main_menu', ingresar '1' envíe el menú de catálogo y cambie el estado a 'catalog'.
    """
    data = {
        "from": "34600000000@c.us",
        "body": "1",
        "sender": {"pushname": "Usuario Test"}
    }

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    
    # Mockear UserSession (actualmente en main_menu)
    mock_user_session = MagicMock()
    mock_user_session.chat_id = "34600000000@c.us"
    mock_user_session.current_state = "main_menu"

    mock_session_result = MagicMock()
    mock_session_result.scalar_one_or_none.return_value = mock_user_session

    mock_history_result = MagicMock()
    mock_history_result.scalars().all.return_value = []

    mock_db.execute.side_effect = [mock_session_result, mock_history_result]

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    mock_openwa = AsyncMock()

    with patch("src.main.SessionLocal", mock_session_local), \
         patch("src.main.openwa_client", mock_openwa):
        
        await procesar_mensaje_asincrono(data)

        # Verificar que el nuevo estado es 'catalog'
        assert mock_user_session.current_state == "catalog"
        
        # Verificar que se envió el catálogo
        mock_openwa.send_text_message.assert_called_once()
        called_args = mock_openwa.send_text_message.call_args[1]
        assert "NUESTRO CATÁLOGO DE PRODUCTOS" in called_args["text"]


@pytest.mark.asyncio
async def test_fallback_inteligencia_artificial():
    """
    Prueba que una consulta libre invoque a Gemini y responda exitosamente con IA.
    """
    data = {
        "from": "34600000000@c.us",
        "body": "¿Tienen soporte para integración de bots?",
        "sender": {"pushname": "Usuario Test"}
    }

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    
    # Mockear UserSession (estado idle/libre)
    mock_user_session = MagicMock()
    mock_user_session.chat_id = "34600000000@c.us"
    mock_user_session.current_state = "idle"

    mock_session_result = MagicMock()
    mock_session_result.scalar_one_or_none.return_value = mock_user_session

    mock_history_result = MagicMock()
    mock_history_result.scalars().all.return_value = []

    mock_db.execute.side_effect = [mock_session_result, mock_history_result]

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    mock_openwa = AsyncMock()
    
    # Mock de respuesta de Gemini
    mock_get_ai_response = AsyncMock(return_value="Claro que sí, contamos con soporte técnico experto para bots.")

    with patch("src.main.SessionLocal", mock_session_local), \
         patch("src.main.openwa_client", mock_openwa), \
         patch("src.main.get_ai_response", mock_get_ai_response):
        
        await procesar_mensaje_asincrono(data)

        # Verificar que get_ai_response fue invocado
        mock_get_ai_response.assert_called_once()
        
        # Verificar que se envió la respuesta del AI a través del cliente de OpenWA
        mock_openwa.send_text_message.assert_called_once()
        called_args = mock_openwa.send_text_message.call_args[1]
        assert "soporte técnico experto para bots" in called_args["text"]
