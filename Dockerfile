# 1. Use a lightweight version of Python
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy all your files into the container
COPY . /app

# 4. Install the required libraries (including plotly!)
RUN pip install --no-cache-dir streamlit pandas pytz requests plotly

# 5. Create the data directory (so the database has a home)
RUN mkdir -p /app/data

# 6. Open the door for the website
EXPOSE 8501

# 7. The command to run when the container starts
CMD ["sh", "-c", "python3 run_forever.py & python3 -m streamlit run app.py --server.address=0.0.0.0"]