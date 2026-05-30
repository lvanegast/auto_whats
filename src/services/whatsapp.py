import os
import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

class OpenWAClient:
    """
    Cliente asíncrono robusto para interactuar con la API de OpenWA.
    """
    def __init__(self, base_url: str, api_key: str, session_id: str = "default"):
        """
        Inicializa el cliente de OpenWA.
        
        :param base_url: URL base del gateway de OpenWA (ej: http://localhost:2785)
        :param api_key: Clave de API para autenticación (X-API-Key)
        :param session_id: ID de la sesión activa en OpenWA (por defecto "default")
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session_id = session_id
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }

    async def check_status(self) -> Dict[str, Any]:
        """
        Verifica el estado del gateway y de la sesión activa.
        """
        url = f"{self.base_url}/api/sessions/{self.session_id}/status"
        print(f"DEBUG: calling status URL: '{url}'")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Error de estado HTTP al verificar sesión: {e.response.status_code} - {e.response.text}")
                raise e
            except httpx.RequestError as e:
                logger.error(f"Error de conexión al conectar con OpenWA: {e}")
                raise e

    async def send_text_message(self, chat_id: str, text: str) -> Dict[str, Any]:
        """
        Envía un mensaje de texto simple a un chat específico.
        
        :param chat_id: Identificador del chat (ej: 34600000000@c.us o ID de grupo)
        :param text: Contenido del mensaje de texto
        """
        url = f"{self.base_url}/api/sessions/{self.session_id}/messages/send-text"
        payload = {
            "chatId": chat_id,
            "text": text
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                logger.info(f"Enviando mensaje a {chat_id} a través de OpenWA...")
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info("Mensaje enviado exitosamente.")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Error de OpenWA al enviar mensaje: {e.response.status_code} - {e.response.text}")
                raise e
            except httpx.RequestError as e:
                logger.error(f"Error de conexión al intentar enviar mensaje: {e}")
                raise e

    async def send_buttons(self, chat_id: str, text: str, buttons: list[dict]) -> Dict[str, Any]:
        """
        Envía un mensaje con botones interactivos (máximo 3 botones).
        
        :param chat_id: Identificador del chat (ej: 34600000000@c.us)
        :param text: Texto principal del mensaje
        :param buttons: Lista de botones (máximo 3), ej: [{"id": "btn_1", "text": "Opción 1"}]
        """
        logger.warning(
            "⚠️ Atención: Estás intentando enviar botones nativos. En muchas versiones de la API "
            "no oficial de WhatsApp Web (OpenWA), los botones nativos han sido deshabilitados por WhatsApp. "
            "Se recomienda usar menús textuales interactivos."
        )
        url = f"{self.base_url}/api/sessions/{self.session_id}/messages/send-buttons"
        payload = {
            "chatId": chat_id,
            "text": text,
            "buttons": buttons
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                logger.info(f"Enviando botones a {chat_id} a través de OpenWA...")
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info("Mensaje con botones enviado exitosamente.")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Error de OpenWA al enviar botones: {e.response.status_code} - {e.response.text}")
                raise e
            except httpx.RequestError as e:
                logger.error(f"Error de conexión al intentar enviar botones: {e}")
                raise e

# Inicialización única de configuración compartida
OPENWA_API_URL = os.getenv("OPENWA_API_URL", "http://localhost:2785")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY", "super-secret-api-key")
OPENWA_SESSION_ID = os.getenv("OPENWA_SESSION_ID", "default")
ADMIN_PHONE_NUMBER = os.getenv("ADMIN_PHONE_NUMBER", None)

openwa_client = OpenWAClient(
    base_url=OPENWA_API_URL,
    api_key=OPENWA_API_KEY,
    session_id=OPENWA_SESSION_ID
)
