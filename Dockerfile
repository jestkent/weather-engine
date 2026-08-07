FROM python:3.11-slim

WORKDIR /app

# Install deps first so Docker caches this layer until requirements.txt changes.
# Use the pinned requirements file (not a hand-typed list) so the image matches dev.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Runtime dirs (databases + rotating logs). data is a volume mount point in prod.
RUN mkdir -p /app/data /app/logs

EXPOSE 8501

# Run the 24/7 collector and the dashboard together.
CMD ["sh", "-c", "python3 run_forever.py & python3 -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501"]
