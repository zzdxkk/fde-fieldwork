FROM python:3.11-slim
WORKDIR /app
COPY app /app
COPY deploy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt || true
CMD ["python3", "main.py"]
