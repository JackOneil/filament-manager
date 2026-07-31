# Filament Manager — Návrh nových funkcionalit a implementační plán

> Tento dokument obsahuje návrh nových funkcí (GUI i backend), které dále rozšiřují stávajícíFilament Manager v souladu s architekturou popsanou v `.kilo/ARCHITECTURE.md` a pravidly v `.github/copilot-instructions.md`.
> Každá funkce má: **cíl**, **uživatelský přínos**, **datový model**, **backend (route/migrace/i18n)**, **frontend (GUI)**, **testy**, **checklist dle pravidel (Rule 1–32)** a **odhad úsilí**.

Verze, do které se funkce plánují: **v1.120.0** (F1–F8) a **v1.121.0+** (F9–F20 z `implement-part2.md`).

> **Doplnění po hloubkové audity projektu** (general sub-agent průzkum celého kódu): níže v tomto dokumentu jsou po F8 uvedeny další funkce F9–F20, které navazují na skutečné mezery v kódu (FTS search, sériové QR vs. bulk-inline grid, OctoPrint/Moonraker, sensor shelf, ML predikce failure, 2FA, Klipper WebSocket, multi-printer queue). Detailní plány pro F9–F20 jsou v samostatném souboru **`implement-part2.md`** pro lepší orientaci; tento soubor je hlavním plánem pro F1–F8.

---

## Přehled navržených funkcí

| #   | Funkce                                            | Kategorie        | Úsilí | Pravidla ovlivněna           |
| --- | ------------------------------------------------- | ---------------- | ----- | ---------------------------- |
| F1  | Tracker sušení filamentu (Drying Tracker)         | Inventory / GUI  | M     | 1,2,3,4,15,17,19,20,22,30,32 |
| F2  | REST API s osobními API tokeny                   | Platforma        | L     | 1,2,3,4,15,19,29             |
| F3  | QR kódy pro cívky (tisk + PWA skener)             | Inventory / PWA  | M     | 1,2,4,14,27,30,32            |
| F4  | E-mailová notifikace (SMTP)                       | Platforma        | M     | 1,2,4,5,15,25,29             |
| F5  | Inteligentní predikce vyčerpání skladu (forecast) | Analytics / GUI  | M     | 1,22,29,30,32                |
| F6  | Fakturace a sledování plateb                      | Projects         | L     | 1,2,3,15,18,29,32            |
| F7  | Webhook systém pro automatizaci                  | Platforma        | M     | 1,2,3,4,15,19,29             |
| F8  | Živý dashboard tiskáren s bed-camera snapshoty   | Printers / GUI   | L     | 1,3,4,15,22,27,30            |

---

# F1 — Tracker sušení filamentu (Drying Tracker)

## Cíl
Vlhkost je nejčastější příčinou vadných tisků (PLA, PETG, nylon). Umožnit uživateli zaznamenávat sušící sezení ke každé cívce: start/stop časovač, teplota sušičky, cílová vlhkost, poznámka.
Systém navrhne sušení na základě toho, kdy bylo naposledy sušeno a jaký materiál je (materiálové výchozí sušicí parametry).

