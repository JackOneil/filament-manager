# Implementační plán — vylepšení stránky Modelů

Stav kódu ke dni 2026-06-06, verze `1.104.6`.  
Pořadí featur je doporučené implementační pořadí (méně invazivní → více invazivní).

---

## Feature 7 — Hover-overlay na thumbnailovém obrázku

**Popis:** Akční tlačítka (Preview / Download / Delete) se zobrazí jako overlay přes thumbnail při najetí myší. Spodní footer na kartě pak zobrazuje jen metadata (velikost, datum).

### Změny

**`templates/_models_cards.html`**

1. Na `<a>` wrappper thumbnailuji je již tříd `group` — stačí přidat overlay `div` uvnitř:

```html
<!-- Přidej UVNITŘ <a href="…" class="… group …"> těsně před zavírací </a> -->
<div class="absolute inset-0 bg-black/0 group-hover:bg-black/50 transition-all duration-200
            flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 z-10">
    <!-- Preview (pro podporované formáty) -->
    <a href="{{ url_for('models.model_detail', root_id=root_file.id) }}"
       class="bg-white/90 hover:bg-white text-slate-900 h-9 w-9 rounded-xl flex items-center
              justify-center shadow transition" title="{{ t('preview') }}">
        <i class="fa-solid fa-expand text-sm"></i>
    </a>
    <a href="{{ url_for('models.model_download_latest', root_id=root_file.id) }}"
       class="bg-white/90 hover:bg-white text-slate-900 h-9 w-9 rounded-xl flex items-center
              justify-center shadow transition" title="{{ t('download') }}">
        <i class="fa-solid fa-download text-sm"></i>
    </a>
    <form method="POST" action="{{ url_for('models.model_delete', root_id=root_file.id) }}"
          onsubmit="return confirm('{{ t('models_delete_confirm') }}');" class="inline-flex">
        <button type="submit"
                class="bg-red-500/90 hover:bg-red-600 text-white h-9 w-9 rounded-xl flex items-center
                       justify-center shadow transition" title="{{ t('models_delete_model') }}">
            <i class="fa-solid fa-trash text-sm"></i>
        </button>
    </form>
</div>
```

2. Smazat původní blok `<!-- Action buttons -->` v card footer (tři `<a>` / `<form>` s `.ui-badge`).

**Poznámka:** `group-hover:opacity-100` funguje protože wrapper `<a>` má třídu `group`.

---

## Feature 8 — Počet verzí jako badge na kartě

**Popis:** Pokud má model více než 1 verzi, zobrazit počet verzí jako badge (fialový) na thumbnailovém obrázku vedle stávajícího `version X` / `latest` badge.

### Změny

**`routes/models.py` — `api_models_list()`**

V obohacovací smyčce přidat `version_count`:

```python
# Stávající kód:
enriched.append({
    'root': root,
    'latest': latest,
    'display_name': root.display_name or root.filename.rsplit('.', 1)[0],
    'project_name': root.project.name if root.project else '',
    'size': latest.file_size_bytes or 0,
    'uploaded_at': latest.uploaded_at or datetime.min
})
# Přidat:
    'version_count': len([root] + root.versions),
```

**`templates/_models_cards.html`** — do badge oblasti na thumbnailovém obrázku:

```html
<!-- Přidat za stávající dva badge (version X, latest): -->
{% if item.version_count > 1 %}
<span class="ui-badge bg-violet-600 text-white text-xs font-extrabold px-2.5 py-0.5 leading-5">
    {{ item.version_count }} {{ t('models_versions_count_badge') }}
</span>
{% endif %}
```

**`messages.py`** — přidat do `cs` i `en`:
```python
# cs:
'models_versions_count_badge': 'verze',
# en:
'models_versions_count_badge': 'versions',
```

---

## Feature 2 — Filtr „Bez projektu"

**Popis:** Quick-filter pill nad kartami modelů — jedno kliknutí izoluje modely bez přiřazeného projektu.

### Změny

**`routes/models.py` — `api_models_list()`**

Za filtr `project_id` přidat:

