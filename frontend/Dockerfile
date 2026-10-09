# Builds the SPA and serves it with Caddy (HTTPS, security headers, /api proxy).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Default interface language and the ones users switch between, baked into
# the build (vite.config.ts).
ARG APP_LANGUAGE=en
ARG APP_LANGUAGES=
ENV APP_LANGUAGE=$APP_LANGUAGE APP_LANGUAGES=$APP_LANGUAGES
RUN npm run build

FROM caddy:2.11.4-alpine
COPY --from=build /app/dist /srv/frontend
