"""Safe Markdown → HTML renderer for user-supplied text.

Extracted from ``utils.py`` (Refactor B) for:

* **Testability** — security-sensitive (XSS-prone) code in its own module.
* **Performance** — regex patterns are pre-compiled at import time rather
  than recompiled on every call.
* **Single responsibility** — the renderer has no dependency on the
  database, Flask, or any application state.

The renderer is **escape-first**: every input character is HTML-escaped
via :func:`html.escape` before any inline Markdown constructs are
recognised.  Only safe URL schemes (``http``, ``https``, ``mailto``) are
allowed in ``[label](href)`` links; everything else is rendered as plain
text.  Code spans are extracted into placeholders and emitted as
``<code>`` *after* escaping the rest of the line.
"""
from __future__ import annotations

import html
import re
from typing import List, Tuple

# ── Pre-compiled regexes (Rule 4.6) ──────────────────────────────────────
# All patterns used inside hot loops are compiled once at import time.
# Python's `re` already caches, but explicit pre-compilation:
#   * makes the cost visible at import time (not first request),
#   * avoids relying on internal cache sizing,
#   * and surfaces syntax errors at import time.

_INLINE_CODE_RE = re.compile(r'`([^`\n]+)`')
_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_INLINE_BOLD_RE = re.compile(r'\*\*([^*\n]+)\*\*')
_INLINE_EM_RE = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
_QUOTE_RE = re.compile(r'^>\s?(.*)$')
_TASK_RE = re.compile(r'^\s*[-*+]\s+\[([ xX])\]\s+(.*)$')
_UL_RE = re.compile(r'^\s*[-*+]\s+(.*)$')
_OL_RE = re.compile(r'^\s*\d+\.\s+(.*)$')
_CHECKBOX_LINE_RE = re.compile(r'^\s*[-*+]\s+\[[ xX]\]\s+')
_CHECKBOX_UNCHECKED_RE = re.compile(r'^(\s*[-*+]\s+)\[ \]')
_CHECKBOX_CHECKED_RE = re.compile(r'^(\s*[-*+]\s+)\[[xX]\]')

_SAFE_URL_SCHEMES = frozenset({'http', 'https', 'mailto'})


def _is_safe_markdown_href(href: str) -> bool:
    """Return True iff *href* uses a safe URL scheme (http/https/mailto)."""
    href = (href or '').strip()
    if not href:
        return False
    from urllib.parse import urlparse
    parsed = urlparse(href)
    return parsed.scheme in _SAFE_URL_SCHEMES


def _render_markdown_inline(text: str) -> str:
    """Render inline Markdown (``code``, **bold**, *em*, [link](url)) on a
    single escaped line.  Always escapes input first."""
    escaped = html.escape(text or '')
    code_tokens: dict[str, str] = {}

    def _store_code(match: re.Match) -> str:
        token = f'@@CODE{len(code_tokens)}@@'
        code_tokens[token] = f'<code>{match.group(1)}</code>'
        return token

    escaped = _INLINE_CODE_RE.sub(_store_code, escaped)

    def _replace_link(match: re.Match) -> str:
        label = match.group(1)
        href = html.unescape(match.group(2)).strip()
        if not _is_safe_markdown_href(href):
            return label
        safe_href = html.escape(href, quote=True)
        return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{label}</a>'

    escaped = _INLINE_LINK_RE.sub(_replace_link, escaped)
    escaped = _INLINE_BOLD_RE.sub(r'<strong>\1</strong>', escaped)
    escaped = _INLINE_EM_RE.sub(r'<em>\1</em>', escaped)

    for token, value in code_tokens.items():
        escaped = escaped.replace(token, value)
    return escaped


def _toggle_markdown_checkbox(text: str, index: int) -> str:
    """Toggle the checkbox at the given 0-based index in *text*.

    Returns the original text unchanged when the index is out of range.
    Used by the project description / comment checkbox widgets.
    """
    lines = (text or '').split('\n')
    count = 0
    for i, line in enumerate(lines):
        if not _CHECKBOX_LINE_RE.match(line):
            continue
        if count == index:
            if _CHECKBOX_UNCHECKED_RE.match(line):
                lines[i] = _CHECKBOX_UNCHECKED_RE.sub(r'\1[x]', line)
            else:
                lines[i] = _CHECKBOX_CHECKED_RE.sub(r'\1[ ]', line)
            return '\n'.join(lines)
        count += 1
    return text


