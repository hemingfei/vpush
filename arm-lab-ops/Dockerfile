FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir p115client

COPY . .

# Host-network compose binds 127.0.0.1:8055. Do not default to 0.0.0.0.
ENV ARM_OPS_HOST=127.0.0.1
ENV ARM_OPS_PORT=8055
EXPOSE 8055

CMD ["python", "ops_app.py"]
