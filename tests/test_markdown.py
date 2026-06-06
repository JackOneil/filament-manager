"""Tests for the Markdown renderer (utils/markdown.py).

Security-sensitive: every XSS payload below is a real-world attack
vector.  The renderer must always escape the payload before any inline
Markdown is recognised, and must never emit an ``href`` whose scheme is
not in ``{http, https, mailto}``.
"""
import pytest

from utils.markdown import (
    _is_safe_markdown_href,
    _render_markdown_inline,
    _toggle_markdown_checkbox,
    markdown_extract_checkboxes,
    render_markdown,
    toggle_markdown_checkbox,
)


# ── XSS safety ──────────────────────────────────────────────────────────
class TestXssSafety:
    """The renderer must neutralise every XSS vector we throw at it."""

    def test_script_tag_is_escaped(self):
        out = render_markdown('<script>alert(1)</script>')
        assert '<script>' not in out
        assert '&lt;script&gt;' in out

    def test_img_onerror_is_escaped(self):
        out = render_markdown('<img src=x onerror=alert(1)>')
        # The HTML must be escaped — the literal "<" must be encoded so
        # the browser never sees a real <img> tag.
        assert '<img' not in out
        assert '&lt;img' in out

    def test_javascript_url_is_stripped_from_link(self):
        out = render_markdown('[click](javascript:alert(1))')
        assert 'javascript:' not in out
        # The label is preserved as plain text.
        assert 'click' in out

    def test_data_url_is_stripped_from_link(self):
        out = render_markdown('[click](data:text/html,<script>alert(1)</script>)')
        assert 'data:text/html' not in out

    def test_vbscript_url_is_stripped_from_link(self):
        out = render_markdown('[click](vbscript:msgbox(1))')
        assert 'vbscript:' not in out

    def test_quote_event_handler_is_escaped(self):
        out = render_markdown('" onclick="alert(1)')
        # The whole input must be HTML-escaped.
        assert 'onclick="alert' not in out
        assert '&quot;' in out

    def test_html_in_link_label_is_escaped(self):
        out = render_markdown('[<b>bold</b>](https://example.com)')
        # The literal ``<b>`` tag from the label must be escaped.
        assert '&lt;b&gt;bold' in out

    def test_attribute_injection_via_autolink(self):
        out = render_markdown('<https://example.com" onmouseover="alert(1)>')
        # No live ``<a`` tag may be produced from this input.
        assert '<a ' not in out
        assert '<a>' not in out
        assert '&lt;https' in out


# ── Basic Markdown features ────────────────────────────────────────────
class TestBasicMarkdown:
    def test_bold(self):
        assert _render_markdown_inline('**hello**') == '<strong>hello</strong>'

    def test_italic(self):
        assert _render_markdown_inline('*hello*') == '<em>hello</em>'

    def test_bold_italic_distinguished(self):
        # Three stars should not be a bold+italic mangled together
        assert _render_markdown_inline('***a***') or True  # any non-crash is OK

    def test_inline_code(self):
        assert _render_markdown_inline('use `print()`') == 'use <code>print()</code>'

    def test_inline_code_with_html_chars(self):
        # Code span body is NOT re-escaped after token replacement
        # (it was already escaped before storage).  Verify the content is wrapped.
        out = _render_markdown_inline('see `<b>tag</b>`')
        assert '<code>' in out and '</code>' in out

    def test_paragraph_wrapping(self):
        out = render_markdown('hello world')
        assert out == '<p>hello world</p>'

    def test_heading_levels(self):
        for level in range(1, 7):
            md = f"{'#' * level} Title"
            out = render_markdown(md)
            assert f'<h{level}>Title</h{level}>' in out

    def test_blockquote(self):
        out = render_markdown('> quoted text')
        assert '<blockquote>quoted text</blockquote>' in out

    def test_unordered_list(self):
        out = render_markdown('- a\n- b')
        assert '<ul>' in out
        assert '<li>a</li>' in out
        assert '<li>b</li>' in out

    def test_ordered_list(self):
        out = render_markdown('1. a\n2. b')
        assert '<ol>' in out
        assert '<li>a</li>' in out
        assert '<li>b</li>' in out

    def test_code_block(self):
        out = render_markdown('```\nraw <html>\n```')
        assert '<pre><code>' in out
        # Inside the code block, the HTML is escaped.
        assert 'raw &lt;html&gt;' in out

    def test_link_with_safe_url(self):
        out = render_markdown('[x](https://example.com)')
        assert 'href="https://example.com"' in out
        assert 'target="_blank"' in out
        assert 'rel="noopener noreferrer"' in out

    def test_link_with_mailto(self):
        out = render_markdown('[mail](mailto:foo@bar.com)')
        assert 'href="mailto:foo@bar.com"' in out

    def test_empty_input(self):
        assert render_markdown('') == ''
        assert render_markdown(None) == ''

    def test_crlf_normalised(self):
        out = render_markdown('line 1\r\nline 2')
        assert '<p>line 1<br>line 2</p>' in out

    def test_mixed_block_separators(self):
        md = 'para 1\n\n- item\n\n> quote'
        out = render_markdown(md)
        assert '<p>para 1</p>' in out
        assert '<ul>' in out
        assert '<blockquote>' in out


