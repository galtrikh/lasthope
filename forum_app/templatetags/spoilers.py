import re
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def spoilerize(content):
    """
    Преобразует [spst]Текст[sped] в <details><summary>Спойлер</summary>Текст</details>
    """
    if not content:
        return content
    
    pattern = r'\[spst\](.*?)\[sped\]'
    replacement = r'''
    <div class="collapse collapse-arrow bg-base-100 border border-base-300">
    <input type="checkbox" name="post-{{ post.id }}" />
    <div class="collapse-title font-semibold">Показать спойлер</div>
    <div class="collapse-content text-sm">
    \1
    </div>
    </div>'''
    
    result = re.sub(pattern, replacement, content, flags=re.DOTALL)
    return mark_safe(result)