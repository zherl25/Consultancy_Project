###############################
# Frontend — nginx static server + API reverse proxy
# Build context: project root (set in docker-compose.yaml)
###############################
FROM nginx:1.27-alpine

# Bake static assets into the image
COPY backend/static/ /usr/share/nginx/html/

# Apply our site config (replaces nginx default)
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
