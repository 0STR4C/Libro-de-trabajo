# Reconstruye código y frontend con dependencias ya instaladas; no usa la red.
FROM librodetrabajo-frontend-check:latest AS frontend-build
COPY frontend /build/frontend
COPY app/static /build/app/static
COPY tailwind.config.js postcss.config.js vite.config.js /build/
RUN npm run build:frontend

FROM librodetrabajo-app:latest
COPY --chown=10001:10001 CHANGELOG.md /app/CHANGELOG.md
COPY --chown=10001:10001 app /app/app
COPY --from=frontend-build --chown=10001:10001 /build/app/static/frontend /app/app/static/frontend
COPY --chown=10001:10001 tools/user_onboarding /app/tools/user_onboarding
