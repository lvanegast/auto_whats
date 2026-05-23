import os
import asyncio
import base64
import httpx
from dotenv import load_dotenv
from src.client import OpenWAClient

# Cargar variables de entorno del archivo .env
load_dotenv()

async def get_or_create_session(client: OpenWAClient) -> str:
    """
    Intenta crear la sesión si no existe o la busca si ya existe.
    Retorna el ID de sesión dinámico (UUID).
    """
    list_url = f"{client.base_url}/api/sessions"
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        try:
            list_res = await http_client.get(list_url, headers=client.headers)
            if list_res.status_code == 200:
                sessions = list_res.json()
                for s in sessions:
                    if s.get("name") == client.session_id:
                        dynamic_id = s.get("id")
                        print(f"✅ Sesión existente encontrada. Nombre: '{client.session_id}', ID real: '{dynamic_id}'")
                        return dynamic_id
        except Exception as e:
            print(f"⚠️ No se pudo listar sesiones: {e}")

    url = f"{client.base_url}/api/sessions"
    payload = {"name": client.session_id}
    
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        try:
            response = await http_client.post(url, headers=client.headers, json=payload)
            if response.status_code == 201:
                res_data = response.json()
                dynamic_id = res_data.get("id")
                print(f"🆕 Sesión creada en OpenWA. ID real: '{dynamic_id}'")
                return dynamic_id
            else:
                print(f"⚠️ Error al crear sesión (Status {response.status_code}): {response.text}")
                raise Exception("No se pudo crear la sesión")
        except Exception as e:
            print(f"⚠️ Error en la petición de creación: {e}")
            raise e

async def start_session_if_needed(client: OpenWAClient):
    """
    Intenta arrancar la sesión de OpenWA.
    """
    url = f"{client.base_url}/api/sessions/{client.session_id}/start"
    async with httpx.AsyncClient(timeout=15.0) as http_client:
        try:
            response = await http_client.post(url, headers=client.headers)
            if response.status_code == 200 or response.status_code == 201:
                print("🔄 Iniciando el motor de WhatsApp Web en segundo plano...")
            else:
                print(f"⚠️ Nota al iniciar sesión: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"⚠️ Error al iniciar sesión: {e}")

async def async_main():
    api_url = os.getenv("OPENWA_API_URL", "http://localhost:2785")
    api_key = os.getenv("OPENWA_API_KEY", "dev-admin-key")
    session_id = os.getenv("OPENWA_SESSION_ID", "default")
    
    print("=========================================================")
    print("      ASISTENTE DE CONFIGURACIÓN Y ENVÍO DE WHATSAPP      ")
    print("=========================================================")

    # Inicializar el cliente
    client = OpenWAClient(base_url=api_url, api_key=api_key, session_id=session_id)
    
    try:
        # 1. Asegurar que la sesión existe y está iniciada
        print("🔄 Comprobando estado del servicio OpenWA...")
        dynamic_id = await get_or_create_session(client)
        client.session_id = dynamic_id
        await start_session_if_needed(client)
        
        # 2. Esperar el estado o el QR
        print("\n⏳ Esperando a que WhatsApp esté listo o genere el QR...")
        qr_saved = False
        
        while True:
            try:
                # Obtener el estado real de la sesión desde la lista general para evitar bugs de OpenWA
                status = "unknown"
                try:
                    list_url = f"{client.base_url}/api/sessions"
                    async with httpx.AsyncClient(timeout=10.0) as http_client:
                        res = await http_client.get(list_url, headers=client.headers)
                        if res.status_code == 200:
                            sessions = res.json()
                            for s in sessions:
                                if s.get("id") == client.session_id:
                                    raw_status = s.get("status", "unknown")
                                    # Si ya tiene teléfono asignado o el estado es CONNECTED/ACTIVE, ya está listo
                                    if s.get("phone") is not None or raw_status.upper() in ["CONNECTED", "ACTIVE", "AUTHENTICATED", "READY"]:
                                        status = "CONNECTED"
                                    else:
                                        status = raw_status
                    print(f"\nDEBUG: Estado detectado en OpenWA: '{status}' (Estado crudo: '{raw_status}')")
                except Exception as e:
                    print(f"\n⚠️ Error al consultar lista de sesiones: {e}")
                    status = "INITIALIZING"

                if status in ["CONNECTED", "authenticated"]:
                    print("\n✅ ¡WhatsApp está CONECTADO y listo para usar!")
                    # Si guardamos un archivo QR anterior, lo limpiamos
                    if os.path.exists("codigo_qr.png"):
                        try:
                            os.remove("codigo_qr.png")
                        except Exception:
                            pass
                    break
                
                # Si no está conectado, pedir el código QR
                qr_url = f"{client.base_url}/api/sessions/{client.session_id}/qr"
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    qr_res = await http_client.get(qr_url, headers=client.headers)
                    if qr_res.status_code == 200:
                        qr_data = qr_res.json()
                        qr_base64 = qr_data.get("qrCode")
                        
                        if qr_base64 and qr_base64.startswith("data:image/png;base64,"):
                            # Extraer los bytes base64 puros
                            raw_b64 = qr_base64.split(",")[1]
                            image_data = base64.b64decode(raw_b64)
                            
                            # Guardar en disco local
                            with open("codigo_qr.png", "wb") as f:
                                f.write(image_data)
                            
                            if not qr_saved:
                                print("\n📷 [QR DETECTADO] Se ha generado el código QR de vinculación.")
                                print("👉 Abre el archivo 'codigo_qr.png' que acabo de crear en tu carpeta del proyecto.")
                                print("👉 Escanéalo con tu celular real (WhatsApp -> Dispositivos vinculados).")
                                print("\n⏳ Esperando a que escanees el código (esta pantalla se actualizará automáticamente)...")
                                qr_saved = True
                        else:
                            print(".", end="", flush=True)
                    else:
                        print(".", end="", flush=True)
                        
            except Exception as e:
                print(f"\n⚠️ Esperando al servicio: {e}")
                
            await asyncio.sleep(3.0)

        # 3. Mandar el mensaje de prueba
        print("\n=========================================================")
        print("                 PROBAR ENVÍO DE MENSAJE                 ")
        print("=========================================================")
        destinatario = input("👉 Introduce el número de destino (con código de país, ej: 34600000000): ").strip()
        
        if not destinatario.endswith("@c.us"):
            chat_id = f"{destinatario}@c.us"
        else:
            chat_id = destinatario

        mensaje = input("👉 Introduce el mensaje a enviar: ").strip()
        
        print(f"\n🔄 Enviando mensaje a '{chat_id}'...")
        response = await client.send_text_message(chat_id=chat_id, text=mensaje)
        print("🎉 ¡Mensaje enviado con éxito!")
        print(f"📝 Respuesta de OpenWA: {response}")
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")

def main():
    import asyncio
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
