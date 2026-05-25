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
from src.database import Base, engine, SessionLocal
from src.models import UserSession, MessageHistory
from src.agent import get_ai_response
from src.agent_graph import bot_graph, BotState
from src.cache import get_cached_state, set_cached_state
from sqlalchemy.future import select
from langserve import add_routes
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import HumanMessage

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
ADMIN_PHONE_NUMBER = os.getenv("ADMIN_PHONE_NUMBER", None)


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

# ==============================================================================
# LANGSERVE: Exposición del Agente de LangGraph como API REST con Playground
# Accede al chat interactivo en: http://localhost:8000/agent/playground/
# ==============================================================================
async def invoke_bot(user_input: str) -> str:
    """
    Wrapper asíncrono que conecta LangServe (entrada string simple)
    con el grafo conversacional de LangGraph.
    Retorna el último mensaje generado por el bot.
    """
    state: BotState = {
        "messages": [HumanMessage(content=user_input)],
        "current_menu": "idle",
        "user_input": user_input.strip().lower()
    }
    result = await bot_graph.ainvoke(state)
    # Extraer el último mensaje generado por el bot (AIMessage)
    last_message = result["messages"][-1]
    return last_message.content

add_routes(
    app,
    RunnableLambda(invoke_bot),
    path="/agent",
)


@app.on_event("startup")
async def startup_event():
    """
    Se ejecuta al arrancar el servidor FastAPI.
    1. Inicializa tablas en PostgreSQL.
    2. Resuelve el ID de sesión dinámico de OpenWA.
    3. Registra automáticamente el webhook en OpenWA (sin intervención manual).
    """
    # 1. Crear tablas en Postgres de forma automática si no existen
    logger.info("Verificando y creando tablas de base de datos asíncronas en PostgreSQL...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Tablas de base de datos creadas/verificadas con éxito.")
    except Exception as e:
        logger.error(f"❌ Error al inicializar tablas en PostgreSQL: {e}")

    # 2. Resolver ID de sesión de OpenWA
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
                        break
                else:
                    logger.warning(f"⚠️ No se encontró ninguna sesión con el nombre '{OPENWA_SESSION_ID}' en OpenWA.")
                    return
            else:
                logger.error(f"⚠️ Error al listar sesiones en OpenWA (Status {res.status_code}): {res.text}")
                return
        except Exception as e:
            logger.error(f"⚠️ No se pudo conectar con OpenWA en el arranque: {e}")
            return

    # 3. Registro automático del Webhook en OpenWA
    # Esto garantiza que el webhook siempre esté activo sin importar cuántas
    # veces se reinicien los contenedores.
    await _register_webhook_on_startup(openwa_client.session_id)


