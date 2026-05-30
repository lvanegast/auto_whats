"""
agent_graph.py - Cerebro Central del Bot de WhatsApp usando LangGraph
Contiene los Nodos (pantallas) y Bordes (rutas) de la máquina de estados.
"""
import os
import logging
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langsmith import traceable
from dotenv import load_dotenv

from src.database import SessionLocal
from src.models import Product
from sqlalchemy.future import select

load_dotenv()
logger = logging.getLogger("agent-graph")

# ==============================================================================
# MODELO GEMINI
# ==============================================================================
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.7,
    timeout=20.0,
    max_retries=2
)

SYSTEM_PROMPT = """Eres el asistente virtual experto de nuestra tienda.
Tu objetivo es responder de forma amable, clara y concisa a las preguntas de los clientes.
Si el usuario te hace una pregunta que se sale totalmente del contexto de la tienda o soporte,
responde amablemente que eres un asistente de la tienda y no puedes ayudar con eso.
Usa emojis moderadamente. Nunca seas descortés."""

# ==============================================================================
# CONSTANTES DE TEXTO (MENÚS)
# ==============================================================================
MENU_PRINCIPAL = """🤖 *¡Hola{name}!* Bienvenido a nuestro asistente virtual.

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

RESPUESTA_DEVOLUCION = """🔄 *DEVOLUCIONES Y GARANTÍAS*
Tienes 30 días naturales para devolver tu producto sin costo adicional si presenta defectos de fábrica.

