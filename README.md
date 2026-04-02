# Filament Manager 🧵
*Current version: **v1.45.2***

A minimalist and modern web application for tracking and managing 3D printer filaments.
The application allows detailed tracking of weight balances, material costs, and also includes a calculator for a precise print cost estimation of a given model (in grams relative to the spool's total weight).

## Key Features
- **Clean Overview + Dedicated Filament List:** The main page is now a focused operations overview, while `/filaments` holds the full stock browser with card/list views, progress bars, low-stock indicators, filtering, sorting, saved views, and remembered card/list mode.
- **Action Center:** The overview dashboard highlights the most important operational tasks at the top: low-stock filaments, overdue projects, unmapped printer jobs, and printer sync issues.
- **Projects System:** Plan and track ongoing 3D prints as unified "Projects". Store details, client names, due dates, attached files, and links; compare estimate vs. actual material/time/margin; work from a tabbed workspace-oriented project detail; and reorder the project board widgets to match your workflow.
- **Print Calculator:** Before starting a print enter the model weight from your slicer and the estimated print time. You instantly see how much the specific part will cost (including calculated electricity consumption). The page saves a **history of your previous calculations**.
- **Statistics Dashboard:** A dual-mode dashboard: an executive overview for daily monitoring plus deeper switchable sections for planning, projects, and detail widgets. Layout customisation and saved browser-side presets are both supported.
- **Storage Shelf Map:** Visualize where each spool lives on your physical shelves. Assign spools to named shelf slots, move or reorient them, and see stock levels at a glance on the shelf grid. Frequent filter combinations can be stored as saved views.
- **Installation & Notifications:** Native PWA (Progressive Web App) support — easily install on your dashboard or mobile device. Elegant non-blocking Toast notifications via Alpine.js.
- **Bambu Cloud Integration:** Sync print jobs from Bambu Lab printers. Assign jobs to projects and optionally deduct material usage directly from inventory.
- **PrusaLink Integration:** Poll any Prusa printer on your local network via the PrusaLink REST API (no cloud account required). Add printers by IP address and API key; the background worker captures active and completed print jobs automatically.
- **Live Connected Printers:** An instantly auto-updating "Live Printers" dashboard grid summarizing all connected (both Prusa and Bambu) print statuses, current temps, progress, estimation logs, etc.
- **Movement History:** Full audit log of every filament weight change with reasons and timestamps.
- **Custom Dictionaries:** Pre-configured with popular manufacturers, materials, and colors. Everything can be freely expanded, renamed, and safely deleted in the base Settings.
- **Multi-Language Support:** Natively supports both English and Czech.
- **Full Backup / Restore:** Export the entire application state (inventory, history, projects, settings, Bambu jobs, PrusaLink printers and jobs) as a compressed `.json.gz` archive including uploaded project files. Import accepts both the compressed format and older plain `.json` backups.

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
