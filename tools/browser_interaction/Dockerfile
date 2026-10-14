FROM node:22-alpine AS frontend-build

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tailwind.config.js postcss.config.js vite.config.js ./
COPY frontend ./frontend
COPY app/static ./app/static
RUN npm run build:frontend -- --outDir /bundle

FROM mcr.microsoft.com/playwright:v1.62.1-noble

WORKDIR /runner
COPY tools/browser_interaction/package.json tools/browser_interaction/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tools/browser_interaction/run.cjs ./run.cjs
COPY app/static /project/app/static
COPY --from=frontend-build /bundle /bundle
ENV PROJECT_ROOT=/project BUNDLE_ROOT=/bundle
CMD ["npm", "test"]
