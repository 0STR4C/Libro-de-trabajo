# Reutiliza las dependencias ya instaladas; no ejecuta pip ni descarga paquetes.
FROM librodetrabajo-app:latest
COPY --chown=10001:10001 CHANGELOG.md /app/CHANGELOG.md
COPY --chown=10001:10001 app /app/app
COPY --chown=10001:10001 tools/user_onboarding /app/tools/user_onboarding
