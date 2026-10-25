# syntax=docker/dockerfile:1
FROM node:22-alpine AS deps
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY dashboard/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN adduser -S -u 10001 atlas
COPY --from=build --chown=atlas /app/.next/standalone ./
COPY --from=build --chown=atlas /app/.next/static ./.next/static
COPY --from=build --chown=atlas /app/public ./public
USER atlas
EXPOSE 3000
CMD ["node", "server.js"]
