from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import relationship
from src.core.database import Base

class UserSession(Base):
    """
    Modelo para almacenar y persistir los estados interactivos de cada cliente.
    """
    __tablename__ = "user_sessions"

    chat_id = Column(String, primary_key=True, index=True)
    current_state = Column(String, default="idle", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relación de uno a muchos con el historial de mensajes
    messages = relationship("MessageHistory", back_populates="session", cascade="all, delete-orphan")

class MessageHistory(Base):
    """
    Modelo para registrar el historial completo de mensajes y memoria contextual.
    """
    __tablename__ = "message_histories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, ForeignKey("user_sessions.chat_id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user" o "assistant"
    body = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relación inversa
    session = relationship("UserSession", back_populates="messages")


class Product(Base):
    """
    Catálogo de productos de la tienda. Gestionable desde el panel de administración.
    Categorías válidas: 'tech' | 'phones' | 'audio'
    """
    __tablename__ = "products"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    price       = Column(Numeric(10, 2), nullable=False)
    stock       = Column(Integer, default=0, nullable=False)
    category    = Column(String(50), nullable=False)   # "tech" | "phones" | "audio"
    active      = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
