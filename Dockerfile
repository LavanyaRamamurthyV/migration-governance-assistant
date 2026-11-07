# Packages the app so it runs the same on any machine (laptop, server, OpenShift / Kubernetes).
#   docker build -t migration-assistant .
#   docker run -p 8501:8501 --env-file .env migration-assistant
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Build the search index from the masked documents committed in docs/indexed/ (needs internet once
# to download the small embedding model; otherwise it falls back to offline embeddings).
RUN python -m pipeline.run_pipeline --index-only

EXPOSE 8501
CMD ["streamlit", "run", "app/ui.py", "--server.address=0.0.0.0", "--server.port=8501"]
