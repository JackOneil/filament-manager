# Filament Manager — Plán funkcionalit F9–F20

> Pokračování `implement.md` po hloubkové auditě projektu (general sub-agent průzkum celého kódu).
> Tyto funkce vycházejí ze skutečných mezer zjištěných v kódu, nikoliv z hypotetických nápadů.
> Pokrývají oblasti: integrace tiskáren (F9–F11), kalkulačka (F12), waste/ML (F13), vyhledávání (F14), mobilní/PWA (F15), bezpečnost/auth (F16), výkonnost tiskáren (F17), storage (F18), projekty (F19–F20).

Verze: **v1.121.0+** (rollováno postupně dle úsilí).

---

## Přehled F9–F20

| #    | Funkce                                                  | Kategorie              | Úsilí | Reactive na implement.md |
| ---- | ------------------------------------------------------- | ---------------------- | ----- | ------------------------ |
| F9   | OctoPrint REST API integrace                            | Integrations           | M     | ne                       |
| F10  | Moonraker/Klipper WebSocket integrace                   | Integrations           | L     | ne                       |
| F11  | PrusaConnect Cloud integrace                            | Integrations           | S     | ne                       |
| F12  | Plnohodnotný kalkulátor (labour/packaging/shipping/VAT)  | Calculator             | M     | ne                       |
| F13  | ML predikce selhání tisku + waste KPI dashboard         | Waste / Stats          | L     | volí F7 (event)          |
| F14  | Fulltextové vyhledávání FTS5 / tsvector                 | Frontend / API         | M     | volí F2 (API endpoint)   |
| F15  | Web Push notifikace + offline PWA filamente             | Mobile / PWA          | M     | volí F4 (SMTP stejné šablony) |
| F16  | 2FA/TOTP autentizace                                    | Auth / Security        | M     | ne                       |
| F17  | Využití tiskáren (uptime, MTBF, cost/hour)              | Stats / Printers        | M     | volí F2 (`/api/v1/printers/stats`) |
| F18  | Environmental sensors na poličkách (ESPHome/DHT22)     | Storage                | M     | volí F7 (event `storage.humidity_warning`) |
| F19  | Custom status workflow designer pro projekty            | Projects               | L     | ne                       |
| F20  | Gantt timeline + multi-printer job splitting             | Projects / Printers    | L     | ne                       |

---

# F9 — OctoPrint REST API integrace

## Cíl (grounded in audit)
Stávající integrace pokrývají pouze Bambu Cloud a PrusaLink místní REST. Audit confirmil oblíbený open-source stack OctoPrint (REST)complement není podporován, což blokuje uživatele s vlastním hardware (Ender, Voron, MK3 bez PrusaLink). Viz `BACKLOG.md` BL-001 (`OctoPrint/moonraker` — Backlog).

## Datový model
```python
class OctoPrinter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    host = db.Column(db.String(255), nullable=False)          # http://192.168.x.x
    api_key = db.Column(db.Text, nullable=False)             # encrypted via encrypt_token
    printer_model = db.Column(db.String(100), nullable=True) # z /api/version printer_profile
    notes = db.Column(db.Text, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_sync_at = db.Column(UtcDateTime, nullable=True)
    last_success_at = db.Column(UtcDateTime, nullable=True)
    last_sync_status = db.Column(db.String(255), nullable=True)
    power_draw_watts = db.Column(db.Integer, nullable=True)
    created_at = db.Column(UtcDateTime, default=_utc_now)

class OctoPrintJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('octo_printer.id', ondelete='SET NULL'), nullable=True, index=True)
    printer_name = db.Column(db.String(200), nullable=True)
    file_name = db.Column(db.String(300), nullable=True)
    display_name = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(50), nullable=True, index=True)  # printing, paused, operational, error, cancelled
    started_at = db.Column(UtcDateTime, nullable=True)
    finished_at = db.Column(UtcDateTime, nullable=True)
    weight_grams = db.Column(db.Float, nullable=True)             # z g-code metadata
    cost_time = db.Column(db.Integer, nullable=True)             # sekundy
    progress = db.Column(db.Float, nullable=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='SET NULL'), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='SET NULL'), nullable=True, index=True)
    deducted = db.Column(db.Boolean, nullable=False, default=False)
    raw_payload = db.Column(db.Text, nullable=True)
    synced_at = db.Column(UtcDateTime, default=_utc_now)
```

