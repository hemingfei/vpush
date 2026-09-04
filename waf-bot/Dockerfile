# sidecar helper runtime
FROM node:22-slim AS node

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM python:3.12-slim

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /app/node_modules /app/node_modules

WORKDIR /app
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" curl_cffi==0.16.0

COPY --chown=99:100 solver.js watchdog.py ./

ENV WAF_COOKIE_FILE=/data/waf_cookies.json
USER 99:100
CMD ["python", "/app/watchdog.py"]