```python
no_project = request.args.get('no_project') == '1'
if no_project:
    query = query.filter(ProjectFile.project_id.is_(None))
elif project_id:
    query = query.filter(ProjectFile.project_id == project_id)
```
(Nahradit stávající blok `if project_id:` výše uvedeným.)

**`templates/models_index.html`** — stav Alpine:

```js
// Přidat do stavu modelsApp():
noProject: false,
```

Do `$watch` sekce:
```js
this.$watch('noProject', () => { this.page = 1; this.fetchContent(); });
```

Při sestavování URL params:
```js
if (this.noProject) params.append('no_project', '1');
```

V `resetFilters()`:
```js
this.noProject = false;
```

V `selectProject()`:
```js
selectProject(id, name) {
    this.projectId = id;
    this.projectQ = name;
    this.noProject = false;  // ← přidat
    this.page = 1;
},
```

**HTML — quick-filter pills** (přidat nad filter panel, vzor z `index.html`):

```html
<!-- Nad div.ui-panel s filtry: -->
<div class="flex flex-wrap gap-2">
    <button type="button" @click="noProject = false; projectId = ''; projectQ = ''"
        :class="!noProject && !projectId ? 'bg-blue-600 text-white shadow-sm' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
        class="px-3 py-1.5 rounded-full text-xs font-semibold transition-all border-0 cursor-pointer">
        <i class="fa-solid fa-cubes"></i> {{ t('filter_all') }}
    </button>
    <button type="button" @click="noProject = true; projectId = ''; projectQ = ''"
        :class="noProject ? 'bg-violet-600 text-white shadow-sm' : 'bg-violet-50 text-violet-700 hover:bg-violet-100'"
        class="px-3 py-1.5 rounded-full text-xs font-semibold transition-all border-0 cursor-pointer">
        <i class="fa-solid fa-unlink"></i> {{ t('models_filter_no_project') }}
    </button>
</div>
```

**`messages.py`**:
```python
# cs:
'models_filter_no_project': 'Bez projektu',
# en:
'models_filter_no_project': 'No project',
```

---

## Feature 3 — Statistický pruh

**Popis:** Řádek s třemi rychlými KPI údaji (celkem modelů, celková velikost, bez thumbnailů) zobrazený nad filtry na stránce `/models`.

### Změny

**`routes/models.py` — `models_index()`**

```python
@bp.route('/models')
def models_index():
    projects = _get_projects()
    setting = AppSetting.query.first()

    # Stats bar
    user = get_current_user()
    base_q = ProjectFile.query.filter(ProjectFile.parent_file_id.is_(None))
    if not is_admin(user):
        base_q = base_q.outerjoin(Project).filter(Project.owner_user_id == user.id if user else False)

    ext_conditions = [ProjectFile.filename.like(f'%.{ext}') for ext in MODEL_EXTENSIONS]
    base_q = base_q.filter(db.or_(*ext_conditions))

    models_stats = {
        'total': base_q.count(),
        'total_size': db.session.query(
            db.func.sum(ProjectFile.file_size_bytes)
        ).filter(
            ProjectFile.id.in_([f.id for f in base_q.with_entities(ProjectFile.id).all()])
        ).scalar() or 0,
        'no_thumb': base_q.filter(ProjectFile.thumbnail_path.is_(None)).count(),
    }

    return render_template(
        'models_index.html',
        projects=projects,
        setting=setting,
        model_extensions=sorted(list(MODEL_EXTENSIONS)),
        models_stats=models_stats,
    )
```

> **Optimalizace:** Pro velké databáze nahradit `id.in_([...])` jedním SQL dotazem s `GROUP BY` / subquery.

**`templates/models_index.html`** — přidat PŘED filter panel:

