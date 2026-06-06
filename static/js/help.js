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
            endpoints: ['index', 'overview_user'],
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
            endpoints: ['filaments_index', 'filament_detail', 'add', 'edit', 'use_filament', 'add_spool', 'remove_spool', 'delete', 'filament_import_csv', 'filament_export_csv', 'filament_update_meta', 'filament_toggle_reorder_snooze', 'inventory_bulk', 'inventory_undo', 'toggle_ui_mode', 'filament_community_db', 'filament_community_db_import'],
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
            endpoints: ['calculator', 'calculator_project', 'delete_history', 'delete_quote', 'export_quote'],
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
            id: 'history',
            icon: 'fa-clock-rotate-left',
            hasTour: false,
            endpoints: ['history', 'clear_history'],
            title: { cs: 'Historie pohybů', en: 'Movement History' },
            tips: [
                {
                    title: { cs: 'Filtrování historie', en: 'Filtering History' },
                    text: {
                        cs: 'Pomocí vyhledávacího pole můžete hledat v názvu filamentu nebo poznámce. Rozbalovací seznam Typ akce omezí záznamy na konkrétní operaci (přidání, odebrání, Bambu tisk atd.). Filtrováním podle data si zobrazíte pohyby pouze z určitého období.',
                        en: 'Use the search field to find records by filament name or note. The Action type dropdown limits records to a specific operation (add, remove, Bambu print, etc.). Date range filters show movements from a specific period.'
                    }
                },
                {
                    title: { cs: 'Typy akcí', en: 'Action Types' },
                    text: {
                        cs: 'Každý záznam má barevný štítek podle typu akce: zelená = přidáno, červená = odebráno, fialová = Bambu tisk, tyrkysová = hromadné přidání, oranžová = hromadné smazání. Při najetí myší na řádek tabulky se zvýrazní odpovídající barvou i levá hrana.',
                        en: 'Each record has a coloured badge according to action type: green = added, red = removed, purple = Bambu print, teal = bulk add, orange = bulk delete. Hovering over a table row also highlights the left border with the matching colour.'
                    }
                },
                {
                    title: { cs: 'Mazání historie', en: 'Clearing History' },
                    text: {
                        cs: 'Tlačítko „Smazat celou historii" vymaže všechny záznamy pohybů najednou. Tato akce je nevratná — po potvrzení dialogu nelze data obnovit.',
                        en: 'The "Clear all history" button deletes every movement record at once. This action is irreversible — once confirmed, the data cannot be restored.'
                    }
                }
            ]
        },
        {
            id: 'projects',
            icon: 'fa-folder-open',
            hasTour: true,
            endpoints: ['projects_index', 'project_create', 'project_detail', 'project_edit', 'project_delete', 'project_upload_file', 'project_download_file', 'project_view_file', 'project_image_file', 'project_delete_file', 'project_add_link', 'project_delete_link', 'project_refresh_link', 'project_add_comment', 'project_update_comment', 'project_delete_comment', 'project_toggle_comment_checkbox', 'project_toggle_description_checkbox', 'project_add_filament', 'project_remove_filament', 'project_update_filament', 'project_consume_filament', 'project_status', 'project_advance_status', 'project_clone', 'project_generate_share_token', 'project_revoke_share_token', 'project_share', 'project_templates_index', 'project_template_save', 'project_template_delete', 'project_create_from_template', 'project_comment_react', 'project_add_todo', 'project_toggle_todo', 'project_delete_todo', 'project_edit_todo', 'project_add_print_item', 'project_edit_print_item', 'project_delete_print_item', 'project_increment_print_item', 'project_decrement_print_item', 'project_share_download_file', 'project_share_view_file', 'project_share_image_file'],
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
            endpoints: ['storage', 'storage_add_shelf', 'storage_update_shelf', 'storage_delete_shelf', 'storage_reorder_shelves', 'storage_assign_slot', 'storage_move_placement', 'storage_update_orientation', 'storage_delete_placement'],
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
            endpoints: ['stats'],
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
            endpoints: ['bambu_jobs', 'bambu_jobs_partial', 'bambu_sync', 'bambu_refetch_thumbnails', 'bambu_job_thumbnail', 'bambu_job_map', 'bambu_job_deduct_slot', 'bambu_job_remap_slot', 'bambu_job_delete', 'bambu_create_project'],
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
            endpoints: ['prusa_jobs', 'prusa_printer_sync', 'prusa_printer_test', 'prusa_job_map', 'prusa_job_delete'],
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
            endpoints: ['settings', 'settings_bambu_test', 'toggle_theme', 'onboarding_dismiss', 'export_data', 'import_data', 'backup_trigger_now', 'backup_list_files', 'backup_download_file', 'backup_delete_file'],
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
                        cs: 'Na záložce Data lze vybrat plný export (včetně souborů) nebo rychlý export bez souborů. Import podporuje dry-run kontrolu kompatibility a režimy konfliktů (skip / merge / overwrite), takže předem víte, co bude přepsáno.',
                        en: 'On the Data tab, you can choose full export (including files) or a quick export without files. Import supports compatibility dry-run and conflict modes (skip / merge / overwrite), so you know in advance what will be overwritten.'
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
                },
                {
                    title: { cs: 'Automatické zálohování', en: 'Automatic Backup' },
                    text: {
                        cs: 'Na záložce Data lze zapnout automatické zálohování. Vyberte frekvenci (denně / týdně / měsíčně), den a čas spuštění. Zálohy se ukládají do složky data/backup na serveru a jsou dostupné ke stažení nebo smazání přímo z nastavení. Tlačítkem „Spustit zálohu teď" lze vytvořit ruční zálohu kdykoliv.',
                        en: 'On the Data tab, you can enable automatic backup. Choose frequency (daily / weekly / monthly), the day and time. Backups are saved to the data/backup folder on the server and are available for download or deletion directly from settings. Use "Run backup now" to trigger a manual backup at any time.'
                    }
                }
            ]
        },
        {
            id: 'users',
            icon: 'fa-users',
            hasTour: true,
            endpoints: ['users_index', 'user_detail', 'audit_logs', 'invite_delete', 'register_account', 'activate_invite', 'login', 'logout'],
            title: { cs: 'Uživatelé', en: 'Users' },
            tips: [
                {
                    title: { cs: 'Vytváření pozvánek', en: 'Creating Invitations' },
                    text: {
                        cs: 'V levém panelu vytvořte pozvánku zadáním e-mailu a výběrem role (Admin / Uživatel). Uživatelům lze dále nastavit přístupová práva k jednotlivým sekcím. Pozvánka je jednorázový odkaz s platností 14 dní. Vygenerovaný odkaz lze jedním kliknutím zkopírovat do schránky.',
                        en: 'In the left panel, create an invite by entering an email and selecting a role (Admin / User). Permissions for individual sections can be configured for users. The invite is a one-time link valid for 14 days. The generated link can be copied to clipboard with one click.'
                    }
                },
                {
                    title: { cs: 'Seznam a filtrování účtů', en: 'Account List and Filtering' },
                    text: {
                        cs: 'Pravý panel zobrazuje přehled všech účtů s možností vyhledávání, filtrování podle role a stavu, a řazení. Tabulka je stránkovaná a veškeré filtrování probíhá bez obnovení stránky. U každého účtu jsou k dispozici checkboxy pro hromadné akce.',
                        en: 'The right panel shows all accounts with search, role/status filtering, and sorting. The table is paginated and all filtering happens without page reload. Each account has a checkbox for bulk actions.'
                    }
                },
                {
                    title: { cs: 'Hromadné akce', en: 'Bulk Actions' },
                    text: {
                        cs: 'Zaškrtněte více účtů a pomocí tlačítka v horní liště proveďte hromadnou akci: aktivovat, deaktivovat nebo smazat účty. Při hromadném mazání jsou projekty přeřazeny na vás. Není možné smazat vlastní účet ani posledního administrátora.',
                        en: 'Check multiple accounts and use the button in the top bar to perform a bulk action: activate, deactivate, or delete accounts. Projects are reassigned to you during bulk deletion. You cannot delete your own account or the last administrator.'
                    }
                },
                {
                    title: { cs: 'Detail a správa účtu', en: 'Account Detail and Management' },
                    text: {
                        cs: 'Na stránce detailu uživatele lze upravit jméno, e-mail, roli, stav účtu, notifikační preference a přístupová práva. V pravé části jsou zobrazeny poslední projekty, komentáře a auditní záznamy daného uživatele. Tlačítkem „Smazat účet" lze účet trvale odstranit (s ochranou proti smazání sebe sama a posledního admina).',
                        en: 'On the user detail page, you can edit name, email, role, account status, notification preferences, and access permissions. The right side shows recent projects, comments, and audit entries for the user. The "Delete Account" button permanently removes the account (with protection against deleting yourself or the last admin).'
                    }
                },
                {
                    title: { cs: 'Audit log', en: 'Audit Log' },
                    text: {
                        cs: 'V sekci Uživatelé → Audit log zobrazíte historii všech důležitých akcí: přihlášení, změny nastavení, přidání/smazání filamentu atd. Lze filtrovat podle akce, typu objektu a fulltextově vyhledávat.',
                        en: 'In Users → Audit Log you can view a history of all important actions: logins, setting changes, filament additions/deletions, etc. Filter by action, object type, and fulltext search are available.'
                    }
                }
            ]
        },
        {
            id: 'account',
            icon: 'fa-user-gear',
            hasTour: false,
            endpoints: ['account_settings', 'notifications_index', 'notification_mark_read', 'notification_mark_all_read', 'notification_delete', 'notification_delete_read'],
            title: { cs: 'Účet', en: 'Account' },
            tips: [
                {
                    title: { cs: 'Přehled účtu', en: 'Account Overview' },
                    text: {
                        cs: 'Stránka účtu zobrazuje vaše jméno, e-mail, roli a datum posledního přihlášení. V levém sloupci najdete statistiky projektů a poslední projekty.',
                        en: 'The account page shows your name, email, role, and last login date. The left column displays project statistics and recent projects.'
                    }
                },
                {
                    title: { cs: 'Záložky nastavení', en: 'Settings Tabs' },
                    text: {
                        cs: 'Nastavení účtu je rozděleno do záložek: Profil (jméno), Zabezpečení (změna hesla, aktivní relace), Vzhled (jazyk a motiv) a Notifikace (co vás má upozornit).',
                        en: 'Account settings are organised into tabs: Profile (name), Security (password change, active sessions), Appearance (language and theme), and Notifications (what to alert you about).'
                    }
                },
                {
                    title: { cs: 'Aktivní relace a odhlášení zařízení', en: 'Active Sessions and Sign Out Everywhere' },
                    text: {
                        cs: 'V záložce Zabezpečení vidíte všechna zařízení, na kterých jste přihlášeni. Tlačítkem „Odhlásit všechna ostatní zařízení" můžete všechny ostatní relace ukončit — vaše aktuální zůstane aktivní.',
                        en: 'The Security tab shows all devices where you are logged in. Use "Sign out all other devices" to end all other sessions — your current one stays active.'
                    }
                },
                {
                    title: { cs: 'Síla hesla', en: 'Password Strength' },
                    text: {
                        cs: 'Při změně hesla se zobrazí ukazatel síly — od „Velmi slabé" po „Velmi silné". Silné heslo by mělo mít alespoň 12 znaků, kombinaci velkých a malých písmen, číslic a speciálních znaků.',
                        en: 'When changing your password, a strength indicator appears — from "Very weak" to "Very strong". A strong password should have at least 12 characters, a mix of upper/lower case, digits, and special characters.'
                    }
                },
                {
                    title: { cs: 'Osobní nastavení jazyka a motivu', en: 'Personal Language and Theme' },
                    text: {
                        cs: 'V záložce Vzhled si můžete nastavit preferovaný jazyk (čeština / English) a motiv (světlý / tmavý / auto). Toto nastavení přepíše výchozí hodnoty aplikace jen pro váš účet.',
                        en: 'In the Appearance tab you can set your preferred language (Čeština / English) and theme (light / dark / auto). These override the app defaults for your account only.'
                    }
                }
            ]
        },
        {
            id: 'maintenance',
            icon: 'fa-wrench',
            hasTour: true,
            endpoints: ['maintenance_index', 'maintenance_add', 'maintenance_edit', 'maintenance_delete', 'maintenance_ics', 'maintenance_duplicate', 'maintenance_schedule_30', 'maintenance_resolve_fault'],
            title: { cs: 'Údržba', en: 'Maintenance' },
            tips: [
                {
                    title: { cs: 'Prediktivní termíny', en: 'Predictive Due Dates' },
                    text: {
                        cs: 'U záznamu lze zapnout predikci podle reálného provozu: tiskové hodiny, počet jobů a spotřeba filamentu. Systém průběžně odhaduje další servisní termín podle dat z Bambu/Prusa historie.',
                        en: 'You can enable prediction based on real operation: print-hours, number of jobs, and filament usage. The system continuously estimates the next service date from Bambu/Prusa history data.'
                    }
                },
                {
                    title: { cs: 'Rychlé akce na kartě', en: 'Quick Actions on Card' },
                    text: {
                        cs: 'Přímo u záznamu můžete jedním klikem: duplikovat záznam, posunout další servis o +30 dní, nebo u poruchy přepnout stav na „Resolved".',
                        en: 'Directly on each record, you can one-click: duplicate the record, move next service by +30 days, or switch a fault to "Resolved".'
                    }
                },
                {
                    title: { cs: 'SOP šablony a Markdown poznámky', en: 'SOP Templates and Markdown Notes' },
                    text: {
                        cs: 'Při přidání záznamu můžete použít SOP šablonu a automaticky předvyplnit strukturovaný postup. Delší poznámky lze zapisovat v Markdownu a v seznamu je rozbalit/sbalit.',
                        en: 'When adding a record, you can use an SOP template to prefill a structured procedure. Longer notes can be written in Markdown and expanded/collapsed in the list.'
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
            id: 'models',
            icon: 'fa-cube',
            hasTour: false,
            endpoints: ['models_index', 'api_models_list', 'model_detail', 'model_edit', 'model_upload_version', 'model_download_latest', 'model_download_version', 'model_view_version', 'model_upload_thumbnail', 'serve_thumbnail', 'model_delete', 'model_delete_version', 'model_upload', 'model_add_comment', 'model_delete_comment', 'model_generate_share', 'model_revoke_share', 'model_public_share', 'model_bulk_delete', 'model_bulk_move'],
            title: { cs: 'Modely', en: 'Models' },
            tips: [
                {
                    title: { cs: 'Prohlížeč 3D modelů', en: '3D Model Browser' },
                    text: {
                        cs: 'Stránka Modely slouží jako centralizovaný katalog všech 3D modelů (soubory formátů STL, 3MF, OBJ, atd.) nahraných napříč všemi vašimi projekty. Můžete je prohledávat, filtrovat podle projektu či přípony, a řadit podle názvu, velikosti či data nahrání.',
                        en: 'The Models page serves as a centralized catalog of all 3D models (STL, 3MF, OBJ, etc. file formats) uploaded across all your projects. You can search them, filter by project or file extension, and sort by name, size, or upload date.'
                    }
                },
                {
                    title: { cs: 'Verzování a historie', en: 'Versioning and History' },
                    text: {
                        cs: 'Každý model podporuje více verzí. Při nahrání nového souboru se automaticky navýší verze. V detailu modelu vidíte přehlednou osu historie, kde lze stáhnout libovolnou historickou verzi nebo si ji načíst přímo do interaktivního náhledu.',
                        en: 'Each model supports multiple versions. When you upload a new file, the version number automatically increments. In the model details page, you see a complete history timeline where you can download any older version or load it directly into the interactive preview.'
                    }
                },
                {
                    title: { cs: '3D interaktivní prohlížeč', en: '3D Interactive Viewer' },
                    text: {
                        cs: 'Detail modelu obsahuje plně interaktivní 3D prohlížeč. Můžete s modelem otáčet, přibližovat a měnit barvu materiálu (podle barev filamentů), abyste viděli, jak bude model vypadat po vytištění.',
                        en: 'Model details include a fully interactive 3D viewer. You can rotate, zoom, and adjust the material color (matching your filament inventory) to see how the model will look when printed.'
                    }
                },
                {
                    title: { cs: 'Uložení náhledu (Snapshot)', en: 'Save Thumbnail Snapshot' },
                    text: {
                        cs: 'Tlačítkem „Save Thumbnail" v prohlížeči můžete pořídit snímek aktuálního pohledu 3D kamery. Tento snímek se uloží na server jako hlavní ikona modelu a zobrazí se v přehledu modelů.',
                        en: 'Using the "Save Thumbnail" button in the viewer, you can take a screenshot of the current 3D camera viewpoint. This screenshot is saved to the server as the model\'s primary icon and displayed in the catalog.'
                    }
                },
                {
                    title: { cs: 'Mazání modelů a verzí', en: 'Deleting Models and Versions' },
                    text: {
                        cs: 'Modely lze smazat z přehledu modelů (ikona koše u každé karty/řádku) nebo z detailu modelu. V detailu modelu je možné smazat celý model (červené tlačítko nahoře) nebo jednotlivé verze v historii. Při smazání poslední verze je odstraněn celý model.',
                        en: 'Models can be deleted from the model catalog (trash icon on each card/row) or from the model detail page. In model details, you can delete the entire model (red button at the top) or individual versions from the history timeline. Deleting the last version removes the entire model.'
                    }
                },
                {
                    title: { cs: 'Nahrávání nových modelů', en: 'Uploading New Models' },
                    text: {
                        cs: 'Nové 3D modely lze nahrát přímo ze stránky Modelů tlačítkem „Nahrát model" vpravo nahoře. Vyberte soubor (3MF, STL, OBJ, atd.), projekt, ke kterému model patří, a volitelně přidejte poznámku k verzi. Po nahrání budete přesměrováni na detail modelu, kde můžete nahrávat další verze.',
                        en: 'New 3D models can be uploaded directly from the Models page using the "Upload model" button in the top right. Select a file (3MF, STL, OBJ, etc.), the project it belongs to, and optionally add a version note. After upload, you\'ll be redirected to the model detail page where you can upload additional versions.'
                    }
                },
                {
                    title: { cs: 'Hromadné akce', en: 'Bulk Actions' },
                    text: {
                        cs: 'Na kartách a v řádcích tabulky je checkbox pro hromadný výběr modelů. Po zaškrtnutí se dole zobrazí plovoucí panel s možností hromadně smazat vybrané modely nebo je přesunout do jiného projektu.',
                        en: 'Each card and table row has a checkbox for bulk selection. When items are selected, a floating bar appears at the bottom with options to bulk-delete selected models or move them to a different project.'
                    }
                },
                {
                    title: { cs: 'Komentáře u modelu', en: 'Model Comments' },
                    text: {
                        cs: 'V detailu modelu pod historií verzí najdete sekci komentářů. Můžete přidávat poznámky, diskutovat o změnách a mazat vlastní komentáře. Správci mohou mazat všechny komentáře.',
                        en: 'In the model detail page below the version history, you\'ll find a comments section. You can add notes, discuss changes, and delete your own comments. Administrators can delete any comment.'
                    }
                },
                {
                    title: { cs: 'Sdílení modelu', en: 'Model Sharing' },
                    text: {
                        cs: 'V detailu modelu lze vygenerovat veřejný odkaz pro sdílení. Kliknutím na „Sdílet odkaz" vytvoříte unikátní URL, kterou může kdokoli otevřít a zobrazit si 3D model včetně historie verzí bez přihlášení. Odkaz lze kdykoli zrušit.',
                        en: 'In the model detail page, you can generate a public share link. Click "Share link" to create a unique URL that anyone can open to view the 3D model and its version history without logging in. The link can be revoked at any time.'
                    }
                },
                {
                    title: { cs: 'Statistiky modelů', en: 'Model Statistics' },
                    text: {
                        cs: 'V horní části stránky Modelů vidíte statistický pruh zobrazující celkový počet modelů, celkovou velikost souborů a počet modelů bez náhledu. To vám pomůže identifikovat modely, u kterých je vhodné vygenerovat náhledový obrázek.',
                        en: 'At the top of the Models page, you\'ll see a statistics bar showing the total number of models, total file size, and the count of models without thumbnails. This helps you identify models that could benefit from generating a preview thumbnail.'
                    }
                },
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
