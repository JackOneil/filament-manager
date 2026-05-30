/**
 * Filament Manager — Interactive Page Tour
 * SVG-spotlight guided tour engine.
 *
 * Public API:
 *   window.startPageTour(sectionId)  — start tour for the given section
 *   window.stopPageTour()            — stop any running tour
 *
 * Language is read from window.__helpLang ('cs' | 'en').
 */
(function () {
    'use strict';

    // ── Step definitions ────────────────────────────────────────────────────────
    // Each step: { selector, title:{cs,en}, text:{cs,en}, position:'auto'|'top'|'bottom'|'left'|'right' }
    // selector: null → centered modal (no spotlight)

    var TOUR_STEPS = {

        overview: [
            {
                selector: null,
                title: { cs: 'Přehledová stránka', en: 'Overview page' },
                text: {
                    cs: 'Toto je centrum aplikace. Odtud máte přehled o stavu skladu, běžících tiscích a všem, co vyžaduje pozornost — na jednom místě.',
                    en: 'This is the app\'s hub. Here you get an overview of stock status, running prints, and everything that needs attention — all in one place.'
                }
            },
            {
                selector: '[data-widget-id="action_center"]',
                title: { cs: 'Akční centrum', en: 'Action Centre' },
                text: {
                    cs: 'Akční centrum shromažďuje upozornění: nízký stav zásoby, projekty blížící se termínu, prošlá údržba nebo chyby tiskáren. Vše na co je třeba reagovat.',
                    en: 'The Action Centre collects notices: low stock, projects nearing deadlines, overdue maintenance, or printer errors. Everything that needs a response.'
                },
                position: 'top'
            },
            {
                selector: '[data-widget-id="live_printers"]',
                title: { cs: 'Live stav tiskáren', en: 'Live Printer Status' },
                text: {
                    cs: 'Widgety tiskáren zobrazují průběh tisku v reálném čase — procenta, zbývající čas a aktuálně použitý filament. Data se obnovují automaticky na pozadí.',
                    en: 'Printer widgets show real-time print progress — percentage, remaining time and current filament. Data refreshes automatically in the background.'
                },
                position: 'top'
            },
            {
                selector: '[data-widget-id="recent_activity"]',
                title: { cs: 'Nedávná aktivita', en: 'Recent Activity' },
                text: {
                    cs: 'Přehled posledních pohybů skladu: spotřeby, přidání nových cívek, ruční korekce. Slouží k rychlé kontrole, co se ve skladu dělo.',
                    en: 'Overview of recent stock movements: usage logs, new spool additions, manual adjustments. A quick audit of recent warehouse activity.'
                },
                position: 'top'
            },
            {
                selector: '#overviewEditBtn',
                title: { cs: 'Přizpůsobení rozvržení', en: 'Customise Layout' },
                text: {
                    cs: 'Kliknutím aktivujete editační režim. Widgety lze přetahovat, měnit jejich šířku nebo je skrýt. Rozvržení se uloží do prohlížeče a přežije i obnovení stránky.',
                    en: 'Click to activate edit mode. Widgets can be dragged, resized, or hidden. The layout is saved in the browser and survives page refresh.'
                },
                position: 'bottom'
            }
        ],

        filaments: [
            {
                selector: null,
                title: { cs: 'Inventář filamentů', en: 'Filament Inventory' },
                text: {
                    cs: 'Centrální sklad všech cívek. Vidíte zde aktuální zásoby s barevnými indikátory stavu, váhami a parametry tisku.',
                    en: 'The central warehouse for all spools. See current stock with colour-coded status indicators, weights and print parameters.'
                }
            },
            {
                selector: '#filter-section',
                title: { cs: 'Filtry', en: 'Filters' },
                text: {
                    cs: 'Filtrujte zásoby podle výrobce, barvy, materiálu, stavu (nízký / prázdný) nebo štítku. Každý filtr má vyhledávací pole a filtry lze libovolně kombinovat.',
                    en: 'Filter stock by brand, colour, material, status (low / empty) or tag. Each filter has a search field and filters can be freely combined.'
                },
                position: 'bottom'
            },
            {
                selector: '#filament-content-wrapper',
                title: { cs: 'Karty filamentů', en: 'Filament Cards' },
                text: {
                    cs: 'Každá cívka zobrazuje hmotnost, barevný pruh a stav zásoby. Oranžový odznak = méně než 20 %, červený = prázdná cívka. Přes ikony ⊕ / ⊖ přidejte nebo odečtěte gramy.',
                    en: 'Each spool shows weight, colour strip and stock status. Orange badge = less than 20 %, red = empty spool. Use the ⊕ / ⊖ icons to add or subtract grams.'
                },
                position: 'top'
            },
            {
                selector: '#btn-add-filament',
                title: { cs: 'Přidat nový filament', en: 'Add New Filament' },
                text: {
                    cs: 'Kliknutím přidáte novou cívku do skladu. Zadáte výrobce, materiál, barvu, celkovou hmotnost, cenu a volitelně parametry tisku.',
                    en: 'Click to add a new spool to the warehouse. You\'ll enter brand, material, colour, total weight, price and optionally print parameters.'
                },
                position: 'bottom'
            },
            {
                selector: '#inventory-view-toggle',
                title: { cs: 'Přepínání zobrazení', en: 'Switch View Mode' },
                text: {
                    cs: 'Přepínejte mezi kartami, seznamem a kompaktním zobrazením. Každý režim se hodí pro jiný způsob práce se zásobami. Volba se uloží.',
                    en: 'Switch between card, list and compact view. Each mode suits a different way of working with stock. Your choice is saved.'
                },
                position: 'bottom'
            }
        ],

        projects: [
            {
                selector: null,
                title: { cs: 'Projekty', en: 'Projects' },
                text: {
                    cs: 'Projekty sledují tiskové zakázky od nápadu po dokončení. Každý projekt má soubory, plánované materiály, komentáře, timeline a možnost generovat cenovou nabídku.',
                    en: 'Projects track print jobs from idea to completion. Each project has files, planned materials, comments, a timeline, and the ability to generate a quote.'
                }
            },
            {
                selector: '#projects-content',
                title: { cs: 'Kanban / Tabulka', en: 'Kanban / Table' },
                text: {
                    cs: 'Projekty zobrazujete jako Kanban nástěnku (sloupce podle stavu) nebo jako tabulku. Přetahováním karet na Kanbanu přesouváte projekt do jiného stavu.',
                    en: 'View projects as a Kanban board (columns by status) or as a table. Drag Kanban cards to move a project to a different status.'
                },
                position: 'top'
            },
            {
                selector: '#btn-create-project',
                title: { cs: 'Nový projekt', en: 'New Project' },
                text: {
                    cs: 'Vytvořte nový projekt — zadejte název, klienta, termín, tag a prioritu. Po vytvoření přidejte soubory, materiály a komentáře.',
                    en: 'Create a new project — enter name, client, deadline, tag and priority. After creation, add files, materials and comments.'
                },
                position: 'bottom'
            },
            {
                selector: '#projectsEditBtn',
                title: { cs: 'Přizpůsobení rozvržení', en: 'Customise Layout' },
                text: {
                    cs: 'Widgety projektové stránky (Kanban, statistiky, termíny) lze přeuspořádat a skrýt. Editační režim aktivujete tímto tlačítkem.',
                    en: 'Project page widgets (Kanban, stats, deadlines) can be rearranged and hidden. Activate edit mode with this button.'
                },
                position: 'bottom'
            }
        ],

        calculator: [
            {
                selector: null,
                title: { cs: 'Kalkulačka tisku', en: 'Print Calculator' },
                text: {
                    cs: 'Kalkulačka spočítá náklady na tisk: cena filamantu, energie a vaše marže. Výsledky lze uložit do historie nebo připojit k projektu jako cenovou nabídku.',
                    en: 'The calculator computes print costs: filament price, energy and your margin. Results can be saved to history or attached to a project as a quote.'
                }
            },
            {
                selector: '#filament-select-container',
                title: { cs: 'Výběr filamantu', en: 'Select Filament' },
                text: {
                    cs: 'Vyberte filament ze skladu. Cena za gram se načte automaticky podle zadané ceny u cívky. Kalkulačka pracuje v krocích — nejprve vyberte filament.',
                    en: 'Select a filament from stock. Price per gram is loaded automatically from the spool\'s price. The calculator works in steps — start by selecting a filament.'
                },
                position: 'bottom'
            },
            {
                selector: null,
                title: { cs: 'Parametry tisku', en: 'Print Parameters' },
                text: {
                    cs: 'Zadejte hmotnost filamantu v gramech a délku tisku v minutách (lze najít v g-kódu nebo sliceru). Ve třetím kroku nastavte marži a volitelně přiřaďte projekt.',
                    en: 'Enter the filament weight in grams and print time in minutes (found in g-code or slicer). In step 3 set the margin and optionally assign a project.'
                }
            }
        ],

        stats: [
            {
                selector: null,
                title: { cs: 'Statistiky', en: 'Statistics' },
                text: {
                    cs: 'Statistický dashboard nabízí přehledy spotřeby, trendy a prognózy doplnění. Zobrazuje data ze skladu, tiskových úloh i projektů.',
                    en: 'The statistics dashboard provides consumption overviews, trends and reorder forecasts. It shows data from stock, print jobs and projects.'
                }
            },
            {
                selector: '#section_overview',
                title: { cs: 'KPI přehled', en: 'KPI Overview' },
                text: {
                    cs: 'Klíčové ukazatele: celková zásoby v gramech, průměrná měsíční spotřeba, počet cívek pod minimem a hodnota skladu.',
                    en: 'Key metrics: total stock in grams, average monthly consumption, number of spools below minimum, and warehouse value.'
                },
                position: 'bottom'
            },
            {
                selector: '#section_charts_primary',
                title: { cs: 'Grafy spotřeby', en: 'Consumption Charts' },
                text: {
                    cs: 'Hlavní grafy zobrazují spotřebu v čase rozdělená podle materiálu nebo výrobce. Přepínejte období a porovnávejte měsíce.',
                    en: 'Main charts show consumption over time broken down by material or brand. Switch periods and compare months.'
                },
                position: 'top'
            },
            {
                selector: '#section_colors',
                title: { cs: 'Paleta barev', en: 'Colour Palette' },
                text: {
                    cs: 'Vizualizace aktuálního zastoupení barev ve skladu seřazená podle barevného tónu. Každý čtvereček představuje jednu cívku.',
                    en: 'Visualisation of the current colour distribution in stock, sorted by hue. Each square represents one spool.'
                },
                position: 'top'
            }
        ],

        storage: [
            {
                selector: null,
                title: { cs: 'Správa fyzického skladu', en: 'Physical Storage' },
                text: {
                    cs: 'Fyzické sklady mapují umístění cívek na policích a ve slotech. Přiřaďte filament ke slotu a vždy budete vědět, kde ho fyzicky najít.',
                    en: 'Physical storage maps spool locations on shelves and in slots. Assign a filament to a slot and you\'ll always know exactly where to find it.'
                }
            },
            {
                selector: null,
                title: { cs: 'Police a sloty', en: 'Shelves and Slots' },
                text: {
                    cs: 'Vytvořte police (v nastavení polices) a na každé polici definujte sloty. Každý slot pojme jednu nebo více cívek. Obsazenost je vidět barevně na přehledu.',
                    en: 'Create shelves (in shelf settings) and define slots on each shelf. Each slot holds one or more spools. Occupancy is shown colour-coded in the overview.'
                }
            },
            {
                selector: null,
                title: { cs: 'Přiřazení filamantu', en: 'Assigning Filament' },
                text: {
                    cs: 'Klikněte na slot a vyberte filament ze skladu. Přiřazení se zobrazí na detailu filamantu i zde na mapě. Slot lze kdykoli uvolnit.',
                    en: 'Click a slot and pick a filament from stock. The assignment shows on the filament detail and on this map. A slot can be cleared at any time.'
                }
            }
        ],

        settings: [
            {
                selector: null,
                title: { cs: 'Nastavení', en: 'Settings' },
                text: {
                    cs: 'Nastavení spravuje veškerou konfiguraci: obecné volby, číselníky (výrobci, barvy, materiály), integrace s tiskárnami a zálohu dat.',
                    en: 'Settings manages all configuration: general options, dictionaries (brands, colours, materials), printer integrations, and data backup.'
                }
            },
            {
                selector: '#settings-tabs',
                title: { cs: 'Záložky nastavení', en: 'Settings Tabs' },
                text: {
                    cs: 'Nastavení je rozděleno do záložek: Obecné (jazyk, měna, téma), Tiskárny (energie), Integrace (Bambu, PrusaLink), Firma, Data (záloha) a Číselníky.',
                    en: 'Settings is split into tabs: General (language, currency, theme), Printers (energy), Integrations (Bambu, PrusaLink), Company, Data (backup) and Dictionaries.'
                },
                position: 'bottom'
            },
            {
                selector: '#reorder-shop-section',
                tab: 'dicts',
                title: { cs: 'E-shop pro doobjednávání', en: 'Reorder Shop' },
                text: {
                    cs: 'Nastavte URL šablonu pro rychlé vyhledávání filamentů v e-shopu. Použijte {query} jako zástupný symbol — bude nahrazen názvem filamantu. Živý náhled odkazu si zobrazíte okamžitě.',
                    en: 'Set a URL template for quick filament search in an online shop. Use {query} as placeholder — it\'s replaced by the filament name. See a live preview of the link instantly.'
                },
                position: 'top'
            },
            {
                selector: '#bambu-cloud',
                tab: 'integrations',
                title: { cs: 'Bambu Lab integrace', en: 'Bambu Lab Integration' },
                text: {
                    cs: 'Přidejte přístupový token Bambu Cloud a přiřaďte tiskárny. Tiskové úlohy se budou synchronizovat automaticky každých 60 sekund.',
                    en: 'Add a Bambu Cloud access token and assign printers. Print jobs will sync automatically every 60 seconds.'
                },
                position: 'top'
            },
            {
                selector: '#printer-energy',
                tab: 'dicts',
                title: { cs: 'Energie a náklady', en: 'Energy and Costs' },
                text: {
                    cs: 'Nastavte cenu kWh a příkon tiskárny ve wattech. Tyto hodnoty se automaticky použijí v kalkulačce pro výpočet nákladů na energii.',
                    en: 'Set the kWh price and printer power in watts. These values are used automatically in the calculator for energy cost computation.'
                },
                position: 'top'
            }
        ],

        bambu: [
            {
                selector: null,
                title: { cs: 'Bambu Lab integrace', en: 'Bambu Lab Integration' },
                text: {
                    cs: 'Tato stránka zobrazuje tiskové úlohy synchronizované z Bambu Cloud. Úlohy jsou automaticky přiřazovány k filamentům a po dokončení tisku odečítají spotřebu ze skladu.',
                    en: 'This page shows print jobs synced from Bambu Cloud. Jobs are automatically matched to filaments and upon completion deduct consumption from stock.'
                }
            },
            {
                selector: '#sync-btn',
                title: { cs: 'Ruční synchronizace', en: 'Manual Sync' },
                text: {
                    cs: 'Kliknutím spustíte okamžitou synchronizaci s Bambu Cloud. Automatická synchronizace probíhá na pozadí každých 60 sekund.',
                    en: 'Click to trigger an immediate sync with Bambu Cloud. Automatic synchronisation runs in the background every 60 seconds.'
                },
                position: 'bottom'
            },
            {
                selector: null,
                title: { cs: 'Filtrování úloh', en: 'Filtering Jobs' },
                text: {
                    cs: 'Pomocí filtrovacích štítků (Všechny, Nepřiřazené, Neodečtené) zobrazte jen relevantní úlohy. Nepřiřazené úlohy potřebují ruční párování s filamentem.',
                    en: 'Use filter pills (All, Unassigned, Not deducted) to show only relevant jobs. Unassigned jobs need manual matching with a filament.'
                }
            }
        ],

        prusa: [
            {
                selector: null,
                title: { cs: 'PrusaLink integrace', en: 'PrusaLink Integration' },
                text: {
                    cs: 'PrusaLink se připojuje přímo k tiskárně v lokální síti. Sledujte stav tisku v reálném čase, historii úloh a automaticky evidujte spotřebu filamantu.',
                    en: 'PrusaLink connects directly to the printer on the local network. Monitor real-time print status, job history and automatically track filament consumption.'
                }
            },
            {
                selector: null,
                title: { cs: 'Přidání tiskárny', en: 'Adding a Printer' },
                text: {
                    cs: 'Tiskárnu přidáte v Nastavení → Integrace → PrusaLink. Zadejte IP adresu a API klíč (najdete v menu tiskárny: Nastavení → Síť → PrusaLink). Klíč je uložen šifrovaně.',
                    en: 'Add a printer in Settings → Integrations → PrusaLink. Enter the IP address and API key (found in printer menu: Settings → Network → PrusaLink). The key is stored encrypted.'
                }
            }
        ],

        history: [
            {
                selector: null,
                title: { cs: 'Historie pohybů', en: 'Movement History' },
                text: {
                    cs: 'Historie zaznamenává každý pohyb skladu: spotřeby, přidání nových cívek, ruční korekce. Přehled slouží k auditování změn a sledování spotřeby v čase.',
                    en: 'History records every stock movement: consumptions, new spool additions, manual adjustments. Use it to audit changes and track consumption over time.'
                }
            },
            {
                selector: null,
                title: { cs: 'Vrácení zpět (Undo)', en: 'Undo' },
                text: {
                    cs: 'Každý záznam spotřeby lze vrátit zpět pomocí ikony ↩ — filament se vrátí do skladu a záznam se smaže. Undo je dostupné pouze pro vlastní záznamy.',
                    en: 'Each consumption entry can be undone with the ↩ icon — the filament returns to stock and the entry is removed. Undo is only available for your own entries.'
                }
            }
        ],

        waste: [
            {
                selector: null,
                title: { cs: 'Zmetky a odpady', en: 'Waste & Scrap' },
                text: {
                    cs: 'Evidence selhání tisku. Sledujte příčiny (stringing, warping, ucpaná tryska…), hmotnost odpadu a přikládejte fotodokumentaci.',
                    en: 'Log print failures. Track causes (stringing, warping, clogging…), waste weight and attach photo documentation.'
                }
            },
            {
                selector: null,
                title: { cs: 'Filtrování a statistiky', en: 'Filtering and Stats' },
                text: {
                    cs: 'Filtrujte záznamy podle důvodu selhání (barevné štítky nahoře) nebo podle konkrétního filamantu. Statistika nahoře ukazuje celkové ztráty a nejčastější příčiny.',
                    en: 'Filter records by failure reason (colour pills at top) or by specific filament. The summary at the top shows total waste and most common causes.'
                }
            }
        ],

        maintenance: [
            {
                selector: null,
                title: { cs: 'Plán údržby', en: 'Maintenance Plan' },
                text: {
                    cs: 'Plánujte pravidelnou nebo jednorázovou údržbu tiskáren. Každý úkol má termín a přiřazenou tiskárnu. Prošlé úkoly se zobrazí v Akčním centru na přehledové stránce.',
                    en: 'Plan regular or one-time maintenance for printers. Each task has a due date and assigned printer. Overdue tasks appear in the Action Centre on the Overview.'
                }
            },
            {
                selector: null,
                title: { cs: 'Opakující se úkoly', en: 'Recurring Tasks' },
                text: {
                    cs: 'Nastavte frekvenci opakování (týdně, měsíčně…). Po označení jako splněné systém automaticky vytvoří nový úkol s posunutým termínem.',
                    en: 'Set a recurrence frequency (weekly, monthly…). After marking as done the system automatically creates a new task with a shifted due date.'
                }
            }
        ],

        users: [
            {
                selector: null,
                title: { cs: 'Správa uživatelů', en: 'User Management' },
                text: {
                    cs: 'Tato stránka slouží k správě uživatelských účtů, rolí, pozvánek a přístupových práv. Máte zde přehled o všech registrovaných účtech.',
                    en: 'This page is for managing user accounts, roles, invitations, and access permissions. Here you get an overview of all registered accounts.'
                }
            },
            {
                selector: '.ui-panel:first-of-type',
                title: { cs: 'Vytvoření pozvánky', en: 'Create Invite' },
                text: {
                    cs: 'V levém panelu vytvořte pozvánku pro nového uživatele. Zadejte e-mail, vyberte roli (Admin / Uživatel) a nastavte přístupová práva k jednotlivým sekcím. Vygenerovaný odkaz lze zkopírovat do schránky.',
                    en: 'In the left panel, create an invite for a new user. Enter an email, select a role (Admin / User) and configure section permissions. The generated link can be copied to clipboard.'
                },
                position: 'right'
            },
            {
                selector: '.xl\\:grid-cols-\\[1fr_340px\\] .ui-panel, .xl\\:grid-cols-\\[340px_minmax\\(0\\,1fr\\)\\] .ui-panel:nth-child(2)',
                title: { cs: 'Seznam a filtrování', en: 'Account List & Filtering' },
                text: {
                    cs: 'Pravá část zobrazuje všechny účty v přehledné tabulce. Použijte vyhledávání, filtrování podle role a stavu, nebo řazení — vše funguje bez obnovení stránky.',
                    en: 'The right side shows all accounts in a clear table. Use search, role/status filtering, or sorting — all work without a page reload.'
                },
                position: 'left'
            },
            {
                selector: '#users-table-container table',
                title: { cs: 'Hromadné akce', en: 'Bulk Actions' },
                text: {
                    cs: 'Každý řádek má checkbox pro výběr. Po zaškrtnutí více účtů se nahoře zobrazí lišta s hromadnými akcemi: aktivovat, deaktivovat nebo smazat vybrané účty.',
                    en: 'Each row has a checkbox for selection. After checking multiple accounts, a bulk action bar appears: activate, deactivate, or delete selected accounts.'
                },
                position: 'top'
            },
            {
                selector: '#users-pagination',
                title: { cs: 'Stránkování', en: 'Pagination' },
                text: {
                    cs: 'Tabulka je stránkovaná po 20 účtech. Při vyhledávání a filtrování se stránkování aktualizuje automaticky. Kliknutím na číslo stránky nebo šipky přecházíte mezi stránkami.',
                    en: 'The table is paginated at 20 accounts per page. Pagination updates automatically during search and filtering. Click page numbers or arrows to navigate.'
                },
                position: 'top'
            },
            {
                selector: null,
                title: { cs: 'Detail uživatele', en: 'User Detail' },
                text: {
                    cs: 'Kliknutím na „Detail" u libovolného uživatele přejdete na stránku s úpravou profilu, nastavením práv, notifikací a přehledem jeho aktivity — projektů, komentářů a auditních záznamů.',
                    en: 'Click "Detail" on any user to go to their profile page where you can edit the profile, set permissions and notifications, and view their recent projects, comments, and audit entries.'
                }
            }
        ]
    };

    // ── Page URLs (for cross-page redirect) ─────────────────────────────────────
    // Maps section IDs to the canonical URL prefix of the page that contains those elements.
    var TOUR_PAGES = {
        overview:    '/',
        filaments:   '/filaments',
        projects:    '/projects',
        calculator:  '/calculator',
        stats:       '/stats',
        storage:     '/storage',
        settings:    '/settings',
        bambu:       '/bambu',
        prusa:       '/prusa',
        history:     '/history',
        waste:       '/waste',
        maintenance: '/maintenance',
        users:       '/users'
    };

    // ── Tour Engine ─────────────────────────────────────────────────────────────

    function TourEngine() {
        this.steps = [];
        this.current = 0;
        this.lang = 'cs';
        this._svg = null;
        this._tip = null;
        this._resizeHandler = null;
    }

    TourEngine.prototype.start = function (steps, lang) {
        if (!steps || steps.length === 0) return;
        this.steps = steps;
        this.current = 0;
        this.lang = lang || window.__helpLang || 'cs';
        this._build();
        this._render();
    };

    TourEngine.prototype._t = function (obj) {
        if (!obj) return '';
        return obj[this.lang] || obj.en || obj.cs || '';
    };

    TourEngine.prototype._build = function () {
        var self = this;

        // ── SVG Overlay ──────────────────────────────────────────────────────────
        var ns = 'http://www.w3.org/2000/svg';
        var svg = document.createElementNS(ns, 'svg');
        svg.id = 'fm-tour-overlay';
        svg.setAttribute('xmlns', ns);
        svg.style.cssText = [
            'position:fixed', 'inset:0', 'width:100%', 'height:100%',
            'z-index:9990', 'pointer-events:all', 'display:block'
        ].join(';');

        // mask: white everywhere (visible), black = hole (transparent)
        var defs = document.createElementNS(ns, 'defs');
        var mask = document.createElementNS(ns, 'mask');
        mask.id = 'fm-tour-mask';
        var bg = document.createElementNS(ns, 'rect');
        bg.setAttribute('width', '100%');
        bg.setAttribute('height', '100%');
        bg.setAttribute('fill', 'white');
        var hole = document.createElementNS(ns, 'rect');
        hole.id = 'fm-tour-hole';
        hole.setAttribute('rx', '10');
        hole.setAttribute('fill', 'black');
        hole.setAttribute('x', '0'); hole.setAttribute('y', '0');
        hole.setAttribute('width', '0'); hole.setAttribute('height', '0');
        mask.appendChild(bg);
        mask.appendChild(hole);
        defs.appendChild(mask);

        // dark backdrop (masked)
        var backdrop = document.createElementNS(ns, 'rect');
        backdrop.setAttribute('width', '100%');
        backdrop.setAttribute('height', '100%');
        backdrop.setAttribute('fill', 'rgba(0,0,0,0.60)');
        backdrop.setAttribute('mask', 'url(#fm-tour-mask)');

        // glow ring around highlighted element
        var ring = document.createElementNS(ns, 'rect');
        ring.id = 'fm-tour-ring';
        ring.setAttribute('fill', 'none');
        ring.setAttribute('stroke', '#818cf8');
        ring.setAttribute('stroke-width', '2.5');
        ring.setAttribute('rx', '12');
        ring.setAttribute('x', '0'); ring.setAttribute('y', '0');
        ring.setAttribute('width', '0'); ring.setAttribute('height', '0');
        ring.style.cssText = 'filter:drop-shadow(0 0 8px rgba(129,140,248,0.8));pointer-events:none;';

        svg.appendChild(defs);
        svg.appendChild(backdrop);
        svg.appendChild(ring);
        document.body.appendChild(svg);
        this._svg = svg;

        // click on dark area = skip to next
        backdrop.addEventListener('click', function () { self.next(); });

        // ── Tooltip ──────────────────────────────────────────────────────────────
        var tip = document.createElement('div');
        tip.id = 'fm-tour-tooltip';
        tip.style.cssText = [
            'position:fixed', 'z-index:9995',
            'width:340px', 'max-width:calc(100vw - 24px)',
            'border-radius:16px', 'overflow:hidden',
            'box-shadow:0 20px 60px rgba(0,0,0,0.35)',
            'background:var(--ui-surface,#fff)',
            'border:1px solid var(--ui-border,#e5e7eb)',
            'transition:opacity 0.15s'
        ].join(';');

        tip.innerHTML = this._tooltipHTML();
        document.body.appendChild(tip);
        this._tip = tip;

        // wire up controls
        tip.querySelector('#fm-tour-prev').addEventListener('click', function () { self.prev(); });
        tip.querySelector('#fm-tour-next').addEventListener('click', function () { self.next(); });
        tip.querySelector('#fm-tour-close').addEventListener('click', function () { self.close(); });

        // resize / scroll re-position
        this._resizeHandler = function () { self._positionTooltip(); };
        window.addEventListener('resize', this._resizeHandler);
    };

    TourEngine.prototype._tooltipHTML = function () {
        return '<div>' +
            // header
            '<div style="display:flex;align-items:center;justify-content:space-between;' +
                'padding:10px 14px 10px 14px;' +
                'background:var(--ui-brand-soft,#eef2ff);' +
                'border-bottom:1px solid var(--ui-border,#e5e7eb);">' +
                '<div style="display:flex;align-items:center;gap:8px;">' +
                    '<div style="width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;' +
                         'background:var(--ui-brand,#6366f1);flex-shrink:0;">' +
                        '<i class="fa-solid fa-route" style="font-size:11px;color:#fff;"></i>' +
                    '</div>' +
                    '<span id="fm-tour-label" style="font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;' +
                         'color:var(--ui-brand,#6366f1);"></span>' +
                '</div>' +
                '<button id="fm-tour-close" title="Zavřít" style="width:24px;height:24px;border:none;background:none;cursor:pointer;' +
                    'display:flex;align-items:center;justify-content:center;border-radius:6px;color:var(--ui-text-muted,#9ca3af);">' +
                    '<i class="fa-solid fa-xmark" style="font-size:13px;"></i>' +
                '</button>' +
            '</div>' +
            // body
            '<div style="padding:16px 16px 12px;">' +
                '<h3 id="fm-tour-title" style="margin:0 0 7px;font-size:15px;font-weight:700;color:var(--ui-text,#111827);line-height:1.3;"></h3>' +
                '<p id="fm-tour-text" style="margin:0;font-size:13px;line-height:1.6;color:var(--ui-text-muted,#6b7280);"></p>' +
            '</div>' +
            // progress dots
            '<div id="fm-tour-dots" style="display:flex;justify-content:center;gap:5px;padding:0 16px 10px;"></div>' +
            // footer
            '<div style="display:flex;align-items:center;justify-content:space-between;' +
                'padding:10px 14px;border-top:1px solid var(--ui-border,#e5e7eb);">' +
                '<button id="fm-tour-prev" style="display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;' +
                    'border:1px solid var(--ui-border,#e5e7eb);background:var(--ui-surface-soft,#f9fafb);' +
                    'font-size:12px;font-weight:600;cursor:pointer;color:var(--ui-text-muted,#6b7280);">' +
                    '<i class="fa-solid fa-chevron-left" style="font-size:9px;"></i>' +
                    '<span id="fm-tour-prev-lbl"></span>' +
                '</button>' +
                '<span id="fm-tour-progress" style="font-size:11px;font-weight:500;color:var(--ui-text-muted,#9ca3af);tabular-nums:true;"></span>' +
                '<button id="fm-tour-next" style="display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;' +
                    'border:none;background:var(--ui-brand,#6366f1);color:#fff;' +
                    'font-size:12px;font-weight:600;cursor:pointer;">' +
                    '<span id="fm-tour-next-lbl"></span>' +
                    '<i class="fa-solid fa-chevron-right" style="font-size:9px;"></i>' +
                '</button>' +
            '</div>' +
        '</div>';
    };

    TourEngine.prototype._render = function () {
        var self = this;
        var step = this.steps[this.current];
        var total = this.steps.length;
        var isFirst = this.current === 0;
        var isLast = this.current === total - 1;
        var L = this.lang;

        // text
        this._tip.querySelector('#fm-tour-title').textContent = this._t(step.title);
        this._tip.querySelector('#fm-tour-text').textContent = this._t(step.text);
        this._tip.querySelector('#fm-tour-label').textContent = L === 'cs' ? 'Průvodce' : 'Tour';
        this._tip.querySelector('#fm-tour-progress').textContent = (this.current + 1) + ' / ' + total;

        // labels
        this._tip.querySelector('#fm-tour-prev-lbl').textContent = L === 'cs' ? 'Zpět' : 'Back';
        this._tip.querySelector('#fm-tour-next-lbl').textContent = isLast ? (L === 'cs' ? 'Dokončit' : 'Finish') : (L === 'cs' ? 'Dále' : 'Next');

        // prev disabled
        var prevBtn = this._tip.querySelector('#fm-tour-prev');
        prevBtn.style.opacity = isFirst ? '0.35' : '1';
        prevBtn.style.pointerEvents = isFirst ? 'none' : 'auto';

        // progress dots
        var dotsEl = this._tip.querySelector('#fm-tour-dots');
        dotsEl.innerHTML = '';
        for (var i = 0; i < total; i++) {
            var dot = document.createElement('div');
            dot.style.cssText = 'width:7px;height:7px;border-radius:50%;transition:all 0.2s;flex-shrink:0;' +
                (i === this.current
                    ? 'background:var(--ui-brand,#6366f1);width:20px;border-radius:4px;'
                    : 'background:var(--ui-border,#d1d5db);');
            dotsEl.appendChild(dot);
        }

        // find element
        var el = (step.selector) ? document.querySelector(step.selector) : null;
        // If this step targets a specific tab panel, switch to that tab first
        // (only if the target element is currently not visible / not rendered by Alpine x-show)
        if (step.tab && step.selector) {
            var r0tab = el ? el.getBoundingClientRect() : null;
            if (!el || (r0tab.width === 0 && r0tab.height === 0)) {
                var tabBtn = document.querySelector('[data-tab-id="' + step.tab + '"]');
                if (tabBtn) {
                    tabBtn.click();
                    var rerenderSelf = this;
                    // Wait for Alpine x-show to re-render, then re-run _render for this step
                    setTimeout(function () { if (rerenderSelf._svg) rerenderSelf._render(); }, 300);
                    return;
                }
            }
        }
        // If selector is specified but element is invisible (hidden tab, collapsed widget,
        // or simply not on this page) — skip to the next step automatically.
        if (step.selector) {
            var r0 = el ? el.getBoundingClientRect() : null;
            var invisible = !el || (r0.width === 0 && r0.height === 0);
            if (invisible) {
                var skipSelf = this;
                // Use a short delay so next() doesn't stack-overflow on consecutive skips
                setTimeout(function () { if (skipSelf._svg) skipSelf.next(); }, 60);
                return;
            }
        }

        // fade tooltip briefly during transition
        this._tip.style.opacity = '0';

        var doPosition = function () {
            self._updateSpotlight(el);
            // wait one frame so tooltip has layout
            requestAnimationFrame(function () {
                self._positionTooltip(el, step.position || 'auto');
                self._tip.style.opacity = '1';
            });
        };

        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
            setTimeout(doPosition, 320);
        } else {
            doPosition();
        }
    };

    TourEngine.prototype._updateSpotlight = function (el) {
        var hole = this._svg.querySelector('#fm-tour-hole');
        var ring = this._svg.querySelector('#fm-tour-ring');
        var PAD = 10;

        if (!el) {
            hole.setAttribute('width', '0'); hole.setAttribute('height', '0');
            ring.setAttribute('width', '0'); ring.setAttribute('height', '0');
            return;
        }

        var r = el.getBoundingClientRect();
        hole.setAttribute('x', r.left - PAD);
        hole.setAttribute('y', r.top - PAD);
        hole.setAttribute('width', r.width + PAD * 2);
        hole.setAttribute('height', r.height + PAD * 2);
        ring.setAttribute('x', r.left - PAD - 3);
        ring.setAttribute('y', r.top - PAD - 3);
        ring.setAttribute('width', r.width + PAD * 2 + 6);
        ring.setAttribute('height', r.height + PAD * 2 + 6);
    };

    TourEngine.prototype._positionTooltip = function (el, position) {
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var tw = this._tip.offsetWidth || 340;
        var th = this._tip.offsetHeight || 220;
        var MARGIN = 16;

        if (!el) {
            // centre on screen
            this._tip.style.left = Math.max(MARGIN, (vw - tw) / 2) + 'px';
            this._tip.style.top = Math.max(MARGIN, (vh - th) / 2) + 'px';
            return;
        }

        var r = el.getBoundingClientRect();
        var pos = position || 'auto';
        var GAP = 16;

        var tryPos = function (p) {
            var x, y;
            if (p === 'bottom') {
                x = Math.max(MARGIN, Math.min(r.left + (r.width - tw) / 2, vw - tw - MARGIN));
                y = r.bottom + GAP;
                return (y + th <= vh - MARGIN) ? { x: x, y: y } : null;
            }
            if (p === 'top') {
                x = Math.max(MARGIN, Math.min(r.left + (r.width - tw) / 2, vw - tw - MARGIN));
                y = r.top - th - GAP;
                return (y >= MARGIN) ? { x: x, y: y } : null;
            }
            if (p === 'right') {
                x = r.right + GAP;
                y = Math.max(MARGIN, Math.min(r.top + (r.height - th) / 2, vh - th - MARGIN));
                return (x + tw <= vw - MARGIN) ? { x: x, y: y } : null;
            }
            if (p === 'left') {
                x = r.left - tw - GAP;
                y = Math.max(MARGIN, Math.min(r.top + (r.height - th) / 2, vh - th - MARGIN));
                return (x >= MARGIN) ? { x: x, y: y } : null;
            }
            return null;
        };

        var order = pos === 'auto' ? ['bottom', 'top', 'right', 'left'] : [pos, 'bottom', 'top', 'right', 'left'];
        var placed = null;
        for (var i = 0; i < order.length; i++) {
            placed = tryPos(order[i]);
            if (placed) break;
        }

        if (!placed) {
            // fallback: centre below element, clamped to viewport
            var fx = Math.max(MARGIN, Math.min(r.left + (r.width - tw) / 2, vw - tw - MARGIN));
            var fy = r.bottom + GAP;
            if (fy + th > vh - MARGIN) fy = Math.max(MARGIN, r.top - th - GAP);
            placed = { x: fx, y: fy };
        }

        this._tip.style.left = placed.x + 'px';
        this._tip.style.top = placed.y + 'px';
    };

    TourEngine.prototype.next = function () {
        if (this.current < this.steps.length - 1) {
            this.current++;
            this._render();
        } else {
            this.close();
        }
    };

    TourEngine.prototype.prev = function () {
        if (this.current > 0) {
            this.current--;
            this._render();
        }
    };

    TourEngine.prototype.close = function () {
        if (this._svg) { this._svg.remove(); this._svg = null; }
        if (this._tip) { this._tip.remove(); this._tip = null; }
        if (this._resizeHandler) {
            window.removeEventListener('resize', this._resizeHandler);
            this._resizeHandler = null;
        }
    };

    // ── Keyboard shortcut (Escape = close) ──────────────────────────────────────
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && _engine) { _engine.close(); _engine = null; }
    });

    // ── Public API ───────────────────────────────────────────────────────────────
    var _engine = null;

    window.startPageTour = function (sectionId) {
        var steps = TOUR_STEPS[sectionId];
        if (!steps) return;

        // If the user is not on the correct page, redirect there and restart via ?tour= param.
        var expectedPath = TOUR_PAGES[sectionId];
        if (expectedPath) {
            var path = window.location.pathname.replace(/\/+$/, '') || '/';
            var onPage = (expectedPath === '/')
                ? (path === '' || path === '/')
                : (path === expectedPath || path.startsWith(expectedPath + '/'));
            if (!onPage) {
                var sep = expectedPath.indexOf('?') >= 0 ? '&' : '?';
                window.location.href = expectedPath + sep + 'tour=' + encodeURIComponent(sectionId);
                return;
            }
        }

        if (_engine) { _engine.close(); }
        _engine = new TourEngine();
        _engine.start(steps, window.__helpLang || 'cs');
    };

    // Auto-start tour when arriving via cross-page redirect (?tour=sectionId)
    document.addEventListener('DOMContentLoaded', function () {
        try {
            var params = new URLSearchParams(window.location.search);
            var tourId = params.get('tour');
            if (tourId && TOUR_STEPS[tourId]) {
                // Clean the param from the URL without a reload
                var clean = new URL(window.location.href);
                clean.searchParams.delete('tour');
                window.history.replaceState({}, '', clean.toString());
                // Delay long enough for Alpine.js and page widgets to initialise
                setTimeout(function () { window.startPageTour(tourId); }, 800);
            }
        } catch (e) { /* non-critical */ }
    });

    window.stopPageTour = function () {
        if (_engine) { _engine.close(); _engine = null; }
    };

})();