```html
<!-- Stats bar -->
<div class="grid grid-cols-3 gap-4">
    <div class="ui-panel py-3 flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-950/40 flex items-center justify-center flex-shrink-0">
            <i class="fa-solid fa-cubes text-blue-600 dark:text-blue-400"></i>
        </div>
        <div>
            <div class="text-2xl font-extrabold text-[var(--ui-text)]">{{ models_stats.total }}</div>
            <div class="text-xs text-gray-400 dark:text-slate-500 font-semibold uppercase tracking-wide">{{ t('models_stats_total') }}</div>
        </div>
    </div>
    <div class="ui-panel py-3 flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-950/40 flex items-center justify-center flex-shrink-0">
            <i class="fa-solid fa-hard-drive text-emerald-600 dark:text-emerald-400"></i>
        </div>
        <div>
            {% set sz = models_stats.total_size %}
            <div class="text-2xl font-extrabold text-[var(--ui-text)]">
                {% if sz >= 1073741824 %}{{ (sz / 1073741824) | round(1) }} GB
                {% elif sz >= 1048576 %}{{ (sz / 1048576) | round(1) }} MB
                {% elif sz >= 1024 %}{{ (sz / 1024) | round(1) }} KB
                {% else %}{{ sz }} B{% endif %}
            </div>
            <div class="text-xs text-gray-400 dark:text-slate-500 font-semibold uppercase tracking-wide">{{ t('models_stats_total_size') }}</div>
        </div>
    </div>
    <div class="ui-panel py-3 flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl {% if models_stats.no_thumb > 0 %}bg-amber-100 dark:bg-amber-950/40{% else %}bg-gray-100 dark:bg-slate-800{% endif %} flex items-center justify-center flex-shrink-0">
            <i class="fa-solid fa-image-slash {% if models_stats.no_thumb > 0 %}text-amber-500{% else %}text-gray-400{% endif %}"></i>
        </div>
        <div>
            <div class="text-2xl font-extrabold {% if models_stats.no_thumb > 0 %}text-amber-600 dark:text-amber-400{% else %}text-[var(--ui-text)]{% endif %}">{{ models_stats.no_thumb }}</div>
            <div class="text-xs text-gray-400 dark:text-slate-500 font-semibold uppercase tracking-wide">{{ t('models_stats_no_thumb') }}</div>
        </div>
    </div>
</div>
```

**`messages.py`**:
```python
# cs:
'models_stats_total':      'Modelů celkem',
'models_stats_total_size': 'Celková velikost',
'models_stats_no_thumb':   'Bez náhledu',
# en:
'models_stats_total':      'Total models',
'models_stats_total_size': 'Total size',
'models_stats_no_thumb':   'No thumbnail',
```

---

## Feature 1 — Hromadné akce (Bulk actions)

**Popis:** Checkboxy na kartách i v řádcích tabulky. Plovoucí panel dole zobrazuje počet vybraných a nabízí „Smazat vybrané" a „Přesunout do projektu".

### Backend

**`routes/models.py`** — přidat dvě nové routes:

```python
@bp.route('/models/bulk-delete', methods=['POST'])
def model_bulk_delete():
    if not is_admin():
        abort(403)
    raw = request.form.get('ids', '')
    ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    deleted = 0
    for root_id in ids:
        root_file = ProjectFile.query.get(root_id)
        if root_file and root_file.parent_file_id is None:
            _delete_model_chain(root_file)
            deleted += 1
    db.session.commit()
    flash(translate('models_bulk_deleted').format(n=deleted), 'success')
    return redirect(url_for('models.models_index'))


@bp.route('/models/bulk-move', methods=['POST'])
def model_bulk_move():
    if not is_admin():
        abort(403)
    raw = request.form.get('ids', '')
    ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    project_id = request.form.get('project_id', type=int) or None
    if project_id:
        _check_project_access(project_id)
    moved = 0
    for root_id in ids:
        root_file = ProjectFile.query.get(root_id)
        if root_file and root_file.parent_file_id is None:
            root_file.project_id = project_id
            moved += 1
    db.session.commit()
    flash(translate('models_bulk_moved').format(n=moved), 'success')
    return redirect(url_for('models.models_index'))
```

Přidat pomocnou funkci `_delete_model_chain(root_file)` — přesuňte logiku z existujícího `model_delete()` do této funkce a zavolejte ji z obou míst:

```python
def _delete_model_chain(root_file):
    """Delete root file and all its versions from DB and disk."""
    all_files = [root_file] + root_file.versions
    upload_folder, thumb_dir = _get_stl_thumbnail_paths()
    for f in all_files:
        if f.filepath and os.path.isfile(f.filepath):
            try: os.remove(f.filepath)
            except OSError: pass
        if f.thumbnail_path:
            thumb_path = os.path.join(upload_folder, f.thumbnail_path)
            if os.path.isfile(thumb_path):
                try: os.remove(thumb_path)
                except OSError: pass
        db.session.delete(f)
```

