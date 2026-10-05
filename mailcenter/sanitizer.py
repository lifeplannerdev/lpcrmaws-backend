"""HTML sanitising helpers. Everything that is stored, sent or displayed goes through here."""
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

ALLOWED_TAGS = [
    'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2', 'h3', 'h4', 'hr', 'i', 'img',
    'li', 'mark', 'ol', 'p', 'pre', 'span', 'strong', 's', 'strike', 'sub', 'sup', 'table', 'tbody', 'td',
    'tfoot', 'th', 'thead', 'tr', 'u', 'ul', 'colgroup', 'col', 'font', 'center',
]

ALLOWED_ATTRIBUTES = {
    '*': ['style', 'class', 'dir', 'align'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'td': ['colspan', 'rowspan', 'width', 'height', 'valign', 'bgcolor'],
    'th': ['colspan', 'rowspan', 'width', 'height', 'valign', 'bgcolor'],
    'table': ['border', 'cellpadding', 'cellspacing', 'width', 'bgcolor'],
    'col': ['width', 'span'],
    'font': ['color', 'face', 'size'],
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'tel', 'data']

CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    'color', 'background-color', 'background', 'text-align', 'font-weight', 'font-style', 'font-size',
    'font-family', 'text-decoration', 'line-height', 'margin', 'margin-top', 'margin-bottom', 'margin-left',
    'margin-right', 'padding', 'padding-top', 'padding-bottom', 'padding-left', 'padding-right', 'border',
    'border-top', 'border-bottom', 'border-left', 'border-right', 'border-collapse', 'border-color',
    'border-style', 'border-width', 'width', 'height', 'max-width', 'min-width', 'vertical-align',
    'white-space', 'list-style-type',
])


def clean_html(html):
    """Strip scripts/handlers/unsafe protocols but keep rich formatting."""
    if not html:
        return ''
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=CSS_SANITIZER,
        strip=True,
        strip_comments=True,
    )


_BLOCK_BREAKS = re.compile(r'</(p|div|h[1-6]|li|tr|blockquote)>|<br\s*/?>', re.IGNORECASE)


def html_to_text(html):
    """Plain-text alternative part for outgoing mail and for snippets."""
    if not html:
        return ''
    text = _BLOCK_BREAKS.sub('\n', html)
    text = bleach.clean(text, tags=[], attributes={}, strip=True)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def make_snippet(html_or_text, length=240):
    text = html_to_text(html_or_text) if '<' in (html_or_text or '') else (html_or_text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:length]
