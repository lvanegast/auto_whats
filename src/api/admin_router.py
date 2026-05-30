"""
admin_router.py — Router del Panel de Administración de Flow Bot.
Rutas protegidas con X-Admin-Key. Incluye CRUD de productos,
listado de conversaciones y métricas del dashboard.
"""
import os
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from sqlalchemy.future import select
from sqlalchemy import func, desc

from src.core.database import SessionLocal
from src.models.domain import UserSession, MessageHistory, Product
from src.schemas.dtos import ProductCreate, ProductUpdate

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "admin-secret-change-me")

# ──────────────────────────────────────────────────────────────────────────────
# AUTENTICACIÓN
# ──────────────────────────────────────────────────────────────────────────────

async def verify_admin(x_admin_key: Optional[str] = Header(None)):
    """Dependencia de autenticación: valida el header X-Admin-Key."""
    if not x_admin_key or x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Clave de administrador inválida o ausente.")
    return True


# ──────────────────────────────────────────────────────────────────────────────
# UI — Servir el panel HTML
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def admin_ui():
    """Sirve la interfaz de administración como SPA."""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "admin", "index.html")
    return FileResponse(html_path)


# ──────────────────────────────────────────────────────────────────────────────
# DASHBOARD — Métricas generales
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/stats", dependencies=[Depends(verify_admin)])
async def get_stats():
    """Métricas generales para el dashboard."""
    async with SessionLocal() as db:
        # Total de conversaciones (usuarios únicos)
        total_conv = await db.execute(select(func.count(UserSession.chat_id)))
        total_conversations = total_conv.scalar()

        # Conversaciones activas (sesión en estado != idle en las últimas 24h)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        active_q = await db.execute(
            select(func.count(UserSession.chat_id)).where(
                UserSession.updated_at >= cutoff
            )
        )
        active_conversations = active_q.scalar()

        # Total de mensajes
        total_msg = await db.execute(select(func.count(MessageHistory.id)))
        total_messages = total_msg.scalar()

        # Mensajes hoy
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_msg = await db.execute(
            select(func.count(MessageHistory.id)).where(
                MessageHistory.timestamp >= today_start
            )
        )
        messages_today = today_msg.scalar()

        # Llamadas a Gemini (mensajes del asistente que no sean menús)
        ai_calls = await db.execute(
            select(func.count(MessageHistory.id)).where(
                MessageHistory.role == "assistant"
            )
        )
        total_ai_calls = ai_calls.scalar()

        # Total productos activos
        prod_q = await db.execute(
            select(func.count(Product.id)).where(Product.active == True)
        )
        active_products = prod_q.scalar()

        # Sesiones en modo human_agent
        human_q = await db.execute(
            select(func.count(UserSession.chat_id)).where(
                UserSession.current_state == "human_agent"
            )
        )
        human_sessions = human_q.scalar()

    return {
        "total_conversations": total_conversations,
        "active_conversations_24h": active_conversations,
        "total_messages": total_messages,
        "messages_today": messages_today,
        "total_ai_calls": total_ai_calls,
        "active_products": active_products,
        "human_sessions": human_sessions,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CONVERSACIONES
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/conversations", dependencies=[Depends(verify_admin)])
async def list_conversations():
    """Lista todas las conversaciones con su estado y último mensaje."""
    async with SessionLocal() as db:
        sessions_q = await db.execute(
            select(UserSession).order_by(desc(UserSession.updated_at)).limit(100)
        )
        sessions = sessions_q.scalars().all()

        result = []
        for s in sessions:
            # Obtener último mensaje
            last_msg_q = await db.execute(
                select(MessageHistory)
                .where(MessageHistory.chat_id == s.chat_id)
                .order_by(desc(MessageHistory.timestamp))
                .limit(1)
            )
            last_msg = last_msg_q.scalar_one_or_none()

            # Contar mensajes totales
            count_q = await db.execute(
                select(func.count(MessageHistory.id)).where(
                    MessageHistory.chat_id == s.chat_id
                )
            )
            msg_count = count_q.scalar()

            result.append({
                "chat_id": s.chat_id,
                "current_state": s.current_state,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "message_count": msg_count,
                "last_message": {
                    "role": last_msg.role,
                    "body": last_msg.body[:120],
                    "timestamp": last_msg.timestamp.isoformat(),
                } if last_msg else None,
            })

    return result


@router.get("/api/conversations/{chat_id}", dependencies=[Depends(verify_admin)])
async def get_conversation(chat_id: str):
    """Historial completo de mensajes de una conversación."""
    async with SessionLocal() as db:
        msgs_q = await db.execute(
            select(MessageHistory)
            .where(MessageHistory.chat_id == chat_id)
            .order_by(MessageHistory.timestamp.asc())
        )
        messages = msgs_q.scalars().all()

        if not messages:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")

        return [
            {
                "id": m.id,
                "role": m.role,
                "body": m.body,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in messages
        ]


# ──────────────────────────────────────────────────────────────────────────────
# PRODUCTOS — CRUD
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/products", dependencies=[Depends(verify_admin)])
async def list_products(category: Optional[str] = None, active_only: bool = False):
    """Lista todos los productos, con filtros opcionales."""
    async with SessionLocal() as db:
        query = select(Product)
        if category:
            query = query.where(Product.category == category)
        if active_only:
            query = query.where(Product.active == True)
        query = query.order_by(Product.category, Product.id)

        result = await db.execute(query)
        products = result.scalars().all()

        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": float(p.price),
                "stock": p.stock,
                "category": p.category,
                "active": p.active,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in products
        ]


@router.post("/api/products", dependencies=[Depends(verify_admin)], status_code=201)
async def create_product(data: ProductCreate):
    """Crea un nuevo producto en el catálogo."""
    valid_categories = {"tech", "phones", "audio"}
    if data.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Categoría inválida. Usa: {valid_categories}")

    async with SessionLocal() as db:
        product = Product(
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            category=data.category,
            active=data.active,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)

        return {
            "id": product.id,
            "name": product.name,
            "price": float(product.price),
            "category": product.category,
            "message": "Producto creado con éxito.",
        }


@router.put("/api/products/{product_id}", dependencies=[Depends(verify_admin)])
async def update_product(product_id: int, data: ProductUpdate):
    """Actualiza los campos de un producto existente."""
    async with SessionLocal() as db:
        q = await db.execute(select(Product).where(Product.id == product_id))
        product = q.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado.")

        if data.name is not None:        product.name = data.name
        if data.description is not None: product.description = data.description
        if data.price is not None:       product.price = data.price
        if data.stock is not None:       product.stock = data.stock
        if data.category is not None:    product.category = data.category
        if data.active is not None:      product.active = data.active
        product.updated_at = datetime.utcnow()

        await db.commit()
        return {"message": f"Producto #{product_id} actualizado con éxito."}


@router.delete("/api/products/{product_id}", dependencies=[Depends(verify_admin)])
async def delete_product(product_id: int):
    """Desactiva un producto (soft delete — no borra de la BD)."""
    async with SessionLocal() as db:
        q = await db.execute(select(Product).where(Product.id == product_id))
        product = q.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado.")

        product.active = False
        product.updated_at = datetime.utcnow()
        await db.commit()
        return {"message": f"Producto #{product_id} desactivado del catálogo."}