**`auth.py`** — přidat do `SECTION_BY_ENDPOINT`:
```python
'model_bulk_delete': SECTION_PROJECTS,
'model_bulk_move':   SECTION_PROJECTS,
```

### Frontend

**`templates/models_index.html`** — do stavu `modelsApp()`:

```js
selectedIds: [],

isSelected(id) { return this.selectedIds.includes(id); },
toggleSelect(id) {
    const idx = this.selectedIds.indexOf(id);
    if (idx === -1) this.selectedIds.push(id);
    else this.selectedIds.splice(idx, 1);
},
selectAll() {
    // Collect all visible IDs from DOM checkboxes
    this.selectedIds = Array.from(
        document.querySelectorAll('.model-checkbox')
    ).map(el => parseInt(el.dataset.id));
},
clearSelection() { this.selectedIds = []; },
```

Plovoucí bulk panel (přidat před `</div>` uzavírací tag pro Alpine root):

```html
<!-- Bulk action bar — shown when items are selected -->
<div x-show="selectedIds.length > 0" x-cloak
     class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 
            bg-slate-900 text-white px-5 py-3 rounded-2xl shadow-2xl border border-white/10">
    <span class="text-sm font-bold" x-text="selectedIds.length + ' {{ t('models_bulk_selected') }}'"></span>
    <div class="h-5 w-px bg-white/20"></div>

    <!-- Move to project form -->
    <form method="POST" action="{{ url_for('models.model_bulk_move') }}" @submit.prevent="submitBulk($el)">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="ids" :value="selectedIds.join(',')">
        <select name="project_id" class="text-sm bg-slate-800 border border-white/20 rounded-lg px-2 py-1.5 text-white">
            <option value="">— {{ t('models_bulk_move_no_project') }} —</option>
            {% for p in projects %}
            <option value="{{ p.id }}">{{ p.name }}</option>
            {% endfor %}
        </select>
        <button type="submit" class="ml-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition">
            <i class="fa-solid fa-right-to-bracket mr-1"></i>{{ t('models_bulk_move') }}
        </button>
    </form>

    <!-- Bulk delete form -->
    <form method="POST" action="{{ url_for('models.model_bulk_delete') }}"
          @submit.prevent="if(confirm('{{ t('models_bulk_delete_confirm') }}')) submitBulk($el)">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="ids" :value="selectedIds.join(',')">
        <button type="submit" class="bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition">
            <i class="fa-solid fa-trash mr-1"></i>{{ t('models_bulk_delete') }}
        </button>
    </form>

    <button type="button" @click="clearSelection()" class="text-white/50 hover:text-white transition ml-1">
        <i class="fa-solid fa-xmark"></i>
    </button>
</div>
```

JS helper v `modelsApp()`:
```js
submitBulk(form) {
    form.querySelector('[name="ids"]').value = this.selectedIds.join(',');
    form.submit();
},
```

**`templates/_models_cards.html`** — na každé kartě přidat checkbox (vlevo nahoře nad thumbnail):

```html
<!-- Přidat uvnitř card před thumbnail <a>: -->
<div class="absolute top-2 left-2 z-20"
     x-data="{ id: {{ root_file.id }} }"
     @click.stop>
    <input type="checkbox" :checked="$root.isSelected(id)"
           @change="$root.toggleSelect(id)"
           data-id="{{ root_file.id }}"
           class="model-checkbox w-4 h-4 rounded accent-blue-600 cursor-pointer">
</div>
```

> **Poznámka:** `$root` odkazuje na nejbližší Alpine parent s `x-data` — protože karty jsou rendrovány v partial mimo `modelsApp()`, je nutné použít `window.__models.toggleSelect(id)`. Při načítání přidat `window.__models = this` v `init()` modelsApp.

**`templates/_models_rows.html`** — přidat sloupec checkboxu jako první `<th>` + `<td>`.

