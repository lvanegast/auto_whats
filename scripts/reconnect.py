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
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 1. Enviar comando de detención /stop para limpiar el estado 'failed' residual
            print(f"1. Deteniendo la sesion {session_id} para limpiar estado 'failed'...")
            stop_res = await client.post(f"{api_url}/api/sessions/{session_id}/stop", headers=headers)
            print(f"   Resultado Stop: {stop_res.status_code}")
            
            await asyncio.sleep(3.0)
            
            # 2. Borrar SingletonLock por si acaso
            lock_path = "openwa_data/sessions/session-default/SingletonLock"
            if os.path.lexists(lock_path):
                print("2. Removiendo archivo SingletonLock residual...")
                os.remove(lock_path)
                print("   [OK] SingletonLock removido con exito.")
            
            # 3. Enviar señal de arranque /start
            print(f"3. Enviando comando de ARRANQUE (/start) a la sesion...")
            res = await client.post(f"{api_url}/api/sessions/{session_id}/start", headers=headers)
            print(f"   Resultado Start: {res.status_code}")
            
            # 4. Monitorear estado
            print("\n4. Monitoreando estado de conexion...")
            for i in range(10):
                await asyncio.sleep(2.0)
                status_res = await client.get(f"{api_url}/api/sessions", headers=headers)
                if status_res.status_code == 200:
                    sessions = status_res.json()
                    for s in sessions:
                        if s.get("id") == session_id:
                            status = s.get("status")
                            print(f"   Consulta {i+1}: Estado = '{status}' (Telefono = '{s.get('phone')}')")
                            if status in ["connected", "active", "authenticated", "ready"]:
                                print("\n[OK] ¡Sesion conectada y en linea!")
                                return
        except Exception as e:
            print(f"[ERROR] Error de conexion al gateway: {e}")

if __name__ == "__main__":
    asyncio.run(main())
