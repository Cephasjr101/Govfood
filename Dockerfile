FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
ENV GOVFOOD_DB=/var/data/govfood.db \
    GOVFOOD_UPLOADS=/var/data/uploads
RUN mkdir -p /var/data/uploads /app/frontend/uploads
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
