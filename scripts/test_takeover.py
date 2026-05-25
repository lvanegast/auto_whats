import httpx
import time

def send_webhook(body):
    url = "http://localhost:8000/webhook"
    payload = {
        "event": "message.received",
        "session": "default",
        "data": {
            "from": "573225382293@c.us",
            "body": body,
            "sender": {"pushname": "Test Cliente"}
        }
    }
    headers = {"Content-Type": "application/json"}
    try:
        res = httpx.post(url, headers=headers, json=payload)
        print(f"Sent: '{body}' -> Webhook Response: {res.status_code} - {res.json()}")
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("=========================================================")
    print("      SIMULANDO ATENCION HUMANA & SILENCIO DEL BOT       ")
    print("=========================================================")
    
    # 1. Enviar saludo inicial
    print("\nStep 1: Enviar saludo inicial 'hola'")
    send_webhook(body="hola")
    time.sleep(2.0)
    
    # 2. Navegar a Soporte
    print("\nStep 2: Navegar a Soporte seleccionando '2'")
    send_webhook(body="2")
    time.sleep(2.0)
    
    # 3. Solicitar hablar con agente en vivo
    print("\nStep 3: Solicitar agente seleccionando '21'")
    print("--> Esto deberia alertar al Administrador y silenciar el bot.")
    send_webhook(body="21")
    time.sleep(5.0)
    
    # 4. Enviar un mensaje adicional (el bot deberia estar silenciado)
    print("\nStep 4: Enviar mensaje de conversacion libre -> '¿Están ahí? Necesito soporte urgente'")
    print("--> IMPORTANTE: El bot NO deberia responder esto de forma automatica.")
    send_webhook(body="¿Están ahí? Necesito soporte urgente")
    time.sleep(5.0)
    
    # 5. Liberar el control
    print("\nStep 5: Enviar '!menu' para liberar el bot y reactivar respuestas")
    send_webhook(body="!menu")
    time.sleep(2.0)
    
    print("\n=========================================================")
    print("             SIMULACIÓN DE TAKEOVER FINALIZADA           ")
    print("=========================================================")

if __name__ == "__main__":
    main()
