"""
webhook_router.py — Router de Webhooks para interactuar con OpenWA Gateway.
Procesa mensajes entrantes, maneja los estados de usuario en caché y DB,
y ejecuta el flujo conversacional de LangGraph en segundo plano.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.future import select
from langchain_core.messages import HumanMessage, AIMessage

from src.core.database import SessionLocal
from src.core.cache import get_cached_state, set_cached_state
from src.models.domain import UserSession, MessageHistory
from src.services.whatsapp import openwa_client, ADMIN_PHONE_NUMBER
from src.services.bot_engine import bot_graph

logger = logging.getLogger("auto-whats-webhook")

router = APIRouter(tags=["webhook"])


# Estructura para el payload entrante de OpenWA
class WebhookPayload(BaseModel):
    event: Optional[str] = None  # Ejemplo: "message" o "state"
    session: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


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
        data.get("isGroupMsg", False)

        # Soporte para clics nativos de botones y listas (enfoque híbrido compatible)
        selected_button = data.get("selectedButtonId")
        list_choice = data.get("listResponse", {}).get("rowId")

        if not chat_id:
            logger.warning(
                "Mensaje recibido sin remitente ('from' o 'chatId'). Ignorando."
            )
            return

        # Limpiar y normalizar el cuerpo de entrada
        text_input = (body or "").strip().lower()
        raw_input = body or selected_button or list_choice or ""

        # Registrar logs detallados de la interacción
        if selected_button:
            logger.info(
                f"Botón nativo presionado por '{sender_name}' ({chat_id}): '{selected_button}'"
            )
        elif list_choice:
            logger.info(
                f"Lista nativa seleccionada por '{sender_name}' ({chat_id}): '{list_choice}'"
            )
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
                logger.info(
                    f"🆕 Creando nueva sesión asíncrona para el usuario {chat_id} en PostgreSQL..."
                )
                db_session = UserSession(chat_id=chat_id, current_state="idle")
                db.add(db_session)
                await db.commit()
                await db.refresh(db_session)

            # 1.1. Auto-liberación por inactividad de sesión humana (TTL de 60 minutos)
            if db_session.current_state == "human_agent" and db_session.updated_at:
                delta = datetime.utcnow() - db_session.updated_at
                if delta.total_seconds() > 3600:  # 60 minutos
                    logger.info(
                        f"⏰ [Inactividad] La sesión de soporte en vivo para {chat_id} superó los 60 minutos. Reactivando el bot..."
                    )
                    db_session.current_state = "idle"
                    await db.commit()
                    await set_cached_state(chat_id, "idle")
                    current_state = "idle"

            # Si hubo un Cache Miss (no está en Redis), cargamos desde PostgreSQL y guardamos en Redis
            if current_state is None:
                current_state = db_session.current_state
                logger.info(
                    f"🔄 Sincronizando estado '{current_state}' desde Postgres hacia el caché de Redis..."
                )
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
                bot_msg = MessageHistory(
                    chat_id=chat_id, role="assistant", body=text_response
                )
                db.add(bot_msg)

                # Actualizar el estado si es necesario en ambas capas (Caché RAM + DB Relacional)
                if new_state:
                    # Actualizar en Redis
                    await set_cached_state(chat_id, new_state)
                    # Actualizar en PostgreSQL
                    db_session.current_state = new_state

                await db.commit()

                # Enviar físicamente por WhatsApp a través del cliente OpenWA
                await openwa_client.send_text_message(
                    chat_id=chat_id, text=text_response
                )

            # ----------------------------------------------------------------------
            # INVOCACIÓN DEL CEREBRO CENTRAL (LANGGRAPH)
            # ----------------------------------------------------------------------
            logger.info(
                f"Invocando Grafo Central para {chat_id} (Estado: {current_state})..."
            )

            # Transformar historial de DB al formato que entiende LangChain/LangGraph
            chat_history = []
            for msg in db_history:
                if msg.role == "user":
                    chat_history.append(HumanMessage(content=msg.body))
                else:
                    chat_history.append(AIMessage(content=msg.body))

            # Ejecutar el grafo de estados
            graph_input = {
                "chat_id": chat_id,
                "sender_name": sender_name,
                "user_input": text_input,
                "current_state": current_state,
                "chat_history": chat_history,
            }

            state_result = await bot_graph.ainvoke(graph_input)

            response_text = state_result.get("response_text")
            new_state = state_result.get("new_state")
            admin_alert = state_result.get("admin_alert")

            # 1. Enviar respuesta al cliente (si el nodo generó una)
            if response_text:
                await responder_y_guardar(response_text, new_state)
            elif new_state and new_state != current_state:
                # Si no hay texto pero el estado cambió (ej. silencio de human_agent)
                await set_cached_state(chat_id, new_state)
                db_session.current_state = new_state
                await db.commit()
            else:
                logger.info(
                    f"🤫 Silencio mantenido por el bot (Estado: {current_state})"
                )

            # 2. Enviar alerta en tiempo real al teléfono del Administrador
            if admin_alert and ADMIN_PHONE_NUMBER:
                try:
                    logger.info(
                        f"📢 Enviando alerta de soporte al Administrador: {ADMIN_PHONE_NUMBER}"
                    )
                    await openwa_client.send_text_message(
                        chat_id=ADMIN_PHONE_NUMBER, text=admin_alert
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Error al enviar alerta de soporte al Administrador: {e}"
                    )

    except Exception as e:
        logger.error(f"Error procesando el mensaje asíncronamente: {e}", exc_info=True)


@router.post("/webhook")
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
            return {
                "status": "accepted",
                "message": "Mensaje en cola para procesamiento",
            }
        else:
            logger.warning("Evento de mensaje recibido pero 'data' está vacío.")
            raise HTTPException(
                status_code=400, detail="Data vacía en evento de mensaje"
            )

    return {"status": "ignored", "event": payload.event}
