import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres-secret-pwd@localhost:5432/auto_whats_db"
)

# Crear el motor asíncrono de base de datos (con pool pre-configurado para rendimiento)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20
)

# Generador asíncrono de sesiones de SQLAlchemy
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Clase base declarativa para herencia de modelos
Base = declarative_base()

async def get_db():
    """
    Generador de sesiones asíncronas para inyección de dependencias o llamadas manuales.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
