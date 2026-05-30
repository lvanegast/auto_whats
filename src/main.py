import os
import httpx
import logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env inmediatamente
load_dotenv()

from src.services.whatsapp import openwa_client, OPENWA_SESSION_ID
from src.core.database import Base, engine
from src.api.admin_router import router as admin_router
from src.api.webhook_router import router as webhook_router
from src.services.bot_engine import bot_graph, BotState

from langserve import add_routes
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import HumanMessage

# Configuración básica de Logging profesional
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("auto-whats-backend")

# Inicializar FastAPI desactivando Swagger y ReDoc por defecto
app = FastAPI(
    title="WhatsApp Automation Backend",
    description="Servicio backend en Python para procesar eventos y lógica de negocio de WhatsApp.",
    version="2.0.0",
    docs_url=None,
    redoc_url=None
)

# Registrar Routers de la capa de presentación (API)
app.include_router(admin_router)
app.include_router(webhook_router)

# Archivos estáticos del panel
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ==============================================================================
# SCALAR: Documentación de API interactiva y moderna de última generación
# ==============================================================================
@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def scalar_api_reference():
    """
    Sirve la documentación de la API con Scalar, ofreciendo una experiencia
    visual interactiva y moderna, con generador de snippets integrado.
    """
    html_content = """
    <!doctype html>
    <html>
      <head>
        <title>WhatsApp Automation API Reference</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          body {
            margin: 0;
          }
        </style>
      </head>
      <body>
        <!-- Configuración de Scalar -->
        <script
          id="api-reference"
          data-url="/openapi.json"
          data-configuration='{"theme": "purple", "layout": "sidebar"}'></script>
        <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
      </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ==============================================================================
# LANGSERVE: Exposición del Asistente de LangGraph como API REST con Playground
# ==============================================================================
async def invoke_bot(user_input: str) -> str:
    """
    Wrapper asíncrono que conecta LangServe (entrada string simple)
    con el grafo conversacional de LangGraph.
    Retorna el último mensaje generado por el bot.
    """
    state: BotState = {
        "chat_id": "langserve_user",
        "sender_name": "LangServe User",
        "user_input": user_input.strip().lower(),
        "current_state": "idle",
        "chat_history": [HumanMessage(content=user_input)],
        "response_text": None,
        "new_state": None,
        "admin_alert": None
    }
    result = await bot_graph.ainvoke(state)
    return result.get("response_text") or "No se pudo generar respuesta."

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


@app.get("/")
async def root():
    """
    Ruta raíz para verificar la salud del backend.
    """
    return {
        "status": "healthy",
        "service": "WhatsApp Automation Backend",
        "configured_openwa_url": openwa_client.base_url
    }


def start():
    """
    Punto de entrada para ejecutar el servidor con 'uv run auto-whats'.
    """
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Iniciando el servidor FastAPI en el puerto {port} con auto-reload...")
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True)