def render_markdown(text: str) -> str:
    """Render a Markdown *text* fragment to safe HTML.

    The input is HTML-escaped first, then block-level (headings, lists,
    code blocks, blockquotes, task lists) and inline (``code``, **bold**,
    *em*, [link](url)) Markdown constructs are recognised.  Untrusted URL
    schemes (e.g. ``javascript:``, ``data:``) are stripped from links and
    rendered as plain text.
    """
    lines: List[str] = (text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocks: List[str] = []
    paragraph_lines: List[str] = []
    quote_lines: List[str] = []
    list_type: str | None = None
    list_items: List[str] = []
    in_code_block = False
    code_lines: List[str] = []
    checkbox_index = [0]

    def _flush_paragraph() -> None:
        if not paragraph_lines:
            return
        content = '<br>'.join(_render_markdown_inline(line) for line in paragraph_lines)
        blocks.append(f'<p>{content}</p>')
        paragraph_lines.clear()

    def _flush_quote() -> None:
        if not quote_lines:
            return
        content = '<br>'.join(_render_markdown_inline(line) for line in quote_lines)
        blocks.append(f'<blockquote>{content}</blockquote>')
        quote_lines.clear()

    def _flush_list() -> None:
        if not list_items:
            return
        if list_type == 'task':
            blocks.append(f'<ul class="task-list">{"".join(list_items)}</ul>')
        else:
            items = ''.join(f'<li>{item}</li>' for item in list_items)
            blocks.append(f'<{list_type}>{items}</{list_type}>')
        list_type_local = None  # noqa: F841 — variable name preserved for clarity
        list_items.clear()
        # Reset via enclosing scope name
        # (closure rebinding needs `nonlocal` in CPython; we work around it
        # by writing back through the outer name on next iteration)
        # Simpler: do an explicit reset here using nonlocal below.
        _reset_list_state()

    def _reset_list_state() -> None:
        nonlocal list_type, list_items
        list_type = None
        list_items = []

    def _flush_code() -> None:
        nonlocal in_code_block, code_lines
        code_html = html.escape('\n'.join(code_lines))
        blocks.append(f'<pre><code>{code_html}</code></pre>')
        in_code_block = False
        code_lines = []

    for raw_line in lines:
        stripped = raw_line.strip()

        if in_code_block:
            if stripped.startswith('```'):
                _flush_code()
            else:
                code_lines.append(raw_line)
            continue

        if stripped.startswith('```'):
            _flush_paragraph()
            _flush_quote()
            _flush_list()
            in_code_block = True
            code_lines = []
            continue

        if not stripped:
            _flush_paragraph()
            _flush_quote()
            _flush_list()
            continue

        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            _flush_paragraph()
            _flush_quote()
            _flush_list()
            level = len(heading_match.group(1))
            blocks.append(
                f'<h{level}>{_render_markdown_inline(heading_match.group(2).strip())}</h{level}>'
            )
            continue

        quote_match = _QUOTE_RE.match(raw_line)
        if quote_match:
            _flush_paragraph()
            _flush_list()
            quote_lines.append(quote_match.group(1))
            continue

        task_match = _TASK_RE.match(raw_line)
        if task_match:
            _flush_paragraph()
            _flush_quote()
            if list_type and list_type != 'task':
                _flush_list()
            list_type = 'task'
            checked = task_match.group(1).lower() == 'x'
            idx = checkbox_index[0]
            checkbox_index[0] += 1
            checked_attr = ' checked' if checked else ''
            item_text = _render_markdown_inline(task_match.group(2))
            list_items.append(
                f'<li class="task-list-item">'
                f'<input type="checkbox" class="task-checkbox" data-index="{idx}"{checked_attr}> '
                f'{item_text}</li>'
            )
            continue

        unordered_match = _UL_RE.match(raw_line)
        ordered_match = _OL_RE.match(raw_line)
        if unordered_match or ordered_match:
            _flush_paragraph()
            _flush_quote()
            next_list_type = 'ul' if unordered_match else 'ol'
            if list_type and list_type != next_list_type:
                _flush_list()
            list_type = next_list_type
            list_items.append(_render_markdown_inline((unordered_match or ordered_match).group(1)))
            continue

        _flush_quote()
        _flush_list()
        paragraph_lines.append(raw_line)

    _flush_paragraph()
    _flush_quote()
    _flush_list()
    if in_code_block:
        _flush_code()

    return ''.join(blocks)


def markdown_extract_checkboxes(text: str) -> List[Tuple[int, str, bool]]:
    """Return a list of ``(index, body, checked)`` for every Markdown task
    list item in *text*.  Useful for re-rendering or syncing checkboxes
    without running the full HTML pipeline.
    """
    out: List[Tuple[int, str, bool]] = []
    for i, line in enumerate((text or '').split('\n')):
        match = _TASK_RE.match(line)
        if not match:
            continue
        out.append((i, match.group(2), match.group(1).lower() == 'x'))
    return out


__all__ = [
    'render_markdown',
    'toggle_markdown_checkbox',
    'markdown_extract_checkboxes',
    '_render_markdown_inline',
    '_is_safe_markdown_href',
]


# Public alias (used by callers that want the leading-underscore name gone).
def toggle_markdown_checkbox(text: str, index: int) -> str:
    """Public alias for :func:`_toggle_markdown_checkbox`."""
    return _toggle_markdown_checkbox(text, index)
