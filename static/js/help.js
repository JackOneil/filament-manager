/**
 * Filament Manager — Interactive Help System
 * Provides contextual tips for every page.
 * Language is controlled by window.__helpLang ('cs' | 'en').
 * Current page is identified by window.__helpEndpoint (Flask endpoint name).
 */
(function () {
    'use strict';

    var HELP_SECTIONS = [
        {
            id: 'overview',
            icon: 'fa-house',
            hasTour: true,
            endpoints: ['overview', 'overview_user'],
            title: { cs: 'Přehled', en: 'Overview' },
            tips: [
                {
                    title: { cs: 'Akční centrum', en: 'Action Centre' },
                    text: {
                        cs: 'Akční centrum shromažďuje vše důležité na jednom místě: filament s nízkým stavem zásoby, projekty blížící se termínu, tiskárny v chybovém stavu a další varování, která vyžadují pozornost.',
                        en: 'The Action Centre collects everything important in one place: low-stock filament, projects approaching deadlines, printers in error state, and other warnings that need attention.'
                    }
                },
                {
                    title: { cs: 'KPI karty', en: 'KPI Cards' },
                    text: {
                        cs: 'Horní řada karet zobrazuje klíčové ukazatele: celkový počet filamentů, projektů, aktivních tiskáren a aktuálně probíhajících tisků. Kliknutím na kartu se dostanete na příslušnou sekci.',
                        en: 'The top row of cards shows key metrics: total filaments, projects, active printers, and currently running prints. Click a card to navigate to the relevant section.'
                    }
                },
                {
                    title: { cs: 'Live stav tiskáren', en: 'Live Printer Status' },
                    text: {
                        cs: 'Widgety Bambu Lab a PrusaLink zobrazují stav tisku v reálném čase — průběh, zbývající čas i aktuálně používaný materiál. Data se automaticky obnovují na pozadí každých 60 sekund.',
                        en: 'Bambu Lab and PrusaLink widgets show print progress in real time — progress bar, remaining time and currently used material. Data refreshes automatically in the background every 60 seconds.'
                    }
                },
                {
                    title: { cs: 'Přeuspořádání widgetů', en: 'Rearranging Widgets' },
                    text: {
                        cs: 'Klikněte na tlačítko „Upravit rozvržení" vpravo nahoře. Widgety lze přetahovat — ostatní widgety se plynule posunou, aby uvolnily místo. Barevná linka ukazuje, kam se widget přesune. Šířku změníte tahem za úchyt v pravém dolním rohu, výšku tahem dolů. Widgety lze také skrýt a znovu zobrazit přes panel viditelnosti. Vše se ukládá do prohlížeče.',
                        en: 'Click "Edit layout" in the top right. Widgets can be dragged — other widgets smoothly slide aside to make room. A coloured line shows where the widget will land. Resize by dragging the handle in the bottom-right corner (width) or pulling down (height). Widgets can also be hidden and restored via the visibility panel. Everything is saved in the browser.'
                    }
                },
                {
                    title: { cs: 'Nejnižší zásoby a nákup', en: 'Lowest Stock and Shopping' },
                    text: {
                        cs: 'Widget „Nejnižší zásoby" zobrazuje filamenty seřazené podle procenta zbývající hmotnosti (od nejmenší zásoby). U každého filamentu je ikona nákupního košíku, která otevře odkaz na produkt v e-shopu (podle nastavení buď přímý odkaz, vyhledávání podle značky, nebo globální šablona).',
                        en: 'The "Lowest Stock" widget shows filaments sorted by remaining weight percentage (lowest first). Each filament has a shopping cart icon that opens the product link in your shop (either a direct URL, brand-specific search, or global search template, depending on your settings).'
                    }
                }
            ]
        },
        {
            id: 'filaments',
            icon: 'fa-boxes-stacked',
            hasTour: true,
            endpoints: ['filaments_index', 'index_user', 'filament_detail', 'add_filament', 'edit_filament', 'use_filament', 'filament_import_csv'],
            title: { cs: 'Inventář filamentů', en: 'Filament Inventory' },
            tips: [
                {
                    title: { cs: 'Zobrazení karet / seznam / kompaktní', en: 'Card / List / Compact view' },
                    text: {
                        cs: 'Přepínač v horním panelu mění způsob zobrazení. Karty jsou přehledné, seznam umožňuje rychlé procházení, kompaktní zobrazení ukáže co nejvíce filamentů najednou.',
                        en: 'The toggle in the top bar switches the display style. Cards are visual, list allows quick scanning, compact view shows as many filaments as possible at once.'
                    }
                },
                {
                    title: { cs: 'Filtry a řazení', en: 'Filters and Sorting' },
                    text: {
                        cs: 'Filtrujte podle výrobce, barvy, materiálu, stavu zásoby nebo tagu. Každý filtr má vyhledávací pole. Kliknutím na záhlaví sloupce seřadíte seznam. Aktivní filtry jsou viditelné jako barevné štítky.',
                        en: 'Filter by brand, colour, material, stock status, or tag. Each filter has a search field. Click a column header to sort the list. Active filters are shown as coloured badges.'
                    }
                },
                {
                    title: { cs: 'Použití filamentu', en: 'Using Filament' },
                    text: {
                        cs: 'Tlačítko „Použít" (ikona odečtení) otevře dialog pro zadání spotřeby v gramech nebo procentech. Pohyby se zaznamenávají do historie a slouží jako základ pro statistiky.',
                        en: 'The "Use" button (subtract icon) opens a dialog to enter consumption in grams or percent. Movements are recorded in history and are used as the basis for statistics.'
                    }
                },
                {
                    title: { cs: 'Hromadné operace', en: 'Bulk Operations' },
                    text: {
                        cs: 'Zaškrtněte více filamentů pomocí checkboxů a hromadně je přidejte do projektu, exportujte nebo smažte. Checkbox v záhlaví vybere vše na aktuální stránce.',
                        en: 'Check multiple filaments and bulk-add them to a project, export, or delete them. The header checkbox selects all items on the current page.'
                    }
                },
                {
                    title: { cs: 'Indikátory nízkého stavu', en: 'Low-stock Indicators' },
                    text: {
                        cs: 'Červený štítek = filament je zcela vyčerpán (0 g). Oranžový štítek = zbývá méně než 20 % původní hmotnosti. Tyto filament jsou také zobrazeny v Akčním centru na přehledu.',
                        en: 'Red badge = filament is fully depleted (0 g). Orange badge = less than 20 % of original weight remains. These filaments also appear in the Action Centre on the overview.'
                    }
                },
                {
                    title: { cs: 'Import z CSV', en: 'CSV Import' },
                    text: {
                        cs: 'V nabídce akcí (⋮) zvolte „Import CSV" a nahrajte soubor se sloupci: name, brand, material, color, weight_total, weight_remaining, price, quantity, nozzle_temp, bed_temp, min_stock_grams, max_stock_grams, tags, shop_url, quality_drying, quality_stringing, quality_adhesion, quality_profile, quality_notes. Existující záznamy (stejný výrobce + barva + materiál) se přeskočí.',
                        en: 'From the actions menu (⋮) choose "Import CSV" and upload a file with columns: name, brand, material, color, weight_total, weight_remaining, price, quantity, nozzle_temp, bed_temp, min_stock_grams, max_stock_grams, tags, shop_url, quality_drying, quality_stringing, quality_adhesion, quality_profile, quality_notes. Existing records (same brand + colour + material) are skipped.'
                    }
                },
                {
                    title: { cs: 'Detail filamentu', en: 'Filament Detail' },
                    text: {
                        cs: 'Klikněte na název filamentu pro detail: kompletní historii pohybů, přiřazené projekty, umístění na polici a rychlé akce (doplnit, použít, přesunout).',
                        en: 'Click the filament name to see the detail page: full movement history, assigned projects, shelf location, and quick actions (refill, use, move).'
                    }
                }
            ]
        },
        {
            id: 'calculator',
            icon: 'fa-calculator',
            hasTour: true,
            endpoints: ['calculator', 'calculator_history_delete'],
            title: { cs: 'Kalkulačka', en: 'Calculator' },
            tips: [
                {
                    title: { cs: 'Výpočet nákladů tisku', en: 'Print cost calculation' },
                    text: {
                        cs: 'Zadejte spotřebu materiálu (g), dobu tisku, cenu filamentu a výkon tiskárny. Kalkulačka automaticky spočítá náklady na materiál, energii a zobrazí celkovou cenu.',
                        en: 'Enter material consumption (g), print time, filament price, and printer power. The calculator automatically computes material and energy costs and shows the total price.'
                    }
                },
                {
                    title: { cs: 'Uložení jako nabídka', en: 'Save as Quote' },
                    text: {
                        cs: 'Po výpočtu klikněte na „Uložit jako nabídku" a přiřaďte výsledek k existujícímu projektu. Nabídka obsahuje rozepsané náklady a lze ji exportovat jako PDF nebo HTML.',
                        en: 'After calculating, click "Save as quote" and assign it to an existing project. The quote includes a cost breakdown and can be exported as PDF or HTML.'
                    }
                },
                {
                    title: { cs: 'Historie výpočtů', en: 'Calculation History' },
                    text: {
                        cs: 'Každý uložený výpočet se zobrazuje v historii. Kliknutím na záznam jej znovu načtete do kalkulačky. Záznamy lze jednotlivě mazat.',
                        en: 'Every saved calculation appears in the history. Clicking an entry reloads it into the calculator. Individual entries can be deleted.'
                    }
                }
            ]
        },
        {
            id: 'projects',
            icon: 'fa-folder-open',
            hasTour: true,
            endpoints: ['projects_index', 'project_create', 'project_detail', 'project_edit', 'project_add_file', 'project_delete_file', 'project_add_link', 'project_delete_link', 'project_add_comment', 'project_add_filament', 'project_remove_filament', 'project_add_quote', 'project_change_status', 'project_add_todo', 'project_toggle_todo', 'project_delete_todo', 'project_edit_todo', 'project_advance_status', 'project_clone', 'project_generate_share_token', 'project_revoke_share_token', 'project_share', 'project_templates_index', 'project_template_save', 'project_template_delete', 'project_create_from_template', 'project_comment_react'],
            title: { cs: 'Projekty', en: 'Projects' },
            tips: [
                {
                    title: { cs: 'Kanban board', en: 'Kanban Board' },
                    text: {
                        cs: 'Projekty jsou uspořádány do sloupců podle stavu: Návrh → Schváleno → Tisk → Dokončeno → Zrušeno. Přepněte na tabulkové zobrazení kliknutím na ikonu tabulky vpravo nahoře.',
                        en: 'Projects are arranged in columns by status: Draft → Approved → Printing → Done → Cancelled. Switch to table view by clicking the table icon in the top right.'
                    }
                },
                {
                    title: { cs: 'Přeuspořádání widgetů', en: 'Rearranging Widgets' },
                    text: {
                        cs: 'Klikněte na tlačítko „Upravit rozvržení" vpravo nahoře. Sloupce Kanbanu a tabulku projektů lze přetahovat — ostatní widgety se plynule posunou, aby uvolnily místo. Barevná linka ukazuje, kam se widget přesune. Šířku změníte tahem za úchyt v pravém dolním rohu. Widgety lze skrýt přes panel viditelnosti. Nastavení se ukládá do prohlížeče.',
                        en: 'Click "Edit layout" in the top right. Kanban columns and the project table can be dragged — other widgets smoothly slide aside to make room. A coloured line shows where the widget will land. Resize by dragging the handle in the bottom-right corner. Widgets can be hidden via the visibility panel. Settings are saved in the browser.'
                    }
                },
                {
                    title: { cs: 'Filtrování projektů', en: 'Filtering Projects' },
                    text: {
                        cs: 'Projekty lze filtrovat podle klienta, tagu, priority nebo přiřazeného filamentu. Filtry lze kombinovat. Vyhledávací pole prohledává název i popis projektu.',
                        en: 'Projects can be filtered by client, tag, priority, or assigned filament. Filters can be combined. The search box searches both the project name and description.'
                    }
                },
                {
                    title: { cs: 'Nahrávání souborů', en: 'File Uploads' },
                    text: {
                        cs: 'Na kartě „Soubory" nahrajte STL, 3MF nebo obrázky. Soubory 3D modelů (.stl, .3mf) se otevírají přímo v prohlížeči s interaktivním 3D náhledem. Přetažení souborů (drag & drop) je podporováno.',
                        en: 'On the "Files" tab, upload STL, 3MF, or images. 3D model files (.stl, .3mf) open directly in the browser with an interactive 3D preview. Drag & drop is supported.'
                    }
                },
                {
                    title: { cs: 'Plánování materiálu', en: 'Material Planning' },
                    text: {
                        cs: 'Na kartě „Materiály" přiřaďte filament k projektu a zadejte plánovanou spotřebu. Systém ukazuje, zda máte dostatek zásoby. Filament lze přidat i ze stránky inventáře pomocí hromadné akce.',
                        en: 'On the "Materials" tab, assign filament to a project and enter planned consumption. The system shows whether you have enough stock. Filament can also be added from the inventory page via bulk action.'
                    }
                },
                {
                    title: { cs: 'Komentáře a úkoly', en: 'Comments and Todos' },
                    text: {
                        cs: 'Každý projekt má kartu komentářů (Markdown s náhledem) a kartu úkolů (TODO seznam). U každého úkolu lze nastavit volitelný termín splnění — červená ikona hodiny = po termínu, oranžová = blíží se termín. Úkoly lze přejmenovat přes tlačítko tužky přímo v řádku.',
                        en: 'Each project has a comments tab (Markdown with preview) and a Todo tab. Each todo can have an optional due date — a red clock means overdue, orange means due soon. Todos can be renamed inline using the pencil button.'
                    }
                },
                {
                    title: { cs: 'Termíny úkolů v přehledu', en: 'Todo Due Dates in Overview' },
                    text: {
                        cs: 'Úkoly s prošlým nebo blížícím se termínem se automaticky zobrazují v sekci „Hoří teď" na hlavní stránce i jako samostatná karta v Akčním centru. Klik na řádek otevře přímo kartu Úkolů daného projektu.',
                        en: 'Todos with overdue or approaching due dates are automatically shown in the hot list on the overview page and as a dedicated card in the Action Centre. Clicking a row opens the Todo tab of that project directly.'
                    }
                },
                {
                    title: { cs: 'Webové odkazy', en: 'Web Links' },
                    text: {
                        cs: 'Na kartě „Soubory" přidejte libovolný URL. Systém automaticky stáhne náhled (OpenGraph titulek, obrázek a popis). Podporuje odkazy na Thingiverse, Printables, MakerWorld a jiné.',
                        en: 'On the "Files" tab, add any URL. The system automatically fetches a preview (OpenGraph title, image and description). Works with Thingiverse, Printables, MakerWorld, and others.'
                    }
                },
                {
                    title: { cs: 'Změna stavu', en: 'Status Workflow' },
                    text: {
                        cs: 'Stav projektu měňte tlačítky ve vrchní části detailu projektu nebo přetažením karty v Kanban boardu. Každá změna stavu se zaznamenává do záznamu o aktivitě.',
                        en: 'Change the project status with the buttons at the top of the project detail or by dragging the card in the Kanban board. Each status change is recorded in the activity log.'
                    }
                },
                {
                    title: { cs: 'Tagy a priority', en: 'Tags and Priorities' },
                    text: {
                        cs: 'Přidejte tagy pro snadné filtrování (např. „klient-novak", „prototyp"). Priority (Nízká / Střední / Vysoká / Kritická) zvýrazní projekty barevně na Kanban boardu.',
                        en: 'Add tags for easy filtering (e.g. "client-novak", "prototype"). Priorities (Low / Medium / High / Critical) colour-code projects on the Kanban board.'
                    }
                },
                {
                    title: { cs: 'Rychlý posun stavu', en: 'Quick Status Advance' },
                    text: {
                        cs: 'Tlačítko „Posunout do dalšího stavu" v záhlaví projektu automaticky přesune projekt na další krok ve workflow (Nový → Čeká na schválení → Schváleno → Tisk → Hotovo) bez nutnosti ručně vybírat stav.',
                        en: 'The "Advance to next status" button in the project header automatically moves the project to the next step in the workflow (New → Pending Approval → Approved → Printing → Done) without manually selecting a status.'
                    }
                },
                {
                    title: { cs: 'Duplikace projektu', en: 'Duplicate Project' },
                    text: {
                        cs: 'Tlačítkem „Duplikovat projekt" vytvoříte kopii projektu s přenesenými filamenty a tiskovými položkami. Komentáře, soubory a joby se nekopírují.',
                        en: 'The "Duplicate project" button creates a copy of the project with its filaments and print items. Comments, files, and jobs are not copied.'
                    }
                },
                {
                    title: { cs: 'Šablony projektů', en: 'Project Templates' },
                    text: {
                        cs: 'Uložte opakující se projekty jako šablony přes tlačítko „Uložit jako šablonu" v detailu projektu. Při zakládání nového projektu vyberte šablonu z rozbalovacího seznamu a formulář se předvyplní. Správa šablon je dostupná přes odkaz „Šablony" v horní liště seznamu projektů.',
                        en: 'Save recurring projects as templates using the "Save as template" button in the project detail. When creating a new project, select a template from the dropdown and the form is pre-filled. Manage templates via the "Templates" link in the project list header.'
                    }
                },
                {
                    title: { cs: 'Veřejný odkaz pro sdílení', en: 'Public Share Link' },
                    text: {
                        cs: 'Vygenerujte veřejný odkaz pro sdílení projektu s klientem (čtení bez přihlášení). Odkaz se zobrazí v postranním panelu detailu projektu. Odkaz lze kdykoliv zrušit.',
                        en: 'Generate a public share link to show the project to a client (read-only, no login required). The link is shown in the project detail sidebar. The link can be revoked at any time.'
                    }
                },
                {
                    title: { cs: 'Reakce na komentáře', en: 'Comment Reactions' },
                    text: {
                        cs: 'Pod každým komentářem klikněte na ikonu smajlíka a přidejte emoji reakci (👍 ✅ 🔄 🎉 ❤️). Kliknutím na existující reakci ji přidáte nebo odeberete. Počty reakcí jsou viditelné všem.',
                        en: 'Below each comment, click the smiley icon to add an emoji reaction (👍 ✅ 🔄 🎉 ❤️). Clicking an existing reaction toggles it on or off. Reaction counts are visible to everyone.'
                    }
                }
            ]
        },
        {
            id: 'storage',
            icon: 'fa-warehouse',
            hasTour: true,
            endpoints: ['storage_index', 'storage_add_shelf', 'storage_edit_shelf', 'storage_delete_shelf', 'storage_add_slot', 'storage_remove_slot', 'storage_reorder_shelves'],
            title: { cs: 'Úložiště', en: 'Storage' },
            tips: [
                {
                    title: { cs: 'Vizuální mapa regálů', en: 'Visual Shelf Map' },
                    text: {
                        cs: 'Stránka úložiště zobrazuje všechny regály jako mřížku slotů. Obsazené sloty zobrazují barvu a název filamentu. Prázdné sloty jsou šedé a kliknutím na ně lze filament umístit.',
                        en: 'The storage page shows all shelves as a grid of slots. Occupied slots show the colour and name of the filament. Empty slots are grey — click them to place a filament.'
                    }
                },
                {
                    title: { cs: 'Přidání regálu', en: 'Adding a Shelf' },
                    text: {
                        cs: 'Klikněte na „Přidat regál" a zadejte název a počet řad a sloupců. Regál pak okamžitě zobrazí prázdnou mřížku. Počet slotů lze později upravit.',
                        en: 'Click "Add Shelf" and enter the name and number of rows and columns. The shelf immediately displays an empty grid. The slot count can be adjusted later.'
                    }
                },
                {
                    title: { cs: 'Umístění filamentu', en: 'Placing Filament' },
                    text: {
                        cs: 'Klikněte na prázdný slot a vyberte filament ze seznamu. Filament pak uvidíte i na stránce detailu filamentu v sekci „Umístění na polici". Na jeden slot lze umístit pouze jeden filament.',
                        en: 'Click an empty slot and select a filament from the list. The filament will then also appear on the filament detail page under "Shelf Location". Only one filament can be placed per slot.'
                    }
                },
                {
                    title: { cs: 'Přeuspořádání polic', en: 'Reordering Shelves' },
                    text: {
                        cs: 'Pořadí polic lze měnit přetažením — chytněte ikonu ⠿ vlevo od názvu police a přetáhněte ji na požadovanou pozici. Pořadí je automaticky uloženo.',
                        en: 'Reorder shelves by drag-and-drop — grab the ⠿ handle to the left of the shelf name and drop it at the desired position. The order is saved automatically.'
                    }
                },
                {
                    title: { cs: 'Velikost dlaždic a hledání', en: 'Tile Size & Find' },
                    text: {
                        cs: 'V panelu nástrojů lze přepínat velikost dlaždic (Malé / Střední / Velké). Pole „Najít filament" okamžitě zvýrazní a přejde na slot s daným filamentem.',
                        en: 'Use the toolbar to switch tile size (Small / Medium / Large). The "Find filament" field instantly highlights and scrolls to the slot containing the matching filament.'
                    }
                },
                {
                    title: { cs: 'Tisk rozložení', en: 'Print Layout' },
                    text: {
                        cs: 'Tlačítko „Tisk rozložení" otevře tiskový dialog prohlížeče. Veškeré ovládací prvky jsou v tisku skryty — vytiskne se pouze mřížka polic.',
                        en: 'The "Print layout" button opens the browser print dialog. All controls are hidden during printing — only the shelf grid is printed.'
                    }
                }
            ]
        },
        {
            id: 'stats',
            icon: 'fa-chart-line',
            hasTour: true,
            endpoints: ['stats_index'],
            title: { cs: 'Statistiky', en: 'Statistics' },
            tips: [
                {
                    title: { cs: 'Dragovatelné sekce', en: 'Draggable Sections' },
                    text: {
                        cs: 'Zapněte „Režim úprav" tlačítkem vpravo nahoře. Sekce pak přetahujte do požadovaného pořadí. Pomocí šipek měňte šířku, tlačítkem oka sekci skryjete. Nastavení se uloží do prohlížeče.',
                        en: 'Enable "Edit mode" with the button in the top right. Sections can then be dragged into the desired order. Use arrows to resize width, use the eye button to hide a section. Settings are saved in the browser.'
                    }
                },
                {
                    title: { cs: 'Prognóza doplnění', en: 'Reorder Forecast' },
                    text: {
                        cs: 'Graf Prognóza vypočítá průměrnou denní spotřebu a odhadne, za kolik dní dojde každý filament. Filament se červeně zvýrazní, pokud dojde do 30 dní.',
                        en: 'The Forecast chart calculates average daily consumption and estimates how many days until each filament runs out. Filaments are highlighted in red if they will run out within 30 days.'
                    }
                },
                {
                    title: { cs: 'Omezení řádků', en: 'Row Limits' },
                    text: {
                        cs: 'Každá tabulka ve statistikách má selector pro omezení počtu zobrazených řádků (5, 10, 25, Vše). Limit se ukládá individuálně per-tabulka.',
                        en: 'Each table in statistics has a row-limit selector (5, 10, 25, All). The limit is saved individually per table.'
                    }
                },
                {
                    title: { cs: 'Barevná paleta', en: 'Colour Palette' },
                    text: {
                        cs: 'Sekce Barvy zobrazuje všechny barvy filamentu seřazené podle odstínu (HSL). Každá barva ukazuje počet filamentů, celkovou hmotnost a odhadovanou hodnotu zásoby.',
                        en: 'The Colours section displays all filament colours sorted by hue (HSL). Each colour shows the number of filaments, total weight, and estimated stock value.'
                    }
                }
            ]
        },
        {
            id: 'bambu',
            icon: 'fa-plug-circle-bolt',
            hasTour: true,
            endpoints: ['bambu_index', 'bambu_sync', 'bambu_job_detail', 'bambu_job_delete', 'bambu_create_project', 'bambu_job_map', 'bambu_job_deduct_slot'],
            title: { cs: 'Bambu Lab', en: 'Bambu Lab' },
            tips: [
                {
                    title: { cs: 'Synchronizace s Bambu Cloud', en: 'Bambu Cloud Sync' },
                    text: {
                        cs: 'Tiskové úlohy se stahují automaticky na pozadí každých 60 sekund (interval lze změnit v Nastavení → Integrace). Ruční synchronizaci spustíte tlačítkem „Synchronizovat".',
                        en: 'Print jobs are fetched automatically in the background every 60 seconds (interval can be changed in Settings → Integrations). Trigger a manual sync with the "Synchronise" button.'
                    }
                },
                {
                    title: { cs: 'Automatické mapování filamentu', en: 'Auto-mapping Filament' },
                    text: {
                        cs: 'Po každé synchronizaci systém porovná barvu a materiál úlohy se zásobou v inventáři. Pokud najde přesně jednu shodu, přiřadí filament automaticky. U nejednoznačných shod zobrazí návrhy v Akčním centru přehledu s tlačítkem Přijmout. Funkci lze zapnout nebo vypnout v Nastavení → Integrace.',
                        en: 'After each sync, the system matches the job\'s colour and material against inventory. If exactly one match is found, the filament is assigned automatically. For ambiguous matches, suggestions appear in the Overview Action Centre with an Accept button. The feature can be toggled in Settings → Integrations.'
                    }
                },
                {
                    title: { cs: 'Automatický odpočet filamentu', en: 'Automatic Filament Deduction' },
                    text: {
                        cs: 'Po dokončeném tisku systém automaticky odečte spotřebu filamentu z inventáře na základě dat z Bambu Cloud (hmotnost na AMS slot). Odpočet lze vypnout v nastavení úlohy.',
                        en: 'After a completed print, the system automatically deducts filament consumption from inventory based on Bambu Cloud data (weight per AMS slot). Deduction can be disabled in the job settings.'
                    }
                },
                {
                    title: { cs: 'Filtry úloh', en: 'Job Filters' },
                    text: {
                        cs: 'Filtrujte tiskové úlohy podle tiskárny, stavu (dokončeno, selháno, probíhá) nebo časového rozsahu pomocí rychlých filtrů (pills) v horní části stránky.',
                        en: 'Filter print jobs by printer, status (completed, failed, in progress), or time range using the quick filter pills at the top of the page.'
                    }
                },
                {
                    title: { cs: 'Vytvoření projektu z tiskové úlohy', en: 'Create Project from Print Job' },
                    text: {
                        cs: 'Klikněte na „Přiřadit projekt" u libovolné tiskové úlohy. Systém nabídne existující projekty na základě shody s názvem úlohy (fuzzy matching). Pokud žádný nevyhovuje, zobrazí se tlačítko „Vytvořit nový projekt" s předvyplněným názvem — jedním kliknutím projekt okamžitě vznikne a přiřadí se k úloze.',
                        en: 'Click "Assign project" on any print job. The system suggests existing projects based on fuzzy-matching the job title. If none match, a "Create new project" button appears with a pre-filled name — one click creates and assigns the project immediately.'
                    }
                }
            ]
        },
        {
            id: 'prusa',
            icon: 'fa-plug',
            hasTour: true,
            endpoints: ['prusa_index', 'prusa_printer_detail', 'prusa_job_detail'],
            title: { cs: 'PrusaLink', en: 'PrusaLink' },
            tips: [
                {
                    title: { cs: 'Lokální polling', en: 'Local Polling' },
                    text: {
                        cs: 'PrusaLink komunikuje přímo s tiskárnou ve vaší lokální síti (bez cloudu). Stav tisku se aktualizuje každých 60 sekund. Tiskárna musí být dostupná na nakonfigurované IP adrese.',
                        en: 'PrusaLink communicates directly with the printer on your local network (no cloud). Print status is updated every 60 seconds. The printer must be reachable at the configured IP address.'
                    }
                },
                {
                    title: { cs: 'Přidání tiskárny', en: 'Adding a Printer' },
                    text: {
                        cs: 'V Nastavení → Tiskárny → PrusaLink zadejte IP adresu a API klíč (najdete ho v menu tiskárny: Nastavení → Síť → PrusaLink). API klíč je šifrovaně uložen v databázi.',
                        en: 'In Settings → Printers → PrusaLink, enter the IP address and API key (found in the printer menu: Settings → Network → PrusaLink). The API key is stored encrypted in the database.'
                    }
                }
            ]
        },
        {
            id: 'settings',
            icon: 'fa-sliders',
            hasTour: true,
            endpoints: ['settings', 'toggle_theme', 'export_data', 'import_data'],
            title: { cs: 'Nastavení', en: 'Settings' },
            tips: [
                {
                    title: { cs: 'Číselníky (výrobci, barvy, materiály)', en: 'Dictionaries (brands, colours, materials)' },
                    text: {
                        cs: 'Na záložce Číselníky spravujte seznam výrobců (včetně URL e-shopu), barev (s hex kódem) a materiálů. Položky, které jsou přiřazeny k filamentům, nelze smazat. Každá akce vás vrátí zpět na tuto záložku.',
                        en: 'On the Dictionaries tab, manage the list of brands (including shop URL), colours (with hex code), and materials. Items assigned to filaments cannot be deleted. Each action returns you to this tab.'
                    }
                },
                {
                    title: { cs: 'Nákupní odkaz výrobce (ikona košíku)', en: 'Brand shop link (cart icon)' },
                    text: {
                        cs: 'U každého výrobce v číselníku je ikona košíku 🛒. Kliknutím na ni otevřete modální okno, kde zadáte šablonu URL pro vyhledávání v e-shopu tohoto výrobce. Použijte {query} jako zástupný symbol — bude nahrazen názvem filamantu. Zadejte testovací dotaz a zobrazte si náhled výsledného odkazu ještě před uložením. K dispozici jsou předvyplněné příklady oblíbených obchodů (Bambu Lab, Prusa, Alza.cz, AliExpress, Amazon).',
                        en: 'Each brand in the dictionary has a cart icon 🛒. Clicking it opens a modal where you set a URL template for searching this brand\'s shop. Use {query} as a placeholder — it will be replaced with the filament name. Enter a test query to preview the resulting link before saving. Quick-fill examples for popular shops are available (Bambu Lab, Prusa, Alza.cz, AliExpress, Amazon).'
                    }
                },
                {
                    title: { cs: 'Globální e-shop pro doobjednávání', en: 'Global reorder shop' },
                    text: {
                        cs: 'V sekci „E-shop pro doobjednávání" nastavte výchozí URL šablonu pro vyhledávání filamentů. Tato šablona se použije u filamentů, jejichž výrobce nemá vlastní nákupní odkaz. Použijte {query} jako zástupný symbol. Zadejte testovací dotaz a hned uvidíte náhled výsledného odkazu — kliknutím na „Otevřít v obchodě" si jej ověřte v prohlížeči. K dispozici jsou předvyplněné příklady: Bambu Lab (EU), Prusa, Alza.cz, Allegro.cz, Mironet.cz, Amazon.de, AliExpress.',
                        en: 'In the "Reorder shop" section, set a default URL template for searching filaments. This template is used for filaments whose brand has no dedicated shop link. Use {query} as a placeholder. Enter a test query and see a live preview of the resulting link — click "Open in shop" to verify it in the browser. Quick-fill examples available: Bambu Lab (EU), Prusa, Alza.cz, Allegro.cz, Mironet.cz, Amazon.de, AliExpress.'
                    }
                },
                {
                    title: { cs: 'Export a Import zálohy', en: 'Backup Export and Import' },
                    text: {
                        cs: 'Na záložce Data exportujte celou databázi do JSON souboru (filament, projekty, nastavení, uživatelé, soubory projektů jsou zakódovány v Base64). Import ze zálohy je idempotentní — existující záznamy se přeskočí.',
                        en: 'On the Data tab, export the entire database to a JSON file (filament, projects, settings, users, project files are Base64-encoded). Import from backup is idempotent — existing records are skipped.'
                    }
                },
                {
                    title: { cs: 'Správa uživatelů', en: 'User Management' },
                    text: {
                        cs: 'V sekci Uživatelé (přístupné jen adminu) vytvořte pozvánky, přiřaďte role (Admin / Uživatel) a deaktivujte účty. Pozvánka je jednorázový odkaz s platností 7 dní.',
                        en: 'In the Users section (admin only), create invitations, assign roles (Admin / User), and deactivate accounts. An invitation is a one-time link valid for 7 days.'
                    }
                },
                {
                    title: { cs: 'Energie a náklady tisku', en: 'Energy and Print Costs' },
                    text: {
                        cs: 'Nastavte cenu kWh a výkon tiskárny (W). Tyto hodnoty se pak automaticky použijí v kalkulačce pro výpočet nákladů na energii. Nastavit lze i délku přípravy tiskárny před tiskem.',
                        en: 'Set the kWh price and printer power (W). These values are then used automatically in the calculator for energy cost calculation. You can also set the pre-job preparation time.'
                    }
                },
                {
                    title: { cs: 'Téma a jazyk', en: 'Theme and Language' },
                    text: {
                        cs: 'Přepínač tématu (světlé / tmavé) je dostupný v pravém horním rohu navigační lišty. Jazyk aplikace (čeština / angličtina) a měnu nastavíte v Nastavení → Obecné.',
                        en: 'The theme toggle (light / dark) is in the top right of the navigation bar. Application language (Czech / English) and currency are set in Settings → General.'
                    }
                },
                {
                    title: { cs: 'Časové pásmo', en: 'Timezone' },
                    text: {
                        cs: 'V Nastavení → Obecné nastavte časové pásmo aplikace. Všechna data a časy (historie pohybů, tiskové úlohy) se zobrazují v tomto pásmu.',
                        en: 'In Settings → General, set the application timezone. All dates and times (movement history, print jobs) are displayed in this timezone.'
                    }
                }
            ]
        },
        {
            id: 'maintenance',
            icon: 'fa-wrench',
            hasTour: true,
            endpoints: ['maintenance_index', 'maintenance_add', 'maintenance_complete', 'maintenance_delete'],
            title: { cs: 'Údržba', en: 'Maintenance' },
            tips: [
                {
                    title: { cs: 'Plánování údržby', en: 'Maintenance Scheduling' },
                    text: {
                        cs: 'Naplánujte opakující se nebo jednorázové úkoly údržby tiskáren. Každý úkol může mít termín a přiřazenou tiskárnu. Prošlé úkoly jsou zvýrazněny v Akčním centru.',
                        en: 'Schedule recurring or one-time maintenance tasks for printers. Each task can have a due date and assigned printer. Overdue tasks are highlighted in the Action Centre.'
                    }
                },
                {
                    title: { cs: 'Označení jako splněné', en: 'Mark as Completed' },
                    text: {
                        cs: 'Klikněte na tlačítko „Splněno" u úkolu. Pokud je úkol opakující se, systém automaticky vytvoří nový úkol s posunutým termínem podle nastavené frekvence.',
                        en: 'Click the "Complete" button on a task. If the task is recurring, the system automatically creates a new task with the due date shifted by the configured frequency.'
                    }
                }
            ]
        },
        {
            id: 'waste',
            icon: 'fa-triangle-exclamation',
            hasTour: true,
            endpoints: ['waste_index', 'waste_add', 'waste_edit', 'waste_delete', 'waste_upload_file', 'waste_serve_file', 'waste_download_file', 'waste_delete_file'],
            title: { cs: 'Zmetky a odpady', en: 'Waste & Scrap' },
            tips: [
                {
                    title: { cs: 'Záznam zmetku', en: 'Logging a Waste Record' },
                    text: {
                        cs: 'Klikněte na „Zapsat zmetek" a vyplňte filament, důvod selhání (stringing, warping, ucpaná tryska…), hmotnost v gramech a volitelně projekt. Záznamy se zobrazují v chronologickém přehledu s kumulativní statistikou.',
                        en: 'Click "Log waste record" and fill in the filament, failure reason (stringing, warping, clogging…), weight in grams, and optionally a project. Records are shown in a chronological overview with cumulative stats.'
                    }
                },
                {
                    title: { cs: 'Úprava záznamu', en: 'Editing a Record' },
                    text: {
                        cs: 'Klikněte na ikonu tužky (✏) u záznamu. Otevře se modální okno předvyplněné aktuálními hodnotami. Změny uložte tlačítkem „Uložit".',
                        en: 'Click the pencil icon (✏) next to a record. A modal pre-filled with the current values opens. Save changes with the "Save" button.'
                    }
                },
                {
                    title: { cs: 'Fotodokumentace selhání', en: 'Photo Documentation' },
                    text: {
                        cs: 'Ke každému záznamu lze přiložit jedno nebo více fotek (JPG, PNG, GIF, WEBP). Klikněte na ikonu fotoaparátu u záznamu a vyberte soubory — nahrají se automaticky. Náhledy jsou viditelné přímo v seznamu. Kliknutím na náhled se otevře celostránkový lightbox s možností stažení.',
                        en: 'One or more photos (JPG, PNG, GIF, WEBP) can be attached to each record. Click the camera icon on the record and select files — they upload automatically. Thumbnails are visible directly in the list. Click a thumbnail to open a full-screen lightbox with a download option.'
                    }
                },
                {
                    title: { cs: 'Smazání fotky', en: 'Deleting a Photo' },
                    text: {
                        cs: 'Najeďte myší na náhled fotky. Zobrazí se červené tlačítko × v rohu. Kliknutím fotku trvale smažete. Smazáním záznamu zmetku se automaticky smažou i všechny přiložené fotky.',
                        en: 'Hover over a photo thumbnail. A red × button appears in the corner. Clicking it permanently deletes the photo. Deleting the waste record also automatically removes all its attached photos.'
                    }
                },
                {
                    title: { cs: 'Filtrování záznamů', en: 'Filtering Records' },
                    text: {
                        cs: 'Filtrujte záznamy podle důvodu selhání (barevné štítky nahoře) nebo podle konkrétního filamentu (vyhledávací pole). Filtry lze kombinovat. Aktivní filtr filamentu se zobrazí jako štítek, kliknutím na × ho odeberete.',
                        en: 'Filter records by failure reason (coloured pills at the top) or by a specific filament (search field). Filters can be combined. An active filament filter is shown as a badge — click × to remove it.'
                    }
                },
                {
                    title: { cs: 'Záznam zmetku z tiskové úlohy', en: 'Log Waste from a Print Job' },
                    text: {
                        cs: 'Na stránkách Bambu Lab a PrusaLink mají selháné, zrušené nebo zastavené úlohy tlačítko „Zaznamenat zmetek". Kliknutím se otevře předvyplněný formulář s filamentem, hmotností a projektem z dané úlohy.',
                        en: 'On the Bambu Lab and PrusaLink pages, failed, cancelled, or stopped jobs have a "Log as waste" button. Clicking it opens a pre-filled form with the filament, weight, and project from that job.'
                    }
                }
            ]
        },
        {
            id: 'general',
            icon: 'fa-circle-info',
            endpoints: [],
            title: { cs: 'Obecné tipy', en: 'General Tips' },
            tips: [
                {
                    title: { cs: 'Tmavé téma', en: 'Dark Theme' },
                    text: {
                        cs: 'Klikněte na ikonu měsíce / slunce v pravém horním rohu navigační lišty pro přepnutí mezi světlým a tmavým tématem. Nastavení se uloží a platí pro celou aplikaci.',
                        en: 'Click the moon / sun icon in the top right of the navigation bar to toggle between light and dark theme. The setting is saved and applies across the whole app.'
                    }
                },
                {
                    title: { cs: 'Rychlé hledání (Cmd/Ctrl + K)', en: 'Quick Search (Cmd/Ctrl + K)' },
                    text: {
                        cs: 'Stiskněte Ctrl+K (nebo Cmd+K na Macu) pro otevření panelu rychlého hledání. Prohledává filament, projekty a navigaci. Kliknutím na výsledek přejdete přímo na danou stránku.',
                        en: 'Press Ctrl+K (or Cmd+K on Mac) to open the quick search panel. It searches filaments, projects, and navigation. Clicking a result navigates directly to that page.'
                    }
                },
                {
                    title: { cs: 'PWA — instalace jako aplikace', en: 'PWA — Install as App' },
                    text: {
                        cs: 'Filament Manager lze nainstalovat jako progresivní webovou aplikaci (PWA). V prohlížeči Chrome nebo Edge klikněte na ikonu instalace v adresním řádku. Aplikace pak funguje podobně jako nativní app.',
                        en: 'Filament Manager can be installed as a Progressive Web App (PWA). In Chrome or Edge, click the install icon in the address bar. The app then behaves similarly to a native application.'
                    }
                },
                {
                    title: { cs: 'Notifikace', en: 'Notifications' },
                    text: {
                        cs: 'Ikona zvonku v navigaci zobrazuje nepřečtené notifikace. Notifikace se generují při dokončení synchronizace, detekci nízké zásoby nebo změně stavu projektu.',
                        en: 'The bell icon in the navigation shows unread notifications. Notifications are generated when a sync completes, low stock is detected, or a project status changes.'
                    }
                },
                {
                    title: { cs: 'Audit log', en: 'Audit Log' },
                    text: {
                        cs: 'Administrátor může v sekci Uživatelé → Audit log zobrazit historii všech důležitých akcí: přihlášení, změny nastavení, přidání/smazání filamentu atd.',
                        en: 'Administrators can view a history of all important actions in Users → Audit Log: logins, setting changes, filament additions/deletions, etc.'
                    }
                }
            ]
        }
    ];

    /**
     * Alpine.js component factory for the help panel.
     * Usage: x-data="helpApp()"
     */
    window.helpApp = function () {
        return {
            open: false,
            query: '',
            expanded: {},   // section id → boolean

            get lang() { return window.__helpLang || 'cs'; },
            get endpoint() { return window.__helpEndpoint || ''; },

            /** Translate a bilingual {cs, en} object */
            tr(obj) {
                if (!obj) return '';
                return obj[this.lang] || obj['en'] || obj['cs'] || '';
            },

            /** Sections whose endpoint list matches the current page */
            get currentSection() {
                var ep = this.endpoint;
                return HELP_SECTIONS.filter(function (s) {
                    return s.endpoints.length > 0 && s.endpoints.indexOf(ep) !== -1;
                });
            },

            /** All sections filtered by search query */
            get filteredSections() {
                var q = this.query.trim().toLowerCase();
                if (!q) return HELP_SECTIONS;
                var self = this;
                return HELP_SECTIONS.filter(function (s) {
                    var titleMatch = self.tr(s.title).toLowerCase().indexOf(q) !== -1;
                    var tipMatch = s.tips.some(function (tip) {
                        return self.tr(tip.title).toLowerCase().indexOf(q) !== -1 ||
                               self.tr(tip.text).toLowerCase().indexOf(q) !== -1;
                    });
                    return titleMatch || tipMatch;
                }).map(function (s) {
                    if (!q) return s;
                    return Object.assign({}, s, {
                        tips: s.tips.filter(function (tip) {
                            return self.tr(tip.title).toLowerCase().indexOf(q) !== -1 ||
                                   self.tr(tip.text).toLowerCase().indexOf(q) !== -1 ||
                                   self.tr(s.title).toLowerCase().indexOf(q) !== -1;
                        })
                    });
                });
            },

            /** Tips of the current page section filtered by query */
            get currentTips() {
                var q = this.query.trim().toLowerCase();
                var self = this;
                var tips = [];
                this.currentSection.forEach(function (s) {
                    s.tips.forEach(function (tip) {
                        if (!q || self.tr(tip.title).toLowerCase().indexOf(q) !== -1 ||
                               self.tr(tip.text).toLowerCase().indexOf(q) !== -1) {
                            tips.push(tip);
                        }
                    });
                });
                return tips;
            },

            /** Whether search matches anything */
            get hasResults() {
                return this.filteredSections.some(function (s) { return s.tips.length > 0; });
            },

            /** Open/close the panel */
            toggle() { this.open = !this.open; if (this.open) this.$nextTick(function () { document.getElementById('help-search') && document.getElementById('help-search').focus(); }); },
            close() { this.open = false; },

            /** Toggle a section open/closed */
            toggleSection(id) { this.expanded[id] = !this.expanded[id]; },

            /** Whether a section is open — current-page sections default open */
            isOpen(section) {
                if (this.expanded[section.id] !== undefined) return this.expanded[section.id];
                // default: open for current page sections
                return this.currentSection.some(function (s) { return s.id === section.id; });
            },

            /** Handle Escape key */
            onKeydown(e) { if (e.key === 'Escape') this.close(); },

            /** Close panel then start page tour */
            startTour(sectionId) {
                this.close();
                setTimeout(function () {
                    if (window.startPageTour) window.startPageTour(sectionId);
                }, 220);
            }
        };
    };
})();
