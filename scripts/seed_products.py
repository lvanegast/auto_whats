"""
seed_products.py — Puebla la base de datos con productos de ejemplo.
Ejecutar una sola vez: uv run python scripts/seed_products.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import engine, SessionLocal, Base
from src.models import Product


PRODUCTS = [
    # ── TECNOLOGÍA Y COMPUTACIÓN ──────────────────────────────────────
    {
        "name": "Laptop Asus VivoBook 15",
        "description": "Ryzen 5, 8GB RAM, SSD 512GB, pantalla Full HD",
        "price": 599.99,
        "stock": 12,
        "category": "tech",
    },
    {
        "name": "Monitor LG 27\" 4K IPS",
        "description": "Panel IPS, HDR400, USB-C, compatible con Mac y PC",
        "price": 349.00,
        "stock": 8,
        "category": "tech",
    },
    {
        "name": "Teclado Mecánico Keychron K2",
        "description": "Switches ópticos, retroiluminación RGB, compacto 75%",
        "price": 89.99,
        "stock": 25,
        "category": "tech",
    },
    # ── CELULARES Y ACCESORIOS ────────────────────────────────────────
    {
        "name": "Samsung Galaxy A55 5G",
        "description": "6.6\" AMOLED, 8GB RAM, 128GB, cámara triple 50MP",
        "price": 399.99,
        "stock": 15,
        "category": "phones",
    },
    {
        "name": "Cargador Inalámbrico 15W",
        "description": "Compatible con iPhone y Android, carga rápida Qi",
        "price": 29.99,
        "stock": 40,
        "category": "phones",
    },
    {
        "name": "Funda MagSafe iPhone 15",
        "description": "Silicona premium con soporte MagSafe integrado",
        "price": 19.99,
        "stock": 60,
        "category": "phones",
    },
    # ── AUDIO Y SONIDO ────────────────────────────────────────────────
    {
        "name": "Sony WH-1000XM5",
        "description": "Cancelación de ruido activa, 30h batería, Hi-Res Audio",
        "price": 279.00,
        "stock": 7,
        "category": "audio",
    },
    {
        "name": "JBL Charge 5 Bluetooth",
        "description": "Resistente al agua IP67, batería 20h, PowerBank integrado",
        "price": 149.99,
        "stock": 18,
        "category": "audio",
    },
    {
        "name": "Auriculares Sony WF-C700N",
        "description": "In-ear TWS, ANC adaptativo, estuche de carga compacto",
        "price": 99.99,
        "stock": 22,
        "category": "audio",
    },
]


async def seed():
    print("🌱 Iniciando seed de productos...")

    # Crear tablas si no existen
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        # Verificar si ya hay productos para no duplicar
        from sqlalchemy.future import select
        existing = await db.execute(select(Product))
        if existing.scalars().first():
            print("⚠️  Ya existen productos en la BD. Seed omitido para evitar duplicados.")
            print("   Si quieres reiniciar, borra la tabla 'products' manualmente.")
            return

        for data in PRODUCTS:
            db.add(Product(**data))

        await db.commit()
        print(f"✅ {len(PRODUCTS)} productos insertados con éxito:")
        for p in PRODUCTS:
            print(f"   [{p['category']:7}] {p['name']} — ${p['price']:.2f}")


if __name__ == "__main__":
    asyncio.run(seed())
