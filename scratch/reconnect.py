import os
import httpx
import asyncio

async def main():
    api_url = "http://localhost:2785"
    api_key = "dev-admin-key"
    session_id = "cf721cc0-9bba-4460-8efb-93c5c9f11899"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # 1. Liberar archivo de bloqueo si existe
    lock_path = "openwa_data/sessions/session-default/SingletonLock"
    if os.path.exists(lock_path):
        try:
            print("Deteniendo archivos de bloqueo residuales de Chromium...")
            os.remove(lock_path)
            print("✅ Archivo SingletonLock removido con éxito.")
        except Exception as e:
            print(f"⚠️ No se pudo eliminar SingletonLock de forma directa: {e}")
            
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 2. Enviar señal de arranque /start
            print(f"Enviando comando de ARRANQUE (/start) a la sesión {session_id}...")
            res = await client.post(f"{api_url}/api/sessions/{session_id}/start", headers=headers)
            print(f"Respuesta del Gateway: {res.status_code}")
            
            # 3. Monitorear estado
            print("\nMonitoreando estado de conexión...")
            for i in range(10):
                await asyncio.sleep(2.0)
                status_res = await client.get(f"{api_url}/api/sessions", headers=headers)
                if status_res.status_code == 200:
                    sessions = status_res.json()
                    for s in sessions:
                        if s.get("id") == session_id:
                            status = s.get("status")
                            print(f"  Consulta {i+1}: Estado actual es '{status}' (Teléfono vinculado: '{s.get('phone')}')")
                            if status in ["connected", "active", "authenticated", "ready"]:
                                print("\n✅ ¡La sesión de WhatsApp está conectada en línea y LISTA para operar!")
                                return
        except Exception as e:
            print(f"❌ Error de conexión al gateway: {e}")

if __name__ == "__main__":
    asyncio.run(main())
