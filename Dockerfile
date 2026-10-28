FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY council-dashboard/frontend/package*.json ./
RUN npm ci
COPY council-dashboard/frontend/app ./app
COPY council-dashboard/frontend/components ./components
COPY council-dashboard/frontend/lib ./lib
COPY council-dashboard/frontend/public ./public
COPY council-dashboard/frontend/next.config.js council-dashboard/frontend/tsconfig.json council-dashboard/frontend/next-env.d.ts ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY council-dashboard/backend/requirements-mission.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY council-dashboard/backend/mission ./mission
COPY --from=frontend /build/out /app/frontend/out
RUN useradd --create-home mission && chown -R mission:mission /app
USER mission
EXPOSE 8000
CMD ["sh", "-c", "uvicorn mission.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