**`messages.py`**:
```python
# cs:
'models_bulk_selected':       'vybráno',
'models_bulk_delete':         'Smazat vybrané',
'models_bulk_delete_confirm': 'Smazat {n} vybraných modelů?',
'models_bulk_deleted':        'Smazáno {n} modelů.',
'models_bulk_move':           'Přesunout',
'models_bulk_move_no_project':'Bez projektu',
'models_bulk_moved':          'Přesunuto {n} modelů.',
# en:
'models_bulk_selected':       'selected',
'models_bulk_delete':         'Delete selected',
'models_bulk_delete_confirm': 'Delete {n} selected models?',
'models_bulk_deleted':        '{n} models deleted.',
'models_bulk_move':           'Move',
'models_bulk_move_no_project':'No project',
'models_bulk_moved':          '{n} models moved.',
```

---

## Feature 11 — Přiřazení projektu z detailu

**Popis:** Přidat projekt-selector do stávajícího modálního okna „Upravit metadata" na stránce detailu modelu.

### Backend

**`routes/models.py` — `model_detail()`** — přidat `projects` do `render_template`:

```python
return render_template(
    'models_detail.html',
    root=root_file,
    latest=latest,
    history=history,
    same_checksum=same_checksum,
    projects=_get_projects(),   # ← přidat
)
```

**`routes/models.py` — `model_edit()`** — přidat čtení a uložení `project_id`:

```python
@bp.route('/models/<int:root_id>/edit', methods=['POST'])
def model_edit(root_id):
    root_file = _check_file_access(root_id)
    display_name = request.form.get('display_name', '').strip()
    version_note = request.form.get('version_note', '').strip()
    project_id   = request.form.get('project_id', type=int) or None

    if not display_name:
        flash(translate('models_error_edit_name_required'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_file.id))

    if project_id:
        _check_project_access(project_id)   # ověří přístup

    latest = _get_latest_version(root_file)
    root_file.display_name = display_name
    root_file.project_id   = project_id    # ← přidat
    latest.version_note    = version_note

    db.session.commit()
    flash(translate('models_success_edit'), 'success')
    return redirect(url_for('models.model_detail', root_id=root_file.id))
```

### Frontend

**`templates/models_detail.html`** — do MODAL 1 (Edit Metadata), za pole `display_name`:

```html
<!-- Přidat mezi version_note a tlačítky: -->
<div>
    <label class="block text-xs font-bold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-2">
        {{ t('project') }}
    </label>
    <select name="project_id" class="ui-input">
        <option value="">— {{ t('models_upload_no_project_option') }} —</option>
        {% for p in projects %}
        <option value="{{ p.id }}" {% if root.project_id == p.id %}selected{% endif %}>{{ p.name }}</option>
        {% endfor %}
    </select>
</div>
```

---

## Feature 13 — Komentáře k modelu

**Popis:** Nová sekce pod historií verzí — chronologická timeline komentářů stejného vzoru jako `_project_activity.html`.

### Backend — nový model

**`models.py`** — přidat za `ProjectComment`:

```python
class ModelComment(db.Model):
    __tablename__ = 'model_comment'
    id          = db.Column(db.Integer, primary_key=True)
    root_file_id= db.Column(db.Integer, db.ForeignKey('project_file.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    body        = db.Column(db.Text, nullable=False)
    created_at  = db.Column(db.DateTime, default=_utc_now, index=True)

    root_file = db.relationship('ProjectFile',
                                backref=db.backref('model_comments', lazy=True,
                                                   cascade='all, delete-orphan'))
    author    = db.relationship('User', backref=db.backref('model_comments', lazy=True))
```

`db.create_all()` vytvoří tabulku automaticky — žádný `_safe_alter` není třeba.

**`routes/models.py`** — přidat dva routes:

```python
@bp.route('/models/<int:root_id>/comments', methods=['POST'])
def model_add_comment(root_id):
    root_file = _check_file_access(root_id)
    body = request.form.get('body', '').strip()
    if not body:
        flash(translate('models_comment_empty_error'), 'error')
        return redirect(url_for('models.model_detail', root_id=root_id))
    from models import ModelComment
    user = get_current_user()
    comment = ModelComment(root_file_id=root_id, user_id=user.id if user else None, body=body)
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id) + '#model-comments')


@bp.route('/models/<int:root_id>/comments/<int:comment_id>/delete', methods=['POST'])
def model_delete_comment(root_id, comment_id):
    from models import ModelComment
    comment = ModelComment.query.get_or_404(comment_id)
    user = get_current_user()
    if not is_admin(user) and (not user or comment.user_id != user.id):
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id) + '#model-comments')
```

