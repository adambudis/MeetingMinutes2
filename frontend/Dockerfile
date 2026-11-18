# syntax=docker/dockerfile:1.7
#
# MeetingMinutes frontend: static React build served by nginx, which also proxies /api to the
# backend and terminates HTTPS (self-signed certificate generated on first start).

# The JS build is platform-independent, so it always runs natively (fast even when the
# target platform is linux/arm64).
FROM --platform=$BUILDPLATFORM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run lint && npm test && npm run build

FROM nginx:1.30-alpine
RUN apk add --no-cache openssl
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/40-generate-cert.sh /docker-entrypoint.d/40-generate-cert.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-generate-cert.sh \
 && chmod +x /docker-entrypoint.d/40-generate-cert.sh \
 && rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    SERVER_HOSTS=localhost \
    BACKEND_UPSTREAM=backend:8000 \
    HTTPS_PORT=443 \
    MAX_UPLOAD_MB=500
EXPOSE 80 443
