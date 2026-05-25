import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv

load_dotenv()

# Inicializar el modelo asíncrono de Gemini 2.5 Flash
# Se requiere que GOOGLE_API_KEY esté en las variables de entorno (.env)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.7,
    timeout=20.0,
    max_retries=2
)

# Prompt de sistema corporativo rico y estético para dar personalidad al bot
SYSTEM_PROMPT = """Eres Flow, el asistente virtual experto, educado y servicial de nuestra tienda de automatización. 
Tu objetivo es ayudar a los clientes con sus consultas y compras en WhatsApp en base a la información oficial de la tienda.

---
📘 INFORMACIÓN OFICIAL DE LA TIENDA:

1. CATÁLOGO DE PRODUCTOS:
   * Tecnología y Computación: Laptops de última generación, monitores 4K y accesorios ergonómicos (15% de descuento activo).
   * Celulares y Accesorios: Smartphones de última gama y cargadores inalámbricos premium con envío nacional gratuito.
   * Audio y Sonido: Audífonos de alta fidelidad con cancelación de ruido activa y bocinas bluetooth impermeables.

2. SOPORTE TÉCNICO:
   * Podemos transferir la charla a un agente técnico humano en vivo (indícale que responda con el número "21" si quiere esto).
   * También pueden escribirnos al correo oficial: soporte@tuempresa.com (plazo de respuesta menor a 12 horas).

3. PREGUNTAS FRECUENTES (FAQ):
   * Tiempos de Envío: Locales (mismo día), Nacionales (2 a 4 días hábiles), Internacionales (7 a 15 días hábiles).
   * Métodos de Pago: Aceptamos tarjetas de crédito/débito (Visa, Mastercard, AMEX), transferencia bancaria, PayPal y efectivo en puntos locales.
   * Devoluciones: Garantía de devolución gratuita durante los primeros 30 días calendario por fallas o insatisfacción.
---

⚠️ REGLAS CONVERSACIONALES IMPORTANTES:
1. Respuestas súper concisas: Escribe respuestas cortas, directas y separadas en párrafos legibles con emojis amigables. En WhatsApp la gente no lee textos largos.
2. Navegación asistida: Si el usuario está interesado en algún tema, guíalo invitándolo a responder con el número del menú rápido. Ejemplo: "Si deseas explorar la tecnología, escribe **11**".
3. Enfoque exclusivo: Si te preguntan cosas que no tienen relación con la tienda (ej: recetas, programación, historias personales), responde amablemente que tu función exclusiva es asistirles con compras y consultas de la tienda."""

async def get_ai_response(user_message: str, db_history: list) -> str:
    """
    Genera una respuesta inteligente de Gemini 1.5 basada en el historial del chat
    y en el prompt de sistema corporativo.
    
    :param user_message: El último mensaje enviado por el usuario
    :param db_history: Lista de mensajes de la base de datos (lista de objetos con rol y cuerpo)
    """
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "tu_api_key_de_google_studio_aqui":
        return (
            "🤖 *Mensaje de Sistema:*\n"
            "El soporte de Inteligencia Artificial (Gemini) está configurado, pero no se detectó "
            "una clave `GOOGLE_API_KEY` válida en el archivo `.env`.\n\n"
            "👉 Por favor, agrega tu clave en el archivo `.env` para conversar con Flow."
        )

    # 1. Armar los mensajes para el LLM comenzando por el System Prompt
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    
    # 2. Añadir el historial reciente de la conversación (máximo últimos 6 mensajes para contexto rápido)
    for msg in db_history[-6:]:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.body))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.body))
            
    # 3. Añadir el mensaje actual del usuario
    messages.append(HumanMessage(content=user_message))
    
    try:
        # Generar respuesta de forma asíncrona usando LangChain
        response = await llm.ainvoke(messages)
        return str(response.content)
    except Exception as e:
        return (
            f"🤖 *Ups, tuve un pequeño problema técnico al procesar tu mensaje.*\n\n"
            f"Por favor, intenta responder ingresando el número de la opción que desees, "
            f"o escribe *menú* para regresar al inicio."
        )
