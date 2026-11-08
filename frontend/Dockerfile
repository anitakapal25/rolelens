# Stage 1: build the static bundle with Node.
# glibc base: Vite 8 / Tailwind 4 ship native binaries; the lockfile was resolved on glibc Linux.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# The browser calls the API through nginx on the same origin (/api), so no CORS and SSE just works.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Stage 2: serve it with nginx. Node, node_modules and sources are left behind (~50 MB image).
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
