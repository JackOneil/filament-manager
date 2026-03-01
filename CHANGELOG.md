# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.12.0] - 2026-03-02
### Added
- Added header row to list view in the overview page with column labels (Name, Brand, Quantity, Remaining, Capacity, Percentage, Actions).
- Added persistence for view mode preference (card/list): user's chosen view is now automatically saved and restored when returning to the overview page.
### Changed
- Improved list view layout with more compact grid system and reorganized columns for better readability.
- First column in list view (Name) now has expanded width to accommodate longer filament names without truncation.
- Action buttons are now positioned at the far right of each row for consistent and easy access.
- Header row is sticky on desktop views for easier navigation through large lists.

## [1.11.1] - 2026-03-01
### Changed
- Improved list view layout on the overview page: Information is now organized into distinct columns (Name, Material, Quantity, Remaining, Capacity, Percentage) instead of being grouped together, providing better readability and data organization.
- List view is now more compact and uses a responsive grid layout with hidden columns on mobile devices (Material and Capacity columns are hidden on small screens for better mobile experience).
- Action buttons remain fixed on the right side of each row for consistent access.

## [1.11.0] - 2026-03-01
### Added
- Added view toggle on the overview page to switch between card view (grid layout with detailed cards) and list view (minimalist row-based layout).
- Added pagination to the overview page, allowing users to browse large filament inventories in manageable chunks (default: 12 items per page).
- View toggle preference and pagination controls preserve applied filters when switching between views or pages.
- New card view displays filament details with progress bars, capacity information, and action buttons in a visual grid layout (3 columns on desktop).
- New list view displays each filament in a compact row format with the color indicator, name, material, quantity, remaining weight, capacity, and action buttons.

## [1.10.0] - 2026-03-01
### Added
- Added light/dark theme toggle available on all pages (in the navigation bar).
- Users can now switch between light mode and dark mode at any time while browsing the application.
- Theme preference is persisted in the database, automatically loading the user's chosen theme on every visit.
- Comprehensive dark mode styling with improved contrast and readability for reduced eye strain.
### Fixed
- Fixed theme toggle button behavior: users now remain on the same page after changing theme instead of being redirected to settings.
- Fixed dark mode input visibility: all input fields now have proper dark backgrounds and light text in dark mode for full readability.

## [1.9.0] - 2026-03-01
### Added
- Added comprehensive debug logging to all major application actions, including filament CRUD operations, settings modifications, calculator functions, and import/export operations.
- Debug messages are now displayed in the Docker container logs when DEBUG logging mode is enabled in Application Settings (Gunicorn output).
- Each loggable action now includes detailed context: operation type, entity names, before/after values, and operation results.

## [1.8.4] - 2026-03-01
### Changed
- Switched from Flask's built-in development server to Gunicorn (production WSGI server) in the Docker container to ensure true production readiness and fix security/performance warnings.

## [1.8.3] - 2026-03-01
### Fixed
- Fixed bug in filament addition where `db.session.commit()` and redirection were missing, causing the new filament not to appear in the overview.

### Added
- Added an option in Application Settings to toggle DEBUG logging mode dynamically.

## [1.8.2] - 2026-03-01
### Added
- Added total inventory monetary value calculation to the main dashboard overview, displaying active capital tied in filaments.

## [1.8.1] - 2026-03-01
### Fixed
- Fixed the visual sign logic representing the operational cost of filament movements in History (Added filament now renders as a visually positive value, deleted filament renders as negative value).

## [1.8.0] - 2026-03-01
### Added
- Created a new Filament Movement History page that tracks precisely when and how much material was added or removed.
- Implemented automatic logging for stock operations (e.g. subtracting material, adding spools, making adjustments).
- Fully paginated logging system using 10/20/50/100 records selection.

## [1.7.0] - 2026-03-01
### Added
- Added combinatorial filters to the main dashboard. Users can now filter their filament spools by Brand, Material, and Color simultaneously.

## [1.6.0] - 2026-03-01
### Added
- Upgraded the Print Calculator's simple filament dropdown into an interactive, live full-text search input component. Uses fast JS DOM manipulation to filter filaments by name, brand, or material instantly.

## [1.5.0] - 2026-03-01
### Added
- Added global Currency Selection setting (CZK, USD, EUR) to the Settings page. This directly modifies how strings and costs are displayed natively everywhere in the main index list and in the precise printing calculator view.
### Fixed
- Fixed currency formatting order on the dashboard index page (e.g., from `Cena 230.00 za 1000 g CZK` to `Cena 230.00 CZK za 1000 g`).

## [1.4.0] - 2026-03-01
### Added
- Added Database Import & Export functionalities (via JSON structure). Users can now natively download and upload back their complete settings/filaments/dictionaries list.

## [1.3.1] - 2026-03-01
### Added
- Added `.github/copilot-instructions.md` to persist project context, development rules, and standard prompts for GitHub Copilot.

## [1.3.0] - 2026-02-28
### Added
- Added calculation history feature to the Print Calculator (tracking past print jobs, used filament, weight, and total cost).
- Added an option to delete individual calculation history logs.

## [1.2.2] - 2026-02-28
### Fixed
- Reverted text shortenings for print weight and fixed layout using CSS grid `items-end` to perfectly align inputs on the Calculator page.

## [1.2.1] - 2026-02-28
### Fixed
- Fixed layout wrapping issue on the Calculator page in Czech language by shortening the text.

## [1.2.0] - 2026-02-28
### Added
- Possibility to delete individual dictionaries items (Brand, Material, Color) in Settings (only if they are not used).
- Display semantic App Version in the footer instead of the static text.

## [1.1.0] - 2026-02-28
### Added
- Electricity cost inclusion in the Print Calculator (Print time, kWh price, printer power).
- Added `-` (minus) button to easily decrease the spool quantity of a filament on the Overview page.
- Allowed editing existing records in Settings (Brands, Materials, Colors).
- Quantity of spools now decrements automatically when enough filament is used (e.g. crossing below previous spool capacity threshold).
- Basic semantic versioning and Changelog initialization.

## [1.0.1] - 2026-02-28
### Added
- Internationalization (i18n) for CZ/EN.
- Added spool quantity tracking.

## [1.0.0] - 2026-02-28
### Added
- Initial release of FilamentApp.
- Filament management, Print calculator, basic settings.
