# ---- Stage 1: Build frontend ----
FROM node:18-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_CLERK_PUBLISHABLE_KEY=""
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim
WORKDIR /app

# System deps (poppler for pdf2image, ca-certificates for MongoDB Atlas TLS)
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Python deps (prod — excludes heavy docling/ollama for ENGINE=openai)
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

# App source
COPY *.py ./
COPY test_docs/ ./test_docs/
COPY dist/.gitkeep ./dist/

# Built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["python", "server.py"]