## Backend
- **Nový blueprint** `routes/octoprint.py` + `routes/octoprint_helpers.py` (pattern dle `bambu.py`+`bambu_helpers.py`).
  - `GET /octo` — dashboard tiskáren + jobů.
  - `POST /octo/printer/add` — admin přidá tiskárnu, test připojení.
  - `POST /octo/printer/<id>/sync` — poll /api/job + /api/printer.
  - `POST /octo/job/<id>/map` — přiřadí filament & projekt, dedukce skladu.
  - `DELETE /octo/job/<id>`.
- **Worker** `octo-sync-worker` (interval 30–60s, backoff → 900s) — pattern přímo z `routes/prusa.py` `do_poll()`.
  - Endpointy OctoPrint: `/api/job` (aktuální job), `/api/printer` (teploty, stav), `/api/version` (printer_profile).
  - Dedukce: job completion → `log_movement` s `action_type='octo_print'` (rozšířit `movement_action_label()`).
- **Auth**: API key v hlavičce `X-Api-Key`, IP validace `validate_printer_host()` (BUG-511).
- **Mapování**: `SECTION_BY_ENDPOINT` → `'printers'`.

## Frontend (GUI)
- `templates/octo.html` — analog `prusa.html` (filter pills, job cards).
  - Dlaždice tiskáren + online/offline badge.
- Nový `static/js/octo-filter.js` (analog `bambu-filter.js`).
- Sidebar toggle `nav_octo_enabled` v `base.html` (analog `nav_prusa_enabled`).
- **i18n**: ~25 klíčů `octo_*`.

## Testy
`tests/test_octoprint.py` (pattern `test_prusa*`): mock `requests.get` na `/api/job`, dedukce RBAC, idempotence.

## Pravidla
4, 13, 15 (backup),17 (worker), 19, 25 (translate), 30 (help.js), 32 (BACKLOG BL-709).

## Úsilí
M — ~2 dny.

---

# F10 — Moonraker/Klipper WebSocket integrace

## Cíl
Klipper firmware (přez Moonraker) je de facto standard moderních tiskáren (Voron, RatRig, custom Ender). Audit potvrdil absenci jakékoliv Klipper integrace. Moonraker podporuje WebSocket — observační `printer.objects.list` subscriptions → real-time push (na rozdíl od pollingu Bambu/Prusa).

## Architektura
- WebSocket client (`websockets` balíček do `requirements.txt`).
- Background worker udržuje persistentní spojení per printer; restartuje při chybě/reconnect.
- Příchozí zprávy → update/match na `OctoPrintJob`-like MongoDB… nebo nová `KlipperPrinter` + `KlipperPrintJob` (zrcadlí stávající model工程施工).
- Object subscriptions:
  - `print_stats.state` → PRINTING / PAUSED / COMPLETE / ERROR / STANDBY
  - `print_stats.filename`, `print_stats.total_duration`, `print_stats.print_duration`
  - `display_status.progress` → 0..1
  - `virtual_sdcard.progress` → fallback
  - `extruder.temperature`, `heater_bed.temperature` → snapshot dashboard (F8).
- POST `/printer/print/start`, `/printer/print/cancel`, `/printer/print/pause`, `/printer/print/resume` — quick actions přes proxy.
- G-code metadata: Moonraker `/server/files/metadata?filename=...` vrací `filament_total`, `estimated_time` → předvyplní weight_grams.

## Datový model
```python
class KlipperPrinter(db.Model):
    id, name, host (ws://192.168.x.x:7125/websocket), api_key (nullable — Moonraker trusted networks často bez tokenu),
    printer_model, notes, enabled, last_sync_at, last_success_at, last_sync_status, power_draw_watts, created_at

class KlipperPrintJob(db.Model):
    id, printer_id (FK SET NULL), printer_name, file_name, display_name, status, started_at, finished_at,
    weight_grams, cost_time, progress, filament_id, project_id, deducted, raw_payload, synced_at
```

## Backend
- `routes/klipper.py` + `routes/klipper_helpers.py`.
- Worker `klipper-ws-worker` (per-printer async task, ne thread). Použít `threading.Thread` + `asyncio.run` (zpráva dává `app.test_request_context` pro DB flush) — pattern blízký existujícím 3 workerům.
- Připojení `wss://` pokud `host` začíná `wss://` — TLS.
- Heartbeat ping/pong 30s.

## Frontend
- `templates/klipper.html` — analog `prusa.html`.
- Live temperature graphy (Chart.js lazy-load přes `loadScript()` Rule 27).
- Quick actions: pause/resume/cancel.

## Testy
`tests/test_klipper.py` — mock WebSocketiran `websockets` stub (najít pattern v tests/test_bambu.py pro HTTP mock).