**`routes/models.py` — `model_detail()`** — předat komentáře:

```python
from models import ModelComment
comments = ModelComment.query.filter_by(root_file_id=root_id)\
                             .order_by(ModelComment.created_at.asc()).all()
return render_template(
    'models_detail.html',
    root=root_file, latest=latest, history=history,
    same_checksum=same_checksum,
    projects=_get_projects(),
    comments=comments,          # ← přidat
)
```

**`auth.py`**:
```python
'model_add_comment':    SECTION_PROJECTS,
'model_delete_comment': SECTION_PROJECTS,
```

### Frontend

**`templates/models_detail.html`** — přidat sekci za `<!-- Bottom Container: Version History Timeline -->`:

```html
<!-- Model Comments -->
<div id="model-comments" class="ui-panel">
    <h3 class="text-lg font-bold text-[var(--ui-text)] border-b border-[var(--ui-border)] pb-3 mb-6">
        <i class="fa-solid fa-comments text-gray-400 mr-1.5"></i> {{ t('models_comments_title') }}
    </h3>

    {% if comments %}
    <div class="space-y-4 mb-6">
        {% for c in comments %}
        <div class="flex gap-3">
            <div class="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-950/40 flex items-center justify-center flex-shrink-0 text-xs font-bold text-blue-700 dark:text-blue-400">
                {{ (c.author.name or c.author.email or '?')[0].upper() if c.author else '?' }}
            </div>
            <div class="flex-1 bg-gray-50 dark:bg-slate-900/30 rounded-2xl px-4 py-3 border border-[var(--ui-border)]">
                <div class="flex items-center justify-between gap-2 mb-1">
                    <span class="text-xs font-bold text-gray-700 dark:text-slate-300">
                        {{ c.author.name or c.author.email if c.author else t('unknown') }}
                    </span>
                    <div class="flex items-center gap-2">
                        <span class="text-[10px] text-gray-400">{{ c.created_at | fmt_dt('%d.%m.%Y %H:%M') }}</span>
                        {% if current_user and (auth_is_admin(current_user) or c.user_id == current_user.id) %}
                        <form method="POST" action="{{ url_for('models.model_delete_comment', root_id=root.id, comment_id=c.id) }}"
                              onsubmit="return confirm('{{ t('models_comment_delete_confirm') }}');" class="inline-flex">
                            <button type="submit" class="text-gray-300 hover:text-red-500 transition text-xs">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                        </form>
                        {% endif %}
                    </div>
                </div>
                <p class="text-sm text-gray-700 dark:text-slate-300 whitespace-pre-line">{{ c.body }}</p>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <p class="text-sm text-gray-400 dark:text-slate-500 italic mb-6">{{ t('models_comment_empty') }}</p>
    {% endif %}

    <!-- Comment form -->
    <form method="POST" action="{{ url_for('models.model_add_comment', root_id=root.id) }}" class="flex gap-3">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <textarea name="body" rows="2" placeholder="{{ t('models_comment_placeholder') }}"
                  class="ui-input flex-1 resize-none" required></textarea>
        <button type="submit" class="ui-badge ui-badge-brand h-10 px-4 self-end font-bold">
            <i class="fa-solid fa-paper-plane mr-1.5"></i>{{ t('models_comment_add') }}
        </button>
    </form>
</div>
```

**`messages.py`**:
```python
# cs:
'models_comments_title':        'Komentáře',
'models_comment_placeholder':   'Přidat komentář…',
'models_comment_add':           'Odeslat',
'models_comment_delete_confirm':'Smazat komentář?',
'models_comment_empty':         'Zatím žádné komentáře.',
'models_comment_empty_error':   'Komentář nesmí být prázdný.',
# en:
'models_comments_title':        'Comments',
'models_comment_placeholder':   'Add a comment…',
'models_comment_add':           'Post',
'models_comment_delete_confirm':'Delete this comment?',
'models_comment_empty':         'No comments yet.',
'models_comment_empty_error':   'Comment cannot be empty.',
```

