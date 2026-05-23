import os
import httpx
import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env
load_dotenv()

from src.client import OpenWAClient

# Configuración básica de Logging profesional
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("auto-whats-backend")

# Leer configuración de variables de entorno con valores por defecto
OPENWA_API_URL = os.getenv("OPENWA_API_URL", "http://localhost:2785")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY", "super-secret-api-key")
OPENWA_SESSION_ID = os.getenv("OPENWA_SESSION_ID", "default")

# Inicializar el cliente de OpenWA
openwa_client = OpenWAClient(
    base_url=OPENWA_API_URL,
    api_key=OPENWA_API_KEY,
    session_id=OPENWA_SESSION_ID
)

app = FastAPI(
    title="WhatsApp Automation Backend",
    description="Servicio backend en Python para procesar eventos y lógica de negocio de WhatsApp.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """
    Se ejecuta al arrancar el servidor FastAPI.
    Resuelve el ID de sesión dinámico (UUID) buscando por el nombre amigable 'default'.
    """
    logger.info("Resolviendo ID de sesión de OpenWA...")
    list_url = f"{openwa_client.base_url}/api/sessions"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(list_url, headers=openwa_client.headers)
            if res.status_code == 200:
                sessions = res.json()
                for s in sessions:
                    if s.get("name") == OPENWA_SESSION_ID:
                        dynamic_id = s.get("id")
                        openwa_client.session_id = dynamic_id
                        logger.info(f"✅ ID de sesión de OpenWA resuelto con éxito: '{dynamic_id}' (nombre: '{OPENWA_SESSION_ID}')")
                        return
                logger.warning(f"⚠️ No se encontró ninguna sesión con el nombre '{OPENWA_SESSION_ID}' en OpenWA.")
            else:
                logger.error(f"⚠️ Error al listar sesiones en OpenWA (Status {res.status_code}): {res.text}")
        except Exception as e:
            logger.error(f"⚠️ No se pudo conectar con OpenWA en el arranque: {e}")

# Estructura para el payload entrante de OpenWA
class WebhookPayload(BaseModel):
    event: Optional[str] = None  # Ejemplo: "message" o "state"
    session: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

# Almacenamiento en memoria de los estados de conversación de los usuarios (chat_id -> state)
USER_STATES = {}

# ==============================================================================
# MENÚS FORMATEADOS CON RICA ESTÉTICA (MARKDOWN DE WHATSAPP)
# ==============================================================================
MENU_PRINCIPAL = """🤖 *¡Hola, {sender_name}!* Bienvenido a nuestro asistente virtual.

Por favor, selecciona una de las siguientes opciones respondiendo con su *número* o *palabra clave*:

*1️⃣ Ver Catálogo* 📦 - Explora nuestros productos y ofertas.
*2️⃣ Contactar Soporte* 🛠️ - Habla con uno de nuestros agentes en vivo.
*3️⃣ Preguntas Frecuentes* ❓ - Resuelve tus dudas al instante.

✍️ _Escribe el número correspondiente (1, 2, 3) o escribe "menú"._"""

MENU_CATALOGO = """📦 *NUESTRO CATÁLOGO DE PRODUCTOS* 📦

Explora nuestras categorías principales respondiendo con su número:
*11* - 💻 *Tecnología y Computación*
*12* - 📱 *Celulares y Accesorios*
*13* - 🎧 *Audio y Sonido*

*0️⃣ Volver al Menú Principal* 🔙"""

MENU_SOPORTE = """🛠️ *SOPORTE TÉCNICO Y CONTACTO* 🛠️

Estamos listos para ayudarte. Por favor selecciona una opción:
*21* - 💬 *Hablar con un Agente (Humano)*
*22* - 📧 *Dejar un correo de Soporte*

*0️⃣ Volver al Menú Principal* 🔙"""

MENU_FAQ = """❓ *PREGUNTAS FRECUENTES (FAQ)* ❓

Selecciona la duda que deseas resolver:
*31* - 🚚 *¿Cuáles son los tiempos de envío?*
*32* - 💳 *¿Qué métodos de pago aceptan?*
*33* - 🔄 *¿Cómo funcionan las devoluciones?*

*0️⃣ Volver al Menú Principal* 🔙"""

RESPUESTA_TEC = """💻 *TECNOLOGÍA Y COMPUTACIÓN*
Disponemos de laptops de última generación, monitores 4K y accesorios ergonómicos con descuentos del 15%.
Visita nuestra tienda para más información.

*0️⃣ Volver al Menú Principal* 🔙
*1️⃣ Volver al Catálogo* 📦"""

RESPUESTA_CEL = """📱 *CELULARES Y ACCESORIOS*
Encuentra los últimos modelos de smartphones y cargadores inalámbricos premium con envío gratis a nivel nacional.

*0️⃣ Volver al Menú Principal* 🔙
*1️⃣ Volver al Catálogo* 📦"""

RESPUESTA_AUD = """🎧 *AUDIO Y SONIDO*
Audífonos con cancelación de ruido activa y parlantes bluetooth impermeables de alta fidelidad.

*0️⃣ Volver al Menú Principal* 🔙
*1️⃣ Volver al Catálogo* 📦"""

RESPUESTA_AGENTE = """💬 *CONECTANDO CON UN AGENTE*
Tu solicitud ha sido transferida a nuestro equipo técnico. Un agente humano se pondrá en contacto contigo en este chat en los próximos 5 minutos.
¡Gracias por tu paciencia! 🕒

*0️⃣ Volver al Menú Principal* 🔙"""

RESPUESTA_CORREO = """📧 *CORREO DE SOPORTE*
Puedes escribirnos en cualquier momento a: *soporte@tuempresa.com*
Respondemos en un plazo máximo de 12 horas hábiles.

*0️⃣ Volver al Menú Principal* 🔙"""

RESPUESTA_ENVIO = """🚚 *TIEMPOS DE ENVÍO*
* Locales: Mismo día o 24 hrs.
* Nacionales: 2 a 4 días hábiles.
* Internacionales: 7 a 15 días hábiles.

*0️⃣ Volver al Menú Principal* 🔙
*3️⃣ Volver a Preguntas Frecuentes* ❓"""

RESPUESTA_PAGO = """💳 *MÉTODOS DE PAGO*
Aceptamos:
* Tarjetas de Crédito y Débito (Visa, Mastercard, AMEX).
* Transferencias bancarias.
* PayPal.
* Efectivo en puntos de pago locales.

*0️⃣ Volver al Menú Principal* 🔙
*3️⃣ Volver a Preguntas Frecuentes* ❓"""

RESPUESTA_DEVOLUCION = """🔄 *POLÍTICA DE DEVOLUCIONES*
Tienes hasta 30 días calendario desde la entrega de tu producto para solicitar una devolución gratuita si el producto presenta fallas o no es de tu agrado.

*0️⃣ Volver al Menú Principal* 🔙
*3️⃣ Volver a Preguntas Frecuentes* ❓"""

async def procesar_mensaje_asincrono(data: Dict[str, Any]):
    """
    Función de fondo para procesar el mensaje sin bloquear la respuesta HTTP al webhook.
    Soporta navegación interactiva por estados tanto para texto tradicional como para
    eventos estructurados de botones/listas.
    """
    try:
        # Extraer campos comunes de OpenWA
        body = data.get("body") or data.get("text")
        chat_id = data.get("from") or data.get("chatId")
        sender_name = data.get("sender", {}).get("pushname", "Usuario")
        is_group = data.get("isGroupMsg", False)
        
        # Soporte para clics nativos de botones y listas (enfoque híbrido compatible)
        selected_button = data.get("selectedButtonId")
        list_choice = data.get("listResponse", {}).get("rowId")
        
        if not chat_id:
            logger.warning("Mensaje recibido sin remitente ('from' o 'chatId'). Ignorando.")
            return

        # Limpiar y normalizar el cuerpo de entrada
        text_input = (body or "").strip().lower()
        
        # Registrar logs detallados de la interacción
        if selected_button:
            logger.info(f"Botón nativo presionado por '{sender_name}' ({chat_id}): '{selected_button}'")
        elif list_choice:
            logger.info(f"Lista nativa seleccionada por '{sender_name}' ({chat_id}): '{list_choice}'")
        else:
            logger.info(f"Mensaje de '{sender_name}' ({chat_id}): '{text_input}'")

        # Comandos básicos inmediatos
        if text_input in ["!ping", "ping"]:
            logger.info("Comando !ping detectado. Respondiendo...")
            await openwa_client.send_text_message(
                chat_id=chat_id,
                text=f"¡Hola {sender_name}! ¡Pong! 🏓 El backend en Python con FastAPI está en línea y funcionando perfectamente."
            )
            return

        # Comandos para desplegar o reiniciar el menú principal
        if text_input in ["!ayuda", "ayuda", "!menu", "menu", "hola", "hi", "inicio", "empezar"]:
            logger.info(f"Comando de inicio/ayuda detectado. Enviando menú principal a {chat_id}...")
            USER_STATES[chat_id] = "main_menu"
            await openwa_client.send_text_message(
                chat_id=chat_id,
                text=MENU_PRINCIPAL.format(sender_name=sender_name)
            )
            return

        # Obtener el estado actual del flujo del usuario (por defecto 'idle')
        current_state = USER_STATES.get(chat_id, "idle")

        # ----------------------------------------------------------------------
        # ENRUTADOR E INTEGRADOR DE INTERACCIONES HÍBRIDAS
        # ----------------------------------------------------------------------
        
        # Atajo global para volver al menú principal en cualquier momento
        if text_input == "0" or selected_button == "btn_menu_principal" or list_choice == "row_menu_principal":
            USER_STATES[chat_id] = "main_menu"
            await openwa_client.send_text_message(
                chat_id=chat_id,
                text=MENU_PRINCIPAL.format(sender_name=sender_name)
            )
            return

        # 1. Flujo desde Menú Principal
        if current_state == "main_menu":
            if text_input == "1" or selected_button == "btn_catalogo" or list_choice == "row_catalogo" or "catálogo" in text_input:
                USER_STATES[chat_id] = "catalog"
                await openwa_client.send_text_message(chat_id=chat_id, text=MENU_CATALOGO)
            elif text_input == "2" or selected_button == "btn_soporte" or list_choice == "row_soporte" or "soporte" in text_input:
                USER_STATES[chat_id] = "support"
                await openwa_client.send_text_message(chat_id=chat_id, text=MENU_SOPORTE)
            elif text_input == "3" or selected_button == "btn_faq" or list_choice == "row_faq" or "preguntas" in text_input:
                USER_STATES[chat_id] = "faq"
                await openwa_client.send_text_message(chat_id=chat_id, text=MENU_FAQ)
            else:
                # Opción no reconocida en el menú principal
                await openwa_client.send_text_message(
                    chat_id=chat_id,
                    text=f"⚠️ Opción no reconocida.\n\n" + MENU_PRINCIPAL.format(sender_name=sender_name)
                )
            return

        # 2. Flujo desde Catálogo
        elif current_state == "catalog":
            if text_input == "11" or list_choice == "row_tec" or "tecnología" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_TEC)
            elif text_input == "12" or list_choice == "row_cel" or "celulares" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_CEL)
            elif text_input == "13" or list_choice == "row_aud" or "audio" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_AUD)
            elif text_input == "1":
                await openwa_client.send_text_message(chat_id=chat_id, text=MENU_CATALOGO)
            else:
                await openwa_client.send_text_message(
                    chat_id=chat_id,
                    text=f"⚠️ Opción de catálogo no reconocida.\n\n" + MENU_CATALOGO
                )
            return

        # 3. Flujo desde Soporte
        elif current_state == "support":
            if text_input == "21" or list_choice == "row_agente" or "agente" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_AGENTE)
            elif text_input == "22" or list_choice == "row_correo" or "correo" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_CORREO)
            else:
                await openwa_client.send_text_message(
                    chat_id=chat_id,
                    text=f"⚠️ Opción de soporte no reconocida.\n\n" + MENU_SOPORTE
                )
            return

        # 4. Flujo desde FAQ
        elif current_state == "faq":
            if text_input == "31" or list_choice == "row_envio" or "envío" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_ENVIO)
            elif text_input == "32" or list_choice == "row_pago" or "pago" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_PAGO)
            elif text_input == "33" or list_choice == "row_devolucion" or "devolución" in text_input:
                await openwa_client.send_text_message(chat_id=chat_id, text=RESPUESTA_DEVOLUCION)
            elif text_input == "3":
                await openwa_client.send_text_message(chat_id=chat_id, text=MENU_FAQ)
            else:
                await openwa_client.send_text_message(
                    chat_id=chat_id,
                    text=f"⚠️ Opción de FAQ no reconocida.\n\n" + MENU_FAQ
                )
            return

        # 5. Respuesta fallback (fuera de menús activos)
        else:
            USER_STATES[chat_id] = "main_menu"
            await openwa_client.send_text_message(
                chat_id=chat_id,
                text=f"🤖 Hola *{sender_name}*, no reconozco ese mensaje.\n\n" + MENU_PRINCIPAL.format(sender_name=sender_name)
            )

    except Exception as e:
        logger.error(f"Error procesando el mensaje asíncronamente: {e}", exc_info=True)



@app.get("/")
async def root():
    """
    Ruta raíz para verificar la salud del backend.
    """
    return {
        "status": "healthy",
        "service": "WhatsApp Automation Backend",
        "configured_openwa_url": OPENWA_API_URL
    }


@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    Endpoint principal de Webhook que recibe eventos de OpenWA.
    """
    logger.info(f"Evento recibido en el Webhook: {payload.event}")
    
    # Si el evento es un mensaje entrante (ejemplo: 'message' o 'message.received')
    if payload.event in ["message", "onMessage", "message.received"]:
        if payload.data:
            # Enviar el procesamiento a segundo plano para retornar 200 OK de inmediato a OpenWA
            background_tasks.add_task(procesar_mensaje_asincrono, payload.data)
            return {"status": "accepted", "message": "Mensaje en cola para procesamiento"}
        else:
            logger.warning("Evento de mensaje recibido pero 'data' está vacío.")
            raise HTTPException(status_code=400, detail="Data vacía en evento de mensaje")

    return {"status": "ignored", "event": payload.event}


def start():
    """
    Punto de entrada para ejecutar el servidor con 'uv run auto-whats'.
    """
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Iniciando el servidor FastAPI en el puerto {port} con auto-reload...")
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True)
