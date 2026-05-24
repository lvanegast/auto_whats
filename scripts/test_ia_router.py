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
    print("      INICIANDO SIMULACION DE IA + POSTGRESQL            ")
    print("=========================================================")
    
    # 1. Enviar saludo inicial
    print("\nStep 1: Enviar saludo inicial 'hola'")
    send_webhook(body="hola")
    time.sleep(2.0)
    
    # 2. Navegar al catalogo
    print("\nStep 2: Navegar seleccionando '1' (Catalogo)")
    send_webhook(body="1")
    time.sleep(2.0)
    
    # 3. Pregunta libre en lenguaje natural
    print("\nStep 3: Pregunta en lenguaje natural -> 'Tienen audifonos y cuales son los tiempos de envio?'")
    send_webhook(body="¿Tienen audífonos y cuáles son los tiempos de envío?")
    time.sleep(6.0)
    
    # 4. Otra pregunta en lenguaje natural relacionada a pagos
    print("\nStep 4: Pregunta de seguimiento -> 'Excelente, y que metodos de pago aceptan?'")
    send_webhook(body="Excelente, ¿y qué métodos de pago aceptan?")
    time.sleep(6.0)
    
    # 5. Volver al menu usando atajo
    print("\nStep 5: Enviar '0' para regresar al Menu Principal")
    send_webhook(body="0")
    time.sleep(2.0)
    
    print("\n=========================================================")
    print("               SIMULACIÓN FINALIZADA                     ")
    print("=========================================================")

if __name__ == "__main__":
    main()