---

## Feature 14 — Sdílení modelu (veřejný odkaz)

**Popis:** Generovat token-based read-only odkaz na model — klient vidí 3D náhled a metadata bez přihlášení.

### Backend — nový sloupec

**`models.py` — `ProjectFile`**:
```python
share_token = db.Column(db.String(64), nullable=True, unique=True)
```

**`migrations.py` — `run_migrations()`**:
```python
_safe_alter(app, "ALTER TABLE project_file ADD COLUMN share_token VARCHAR(64)")
```

**`routes/models.py`** — přidat tři routes:

```python
import secrets

@bp.route('/models/<int:root_id>/share/generate', methods=['POST'])
def model_generate_share(root_id):
    root_file = _check_file_access(root_id)
    if not root_file.share_token:
        root_file.share_token = secrets.token_urlsafe(32)
        db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id))


@bp.route('/models/<int:root_id>/share/revoke', methods=['POST'])
def model_revoke_share(root_id):
    root_file = _check_file_access(root_id)
    root_file.share_token = None
    db.session.commit()
    return redirect(url_for('models.model_detail', root_id=root_id))


@bp.route('/models/share/<token>')
def model_public_share(token):
    """Public (no-auth) read-only model view."""
    root_file = ProjectFile.query.filter_by(share_token=token, parent_file_id=None).first_or_404()
    latest    = _get_latest_version(root_file)
    history   = sorted([root_file] + root_file.versions, key=lambda f: f.version, reverse=True)
    return render_template(
        'models_share.html',          # nová šablona — kopie models_detail.html bez edit/delete akcí
        root=root_file,
        latest=latest,
        history=history,
    )
```

**`auth.py`** — public route musí být ve whitelistu, ostatní do `SECTION_PROJECTS`:
```python
# V PUBLIC_ENDPOINTS setu (stejně jako 'project_public_share'):
'model_public_share',

# V SECTION_BY_ENDPOINT:
'model_generate_share': SECTION_PROJECTS,
'model_revoke_share':   SECTION_PROJECTS,
```

### Frontend

