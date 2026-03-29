# Filament Manager 🧵
*Current version: **v1.41.0***

A minimalist and modern web application for tracking and managing 3D printer filaments.
The application allows detailed tracking of weight balances, material costs, and also includes a calculator for a precise print cost estimation of a given model (in grams relative to the spool's total weight).

## Key Features
- **Clear Dashboard:** View all your filaments (brand, color, material, remaining weight) in one place. Includes visual progress bars, low-stock/out-of-stock indicators, and both card and list views. Supports fulltext filtering by brand, material, and color with persistent sort preferences.
- **Projects System:** Plan and track ongoing 3D prints as unified "Projects". Store details, client names, due dates, and attached files (e.g., `.3mf`). Connect allocated materials via the Print Planning module to gracefully deduct them from the inventory stock when printed. Link external resources with rich link previews.
- **Print Calculator:** Before starting a print enter the model weight from your slicer and the estimated print time. You instantly see how much the specific part will cost (including calculated electricity consumption). The page saves a **history of your previous calculations**.
- **Statistics Dashboard:** A fully customizable dashboard with 7 draggable/hideable sections: KPI overview, stock health and turnover charts, forecast tables, purchase recommendations, project analytics, and a color palette. Section order, hidden cards, and per-card record limits are persisted per browser via `localStorage`.
- **Storage Shelf Map:** Visualize where each spool lives on your physical shelves. Assign spools to named shelf slots, move or reorient them, and see stock levels at a glance on the shelf grid.
- **Bambu Cloud Integration:** Sync print jobs from Bambu Lab printers. Assign jobs to projects and optionally deduct material usage directly from inventory.
- **Movement History:** Full audit log of every filament weight change with reasons and timestamps.
- **Custom Dictionaries:** Pre-configured with popular manufacturers, materials, and colors. Everything can be freely expanded, renamed, and safely deleted in the base Settings.
- **Multi-Language Support:** Natively supports both English and Czech.
- **Full Backup / Restore:** Export the entire application state (inventory, history, projects, settings, Bambu jobs) as a compressed `.json.gz` archive including uploaded project files. Import accepts both the compressed format and older plain `.json` backups.

## Technologies Used 🛠️
The application is built and bundled within Python, making it lightweight, reliable, and instantly portable.
- Backend logic: **Python 3.11 (Flask)**
- Database & ORM: **SQLite3** communicating via the **Flask-SQLAlchemy** framework
- Frontend rendering engine: **Jinja2**
- Frontend design library: **TailwindCSS** via CDN
- Reactive UI state: **Alpine.js 3.x** via CDN (inventory filters, sort, view toggle)
- Charts: **Chart.js** via CDN (statistics dashboard)
- UI Icons: **FontAwesome**

## Quick Deployment via Docker 🐳
This package includes an optimized `Dockerfile` and `docker-compose.yml`. You can install it on your server natively in a matter of minutes.

**A. Build and Run:**
1. In your Linux server shell, navigate to the repository directory:
   ```bash
   cd /opt/git/filament/
   ```
2. Start and detach the docker containers
   ```bash
   docker compose up -d --build
   ```

**B. Access:**
1. Go to your local browser and enter the URL: `http://localhost:5050` (Using your machine's IP, e.g., `http://192.168.x.x:5050`)
2. On the first launch, the local `filament.db` file will be automatically crafted and safely mounted inside the `./data/` folder block. Basic catalogs (colors, producers, materials) will be sequentially loaded into the DB.

## Safe Backups
The whole backend database portfolio resides locally within your mounted project layout.
It's fully sufficient to just safely backup your `/opt/git/filament/data/` folder if needed.
The built-in Settings export downloads a compressed `.json.gz` backup that also contains uploaded project files, while import accepts both the new compressed format and older plain `.json` backups.
During version upgrades, standard rebuilding the app instance triggers natively, while seamlessly linking back to your original uncompromised DB location. Users do not lose tracking metrics.
