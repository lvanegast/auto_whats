"""
agent_graph.py - Grafo Conversacional del Chatbot de WhatsApp con LangGraph
Convierte la máquina de estados if/else de main.py en un grafo visual y modular.
"""
import os
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from dotenv import load_dotenv

load_dotenv()

# ==============================================================================
# MODELO GEMINI - Reutilizamos la configuración de agent.py
# ==============================================================================
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.7,
    timeout=20.0,
    max_retries=2
)

# ==============================================================================
# MENÚS DEL CHATBOT (Reutilizados de main.py para consistencia)
# ==============================================================================
MENU_PRINCIPAL = """🤖 *¡Hola!* Bienvenido al asistente virtual de exploración tecnológica.

Por favor, selecciona una opción respondiendo con su *número*:

*1️⃣ LangGraph* 🔵 - Explorar el grafo de conversación.
*2️⃣ LangSmith* 💛 - Ver el rastreo y telemetría del bot.
*3️⃣ LangServe* 🟣 - Aprender cómo se expone este agente como API.
*4️⃣ Hablar con Gemini* 🤖 - Consulta libre con Inteligencia Artificial.

✍️ _Escribe el número (1-4) o escribe "menú" para volver al inicio._"""

RESPUESTA_LANGGRAPH = """🔵 *LANGGRAPH: Motor de Flujos Conversacionales*

LangGraph estructura el bot como un *grafo dirigido de nodos*. Cada pantalla del menú es un nodo, y las respuestas del usuario son los bordes que conectan nodos.

*Ventajas principales:*
• Flujos complejos y cíclicos sin código if/else desordenado.
• Persistencia de estado entre turnos de conversación.
• Visualización automática del flujo como diagrama.

*0️⃣ Volver al Menú Principal* 🔙"""

RESPUESTA_LANGSMITH = """💛 *LANGSMITH: Observabilidad y Depuración de IA*

LangSmith registra en tiempo real cada llamada a Gemini, mostrando:
• El prompt exacto inyectado al modelo.
• Los tokens consumidos y el costo estimado.
• La latencia en milisegundos de cada nodo.
• El historial de cambios de respuesta entre versiones.

Puedes verlo en: https://smith.langchain.com

*0️⃣ Volver al Menú Principal* 🔙"""

RESPUESTA_LANGSERVE = """🟣 *LANGSERVE: Tu Agente como API REST*

LangServe expone este grafo de LangGraph como un endpoint HTTP estándar con:
• POST `/agent/invoke` - Invocar el bot y obtener la respuesta completa.
• POST `/agent/stream` - Recibir la respuesta en tiempo real (streaming).
• GET `/agent/playground/` - Interfaz web visual para chatear con el bot.

*0️⃣ Volver al Menú Principal* 🔙"""

SYSTEM_PROMPT_GEMINI = """Eres un asistente experto en el ecosistema de LangChain y en desarrollo de bots conversacionales con FastAPI y WhatsApp. Tu objetivo es responder preguntas técnicas de forma concisa, directa y educativa. Usa emojis de forma moderada. Evita respuestas muy largas, ve siempre al punto."""

# ==============================================================================
# ESTADO DEL GRAFO
# ==============================================================================
class BotState(TypedDict):
    """Estado que viaja a través de todos los nodos del grafo."""
    # add_messages es un reducer que acumula mensajes en la lista en vez de reemplazarlos
    messages: Annotated[list[BaseMessage], add_messages]
    # Estado actual del menú del usuario
    current_menu: str
    # Última entrada del usuario (texto plano normalizado)
    user_input: str


# ==============================================================================
# NODOS DEL GRAFO
# ==============================================================================
def main_menu_node(state: BotState) -> dict:
    """Nodo del Menú Principal: genera el texto de bienvenida."""
    return {
        "messages": [AIMessage(content=MENU_PRINCIPAL)],
        "current_menu": "main_menu"
    }


def langgraph_node(state: BotState) -> dict:
    """Nodo de información sobre LangGraph."""
    return {
        "messages": [AIMessage(content=RESPUESTA_LANGGRAPH)],
        "current_menu": "langgraph_info"
    }


def langsmith_node(state: BotState) -> dict:
    """Nodo de información sobre LangSmith."""
    return {
        "messages": [AIMessage(content=RESPUESTA_LANGSMITH)],
        "current_menu": "langsmith_info"
    }


def langserve_node(state: BotState) -> dict:
    """Nodo de información sobre LangServe."""
    return {
        "messages": [AIMessage(content=RESPUESTA_LANGSERVE)],
        "current_menu": "langserve_info"
    }


async def gemini_node(state: BotState) -> dict:
    """
    Nodo de IA: invoca Gemini con el historial completo de la conversación.
    LangSmith rastreará automáticamente esta llamada al LLM.
    """
    system = SystemMessage(content=SYSTEM_PROMPT_GEMINI)
    history = state["messages"][-6:]  # Últimos 6 mensajes de contexto
    response = await llm.ainvoke([system] + history)
    return {
        "messages": [response],
        "current_menu": "gemini_chat"
    }


# ==============================================================================
# ENRUTADOR CONDICIONAL
# Decide a qué nodo ir basándose en el estado y la entrada del usuario.
# ==============================================================================
def router(state: BotState) -> str:
    """
    Función de enrutamiento: decide el siguiente nodo del grafo
    según el estado actual del menú y la entrada del usuario.
    """
    user_input = state.get("user_input", "").strip().lower()
    current_menu = state.get("current_menu", "idle")

    # Comandos globales de regreso al menú principal
    if user_input in ["0", "menu", "menú", "inicio", "hola", "hi", "start"]:
        return "main_menu"

    # Desde el menú principal, dirigir a submenús
    if current_menu in ["main_menu", "idle", "gemini_chat",
                        "langgraph_info", "langsmith_info", "langserve_info"]:
        if user_input == "1":
            return "langgraph_info"
        elif user_input == "2":
            return "langsmith_info"
        elif user_input == "3":
            return "langserve_info"
        elif user_input == "4":
            return "gemini_chat"

    # Fallback por defecto: si no reconoce la entrada, va a Gemini
    return "gemini_chat"


# ==============================================================================
# CONSTRUCCIÓN DEL GRAFO
# ==============================================================================
def build_graph() -> StateGraph:
    """Construye y compila el grafo conversacional del bot."""
    workflow = StateGraph(BotState)

    # 1. Registrar todos los nodos
    workflow.add_node("main_menu", main_menu_node)
    workflow.add_node("langgraph_info", langgraph_node)
    workflow.add_node("langsmith_info", langsmith_node)
    workflow.add_node("langserve_info", langserve_node)
    workflow.add_node("gemini_chat", gemini_node)

    # 2. Nodo de enrutamiento: punto de entrada desde el inicio
    workflow.add_conditional_edges(
        START,
        router,
        {
            "main_menu": "main_menu",
            "langgraph_info": "langgraph_info",
            "langsmith_info": "langsmith_info",
            "langserve_info": "langserve_info",
            "gemini_chat": "gemini_chat",
        }
    )

    # 3. Todos los nodos terminales apuntan a END
    workflow.add_edge("main_menu", END)
    workflow.add_edge("langgraph_info", END)
    workflow.add_edge("langsmith_info", END)
    workflow.add_edge("langserve_info", END)
    workflow.add_edge("gemini_chat", END)

    return workflow.compile()


# Instancia global del grafo compilado (reutilizable por LangServe y webhooks)
bot_graph = build_graph()
