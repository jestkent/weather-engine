# 1. Base Image
FROM python:3.11-slim

# 2. Set Folder
WORKDIR /app

# --- THE SPEED FIX ---
# We install the libraries BEFORE copying your code.
# Docker will "Cache" this step. It won't run again unless you add a new library.
RUN pip install --no-cache-dir streamlit pandas pytz requests plotly
# ---------------------

# 3. NOW copy your code
# If you change app.py, Docker only starts working from HERE.
COPY . /app

# 4. Create data folder
RUN mkdir -p /app/data

# 5. Run it
EXPOSE 8501
CMD ["sh", "-c", "python3 run_forever.py & python3 -m streamlit run app.py --server.address=0.0.0.0"]