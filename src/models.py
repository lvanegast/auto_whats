from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship
from src.database import Base

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
