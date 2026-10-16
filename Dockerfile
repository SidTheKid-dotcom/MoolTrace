# FastAPI (4317) + Next.js viewer (4318). Hosted demo sets MOOLTRACE_PUBLIC_DEMO=1.
# Compose writes /data/demo.db. It never mounts data/mooltrace.db.

FROM python:3.14-slim-trixie AS api
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MOOLTRACE_DB=/data/demo.db \
    MOOLTRACE_API_HOST=0.0.0.0 \
    MOOLTRACE_API_PORT=4317 \
    MOOLTRACE_MAILTO=mooltrace-demo@example.com \
    MOOLTRACE_CORS_ORIGINS=http://127.0.0.1:4318,http://localhost:4318
COPY pyproject.toml README.md LICENSE ./
COPY mooltrace ./mooltrace
COPY examples ./examples
COPY scripts/docker-entrypoint-api.sh /entrypoint.sh
RUN pip install --no-cache-dir --only-binary falkordblite . \
    && chmod +x /entrypoint.sh \
    && mkdir -p /data
EXPOSE 4317
ENTRYPOINT ["/entrypoint.sh"]

FROM node:20-bookworm-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG MOOLTRACE_API_ORIGIN=http://api:4317
ENV MOOLTRACE_API_ORIGIN=${MOOLTRACE_API_ORIGIN}
RUN npm run build
EXPOSE 4318
CMD ["npx", "next", "start", "--port", "4318", "--hostname", "0.0.0.0"]