## Uživatelský přínos
- Na detailu filamentu nová záložka „Sušení".
- Tlačítko „Spustit sušení" otevře modal s prefillnutou doporučenou teplotou dle materiálu.
- Běžící sušení se ukazuje v Action Centeru a v přehledu vlhkosti („Na sušení: 3 cívky").
- Po dokončení záznam zaneseme do MovementHistory s `action_type='dry'` a do Filament.quality_drying text.
- Push notifikace (F4) po dokončení/nedokončení sušení.

## Datový model (`models.py`)

```python
class DryingSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filament_id = db.Column(db.Integer, db.ForeignKey('filament.id', ondelete='CASCADE'), nullable=False, index=True)
    started_at = db.Column(UtcDateTime, nullable=False, default=_utc_now, index=True)
    finished_at = db.Column(UtcDateTime, nullable=True, index=True)
    target_temp_c = db.Column(db.Integer, nullable=False)             # teplota sušičky
    target_humidity_pct = db.Column(db.Float, nullable=True)          # volitelné hygrometrické měření
    duration_minutes = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='running')  # running, finished, aborted
    started_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    filament = db.relationship('Filament', backref=db.backref('drying_sessions', lazy=True, cascade='all, delete-orphan'))
    started_by = db.relationship('User', backref=db.backref('drying_sessions', lazy=True))
```

Pro materiálová výchozí nastavení přidat do `AppSetting` JSON sloupec:

```python
drying_presets_json = db.Column(db.Text, nullable=True)  # {"PLA":{"temp_c":55,"hours":4},...}
```

## Backend

- **Migrace**: `_safe_alter(app, 'CREATE TABLE drying_session ...')` nepoužíváme — nová tabulka přes `db.create_all()`. Do `run_migrations()` přidat případné seed výchozích presetů (PLA/PETG/ABS/TPU/Nylon).
- **Nový blueprint** `routes/drying.py`:
  - `drying.start(filament_id)` → vyrenderuje detail se záložkou Sušení
  - `POST drying/start/<filament_id>` → vytvoří `DryingSession(status='running')`, validuje že už neběží
  - `POST drying/stop/<session_id>` → nastaví `finished_at`, `duration_minutes`, `status='finished'`, zapíše do MovementHistory `action_type='dry'`
  - `POST drying/abort/<session_id>` → `status='aborted'`
  - `DELETE drying/<session_id>` → admin only
  - `GET drying/active_partial` → AJAX partial pro Action Center widget
- **Rollback / bezpečnost**: `safe_commit()`, `request.form.get(..., type=...)`, `_require_inventory_admin()` pro DELETE.
- **Mapování**: do `auth.SECTION_BY_ENDPOINT` přidat všechny endpointy → `'filaments'`.
- **MovementHistory**: rozšířit `action_type` o `'dry'` (stats, history, movement label).
  - `movement_action_label()` v `utils/__init__.py` přidat překlad `dry`.
- **Help**: do `static/js/help.js` `HELP_SECTIONS` do sekce inventáře přidat endpoint a tip (cs + en).

## Frontend (GUI)
- **`templates/filament_detail_tabs_drying.html`** — nový partial vykreslený v detailu filamentu (přepínač záložek v `filament_detail.html`).
  - Tabulka posledních sušení (datum, trvání, teplota, status, poznámka).
  - Tlačítko „Spustit sušení" otevírá modal s výběrem teploty (prefill z presetu), očekávané doby, volitelné hygrometrické měření.
  - Běžící sezení: progress bar s timerem (Alpine.js `x-init` + `setInterval`), „Dokončit" a „Přerušit".
- **Overview / Action Center**: nový widget „Na sušení" — pill badge s počtem běžících + odkaz do detailu.
- **Dashboard API**: `/storage` a inventářní karty mohou ukázat ikonu 🔥 pro cívku na sušení (overlay badge podobně jako low-stock).
- **i18n**: klíče v `messages.py` v cs+en — `drying_tab`, `drying_start`, `drying_stop`, `drying_abort`, `drying_running`, `drying_finished`, `drying_temp_c`, `drying_target_humidity`, `drying_duration`, `drying_no_sessions`, `drying_preset_default`, `drying_recommend`, `drying_toast_started`, `drying_toast_stopped`, `drying_action_center`.

## Testy (`tests/test_drying.py`)
- CRUD sezení, zákaz soubežného běhu, `action_type='dry'` v MovementHistory.
- RBAC: user bez sekce filaments → 403.
- Statistika započítává `dry` akci do deníku.

## Checklist (vybrané pravidla)
- Rule 1: všechny texty přes `t()`, cs+en.
- Rule 2: nová tabulka → `db.create_all()`; nové sloupce do `AppSetting` přes `_safe_alter`.
- Rule 4: endpoint mapping.
- Rule 15: export/import `DryingSession` (nová tabulka) — přidat do `backup_helpers.py` a `backup.py`.
- Rule 30: help.js aktualizace.
- Rule 32: BACKLOG položka `BL-...`.

## Úsilí
M (Medium) — ~1–2 dny: model, route, partial, modal, migrace, testy, backup.

---

# F2 — REST API s osobními API tokeny

## Cíl
Poskytnout stabilní REST API pro integrace třetích stran (Home Assistant, Notion, vlastní skripty, e-shopy). API používá osobní tokeny uživatelů, ve výchozím stavu je read-only. Viz roadmapa v `README.md` („REST API for third-party integrations").

## Uživatelský přínos
- Uživatel v `/account` generuje / ruší API tokeny (s popiskem用途, např. „Home Assistant").
- Token se předává hlavičkou `Authorization: Bearer <token>`.
- OpenAPI/Swagger UI dostupné na `/api/docs` (statické HTML, žádný externí přístup).

## Datový model

```python
class ApiToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)
    token_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)  # sha256(token)
    prefix = db.Column(db.String(12), nullable=False)  # first 8 chars zobrazen pro identifikaci
    scopes = db.Column(db.String(200), nullable=False, default='read')  # read, read:write
    created_at = db.Column(UtcDateTime, default=_utc_now, index=True)
    last_used_at = db.Column(UtcDateTime, nullable=True)
    expires_at = db.Column(UtcDateTime, nullable=True)
    is_revoked = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship('User', backref=db.backref('api_tokens', lazy=True, cascade='all, delete-orphan'))
```

Token se ukládá pouze jako hash — plnotext se uživateli ukáže **jednou** při vytvoření.

## Backend
- **Blueprint** `routes/api_rest.py` (odděleno od stávajícího `routes/api.py`, který jsou interní AJAX endpointy).
- před každým požadavkem dekorátor `@require_api_token(scope='read')`:
  - čte `Authorization`, ověří `token_hash` přes `secrets.compare_digest`.
  - nastaví `g.user`, `g.token`.
  - loguje `last_used_at`.
  - vynucuje rate limit (např. 60 req/min/token) přes existující mechanismus (BUG-405).
- Ve výchozím režimu **CSRF mimo halving** — API blueprint označen `csrf.exempt()` v `app.py` (jen pro `/api/v1/*`).
- Endpoints (verzovaná:
  - `GET /api/v1/filaments` — seznam s filtry (`brand`, `material`, `low_stock`).
  - `GET /api/v1/filaments/<id>`.
  - `POST /api/v1/filaments/<id>/movement` — změna skladu (scope `read:write`).
  - `GET /api/v1/projects`, `GET /api/v1/projects/<id>`.
  - `GET /api/v1/projects/<id>/quotes`.
  - `POST /api/v1/projects/<id>/comment` (write).
  - `GET /api/v1/stats/forecast` (F5 výstup).
  - `GET /api/v1/printers`, `GET /api/v1/printers/<id>/jobs`.
  - `GET /api/v1/health`.
- **OpenAPI spec** generován staticky v build time (`scripts/gen_openapi.py`) → `static/api/openapi.json`, UI na `/api/docs` hostuje [swagger-ui](https://static) z lokální bundle (samostatný build krok v `package.json`) — Rule 27 (`loadScript`).
- **Mapování**: nové endpointy přidat jako `UNRESTRICTED_ENDPOINTS` (token auth místo session), ale s default deny viz BUG-503 (explicitní seznam).
- **Audit log** pro operace zápisu přes API (kategorizováno `action_type='api_<op>'`).

## Frontend (GUI)
- **`templates/auth/account.html`** — nová sekce „API tokens":
  - Tabulka (prefix, label, scope, vytvořeno, naposled použito, platnost, akce Zrušit).
  - Modal „Vytvořit token" — label, scope select, doba platnosti.
  - Po vytvoření jednorázově zobrazen token s kopírovacím tlačítkem a varováním.
- **Settings → Integrations** — nový přepínač „Vystavit REST API" (`AppSetting.api_enabled`), výchozí False.
- **i18n**: `api_tokens_title`, `api_token_create`, `api_token_warning`, `api_token_scope`, `api_token_revoke`, `api_token_label`, `api_token_never_used`, `api_docs_link`, ... (cs+en).

## Testy
- `tests/test_api_rest.py`:
  - Bez tokenu → 401.
  - Vypršený/zrušený token → 401.
  - Scope read pokus o POST → 403.
  - Rate limit → 429.
  - CRUD happy path.
  - RBAC metodou: user bez sekce projects rejected na `/api/v1/projects`.

## Checklist
- Rule 4: token auth je nová auth vrstva, explicitní mapování, default deny.
- Rule 15: `ApiToken` do backup export/import.
- Rule 19: security-sensitive → pokryté testy.
- Rule 27: swagger-ui lazy přes `loadScript`.
- Rule 32: BACKLOG.

## Úsilí
L (Large) — ~2–3 dny: model, auth middleware, ~10 endpointů, swagger build, GUI, testy.

---

# F3 — QR kódy pro cívky (tisk + PWA skener)

## Cíl
Vygenerovat tisknutelný QR štítek pro každou cívku. QR obsahuje absolutní URL na `/filaments?qr=<id>` (deep-link s parametrem). V PWA lze QR oskenovat vestavěnou kamerou (přes native `BarcodeDetector` API nebo fallback na dynamicky načtenou `qrcode-reader` knihovnu) — po skenování se otevře detail cívky a nabídne akce jako „Aktualizovat váhu", „Odebrat ze skladu".

## Uživatelský přínos
- Na detailu filamentu tlačítko „Stáhnout štítek" — generuje A4 list se 6 štítky (lze v nastavení upravit velikost), tisknutelné.
- PWA: plovoucí tlačítko „Skener" v inventáři otevírá kameru.
- Skener podporuje URL i čistý ID (jen číslo) — flexibilita.
- Bez nutnosti ručního vyhledávání — efektivita na farmě.

## Backend
- **Generování QR**: knihovna `qrcode` (přidat do `requirements.txt`).
- **Endpoint** `GET /filaments/qr/<id>.png` (admin) — vygeneruje PNG s vysokým rozlišením (Module Tracker + rámec).
- **Endpoint** `GET /filaments/labels.pdf` —接受 `?ids=1,2,3` — vygeneruje PDF přes `reportlab` (přidat do `requirements.txt`) s mřížkou štítků.
- **Deep link**: `/filaments?qr=<id>` — route v `inventory.py` přečte parametr `qr`, pokud existuje, přesměruje na `/filament/<id>`.
- **i18n**: `qr_label_download`, `qr_label_print`, `qr_scanner_title`, `qr_scainer_start`, `qr_scanner_not_found`, `qr_scanner_no_camera`, ... (cs+en).

## Frontend (GUI / PWA)
- **Modal „Tisk štítků"** v detailu filamentu a v bulk operacích (vybrané cívky → „Vytisknout štítky").
- **Scanner modal** otevřený z floating buttonu v `index.html`:
  - Pokud `window.BarcodeDetector` existuje → nativně.
  - Jinak fallback přes `loadScript()` (Rule 27) na staticky hostovanou knihovnu `jsQR` (npm dependency, kopírováno do `static/js/vendor/jsQR.js`).
  - Po úspěšném skenu: parsování ID, redirect nebo otevření inline panelu akcí hnad-side.
- **Doplnění do PWA manifest** k.writeFile bez změn.

## Testy
- `tests/test_qr.py`:
  - `GET /filaments/qr/1.png` → 200, content-type image/png.
  - `GET /filaments/labels.pdf?ids=1` → 200, application/pdf.
  - RBAC (admin only na generování štítků).
  - Deep link redirect.

## Checklist
- Rule 4: endpoint mapping.
- Rule 14: žádné nahrávání — není potřeba, ale validovat `ids` (integer comma list) — prevence path / injection.
- Rule 27: scanner knihovna lazy-load.
- Rule 30: help.js sekce inventář — tipy.

## Úsilí
M — ~1–2 dny: knihovny, route, modaly, scanner PWA.

---

# F4 — E-mailová notifikace (SMTP)

## Cíl
Stávající `Notification` modely jsou pouze in-app. Doplnit e-mailový kanál pro klíčové události: projekt vytvořen, status změněn, komentář přidán, cívka low-stock, sušení dokončeno (F1), faktura splatná (F6). SMTP je volitelné — pokud není nakonfigurováno, in-app notifikace zůstávají funkční.

## Uživatelský přínos
- Settings → Integrations → sekce „E-mail (SMTP)" — host, port, TLS/SSL, uživatel, heslo (šifrováno Fernet jako u Bambu/Prusa), odesílatel, testovací odeslání.
- Každý uživatel si v `/account` zapne e-mail pro jednotlivé kategorie (již existují příznaky `notify_project_created` atd. — rozšířit o `notify_low_stock`).
- „Test SMTP" tlačítko odešle zkušební mail na e-mail přihlášeného uživatele.

## Datový model
- `AppSetting` nové sloupce:
  - `smtp_enabled` (Boolean, default False)
  - `smtp_host` (String 255)
  - `smtp_port` (Integer, default 587)
  - `smtp_security` (String 10, default 'starttls')  # 'none','starttls','ssl'
  - `smtp_username` (String 255)
  - `smtp_password` (Text, encrypted) — Fernet via `encrypt_token`
  - `smtp_from` (String 255)
- Nová tabulka `EmailQueue` (pro spolehlivost a dávkové odeslání workerem):
  ```python
  class EmailQueue(db.Model):
      id = ...
      to_address = db.Column(db.String(255), nullable=False, index=True)
      subject = db.Column(db.String(255), nullable=False)
      body_text = db.Column(db.Text, nullable=False)
      body_html = db.Column(db.Text, nullable=True)
      created_at = db.Column(UtcDateTime, default=_utc_now, index=True)
      attempts = db.Column(db.Integer, nullable=False, default=0)
      last_attempt_at = db.Column(UtcDateTime, nullable=True)
      status = db.Column(db.String(20), nullable=False, default='pending')  # pending, sent, failed
      error_message = db.Column(db.Text, nullable=True)
      next_attempt_at = db.Column(UtcDateTime, nullable=True)
  ```

## Backend
- **Modul** `utils/mail.py`:
  - `enqueue_email(to, subject, body_text, body_html=None)` — vloží do `EmailQueue`.
  - `send_pending_emails(app)` — spustí se z nového background workeru `email-worker` (podobně jako bambu/prusa/auto-backup). Interval 30s, `MAX_ATTEMPTS=5`, exponenciální backoff.
  - SMTP klient přes `smtplib.SMTP`/`SMTP_SSL`.
- **Integrace**: v místech, kde vznikají `Notification` záznamy (`routes/projects.py`, `routes/projects_helpers.py`, low-stock loop v `routes/inventory_helpers.py`), přidat volání `enqueue_email` pokud uživatel má daný příznak a SMTP je enabled.
- **Šablony** v `utils/mail_templates.py` — vrátí (subject, text, html) dle typu události. Lokalizováno přez `translate()` dle `user.preferred_language` nebo app default (Rule 25).
- **Settings** — extend `routes/settings.py` s novou sekcí, encrypt/decrypt hesla.
- **Backup** (Rule 15): `EmailQueue` lze vynechat (transientní) — dokumentovat v backup_meta že e-mail fronta není exportována. `AppSetting` SMTP sloupce zařadit do export/import (sloupce bez hesla — heslo vynechat z JSON z bezpečnostních důvodů nebo šifrovaně s `FERNET_KEY` warning).

## Frontend (GUI)
- **Settings → Integrations** nový panel pro SMTP. Stejné UX jako Bambu/Prusa (test connection tlačítko s live status badge).
- **Account** — checkboxy pro `notify_low_stock` (přidat sloupec do `User`).
- **Toast indikace** při úspěšném SMTP testu.

## Testy
- `tests/test_mail.py`:
  - `enqueue_email` vloží do fronty.
  - `send_pending_emails` s mock SMTP — uspěje/fail s backoff.
  - Šifrování hesla (encrypt/decrypt roundtrip).
  - Lokalizace předlohy (cs/en).
- `tests/test_mail_integration.py`:
  - End-to-end: projekt vytvořen → SMTP disabled → nic ve frontě.
  - SMTP enabled → mail ve frontě, worker pošle (mock `smtplib`).

## Checklist
- Rule 4: nové endpointy (smtp_test) mapping.
- Rule 5,15: backup schéma znovuusal s dokumentací.
- Rule 25: lokalizace v backendu přes `translate()`.
- Rule 19: šifrování hesla test.

## Úsilí
M — ~2 dny: model, worker, šablony, GUI v settings, testy.

---

# F5 — Inteligentní predikce vyčerpání skladu (forecast)

## Cěl
Na Statistics dashboardu a v Action Centeru zobrazit predikovaný den, kdy daná cívka vyčerpá, na základě reálné historie spotřeby (`MovementHistory` action_type `bambu_print`/`prusa_print`/`remove`). Lineární regrese denních průměrů za posledních 30/60/90 dní. Výstup: za每个 filament — `days_until_empty`, `predicted_empty_date`, `confidence`. Dále družící „nákupní kalendář" — kdy dojde po filamentů v daném měsíci.

## Uživatelský přínos
- Stats dashboard nový widget „Forecast vyčerpání" s bublinovým/Timeline grafem (x = dny do vyčerpání, y = zásoba gramů, barva = urgency).
- Action Center: nová sekce „Brzo vyčerpá" s top 5 — dříve než existující static low-stock.
- Export `/api/v1/stats/forecast` (F2 API) pro integraci nákupních reminderů.
- Filtrovací pill „Brzo vyčerpá" v inventáři (klik přidá filtr na `predicted_empty_date <= +30d`).

## Backend
- **Nový modul** `routes/forecast.py` (nebo rozšíření `routes/stats.py`):
  - `compute_forecast(filament_id, window_days=30)`:
    1. Agregace denní spotřeby z `MovementHistory` (sum weight na akce s kladným spotřebováním).
    2. Lineární regrese `numpy.polyfit(deg=1)` na denní průběh popřípadě jednoduchý průměr bez numpy (pro self-host minimalizace dependency — preferovat `statistics` ze stdlib než numpy).
    3. Výpočet `days_until_empty = weight_remaining / slope`.
    4. Confidence = `r²` korelace nebo `1 / std`.
  - `forecast_all()` — batch přes všechny aktivní filamenty.
- **Cache**: výsledek přes `functools.lru_cache` s TTL v `utils/forecast_cache.py` — přepočet max 1x za 1h nebo po MovementHistory změně (invalidace).
- **API**: `GET /api/v1/stats/forecast` (F2).
- **i18n**: `stats_forecast_title`, `forecast_days_until_empty`, `forecast_predicted_date`, `forecast_confidence`, `forecast_soon`, `forecast_no_data`, `forecast_purchase_calendar`.

## Frontend (GUI)
- `stats.html` nová sekce `section_forecast` (Rule 16 — draggable layout, `data-section-id`).
  - Předané `forecast_data` JSON (přes `|tojson` — Rule odpovídá BUG-502).
  - Chart.js lazy-load přes `loadScript()` (Rule 27).
- `overview.html` — Action Center widget „Brzo vyčerpá".
- Inventář — filter pill a indikátor ICON/Ribbon u cívky s `predicted_empty_date <= +14d`.

## Testy
- `tests/test_forecast.py`:
  - Lineární regrese na syntetických datech.
  - Confidence low pro vysoce variabilní data.
  - Edge cases: žádná history (None), negativní spotřeba (pridané), rozděloťě doby.
  - Cache invalidace po novém movement.
- `tests/test_stats_extended.py` rozšíření — widget HTML obsahuje data.

## Checklist
- Rule 16: stats layout draggable.
- Rule 22: dashboard consistency — widget v dashboard.js (or STAT cụ card resize manager).
- Rule 29: aktualizovat ARCHITECTURE.md (analytics section).
- Rule 32: BACKLOG.

## Úsilí
M — ~1–2 dny: algoritmus, cache, API, widgety, testy.

---

# F6 — Fakturace a sledování plateb

## Cíl
Rozšířit `ProjectQuote` o plnohodnotné fakturační info: vystavená faktura, splatnost, platba (částka, datum, metoda), status (unpaid, partial, paid, overdue), variabilní symbol. Historie plateb per projekt. Připomínky splatných faktur v Action Center a (F4) e-mailem.

## Uživatelský přínos
- Detail projektu → záložka „Platba":
  - Seznam přijatých plateb, celková zaplaceno/zbývá, status badge.
  - „Označit jako zaplaceno" quick action.
  - Generování variabilního symbolu z ID faktury + invoice prefix (již existuje `AppSetting.invoice_*`).
- Settings → Company: nové pole „Výchozí splatnost (dní)".
- Overview: bullet „X splatných faktur".

## Datový model
- **`ProjectQuote`** rozšířit:
  - `invoice_issued_at = UtcDateTime, nullable=True`
  - `invoice_due_at = UtcDateTime, nullable=True`
  - `variable_symbol = String(50), nullable=True, index=True`
  - `paid_amount = Numeric(10,2), default=0`
  - `payment_status = String(20), default='unpaid'`  # unpaid, partial, paid
- **Nová tabulka** `ProjectPayment`:
  ```python
  class ProjectPayment(db.Model):
      id = db.Column(db.Integer, primary_key=True)
      quote_id = db.Column(db.Integer, db.ForeignKey('project_quote.id', ondelete='CASCADE'), nullable=False, index=True)
      amount = db.Column(db.Numeric(10,2), nullable=False)
      paid_at = db.Column(UtcDateTime, nullable=False, default=_utc_now)
      method = db.Column(db.String(30), nullable=True)  # bank, cash, card, online
      note = db.Column(db.Text, nullable=True)
      recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
  ```

## Backend
- `routes/projects.py`:
  - `POST /projects/<id>/quote/<qid>/issue` — nastaví `invoice_issued_at`, `invoice_due_at = issued + default_due_days`, generuje VS.
  - `POST /projects/<id>/quote/<qid>/payment` — přidá `ProjectPayment`, přepočítá `paid_amount` a `payment_status`.
  - `POST /projects/<id>/quote/<qid>/cancel`.
  - `GET /projects/<id>/quote/<qid>/invoice.pdf` — existující faktura rozšířit o QR platbu (IBAN + variabilní symbol) přes `qrcode` (F3 sdílená závislost).
- **Scheduling worker** rozšíření workeru `auto-backup-worker` o periodickou kontrolu splatných faktur (`invoice_due_at < utc_now` AND `payment_status != 'paid'`) → notifikace + (F4) e-mail.
- **Mapování** endpointů do `SECTION_BY_ENDPOINT` — sekce `projects`.

## Frontend (GUI)
- **`templates/_project_billing.html`** nový partial renderovaný v `project_detail.html` jako nová záložka „Platba".
- **Quote modal** v `templates/calculator.html` rozšířit — po uložení quote se nabídne „Vystavit fakturu".
- **Overview / Action Center** — widget „Splatné faktury".
- **i18n** — rozsáhlý set: `billing_tab`, `billing_issue_invoice`, `billing_due_date`, `billing_variable_symbol`, `billing_paid_amount`, `billing_remaining`, `billing_status_unpaid`, `billing_status_partial`, `billing_status_paid`, `billing_status_overdue`, `billing_add_payment`, `billing_payment_method_bank`, ... (cs+en).
- **Help** (Rule 30): nový tip v sekci projekty + fakturace.

## Testy
- `tests/test_billing.py`:
  - Vystavení faktury generuje VS a splatnost.
  - Přidání platby `payment_status` přechod unpaid → partial → paid.
  - Splatná faktura (due < now) se označí overdue.
  - RBAC: user bez projects → 403.

## Checklist
- Rule 2: nové sloupce v `ProjectQuote` + nová tabulka `ProjectPayment` — migrace + `_safe_alter` pro sloupce.
- Rule 15: backup — ProjectPayment do export/import, rozšířit ProjectQuote serializer.
- Rule 18: README — feature do Key Features.
- Rule 32: BACKLOG.

## Úsilí
L — ~2–3 dny: model/migrace, route, partial, QR platba v PDF, worker, GUI, testy.

---

# F7 — Webhook systém pro automatizaci

## Cíl
Umožnit uživatelům registrovat webhook URL, na které systém pošle POST s JSON payload při definovaných událostech. Integrace s Home Assistant, automations, Discord/Slack.

## Podporované události (event types)
- `filament.low_stock` — `filament_id`, `weight_remaining`, `min_stock_grams`.
- `filament.created`, `filament.deleted`.
- `project.created`, `project.status_changed`, `project.comment_added`.
- `bambu.job_started`, `bambu.job_finished`.
- `prusa.job_finished`.
- `drying.session_finished` (F1).
- `invoice.overdue` (F6).

## Datový model
```python
class Webhook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.String(500), nullable=False)  # comma-separated event types
    secret = db.Column(db.String(128), nullable=False)  # HMAC signing secret
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_delivery_at = db.Column(UtcDateTime, nullable=True)
    last_status = db.Column(db.Integer, nullable=True)  # HTTP status code
    created_at = db.Column(UtcDateTime, default=_utc_now)

class WebhookDelivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    webhook_id = db.Column(db.Integer, db.ForeignKey('webhook.id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    attempt = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, success, failed
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(UtcDateTime, default=_utc_now, index=True)
    next_attempt_at = db.Column(UtcDateTime, nullable=True)
```

## Backend
- **Modul** `utils/webhooks.py`:
  - `emit_event(event_type, payload)` — vybere aktivní webhooky uživatele vlastnícího objekt (pro filament events — vlastník / admin; pro projekty — vlastník), vyrobí `WebhookDelivery` záznamy.
  - `process_webhook_deliveries(app)` — worker spouštěný z `email-worker` nebo samostatně (`webhook-worker`, 15s interval). HTTP POST přes `requests`, hlavička `X-Filament-Signature: sha256=<HMAC>`, exponenciální backoff, max 5 pokusů.
  - URL validace přes `is_safe_external_url()` (BUG-513 / Rule 13) — žádné SSRF.
- **Integrace bodů**: v místech emise událostí (low-stock, project created, bambu job finished, …) vložit jediný `emit_event(...)` call.
- **Endpointy** `routes/webhooks.py`:
  - `GET /webhooks` — admin přehled poskytnutých webhooků + doručení (statistiky úspěšnosti).
  - `POST /webhooks/create`, `POST /webhooks/<id>/edit`, `POST /webhooks/<id>/test`, `POST /webhooks/<id>/delete`, `POST /webhooks/<id>/replay/<delivery_id>`.
- **GUI** `templates/webhooks.html` — tabulka, formulář, log doručení, tlačítko „Test" odešle ping payload.

## Testy
- `tests/test_webhooks.py`:
  - HMAC signatura validní.
  - SSRF odmítnutí (`http://localhost`, `192.168.x.x`).
  - Backoff + retry při 503.
  - Filtrace událostí — webhook s `events='project.*'` nedostane `filament.*`.
  - Replay delivery znovu odešle.

## Checklist
- Rule 4,13,15,19,29,32.

## Úsilí
M — ~2 dny:_MODELY, worker, integrace bodů, GUI, testy.

---

# F8 — Živý dashboard tiskáren s bed-camera snapshoty

## Cíl
Spojit stávající Bambu a Prusa mobu do jediného live dashboardu `/printers` s dlaždicemi tiskáren:
- Aktuální stav (idle, printing, paused, offline).
- Progress bar reálného tisku (Bambu: zed Cloud / push; Prusa: poll).
- **Bed/camera snapshot** — Bambu Cloud `/api/v1/printers/<id>/camera/照片` přez nový endpoint proxy s cache; PrusaLink `//api/v1/camera/snapshot` podobně. Snapshoty se periodicky obnovují.
- Aktuální filament v AMS / extruderu.
- Quick actions: „Pauza", „Obnovit", „Zastavit" (pouze admin) — proxy na Bambu Cloud nebo PrusaLink API.

## Poznámka k importovaným knihovnám
Žádný streaming video. Pouze JPEG obrázek přes `<img>` s `onerror` fallbackem a reloadem na refreshe (cache-busting query parametr). To minimalizuje datovou zátěž i komplexitu.

## Backend
- **Nový blueprint** `routes/printers.py` (agregátor) — vedle bambu/prusa, nelze je spojit kvůli závislostem.
- **Cache snapshotů**: `data/camera_cache/<printer_type>_<id>.jpg` s TTL ~30s; endpoint `GET /printers/<type>/<id>/snapshot` vrátí buď cache nebo provede fetch a uloží.
  - SSRF validace IP peeru (BUG-513), proxy přesnjí Fernet šifrovaný token / API key.
  - Cache-Control hlavičky (`no-store, must-revalidate` na HTML obrázku na ochranu před случаンドózním cachingem), CSP nonce na inline reload script.
- **Background worker** rozšíření: `printer-snapshot-worker` (interval 30s) — prefetch snapshot pro každý Bambu/Prusa printer s `is_active` a `enabled`.
- **Quick action proxy**: `POST /printers/<type>/<id>/action` s `action=pause|resume|stop` → přiad `X-Api-Key` (Prusa) nebo Bambu access token → ověření RBAC admin.

## Frontend (GUI)
- **`templates/printers.html`** — grid dlaždic (Tailwind grid `md:grid-cols-2 xl:grid-cols-3`), každá dlaždice:
  - Header: název tiskárny, model, status badge, CO indikátor „offline" (~amber).
  - Snapshot obrázek (lazy domeně), below: progress bar, ETA, aktuální file/project (s linkem na detail projektu), materiál vlkna + barevný swatch.
  - Footer: quick actions (admin), „Poslední sync".
- **Lazy refresh** přes Alpine.js `setInterval` —GET `?tstamp=...` na thumbnailim cesty — refresh ~30s. Při nečinnosti karty (offscreen) se interval pozastaví (`IntersectionObserver`), úspora penalty CPU/battery.
- **Snapshot lazy load**: `loadScript` není potřebný — `<img>` s `data-src` pro IntersectionObserver lazy-load (Rule 27 analogy).
- **Dashboard** — overview widget „Live tiskárny" přepíná mezi Bambu/Prusa nebo agregated.

## Testy
- `tests/test_printers.py`:
  - Snapshot endpoint vrací JPEG a ukládá do cache.
  - SSRF odmítnutí.
  - Admin-only quick actions (user → 403).
  - Offline tiskárna renderer badge.
- `tests/test_printers_camera.py` — mock HTTP fetch IP validation.

## Checklist
- Rule 4,15,22,27,29,30.

## Úsilí
L — ~3 dny: blueprint, snapshot cache worker, GUI dlaždice, quick actions, testy.

---

# Souhrnný implementační postup (doporučené pořadí)

1. **F4 SMTP** — potřebné pro F1, F6 notifikace. Začít sem.
2. **F1 Drying** — samostatný modul, nízká návaznost.
3. **F5 Forecast** — používá data již v aplikaci, nezávislý.
4. **F6 Billing** — závisí na existující fakturou infra ($invoice_*), rozšíření.
5. **F7 Webhooks** — výhodnější po F1, F6 (více eventů k emitování).
6. **F3 QR** — nezávislý, použitelný i pro F6 (QR platba).
7. **F2 REST API** — agregátor _exponuje_ data z F1–F6; nejlépe po ostatních.
8. **F8 Printers dashboard** — finální vizuální rozšíření.

## Závislosti
```
F4 ──► F1 (notifikace)
F4 ──► F6 (upozornění na splatnost)
F1, F6 ──► F7 (eventy)
F1, F5, F6 ──► F2 (API payloads)
F3 ──► F6 (QR platba v PDF)
```

## Globální checklist (po dokončení všech funkcí)
- ✅ Bump `APP_VERSION` na `1.120.0` (app.py).
- ✅ `CHANGELOG.md` založit nový section `## [1.120.0]` s podsekci Added.
- ✅ `README.md`:
  - Verze na `v1.120.0`.
  - Key Features doplnit o: Drying Tracker, REST API, QR kódy, E-mail notifikace, Forecast, Billing, Webhooks, Live Printers Dashboard.
  - Project Structure doplnit o `routes/drying.py`, `routes/api_rest.py`, `routes/printers.py`, `routes/webhooks.py`, `utils/mail.py`, `utils/webhooks.py`, `forecast.py`.
  - Roadmap: přesun REST API z „Potential Future Work" do „Completed".
- ✅ `.kilo/ARCHITECTURE.md` — nová data flow sekce pro SMTP worker, webhook worker, REST API auth, snapshot worker; nové tabulky.
- ✅ `.github/copilot-instructions.md` — synchronizovat strukturou/flow/rules.
- ✅ `.kilo/agent/filament-agent.md` — Project Context aktualizace.
- ✅ `.kilo/BACKLOG.md` — zaevidovat `BL-700` až `BL-707`, status Fixed in v1.120.0 po dokončení.
- ✅ `static/js/help.js` — nové sekce / tipy pro Drying, Billing, Webhooks, Printers dashboard, Scanner.
- ✅ `requirements.txt` — `qrcode`, `reportlab`, případně `duckduckgo-publisher` ne, pouze tyto.
- ✅ `docker compose up -d --build` — finální build + curl `/login` HTTP 200.

## Odhad celkového úsilí (F1–F8)
~12–18 MD (man-day) pro kompletní implementaci všech 8 funkcí včetně testů a dokumentace.

---

# Pokračování: F9–F20

Po hloubkové auditě projektu (general sub-agent průzkum celého kódu) byly navrženy další funkce F9–F20, vycházející ze skutečných mezer v kódu:

| #    | Funkce                                                    | Kategorie           | Úsilí |
| ---- | --------------------------------------------------------- | ------------------- | ----- |
| F9   | OctoPrint REST API integrace                              | Integrations         | M     |
| F10  | Moonraker/Klipper WebSocket integrace                     | Integrations         | L     |
| F11  | PrusaConnect Cloud integrace                              | Integrations         | S     |
| F12  | Plnohodnotný kalkulátor (labour/packaging/shipping/VAT)   | Calculator           | M     |
| F13  | ML predikce selhání tisku + waste KPI dashboard           | Waste / Stats        | L     |
| F14  | Fulltextové vyhledávání (FTS5 / tsvector)                  | Frontend / API       | M     |
| F15  | Web Push notifikace + offline PWA filament listing         | Mobile / PWA         | M     |
| F16  | 2FA/TOTP autentizace                                       | Auth / Security      | M     |
| F17  | Využití tiskáren (uptime, MTBF, cost/hour)                 | Stats / Printers     | M     |
| F18  | Environmental sensors na poličkách (ESPHome/DHT22)        | Storage              | M     |
| F19  | Custom status workflow designer pro projekty               | Projects             | L     |
| F20  | Gantt timeline + multi-printer job splitting                | Projects / Printers  | L     |

**Detailní implementační plány pro F9–F20 jsou v samostatném souboru [`implement-part2.md`](implement-part2.md).**

Shrnutí oblastí pokrytých auditem, které vedly k návrhu F9–F20:

- **Integrace tiskáren** — chybí OctoPrint (BL-001 v backlog), Moonraker/Klipper/Voron, PrusaConnect Cloud. Stávající Bambu Cloud + PrusaLink REST pokrývají dne 2 integrace z ~6 oblíbených.
- **Kalkulátor** — chybí labour, packaging, shipping, VAT/sales tax, waste factor % — nezbytné pro reálnou cenovou kalkulaci.
- **Waste** — `WasteRecord` sbírá bohatá data, ale chybí jakákoli korelační analýza (material + brand + printer → reason). ML heuristika identifikuje "32 % warp rate pro PLA+Brand X".
- **Vyhledávání** — `/api/search` je jen LIKE na 2 entity. FTS5 / tsvector umožní fulltext nad notes, comments, popisy, brands.
- **Mobilní/PWA** — service worker kešuje jen static, ne HTML. Push notifikace neexistují. Offline listing absent.
- **Bezpečnost** — žádné 2FA. Expose self-host do veřejného internetu (Tailscale, Cloudflare Tunnel) toto vyžaduje.
- **Stats / výkonnost tiskáren** — chybí per-printer uptime, MTBF, cost/hour. Klíčové pro tisk farmy.
- **Storage** — žádné sensor integrace. Filament degradation závisí na podmínkách; ESPHome/DHT22 je oblíbené.
- **Projekty** — status hardcoded 6 hodnot. Gantt / scheduling absent. Multi-printer queue absent.

## Odhad celkového úsilí (F9–F20)
~18–25 MD. Doporučeno rollování napříč 3–5 minors verzemi (v1.121.0, v1.122.0, v1.123.0), nikoli jeden megarelease.

## Kombinovaný odhad (F1–F20)
~30–43 MD napříč v1.120.0 – v1.123.0 (4 minor releasy).