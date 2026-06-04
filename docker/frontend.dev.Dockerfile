###############################
# Frontend dev — static files are bind-mounted from the host.
# Edit app/static/** on the host; changes appear instantly with no rebuild.
###############################
FROM nginx:1.27-alpine

# Apply site config (proxy routes + SSE support).
# Static files come from the bind-mount defined in docker-compose-dev.yaml.
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
