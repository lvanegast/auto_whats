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
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1. Listar webhooks existentes y eliminarlos
            print("Buscando webhooks antiguos registrados...")
            res = await client.get(f"{api_url}/api/sessions/{session_id}/webhooks", headers=headers)
            if res.status_code == 200:
                webhooks = res.json()
                for wh in webhooks:
                    wh_id = wh.get("id")
                    print(f"Eliminando webhook antiguo: {wh_id} ({wh.get('url')})...")
                    del_res = await client.delete(f"{api_url}/api/sessions/{session_id}/webhooks/{wh_id}", headers=headers)
                    print(f"  Resultado de la eliminación: {del_res.status_code}")
            
            # 2. Registrar el nuevo webhook correcto
            payload = {
                "url": "http://host.docker.internal:8000/webhook",
                "events": ["message.received", "session.status"]
            }
            print("\nRegistrando nuevo webhook activo en OpenWA...")
            res = await client.post(f"{api_url}/api/sessions/{session_id}/webhooks", headers=headers, json=payload)
            if res.status_code == 201:
                data = res.json()
                print("✅ ¡Webhook registrado con éxito!")
                print(f"  ID del Webhook: {data.get('id')}")
                print(f"  URL Destino: {data.get('url')}")
                print(f"  Eventos Suscritos: {data.get('events')}")
            else:
                print(f"⚠️ Error al registrar webhook (Status {res.status_code}): {res.text}")
            
        except Exception as e:
            print(f"❌ Error de conexión al intentar configurar webhooks: {e}")

if __name__ == "__main__":
    asyncio.run(main())
