# Base image — slim Python, keeps the container small
FROM python:3.11-slim

# All subsequent commands run from /app inside the container
WORKDIR /app

# Copy just requirements first (Docker layer caching: if only main.py
# changes later, this pip install step won't need to re-run)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code
COPY . .

# Start the FastAPI app via uvicorn, listening on all interfaces so
# other containers on the Docker network (e.g., the orchestrator) can reach it
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]