## Pravidla
4, 13, 15, 17, 19, 27, 30, 32.

## Úsilí
L — ~3 dny (WebSocket lifecycle nejkomplikovanější část).

---

# F11 — PrusaConnect Cloud integrace

## Cíl (grounded)
Stávající `PrusaPrinter` podporuje pouze místní PrusaLink REST API. Uživatelé bez lokálního přístupu (tiskárna mimo síť, na LAN mimo uživatele) nemají cloud sync. PrusaConnect Cloud API (https://connect.prusa3d.com/) nabízí REST + MQTT stejné payload jako PrusaLink.

## Architektura
- Rozšíření `PrusaPrinter` o `cloud_token` (Fernet) a `cloud_enabled` columny.
- Worker `prusa-cloud-worker` (interval 60s) volá PrusaConnect REST `/v1/printers/<device_id>/jobs`+ `/v1/printers/<device_id>/status`.
- Reuse esfor `PrusaPrintJob` model — přidat `source = db.Column(db.String(20), default='local')`  # 'local', 'cloud'.
- Deduplikace: přirozený klíč `(printer_id, file_name, started_at)`.

## Pravidla
4, 13, 15, 17, 19, 30, 32 (BL-711).

## Úsilí
S — ~1 den (přidaná metoda k existujícímu modulu).

---

# F12 — Plnohodnotný kalkulátor (labour + packaging + shipping + VAT)

## Cíl (grounded)
Stávajní `ProjectQuote` kumuluje `material_cost + electricity_cost` → margin → `final_price`. Audit confirmil chybějící cost komponenty: **labour** (modelování/podpora), **packaging**, **shipping**, **VAT/sales tax** (pro účely faktur). Toto je největší calculátor gap.

## Datový model
Rozšířit `ProjectQuote`:
```python
labour_minutes = db.Column(db.Integer, nullable=False, default=0)
labour_hourly_rate = db.Column(db.Numeric(10,2), nullable=False, default=0.0)
packaging_cost = db.Column(db.Numeric(10,2), nullable=False, default=0.0)
shipping_cost = db.Column(db.Numeric(10,2), nullable=False, default=0.0)
waste_factor_pct = db.Column(db.Float, nullable=False, default=0.0)        # % odpadu připočítá se k material cost
tax_rate_pct = db.Column(db.Float, nullable=False, default=0.0)            # VAT/sales tax %
tax_amount = db.Column(db.Numeric(10,2), nullable=False, default=0.0)
total_with_tax = db.Column(db.Numeric(10,2), nullable=False, default=0.0)
```

Nová tabulka `LabourRate`:
```python
class LabourRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False)               # "Modelování", "Podpora", "Příprava"
    hourly_rate = db.Column(db.Numeric(10,2), nullable=False)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(UtcDateTime, default=_utc_now)
```

## Backend
- `routes/calculator.py` rozšířit formulář o inputy.
- `ProjectQuote` přepočet_extendovat `final_price = base_cost + labour_cost + packaging + shipping + margin_amount`, `tax_amount = final_price * tax/100`, `total_with_tax = final_price + tax_amount`.
- `AppSetting`: `default_waste_factor_pct`, `default_tax_rate_pct`, `default_packaging_cost`.
- Worker rozšiřuje F6 faktura (invoice PDF obsahuje nové řádky).

## Frontend
- `templates/calculator.html` a `calculator_project.html` — nové pole accordion "Další náklady".
- Live přepočet přes Alpine.js `x-effect`.
- `templates/quote_export.html` obsahuje tabulku s rozdělením base/material/electric/labour/packaging/shipping/tax.

## Testy
`tests/test_calculator.py` rozšíření — assert że labour, packaging, tax se započítají.

## Pravidla
1, 2 (migrace `_safe_alter`), 15 (backup), 18 (README), 32.

## Úsilí
M — ~1.5 dne.

---

# F13 — ML predikce selhání tisku + Waste KPI dashboard

## Cíl (grounded)
`WasteRecord` dataset je bohatý: filament + brand + material + printer + teploty (z `Project.quality_*`) + reason. Audit confirmil absenci jakékoliv analýzy korelace mezi konfigurací tisku (material/brand/printer/nozzle_temp/bed_temp) a reason waste. Navíc **F8 (waste KPI)** je contemplate; Zde davame **modelhely sadu statistik + heuristický model** založený na `sklearn`-like rozhodovací strom (self-host, no AI platform dependency).

## Datový model
```python
class PrintFailureRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rule_json = db.Column(db.Text, nullable=False)            # JSON: {"material":"PLA","brand":"Prusa","reason":"warping","rate_pct":42}
    confidence = db.Column(db.Float, nullable=False, default=0.0)  # 0..1 — coverage
    failure_rate = db.Column(db.Float, nullable=False, default=0.0)  # historical waste %
    last_recompute_at = db.Column(UtcDateTime, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(UtcDateTime, default=_utc_now)
```

## Backend
- `routes/forecast.py` extendovat (společný modul s F5) o `compute_waste_correlations()`:
  - Grupbuscar `WasteRecord` podle `(material, brand, reason)` → frekvenční tabulka.
  - Lambda: `rate = waste_count / (waste_count + success_count)` per kombinaci.
  - Persistovat top 20 pravidel do `PrintFailureRule`, přepočet workerem `waste-analytics-worker` (1x denně).
  - Heuristika (no external deps): `collections.Counter` + `statistics.mean`.
- **Warning v UI**: na detailu projektu / prida-waste modal inspectujte `PrintFailureRule` pro (material, brand) → alert "Kombinace X+Y má 32 % warp rate (12 wastes / 37 prints)".
- **Waste KPI dashboard** v `stats.html` nová sekce `section_waste` (Rule 16):
  - Waste rate % trend (line chart).
  - Waste by reason (doughnut).
  - Waste by material (bar).
  - Waste cost sum (cumple months) (sparkline).
  - Top failing combinations (table).

## Frontend
- `stats.html` nová sekce (přidat do sortable list `stats_layout_v2`).
- Waste modal výstražný banner Alpine.js-bound (badge near save button).

## Testy
`tests/test_waste_analytics.py`:
- Compute waste rules z synthetic dataset.
- Recomputate worker invaliduje stará pravidla.
- Alert rendering v project detail HTML.

## Pravidla
16, 22, 29, 30, 32.

## Úsilí
L — ~2.5 dne (model heuristiky, worker, sekce, modal).

---

# F14 — Fulltextové vyhledávání (FTS5 / tsvector)

## Cíl (grounded)
`/api/search` audit confirmoval simple `LIKE` query jen na `Project.name` a `Filament.name`. Není možné hledat v notes, comments, descriptions, brand. Pro projectES je velký inventar nevyhnutelná fulltext index (nativní FTS5 v SQLite + `tsvector` v PostgreSQL).

## Architektura
- Virtual table `search_index`:
  - SQLite: `CREATE VIRTUAL TABLE search_fts USING fts5(entity_type, entity_id, content, tokenize='unicode61')`.
  - PostgreSQL: `GENERATED COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED` + GIN index.
- Trigger / `after_commit` hook v SQLAlchemy: po insert/update `Project`, `Filament`, `ProjectComment`, `ModelComment`, `ProjectFile.model_note` sync `search_fts`.
  - Implementation: `event.listen(Filament, 'after_insert', _sync_fts)` — @app context pro přístup k session.execute raw SQL.
- API `GET /api/search?q=...` (AJAX) vrací:
  ```json
  [{"entity_type":"project","id":12,"title":" Motorcycle helmet","snippet":"...","url":"/projects/12"}, ...]
  ```
- Výstup vykreslen v command pallete (Ctrl+K `app-shell.js`) — rozšířit `fetchResults()` (BUG-519 fixed) o volání `/api/search`.

## Frontend
- Ctrl+K command paleta — nová sekce "Výsledky vyhledávání".
- `/search` plnostránková evidence (volitelné).
- Snippet highlight přes `<mark>`.
- i18n: `search_no_results`, `search_hint`, `search_short_query`.

## Migrace
- `migrations.py`: `_safe_alter(app, "CREATE VIRTUAL TABLE ...")` pro SQLite — avšak jiz pak `_run_fts_reindex()` poprvé naplní index přes `INSERT INTO search_fts SELECT ...`.

## Testy
`tests/test_search.py`:
- Insert filament "Prusa PLA Orange" → search "oran" → match.
- Insert comment "XYZ" → search nalezne.
- PostgreSQL-specific ignore pro SQLite testy (`@pytest.mark.skip_if_sqlite`).

## Pravidla
14 (no upload), 19, 25, 29, 32.

## Úsilí
M — ~2 dny (FTS5 + tsvector dual-bend).

---

# F15 — Web Push notifikace + offline PWA filament listing

## Cíl (grounded)
Audit confirmed: notification bell polling jen AJAX; service worker `sw.js` kešuje pouze static assets, ne HTML. Mobilní uživatelé nemohou dostat notifikace když app není otevřená, a offline nemohou procházet inventář.

## Architektura

### Web Push
- VAPID keys vygenerovány přes `pywebpush` (`requirements.txt`). Privátní klíč v `AppSetting.vapid_private_key` (Fernet), veřejný `vapid_public_key` (plain).
- DB: `PushSubscription`:
  ```python
  class PushSubscription(db.Model):
      id = db.Column(db.Integer, primary_key=True)
      user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
      endpoint = db.Column(db.String(500), nullable=False, unique=True)
      p256dh = db.Column(db.String(200), nullable=False)
      auth = db.Column(db.String(100), nullable=False)
      created_at = db.Column(UtcDateTime, default=_utc_now)
      last_used_at = db.Column(UtcDateTime, nullable=True)
  ```
- Frontend: `static/js/push.js` (lazy `loadScript` Rule 27):
  - `navigator.serviceWorker.ready` → `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })`.
  - POST `/push/subscribe` s endpoint+p256dh+auth.
- Backend worker `push-worker` (interval 60s): queue notif `Notification.unsent_push` flag → odešle přes `webpush()` pywebpush → označí.
  - Návaznost na F4 (SMTP worker) — stejné šablony vrátí (subject, body).
  - Akce "Označit jako přečtené" → notifikace obsahuje URL s `?notif_id=X`; SW při kliku otevírá URL + POST mark_read.

### Offline PWA filament listing
- `sw.js` rozšířit o Pull-Through Cache pattern:
  - Cache-First pro static assets (již existuje).
  - Stale-While-Revalidate pro `/filaments?view=compact` (cache HTML 60s) + `/api/filaments-list` (cache 30s).
- IndexedDB synchonize:    	
  - `static/js/offline.js` (lazy načtení na `/filaments`) uloží posledních 100 filamentů do IndexedDB na každém fetch.
  - Pokud offline → manifest fallback `/_offline/filaments` route servíruje HTML, který vykreslí data z IndexedDB (Alpine.js).

## Backend
- `routes/push.py` blueprint (nový):
  - `POST /push/subscribe` (auth user).
  - `POST /push/unsubscribe` (auth user).
  - `POST /push/test` (admin).
- `routes/pwa.py` rozšířit `/sw.js` o push event handler + offline cache.
- Worker přidán v `app.py` (4. daemon thread).
- `AppSetting`: `push_enabled`, `vapid_public_key`, `vapid_private_key`.

## Frontend
- Account settings — checkbox "Povolit push notifikace".
- Browser permission request button (HTTPS requirement highlight pro self-host).
- Service Worker — `push` event `self.registration.showNotification()` s action buttony (Mark as read / View).

## Testy
`tests/test_push.py`: subscribe/unsubscribe RBAC; worker delivers with fake webpush.
`tests/test_pwa.py`: service worker snippet FTS search `/sw.js` vrací required patterns.

## Pravidla
2, 4, 14 (HTTPS only), 17, 19, 27, 30, 32.

## Úsilí
M — ~2 dny (VAPID + worker + SW patterns).

---

# F16 — 2FA/TOTP autentizace

## Cíl (grounded)
Audit confirmed absence 2FA completely. Pro self-host s veřejně exponovanými instancemi (expose via Tailscale, Cloudflare Tunnel) je 2FA standardní bezpečnostní požadavek.

## Datový model
```python
class UserTwoFactor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    secret = db.Column(db.String(64), nullable=False)           # TOTP secret (Fernet)
    recovery_codes = db.Column(db.Text, nullable=True)           # JSON array of bcryptoded hashes
    last_used_code = db.Column(db.String(10), nullable=True)     # prevent replay
    enabled_at = db.Column(UtcDateTime, nullable=True)
```

## Backend
- `pyotp` knihovna (`requirements.txt`) — standard RFC 6238.
- `routes/auth.py` rozšíření:
  - `GET /account/2fa/setup` — vygeneruje secret + QR URL (`pyotp.totp.TOTP(secret).provisioning_uri(email)`).
  - `POST /account/2fa/enable` — ověří první TOTP, uloží secret + recovery codes (10 kódů, bcrypt hash).
  - `POST /account/2fa/disable`.
  - Login flow: po úspěšném heslu, pokud `UserTwoFactor.enabled` → přesměrování na `/login/totp` (nová stránka), v session `pending_user_id` (expirace 5 min),服药 úvahy rate limit.
- Bypass mechanismy: recovery codes (`hashlib.sha256(code).hexdigest()` porovnáníní s uloženými — jeden used, ostatní smazány).
- `AppSetting`: `force_2fa_for_admin` boolean (admin enforce).

## Frontend
- `auth_login.html` — detekce `pending_user_id` → redirect.
- `templates/auth_totp.html` — jeden input + jumlah 6 digitní formát.
- `templates/auth_totp.html` recovery codes display po enable (jednorázově).
- `templates/account.html` — new section "2FA".
- `templates/auth_activate.html` — banner "Admin účty vyžadují 2FA" pokud `force_2fa_for_admin`.

## Testy
`tests/test_2fa.py`:
- Regenerate secret, verify valid TOTP, rejection invalid.
- Recovery code flow (single use).
- Force 2FA pro admin blokuje login bez 2FA setup.
- Session expiration 5 min.

## Pravidla
2, 4, 19 (security-sensitive), 25, 32.

## Úsilí
M — ~1.5 dne.

---

# F17 — Využití tiskáren (uptime, MTBF, cost/hour)

## Cíl (grounded)
Stats dashboard currently má heatmap usage ale no per-printer analytics. Pro tisk farmy klíčové vědět: kterýprinter je nevyužitý, kolik stojí jedna hodina provozu, MTBF (Mean Time Between Failures) — vztahně k `PrinterMaintenance`.

## Datový model
Volitelné (lookups nad existujícími modely). Lze přidat snapshot tabulka pro denní agregaci:
```python
class PrinterDailyStat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, nullable=False, index=True)
    printer_type = db.Column(db.String(20), nullable=False)      # 'bambu','prusa','octo','klipper'
    printer_id = db.Column(db.Integer, nullable=False, index=True)
    jobs_count = db.Column(db.Integer, nullable=False, default=0)
    total_print_seconds = db.Column(db.Integer, nullable=False, default=0)
    idle_seconds = db.Column(db.Integer, nullable=False, default=0)
    filament_grams = db.Column(db.Float, nullable=False, default=0.0)
    maintenance_count = db.Column(db.Integer, nullable=False, default=0)
```
- Worker `printer-stats-worker` 1x denně (01:00) aggreguje.

## Backend
- `routes/stats.py` nová sekce `section_printers`:
  - Využití % (24h / 7d / 30d).
  - Filament tlačen per printer (bar chart).
  - Cost/hour = (electricity + maintenance_cost_amortized) / print_hours.
  - MTBF = avg(printer_time_between_failures) — pro každý maintenance_type='fault'.
- `/api/v1/printers/stats` (F2 API).

## Frontend
- Stats page new draggable section (Rule 16/22).
- Tabbed view per printer (list s heatmapem).

## Testy
`tests/test_printer_stats.py`:
- Aggregation correct pro syntetická data (2 printers, 5 jobs, 1 maint).
- MTBF computation.

## Pravidla
2, 16, 22, 29, 32.

## Úsilí
M — ~1.5 dne.

---

# F18 — Environmental sensors na poličkách (ESPHome/DHT22/BME280)

## Cíl (grounded)
Audit confirmed žádné sensor integrace. Filament degradation závisí na okolních podmínkách (ideálně < 50 % humidity, 15–25 °C). Uživatelé s ESP8266/ESP32 + DHT22/BME280 mohou push-nout data přes HTTP POST endpoint. Systém warnne když podmínky exceed material-safe limity.

## Datový model
```python
class StorageShelfSensor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shelf_id = db.Column(db.Integer, db.ForeignKey('storage_shelf.id', ondelete='CASCADE'), nullable=True, index=True)  # nullable pro "global"
    name = db.Column(db.String(120), nullable=False)           # "ESP1"
    token = db.Column(db.String(64), nullable=False, unique=True, index=True)  #ötz autentizace
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_seen_at = db.Column(UtcDateTime, nullable=True)
    created_at = db.Column(UtcDateTime, default=_utc_now)

class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey('storage_shelf_sensor.id', ondelete='CASCADE'), nullable=False, index=True)
    recorded_at = db.Column(UtcDateTime, nullable=False, default=_utc_now, index=True)
    temperature_c = db.Column(db.Float, nullable=True)
    humidity_pct = db.Column(db.Float, nullable=True)
    co2_ppm = db.Column(db.Float, nullable=True)               # pro VOC/CO2 senzory optionally
    raw_payload = db.Column(db.Text, nullable=True)
```

## Backend
- `routes/sensors.py`:
  - `POST /sensors/<token>/push` — endpoint bez session auth, auth via token. Accept `temp`, `humidity`, `co2`.
    - Rate limit např. 1 req / 30s (sensory typicky periodicky postují).
  - `GET /sensors` — dashboard admin.
  - `POST /sensors/<id>/edit`, `DELETE /sensors/<id>`.
- **Validation**: `temp` v range (-40..125), `humidity` 0..100, `co2` 0..5000.
- **Alerts**: worker `sensor-alert-worker` (60s) check latest <24h čtení proti limity (PLA: <55 °C, <55 %). Překročení → `Notification`, F7 webhook `storage.environment_warning`, F4 e-mail.
  - Histereze: alert jen při přechodu OK → bad, ne při každém měření.

## Frontend
- `templates/sensors.html` nová stránka:
  - Tabulka senzorů (poslední hodnota, status, link na shelf).
  - Chart.js lazy line chart posledních 24h (Rule 27).
  - Threshold config per sensor (override globálních limitů).
- `templates/storage.html` — na poličce badge s aktuálními teplotou/vlhkostí a stavem (OK/warning/critical).

## Testy
`tests/test_sensors.py`:
- Push endpoint autentizace tokenem, validace ranges.
- Alert trigger při překročení, dedupe (no spam).
- RBAC admin only pro konfiguraci.

## Pravidla
4, 14 (no upload), 17, 19, 25, 30, 32.

## Úsilí
M — ~2 dny.

---

# F19 — Custom status workflow designer pro projekty

## Cíl (grounded)
`Project.status` má hardcoded 6 hodnot (`NEW`/`PENDING_APPROVAL`/`APPROVED`/`REJECTED`/`PRINTING`/`DONE`). Audit confirmil že admini často want custom workflows (např. "In QC", "Awaiting payment", "Shipped"). Kanban i stats dependují na hardcoded list.

## Datový model
- `AppSetting` `project_status_workflow_json` (Text):
  ```json
  {
    "statuses": [
      {"key": "NEW", "label_cs": "Nový", "label_en": "New", "color": "#888888", "order": 0, "is_done": false, "is_reject": false},
      {"key": "PRINTING", "label_cs": "Tisknu", "label_en": "Printing", "color": "#3b82f6", "order": 4, "is_done": false, "is_reject": false},
      {"key": "DONE", "label_cs": "Hotovo", "label_en": "Done", "color": "#22c55e", "order": 10, "is_done": true, "is_reject": false}
    ],
    "transitions": [
      {"from": "NEW", "to": "PRINTING", "role": "admin"},
      {"from": "PRINTING", "to": "DONE", "role": "any"}
    ]
  }
  ```
- Default: aktuálních 6 statuses.

## Backend
- `routes/projects.py`:
  - `_get_statuses()` — cached parser.
  - `project_edit` / `project_advance_status` validují přechod dle `transitions`.
  - `project_create` nový select místo hardcoded dropdown.
- Kanban (`_projects_layout.html`) načtena z `statuses`.
- Stats (`stats.py`) reflect dynamic statuses.
- **Migration**: jelikož `Project.status` je `String(20)`, custom klíče (např. `QC_PENDING`) jsou kompatibilní. Validace v routes (místo DB constraint).

## Frontend
- Settings → Projects → nový vizualní editor:
  - Drag cards per status (order).
  - Click card → label/cs/en/color/is_done/is_reject inputs.
  - Transition rules table (from → to → role).
  - "Save" + "Reset to defaults".
- Kanban board + filter pills → dynamické z workflow.

## Testy
`tests/test_workflow.py`:
- Add custom status "QC" → create project s tímto statusem.
- Transition rule zakazuje user → PRINTING → DONE → user rejected.
- Stats rozpozná custom finished status (`is_done=true`).

## Pravidla
1, 3, 16/22 (Kanban), 25, 30, 32.

## Úsilí
L — ~2 dny (UI editor nejkomplikovanější část).

---

# F20 — Gantt timeline + multi-printer job splitting

## Cíl (grounded)
Project page nemá žádnou scheduling vizualizaci (jen Kanban + kalendář strip). `ProjectPrintItem` je statická `quantity_total/done`. Audit confirmil absenci:
1. Gantt timeline (tasks per project across time).
2. Multi-printer queue — rozdělení print_items mezi tiskárny s estimated completion.

## Datový model
Rozšířit `ProjectPrintItem`:
```python
assigned_printer_type = db.Column(db.String(20), nullable=True)  # 'bambu','prusa','octo','klipper'
assigned_printer_id = db.Column(db.Integer, nullable=True)
planned_start_at = db.Column(UtcDateTime, nullable=True)
planned_end_at = db.Column(UtcDateTime, nullable=True)
estimated_minutes = db.Column(db.Integer, nullable=False, default=0)
sort_order_in_printer = db.Column(db.Integer, nullable=False, default=0)
```
Nová tabulka `PrintItemDependency` (sub-task závislosti):
```python
class PrintItemDependency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(..., nullable=False, index=True)
    from_item_id = db.Column(..., nullable=False)   # must finish first
    to_item_id = db.Column(..., nullable=False)       # starts after from
    type = db.Column(db.String(20), default='finish_to_start')  # Gantt typ
```

## Backend
- `routes/projects.py` nové endpointy:
  - `GET /projects/<id>/gantt` — JSON pro Gantt chart (tasks, dependencies, assigned printers).
  - `POST /projects/<id>/print_item/<item_id>/assign_printer` — přiřazení tiskárny.
  - `POST /projects/<id>/print_item/<item_id>/reschedule` — drag-change of planned_start_at.
  - `POST /projects/<id>/dependency` — add/remove dependency.
- **Auto-scheduling** heuristic:
  - Pro každý print_item bez dependency: assign na první volnou tiskárnu shora (tiskárny setříděné dle power_draw? no).
  - Compute `planned_end_at = planned_start_at + estimated_minutes`.
  - Pridružte k `expected_completion_at` projektu pro due_date warning.

## Frontend
- **`templates/_project_gantt.html`** — nový tab v project_detail:
  - **Knihovna**: `static/js/vendor/frappe-gantt.min.js` (npm dependency, self-host), lazy-load přes `loadScript()` Rule 27.
  - Interaktivní drag, zoom (day/week/month), dependency šipky.
  - Boční panel seznam printers s barvou.
- `templates/projects_index.html` — „Calendar" přepínač rozšířen o „Gantt".
- Bulk "Auto-assign printers" tlačítko (vyvolá backend heuristic, refresh Gantt).

## Testy
`tests/test_gantt.py` / `test_print_queue.py`:
- Auto-assign – 3 print items, 2 printers → rozdělí správně.
- Dependency – from_item neutlačí start to_item předčasně.
- RBAC edit print_item assignment.

## Pravidla
1, 2 (migrace), 14 (no upload), 25, 27 (lazy load), 30, 32 (BL-720).

## Úsilí
L — ~3 dny (Gantt knihovna, scheduling heuristic, drag frontend).

---

# Souhrnný implementační postup (F9–F20)

1. **F11 PrusaConnect** — nejjednodušší, přidává cloud k existujícímu Prusa modulu.
2. **F9 OctoPrint** — pattern 1:1 z Prusa, REST, opens door komunitě.
3. **F12 Calculator plnohodnotný** — nezávislý low-labour rozšíření.
4. **F16 2FA** — independent security bez závislostí.
5. **F14 FTS search** — independent infra.
6. **F15 Web Push + offline PWA** — závisí na existující infra (settings, account).
7. **F13 ML/stats waste** — závisí na worker infra z F4.
8. **F17 Printer stats** — doporučeno po F9 / F10 (data source pro OctoPrint/Klipper).
9. **F10 Moonraker/Klipper** — nejtěžší integrace; až user požadavky.
10. **F18 Sensors** — nezávislý, wohkowners s ESP32.
11. **F19 Custom workflow** — L úsilí, ale nezávislý; spustit koncem.
12. **F20 Gantt + multi-printer** — finální feature, vizuálně heavy.

## Závislosti
```
F9/F10/F11 ──► F17 (printer stats spotřebovává jobs)
F4 ──► F13 (waste worker emailem)
F14 nezávislý, ale volí F2 (API pro search)
F15 volí F4 (šablony notifikací)
F2 (already in part 1) ──► F13,F14,F17 (exponuje outputs přes API)
```

# Globální checklist pro F9–F20

- ✅ Každá funkce: bump version (`APP_VERSION`), `CHANGELOG.md`, `README.md`.
- ✅ `.kilo/ARCHITECTURE.md` — per feature nová data flow sekce (worker, blueprint).
- ✅ `.github/copilot-instructions.md` — sync.
- ✅ `.kilo/BACKLOG.md` — `BL-709` až `BL-720` evidence + status `Fixed in vX.Y.Z`.
- ✅ `static/js/help.js` — rozšíření pro Každou novou stránku/sekci.
- ✅ `requirements.txt` — `pyotp`, `pywebpush`, `websockets`, případně `frappe-gantt` (npm), `qrcode` (již v F3).
- ✅ `docker compose up -d --build` po každé nasazené funkci.
- ✅ Curl smoke pro nové endpointy.

## Odhad celkového úsilí F9–F20
~18–25 MD. Doporučeno rollování postupně napříč 3–5 minors verzí (v1.121.0, v1.122.0, v1.123.0), nikoli jeden megarelease.