async def _register_webhook_on_startup(session_id: str):
    """
    Limpia los webhooks existentes de la sesión y registra uno nuevo apuntando
    a este backend. Se ejecuta automáticamente en cada arranque del servidor.
    La URL destino se puede sobreescribir con la variable WEBHOOK_SELF_URL.
    """
    webhook_url = os.getenv("WEBHOOK_SELF_URL", "http://host.docker.internal:8000/webhook")
    webhook_events = ["message.received", "session.status"]

    logger.info(f"🔗 Configurando webhook automático -> {webhook_url}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            list_wh_url = f"{openwa_client.base_url}/api/sessions/{session_id}/webhooks"

            # 3a. Eliminar webhooks anteriores de la sesión para evitar duplicados
            res = await client.get(list_wh_url, headers=openwa_client.headers)
            if res.status_code == 200:
                for wh in res.json():
                    wh_id = wh.get("id")
                    del_res = await client.delete(
                        f"{openwa_client.base_url}/api/sessions/{session_id}/webhooks/{wh_id}",
                        headers=openwa_client.headers
                    )
                    logger.info(f"  🗑️  Webhook anterior eliminado: {wh_id} (status {del_res.status_code})")

            # 3b. Registrar el nuevo webhook
            payload = {"url": webhook_url, "events": webhook_events}
            reg_res = await client.post(list_wh_url, headers=openwa_client.headers, json=payload)

            if reg_res.status_code == 201:
                data = reg_res.json()
                logger.info(
                    f"✅ Webhook registrado automáticamente: "
                    f"ID={data.get('id')} | URL={data.get('url')} | Eventos={data.get('events')}"
                )
            else:
                logger.error(f"❌ Error al registrar webhook (Status {reg_res.status_code}): {reg_res.text}")

        except Exception as e:
            logger.error(f"❌ No se pudo registrar el webhook automáticamente: {e}")

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
    eventos estructurados de botones/listas, persistidos en base de datos PostgreSQL,
    con soporte conversacional de Inteligencia Artificial (Gemini).
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
        raw_input = body or selected_button or list_choice or ""
        
        # Registrar logs detallados de la interacción
        if selected_button:
            logger.info(f"Botón nativo presionado por '{sender_name}' ({chat_id}): '{selected_button}'")
        elif list_choice:
            logger.info(f"Lista nativa seleccionada por '{sender_name}' ({chat_id}): '{list_choice}'")
        else:
            logger.info(f"Mensaje de '{sender_name}' ({chat_id}): '{text_input}'")

        # ----------------------------------------------------------------------
        # PERSISTENCIA HÍBRIDA DE ESTADOS (REDIS CACHE + POSTGRESQL)
        # ----------------------------------------------------------------------
        async with SessionLocal() as db:
            # 1. Intentar obtener el estado actual desde el caché de Redis (RAM)
            current_state = await get_cached_state(chat_id)
            
            # Buscar o crear la sesión de usuario en PostgreSQL para consistencia y auditoría
            session_query = select(UserSession).where(UserSession.chat_id == chat_id)
            session_result = await db.execute(session_query)
            db_session = session_result.scalar_one_or_none()
            
            if not db_session:
                logger.info(f"🆕 Creando nueva sesión asíncrona para el usuario {chat_id} en PostgreSQL...")
                db_session = UserSession(chat_id=chat_id, current_state="idle")
                db.add(db_session)
                await db.commit()
                await db.refresh(db_session)
            
            # 1.1. Auto-liberación por inactividad de sesión humana (TTL de 60 minutos)
            from datetime import datetime
            if db_session.current_state == "human_agent" and db_session.updated_at:
                delta = datetime.utcnow() - db_session.updated_at
                if delta.total_seconds() > 3600:  # 60 minutos
                    logger.info(f"⏰ [Inactividad] La sesión de soporte en vivo para {chat_id} superó los 60 minutos. Reactivando el bot...")
                    db_session.current_state = "idle"
                    await db.commit()
                    await set_cached_state(chat_id, "idle")
                    current_state = "idle"
            
            # Si hubo un Cache Miss (no está en Redis), cargamos desde PostgreSQL y guardamos en Redis
            if current_state is None:
                current_state = db_session.current_state
                logger.info(f"🔄 Sincronizando estado '{current_state}' desde Postgres hacia el caché de Redis...")
                await set_cached_state(chat_id, current_state)
            
            # 2. Registrar el mensaje entrante del usuario en el historial relacional
            user_msg = MessageHistory(chat_id=chat_id, role="user", body=str(raw_input))
            db.add(user_msg)
            await db.commit()
            
            # 3. Cargar el historial reciente de mensajes (últimos 10) para el contexto de la IA
            history_query = (
                select(MessageHistory)
                .where(MessageHistory.chat_id == chat_id)
                .order_by(MessageHistory.timestamp.asc())
            )
            history_result = await db.execute(history_query)
            db_history = history_result.scalars().all()

            # Helper para registrar respuesta enviada por el bot y guardarla en DB y Redis
            async def responder_y_guardar(text_response: str, new_state: str = None):
                # Guardar en base de datos la respuesta de la app/asistente
                bot_msg = MessageHistory(chat_id=chat_id, role="assistant", body=text_response)
                db.add(bot_msg)
                
                # Actualizar el estado si es necesario en ambas capas (Caché RAM + DB Relacional)
                if new_state:
                    # Actualizar en Redis
                    await set_cached_state(chat_id, new_state)
                    # Actualizar en PostgreSQL
                    db_session.current_state = new_state
                
                await db.commit()
                
                # Enviar físicamente por WhatsApp a través del cliente OpenWA
                await openwa_client.send_text_message(chat_id=chat_id, text=text_response)

            # 2.5. Control de Silencio para Intervención Humana (Human Takeover / Silencio del Bot)
            if current_state == "human_agent":
                # Si el usuario escribe "!menu" o "!ayuda", libera la sesión para regresar al bot automático
                if text_input in ["!menu", "!ayuda", "menu", "ayuda"]:
                    logger.info(f"🔓 Cliente {chat_id} solicitó salir de atención humana. Devolviendo control al bot...")
                    await responder_y_guardar(MENU_PRINCIPAL.format(sender_name=sender_name), new_state="main_menu")
                    return
                
                # Si no es un comando de liberación, entra en silencio absoluto. Guardamos en DB para el historial y retornamos.
                logger.info(f"🤫 [Takeover Activo] Cliente {chat_id} en atención humana. Bot silenciado.")
                return

            # Comandos básicos inmediatos
            if text_input in ["!ping", "ping"]:
                logger.info("Comando !ping detectado. Respondiendo...")
                await responder_y_guardar(
                    f"¡Hola {sender_name}! ¡Pong! 🏓 El backend asíncrono con PostgreSQL está en línea y funcionando perfectamente."
                )
                return

            # Comandos para desplegar o reiniciar el menú principal
            if text_input in ["!ayuda", "ayuda", "!menu", "menu", "hola", "hi", "inicio", "empezar"]:
                logger.info(f"Comando de inicio/ayuda detectado. Enviando menú principal a {chat_id}...")
                await responder_y_guardar(MENU_PRINCIPAL.format(sender_name=sender_name), new_state="main_menu")
                return

            # Atajo global para volver al menú principal en cualquier momento
            if text_input == "0" or selected_button == "btn_menu_principal" or list_choice == "row_menu_principal":
                logger.info("Atajo global recibido. Volviendo al menú principal...")
                await responder_y_guardar(MENU_PRINCIPAL.format(sender_name=sender_name), new_state="main_menu")
                return

            # ----------------------------------------------------------------------
            # ENRUTADOR E INTEGRADOR DE INTERACCIONES HÍBRIDAS (ESTÁTICO / DINÁMICO)
            # ----------------------------------------------------------------------
            
            # 1. Flujo desde Menú Principal
            if current_state == "main_menu":
                if text_input == "1" or selected_button == "btn_catalogo" or list_choice == "row_catalogo" or "catálogo" in text_input:
                    await responder_y_guardar(MENU_CATALOGO, new_state="catalog")
                    return
                elif text_input == "2" or selected_button == "btn_soporte" or list_choice == "row_soporte" or "soporte" in text_input:
                    await responder_y_guardar(MENU_SOPORTE, new_state="support")
                    return
                elif text_input == "3" or selected_button == "btn_faq" or list_choice == "row_faq" or "preguntas" in text_input:
                    await responder_y_guardar(MENU_FAQ, new_state="faq")
                    return

            # 2. Flujo desde Catálogo
            elif current_state == "catalog":
                if text_input == "11" or list_choice == "row_tec" or "tecnología" in text_input:
                    await responder_y_guardar(RESPUESTA_TEC)
                    return
                elif text_input == "12" or list_choice == "row_cel" or "celulares" in text_input:
                    await responder_y_guardar(RESPUESTA_CEL)
                    return
                elif text_input == "13" or list_choice == "row_aud" or "audio" in text_input:
                    await responder_y_guardar(RESPUESTA_AUD)
                    return
                elif text_input == "1":
                    await responder_y_guardar(MENU_CATALOGO)
                    return

            # 3. Flujo desde Soporte
            elif current_state == "support":
                if text_input == "21" or list_choice == "row_agente" or "agente" in text_input:
                    # 1. Responder al cliente de forma amigable y pasarlo al estado human_agent
                    await responder_y_guardar(RESPUESTA_AGENTE, new_state="human_agent")
                    
                    # 2. Enviar alerta en tiempo real al teléfono del Administrador
                    if ADMIN_PHONE_NUMBER:
                        alerta_msg = (
                            f"🤖 *[Alerta de Soporte en Vivo]*\n\n"
                            f"El cliente *{sender_name}* ({chat_id}) ha solicitado asistencia humana en este chat.\n\n"
                            f"👉 _Por favor, abre WhatsApp Web o tu celular para responderle. El bot ha sido suspendido y silenciado para esta conversación._\n\n"
                            f"💡 _Para reactivar el bot automático, tú o el cliente pueden escribir *!menu* en cualquier momento._"
                        )
                        try:
                            logger.info(f"📢 Enviando alerta de soporte al Administrador: {ADMIN_PHONE_NUMBER}")
                            await openwa_client.send_text_message(chat_id=ADMIN_PHONE_NUMBER, text=alerta_msg)
                        except Exception as e:
                            logger.error(f"❌ Error al enviar alerta de soporte al Administrador: {e}")
                    return
                elif text_input == "22" or list_choice == "row_correo" or "correo" in text_input:
                    await responder_y_guardar(RESPUESTA_CORREO)
                    return

            # 4. Flujo desde FAQ
            elif current_state == "faq":
                if text_input == "31" or list_choice == "row_envio" or "envío" in text_input:
                    await responder_y_guardar(RESPUESTA_ENVIO)
                    return
                elif text_input == "32" or list_choice == "row_pago" or "pago" in text_input:
                    await responder_y_guardar(RESPUESTA_PAGO)
                    return
                elif text_input == "33" or list_choice == "row_devolucion" or "devolución" in text_input:
                    await responder_y_guardar(RESPUESTA_DEVOLUCION)
                    return
                elif text_input == "3":
                    await responder_y_guardar(MENU_FAQ)
                    return

            # ----------------------------------------------------------------------
            # FALLBACK DE LENGUAJE NATURAL: INVOCAR INTELIGENCIA ARTIFICIAL (GEMINI)
            # ----------------------------------------------------------------------
            logger.info(f"Interacción libre en lenguaje natural detectada para {chat_id}. Invocando Gemini...")
            ai_reply = await get_ai_response(user_message=str(body or ""), db_history=db_history)
            
            # Responder al cliente con la respuesta de la IA
            await responder_y_guardar(ai_reply)

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