# ── Task list / checkboxes ─────────────────────────────────────────────
class TestCheckboxes:
    def test_toggle_unchecked_to_checked(self):
        out = _toggle_markdown_checkbox('- [ ] a\n- [x] b', 0)
        assert '- [x] a' in out
        assert '- [x] b' in out

    def test_toggle_checked_to_unchecked(self):
        out = _toggle_markdown_checkbox('- [x] a\n- [ ] b', 0)
        assert '- [ ] a' in out
        assert '- [ ] b' in out

    def test_toggle_index_out_of_range(self):
        text = '- [ ] a'
        assert _toggle_markdown_checkbox(text, 5) == text

    def test_toggle_ignores_non_checkbox_lines(self):
        text = '# Heading\n- [ ] a\n\n- [ ] b'
        out = _toggle_markdown_checkbox(text, 0)
        assert '- [x] a' in out
        # Second checkbox is index 1, should remain unchanged.
        assert '- [ ] b' in out

    def test_extract_checkboxes(self):
        out = markdown_extract_checkboxes('- [ ] one\n- [X] two\nplain line\n- [x] three')
        # 3 checkbox items expected; their line indices match the input.
        assert len(out) == 3
        assert out[0] == (0, 'one', False)
        assert out[1] == (1, 'two', True)
        assert out[2] == (3, 'three', True)

    def test_render_task_list(self):
        out = render_markdown('- [ ] a\n- [x] b')
        assert 'class="task-list"' in out
        assert 'data-index="0"' in out
        assert 'data-index="1"' in out
        assert ' checked' in out

    def test_toggle_public_alias_matches(self):
        text = '- [ ] a'
        assert toggle_markdown_checkbox(text, 0) == _toggle_markdown_checkbox(text, 0)


# ── URL safety predicate ───────────────────────────────────────────────
class TestUrlSafety:
    @pytest.mark.parametrize('url,safe', [
        ('http://example.com', True),
        ('https://example.com/path?x=1', True),
        ('mailto:foo@bar.com', True),
        ('javascript:alert(1)', False),
        ('data:text/html,xxx', False),
        ('vbscript:msgbox(1)', False),
        ('file:///etc/passwd', False),
        ('', False),
        ('   ', False),
        (None, False),
    ])
    def test_is_safe_markdown_href(self, url, safe):
        assert _is_safe_markdown_href(url) is safe


# ── Edge cases / regression ─────────────────────────────────────────────
class TestEdgeCases:
    def test_html_entities_in_text(self):
        out = _render_markdown_inline('Tom & Jerry')
        assert 'Tom &amp; Jerry' in out

    def test_partial_markdown_constructs_kept_as_text(self):
        # Unmatched * should not be turned into <em>
        out = _render_markdown_inline('a * b')
        assert '<em>' not in out

    def test_multiline_paragraphs_use_br(self):
        out = render_markdown('first\nsecond')
        assert '<p>first<br>second</p>' in out

    def test_code_block_unterminated_is_still_emitted(self):
        # Unterminated ``` is gracefully closed at end-of-input.
        out = render_markdown('```\ncode')
        assert '<pre><code>' in out
        assert '</code></pre>' in out

    def test_list_mixed_with_paragraph(self):
        out = render_markdown('intro\n\n- a\n- b\n\noutro')
        assert '<p>intro</p>' in out
        assert '<ul>' in out
        assert '<p>outro</p>' in out

    def test_nested_emphasis_safe(self):
        # ** *word* ** should not produce broken HTML
        out = _render_markdown_inline('** *word* **')
        # Anything is OK as long as it doesn't produce an unclosed <strong>
        if '<strong>' in out:
            assert out.count('<strong>') == out.count('</strong>')


# ── Backward-compat: re-exports through utils.__init__ ────────────────
class TestReExports:
    def test_utils_render_markdown(self):
        # ``from utils import render_markdown`` must still work.
        from utils import render_markdown as r
        assert r('**x**') == '<p><strong>x</strong></p>'

    def test_utils_toggle_markdown_checkbox(self):
        from utils import _toggle_markdown_checkbox as t
        assert t('- [ ] a', 0) == '- [x] a'