**`templates/models_detail.html`** — do hlavičkového řádku akcí (za tlačítko „Download latest"):

```html
<!-- Share link block -->
{% if root.share_token %}
<div class="flex items-center gap-2 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 rounded-xl px-3 py-2">
    <i class="fa-solid fa-link text-emerald-600 text-sm"></i>
    <input type="text" readonly
           value="{{ request.host_url.rstrip('/') }}{{ url_for('models.model_public_share', token=root.share_token) }}"
           class="bg-transparent text-xs font-mono text-emerald-700 dark:text-emerald-300 outline-none w-64 truncate"
           onclick="this.select(); document.execCommand('copy');"
           title="{{ t('models_share_copy_hint') }}">
    <form method="POST" action="{{ url_for('models.model_revoke_share', root_id=root.id) }}" class="inline-flex">
        <button type="submit" class="text-red-400 hover:text-red-600 transition text-xs font-semibold whitespace-nowrap">
            {{ t('models_share_revoke') }}
        </button>
    </form>
</div>
{% else %}
<form method="POST" action="{{ url_for('models.model_generate_share', root_id=root.id) }}" class="inline-flex">
    <button type="submit" class="ui-badge h-10 px-4 gap-1.5 font-bold">
        <i class="fa-solid fa-share-nodes"></i> {{ t('models_share_generate') }}
    </button>
</form>
{% endif %}
```

**`templates/models_share.html`** — nová šablona:
- Kopie `models_detail.html` s `{% extends 'base.html' %}` nebo samostatná stránka bez přihlášení
- Odebrat: tlačítka Edit, Upload version, Delete, Share-generate
- Přidat: banner „Read-only public view — shared by …"
- Viewer zůstává plně funkční

**`messages.py`**:
```python
# cs:
'models_share_generate':   'Sdílet odkaz',
'models_share_revoke':     'Zrušit odkaz',
'models_share_copy_hint':  'Kliknutím zkopírovat odkaz',
'models_share_public_view':'Veřejné zobrazení',
# en:
'models_share_generate':   'Share link',
'models_share_revoke':     'Revoke link',
'models_share_copy_hint':  'Click to copy link',
'models_share_public_view':'Public view',
```

---

## Feature 16 — Fullscreen viewer

**Popis:** Tlačítko v overlay controlsech vieweru — fullscreen přes Fullscreen API, žádná nová záložka.

### Frontend (pouze JS + HTML)

**`templates/models_detail.html`** — do Alpine stavu `modelDetailApp()`:

```js
isFullscreen: false,

toggleFullscreen() {
    const el = document.getElementById('3d-viewer-container');
    if (!document.fullscreenElement) {
        el.requestFullscreen().catch(err => {
            console.warn('Fullscreen request failed:', err);
        });
    } else {
        document.exitFullscreen();
    }
},

initFullscreenListener() {
    document.addEventListener('fullscreenchange', () => {
        this.isFullscreen = !!document.fullscreenElement;
    });
},
```

V `init()` přidat volání:
```js
this.initFullscreenListener();
```

Do floating viewer overlay (vedle stávajícího `<button>` Save Thumbnail):

```html
<button type="button" @click="toggleFullscreen()"
        class="bg-white/90 hover:bg-white text-slate-900 h-9 px-3 rounded-xl transition
               font-bold text-xs flex items-center gap-1.5 shadow"
        :title="isFullscreen ? '{{ t('models_viewer_exit_fullscreen') }}' : '{{ t('models_viewer_fullscreen') }}'">
    <i class="fa-solid" :class="isFullscreen ? 'fa-compress' : 'fa-expand'"></i>
    <span x-text="isFullscreen ? '{{ t('models_viewer_exit_fullscreen') }}' : '{{ t('models_viewer_fullscreen') }}'"></span>
</button>
```

Přidat CSS pro fullscreen stav `<iframe>` — nutné aby viewer vyplnil celou obrazovku:

```html
<!-- Přidat do <style> tagu v models_detail.html -->
<style>
#3d-viewer-container:fullscreen {
    background: #0f172a;
}
#3d-viewer-container:fullscreen iframe {
    width: 100%;
    height: 100%;
}
</style>
```

**`messages.py`**:
```python
# cs:
'models_viewer_fullscreen':      'Celá obrazovka',
'models_viewer_exit_fullscreen': 'Ukončit celou obrazovku',
# en:
'models_viewer_fullscreen':      'Fullscreen',
'models_viewer_exit_fullscreen': 'Exit fullscreen',
```

---

## Pořadí implementace (doporučené)

| # | Feature | Složitost | Riziko regrese |
|---|---------|-----------|----------------|
| 1 | Hover-overlay (F7) | Nízká | Nízké — pouze HTML/CSS |
| 2 | Počet verzí badge (F8) | Nízká | Nízké — přidání pole do enriched dict |
| 3 | Filtr bez projektu (F2) | Nízká | Nízké — jednoduchý query filtr |
| 4 | Statistický pruh (F3) | Střední | Nízké — jen nová data v route |
| 5 | Fullscreen viewer (F16) | Nízká | Nízké — jen JS/HTML |
| 6 | Přiřazení projektu z detailu (F11) | Střední | Střední — změna model_edit() |
| 7 | Komentáře (F13) | Střední | Střední — nový model, nové routes |
| 8 | Sdílení (F14) | Vysoká | Vysoké — nový public endpoint + migrace |
| 9 | Hromadné akce (F1) | Vysoká | Střední — nové routes, nový JS stav |

## Checklist po implementaci každé featury

- [ ] `messages.py` — obě jazyková mutace (Rule 1)
- [ ] `auth.py SECTION_BY_ENDPOINT` — nové routes (Rule 4)
- [ ] `migrations.py _safe_alter()` — nové sloupce (Rule 2)
- [ ] `routes/backup.py` — nové modely/sloupce (Rule 15)
- [ ] `static/js/help.js` — nové endpointy + tipy (Rule 30)
- [ ] `python -m pytest tests/ -v` — všechny testy zelené (Rule 19)
- [ ] `docker compose up -d --build` (Rule 17)