*0️⃣ Volver al Menú Principal* 🔙
*3️⃣ Volver a Preguntas Frecuentes* ❓"""


# ==============================================================================
# FUNCIONES AUXILIARES (BD)
# ==============================================================================
async def get_catalogo_categoria(category: str) -> str:
    """Consulta los productos dinámicamente desde la BD."""
    _CATALOGO_EMOJIS = {"tech": "💻", "phones": "📱", "audio": "🎧"}
    _CATALOGO_TITULOS = {"tech": "TECNOLOGÍA Y COMPUTACIÓN", "phones": "CELULARES Y ACCESORIOS", "audio": "AUDIO Y SONIDO"}
    
    async with SessionLocal() as db:
        try:
            q = await db.execute(select(Product).where(Product.category == category, Product.active == True).order_by(Product.id))
            products = q.scalars().all()

            emoji  = _CATALOGO_EMOJIS.get(category, "📦")
            titulo = _CATALOGO_TITULOS.get(category, category.upper())

            if not products:
                return f"{emoji} *{titulo}*\n\n_No hay productos disponibles por el momento._\n\n*0️⃣ Volver al Menú Principal* 🔙\n*1️⃣ Volver al Catálogo* 📦"

            lines = [f"{emoji} *{titulo}*\n"]
            for i, p in enumerate(products, 1):
                stock_icon = "✅" if p.stock > 0 else "❌"
                stock_txt  = f"En stock ({p.stock})" if p.stock > 0 else "Sin stock"
                lines.append(f"*{i}.* {p.name}\n     💰 *${float(p.price):.2f}* | {stock_icon} {stock_txt}\n     _{p.description}_")

            lines.append("\n*0️⃣ Volver al Menú Principal* 🔙")
            lines.append("*1️⃣ Volver al Catálogo* 📦")
            return "\n\n".join(lines[:1] + lines[1:])
        except Exception as e:
            logger.error(f"Error cargando catálogo: {e}")
            return "Error al cargar catálogo."


# ==============================================================================
# ESTADO DEL GRAFO
# ==============================================================================
class BotState(TypedDict):
    chat_id: str
    sender_name: str
    user_input: str
    current_state: str
    chat_history: list[BaseMessage]
    response_text: Optional[str]
    new_state: Optional[str]
    admin_alert: Optional[str]


# ==============================================================================
# NODOS
# ==============================================================================
def human_agent_node(state: BotState) -> dict:
    text_input = state["user_input"].lower()
    if text_input in ["!menu", "!ayuda", "menu", "ayuda"]:
        # Se libera el silencio
        msg = MENU_PRINCIPAL.format(name=f", {state['sender_name']}")
        return {"response_text": msg, "new_state": "main_menu"}
    
    # Si sigue en human_agent y no hay comando de escape, no responde nada.
    return {"response_text": None, "new_state": "human_agent"}


def main_menu_node(state: BotState) -> dict:
    msg = MENU_PRINCIPAL.format(name=f", {state['sender_name']}")
    return {"response_text": msg, "new_state": "main_menu"}


async def catalog_node(state: BotState) -> dict:
    text_input = state["user_input"].lower()
    
    if text_input == "11" or "tecnología" in text_input:
        msg = await get_catalogo_categoria("tech")
        return {"response_text": msg, "new_state": "catalog"}
    elif text_input == "12" or "celulares" in text_input:
        msg = await get_catalogo_categoria("phones")
        return {"response_text": msg, "new_state": "catalog"}
    elif text_input == "13" or "audio" in text_input:
        msg = await get_catalogo_categoria("audio")
        return {"response_text": msg, "new_state": "catalog"}
    
    # Default: mostrar menú de catálogo
    return {"response_text": MENU_CATALOGO, "new_state": "catalog"}


def support_node(state: BotState) -> dict:
    text_input = state["user_input"].lower()
    
    if text_input == "21" or "agente" in text_input:
        alerta = (
            f"🤖 *[Alerta de Soporte en Vivo]*\n\n"
            f"El cliente *{state['sender_name']}* ({state['chat_id']}) ha solicitado asistencia humana.\n\n"
            f"👉 _Abre WhatsApp Web o tu celular. El bot ha sido suspendido y silenciado._\n\n"
            f"💡 _Para reactivar el bot automático, escribe *!menu* en cualquier momento._"
        )
        return {"response_text": RESPUESTA_AGENTE, "new_state": "human_agent", "admin_alert": alerta}
        
    elif text_input == "22" or "correo" in text_input:
        return {"response_text": RESPUESTA_CORREO, "new_state": "support"}
        
    return {"response_text": MENU_SOPORTE, "new_state": "support"}


def faq_node(state: BotState) -> dict:
    text_input = state["user_input"].lower()
    
    if text_input == "31" or "envío" in text_input:
        return {"response_text": RESPUESTA_ENVIO, "new_state": "faq"}
    elif text_input == "32" or "pago" in text_input:
        return {"response_text": RESPUESTA_PAGO, "new_state": "faq"}
    elif text_input == "33" or "devolución" in text_input or "devolucion" in text_input:
        return {"response_text": RESPUESTA_DEVOLUCION, "new_state": "faq"}
        
    return {"response_text": MENU_FAQ, "new_state": "faq"}


@traceable(name="WhatsApp → Gemini", run_type="llm")
async def ai_fallback_node(state: BotState) -> dict:
    """Llama a Gemini cuando el texto no coincide con ningún menú numérico."""
    system = SystemMessage(content=SYSTEM_PROMPT)
    history = state["chat_history"][-8:]  # Traer contexto reciente
    user_msg = state["user_input"]
    
    # Aquí podríamos convertir los diccionarios en objetos BaseMessage, pero 
    # la librería de LangChain acepta directamente la lista de mensajes si están bien formateados.
    # En nuestro caso, history ya debe ser una lista de BaseMessage (HumanMessage, AIMessage).
    messages = [system] + history
    
    response = await llm.ainvoke(messages)
    return {"response_text": response.content, "new_state": state["current_state"]}


# ==============================================================================
# ENRUTADOR
# ==============================================================================
def route_decision(state: BotState) -> str:
    current = state.get("current_state", "idle")
    text = state.get("user_input", "").lower().strip()

    # 1. Prioridad: Intervención humana
    if current == "human_agent":
        return "human_agent_node"

    # 2. Comandos globales (Escape)
    if text in ["0", "menu", "menú", "inicio", "hola", "hi", "start"]:
        return "main_menu_node"
        
    if text in ["!ping", "ping"]:
        # Se podría hacer un nodo de comandos, pero podemos enviarlo al main_menu que no hará ping.
        # Por simplicidad, que Gemini lo responda o le creamos un nodo rápido.
        return "ai_fallback_node"

    # 3. Flujo guiado por el estado actual
    if current in ["main_menu", "idle"]:
        if text == "1" or "catálogo" in text or "catalogo" in text:
            return "catalog_node"
        if text == "2" or "soporte" in text:
            return "support_node"
        if text == "3" or "preguntas" in text or "faq" in text:
            return "faq_node"
            
    elif current == "catalog":
        if text in ["1", "11", "12", "13"]: return "catalog_node"
        
    elif current == "support":
        if text in ["2", "21", "22"]: return "support_node"
        
    elif current == "faq":
        if text in ["3", "31", "32", "33"]: return "faq_node"

    # 4. Fallback: Lenguaje Natural (Gemini)
    return "ai_fallback_node"


# ==============================================================================
# CONSTRUCCIÓN DEL GRAFO
# ==============================================================================
workflow = StateGraph(BotState)

workflow.add_node("human_agent_node", human_agent_node)
workflow.add_node("main_menu_node", main_menu_node)
workflow.add_node("catalog_node", catalog_node)
workflow.add_node("support_node", support_node)
workflow.add_node("faq_node", faq_node)
workflow.add_node("ai_fallback_node", ai_fallback_node)

workflow.add_conditional_edges(
    START,
    route_decision,
    {
        "human_agent_node": "human_agent_node",
        "main_menu_node": "main_menu_node",
        "catalog_node": "catalog_node",
        "support_node": "support_node",
        "faq_node": "faq_node",
        "ai_fallback_node": "ai_fallback_node",
    }
)

workflow.add_edge("human_agent_node", END)
workflow.add_edge("main_menu_node", END)
workflow.add_edge("catalog_node", END)
workflow.add_edge("support_node", END)
workflow.add_edge("faq_node", END)
workflow.add_edge("ai_fallback_node", END)

bot_graph = workflow.compile()
