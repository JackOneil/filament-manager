# Filament Manager 🧵
*Current version: **v1.8.4***

A minimalist and modern web application for tracking and managing 3D printer filaments.
The application allows detailed tracking of weight balances, material costs, and also includes a calculator for a precise print cost estimation of a given model (in grams relative to the spool's total weight).

## Key Features
- **Clear Dashboard:** View all your filaments (brand, color, material) in one place. Includes a visual progress bar indicating how much filament is left on the spools.
- **1-Click Tracking Deduction:** A quick subtraction input makes it easy to deduct explicitly weighed amounts of grams from a spool once your print finishes. It automatically deducts empty spools from the overall stock inventory.
- **Print Calculator:** Before starting a print, simply enter the model's weight from your Slicer and the estimated print time. You will instantly see how much the specific part will cost (including calculated electricity consumption). The page automatically saves a **history of your precise previous calculations**.
- **Custom Dictionaries:** Pre-configured with popular manufacturers, materials, and colors. Everything can be freely expanded, renamed, and safely deleted in the base Settings.
- **Multi-Language Support:** Natively supports both English and Czech.

## Technologies Used 🛠️
The application is built and bundled within Python, making it lightweight, reliable, and instantly portable.
- Backend logic: **Python (Flask)**
- Database & ORM: **SQLite3** communicating via the **Flask-SQLAlchemy** framework
- Frontend rendering engine: **Jinja2**
- Frontend design library: **TailwindCSS** via CDN
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
During version upgrades, standard rebuilding the app instance triggers natively, while seamlessly linking back to your original uncompromised DB location. Users do not lose tracking metrics.
