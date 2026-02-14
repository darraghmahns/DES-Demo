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

EXPOSE 8000

CMD ["python", "server.py"]
