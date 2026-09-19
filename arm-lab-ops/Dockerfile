FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
# iproute2: host-network compose can resolve tailscale0 without the Tailscale CLI.
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir p115client

COPY . .

# Image default is loopback (safe without host net / Tailscale).
# Lab compose sets ARM_OPS_BIND=tailscale on network_mode: host.
# Do not default to 0.0.0.0 — that publishes on the public NIC.
ENV ARM_OPS_BIND=127.0.0.1
ENV ARM_OPS_PORT=8055
EXPOSE 8055

CMD ["python", "ops_app.py"]
