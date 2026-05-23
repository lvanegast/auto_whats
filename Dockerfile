# ==============================================================================
# Dockerfile optimizado para la aplicación Python auto-whats utilizando uv
# ==============================================================================

# Etapa 1: Construcción y descarga de dependencias
FROM python:3.12-slim AS builder

# Instalar uv de forma nativa desde la imagen oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Habilitar el guardado de cache de uv y definir variables de entorno
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copiar archivos de metadatos del proyecto primero
COPY pyproject.toml uv.lock* README.md ./

# Sincronizar las dependencias (sin instalar la app principal para aprovechar cache)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copiar el código fuente
COPY src/ ./src/

# Sincronizar la app completa (registra el script ejecutable 'auto-whats')
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ------------------------------------------------------------------------------
# Etapa 2: Imagen final optimizada y ligera
# ------------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema mínimas si fueran necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar el entorno virtual y la aplicación construida desde la etapa anterior
COPY --from=builder /app /app

# Poner el entorno virtual en el PATH para acceso directo
ENV PATH="/app/.venv/bin:$PATH"

# Definir variables de entorno de producción por defecto
ENV PORT=8000
ENV OPENWA_API_URL=http://openwa-gateway:2785

EXPOSE 8000

# Arrancar la aplicación usando la arquitectura modular de uv
CMD ["uv", "run", "auto-whats"]
