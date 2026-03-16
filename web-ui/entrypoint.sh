#!/bin/sh
cat > /usr/share/nginx/html/config.js << EOF
window.__BRAIN_CONFIG__ = {
  apiUrl: "${BRAIN_API_URL:-http://localhost:8000}"
};
EOF
nginx -g "daemon off;"
