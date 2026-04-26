# ── Stage 1: build frontend assets ─────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /build

# Install npm packages (JS libs + Tailwind CLI)
COPY package.json .
RUN npm install --ignore-scripts

# Build Tailwind CSS from templates
COPY tailwind.config.js .
COPY static/css/tailwind.input.css tailwind.input.css
COPY templates/ ./templates/
COPY static/js/ ./static/js/
RUN npx tailwindcss -i tailwind.input.css -o tailwind.css --minify

# Download Plus Jakarta Sans variable font subsets (weights 200–800).
# Latin Extended keeps Czech glyphs in the same family instead of browser fallback.
RUN apk add --no-cache curl && \
    mkdir -p fonts/files && \
    curl -sL "https://cdn.jsdelivr.net/npm/@fontsource-variable/plus-jakarta-sans@5.1.1/files/plus-jakarta-sans-latin-wght-normal.woff2" \
         -o fonts/files/plus-jakarta-sans-latin-wght-normal.woff2 && \
    curl -sL "https://cdn.jsdelivr.net/npm/@fontsource-variable/plus-jakarta-sans@5.1.1/files/plus-jakarta-sans-latin-ext-wght-normal.woff2" \
         -o fonts/files/plus-jakarta-sans-latin-ext-wght-normal.woff2

# ── Stage 2: Python application ──────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy built Tailwind CSS
COPY --from=frontend /build/tailwind.css static/css/tailwind.css

# Copy self-hosted JS libraries
RUN mkdir -p static/js
COPY --from=frontend /build/node_modules/alpinejs/dist/cdn.min.js static/js/alpine.min.js
COPY --from=frontend /build/node_modules/chart.js/dist/chart.umd.min.js static/js/chart.min.js
COPY --from=frontend /build/node_modules/online-3d-viewer/build/engine/o3dv.min.js static/js/o3dv.min.js

# Copy FontAwesome CSS + webfonts (npm package uses relative ../webfonts/ paths)
RUN mkdir -p static/webfonts
COPY --from=frontend /build/node_modules/@fortawesome/fontawesome-free/css/all.min.css static/css/fontawesome.min.css
COPY --from=frontend /build/node_modules/@fortawesome/fontawesome-free/webfonts/ static/webfonts/

# Copy Plus Jakarta Sans font files
RUN mkdir -p static/fonts/files
COPY --from=frontend /build/fonts/files/ static/fonts/files/

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app:app"]
