from django import template
import bleach
from bleach.css_sanitizer import CSSSanitizer
import re
from bs4 import BeautifulSoup
import bleach
from bleach.css_sanitizer import CSSSanitizer
from urllib.parse import urlparse

register = template.Library()

ALLOWED_TAGS = [
    # текст
    'p', 'br', 'span',
    'b', 'i', 'u', 'em', 'strong', 's',

    # заголовки
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',

    # списки
    'ul', 'ol', 'li',

    # цитаты
    'blockquote',

    # ссылки и медиа
    'a', 'img', 'figure', 'figcaption',

    # код
    'pre', 'code',

    # таблицы
    'table', 'thead', 'tbody', 'tr', 'th', 'td',

    # разделители
    'hr',

    # mediaEmbed
    'iframe',

    # чекбоксы (todo list)
    'input',
]
ALLOWED_ATTRS = {
    '*': ['class', 'style'],

    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'iframe': [
        'src',
        'width',
        'height',
        'title',
        'frameborder',
        'allow',
        'allowfullscreen',
        'referrerpolicy',
    ],
    'input': ['type', 'checked', 'disabled'],
}
ALLOWED_STYLES = [
    'color',
    'background-color',

    'width',
    'height',
    'max-width',

    'text-align',
    'float',

    'margin',
    'margin-left',
    'margin-right',

    'border',
    'border-radius',
]

ALLOWED_IFRAME_DOMAINS = (
    'youtube.com',
    'www.youtube.com',
    'youtu.be',
    'vk.com',
    'vkvideo.ru',
    'www.vk.com'
)

@register.filter(name='safe_html')
def safe_html(value):
    if not value:
        return ''
    cleaned = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
        css_sanitizer=CSSSanitizer(
            allowed_css_properties=ALLOWED_STYLES
        )
    )

    soup = BeautifulSoup(cleaned, 'html.parser')

    for iframe in soup.find_all('iframe'):
        src = iframe.get('src', '')
        parsed = urlparse(src)

        domain = parsed.netloc.lower()

        if not any(domain.endswith(d) for d in ALLOWED_IFRAME_DOMAINS):
            iframe.decompose()  # ❌ удаляем iframe целиком

    return str(soup)