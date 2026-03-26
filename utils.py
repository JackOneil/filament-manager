import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from database import db
from models import AppSetting, MovementHistory


def get_settings():
    return AppSetting.query.first()


def get_current_lang():
    setting = get_settings()
    return setting.lang if setting else 'cs'


def get_current_currency():
    setting = get_settings()
    return setting.currency if setting and setting.currency else 'CZK'


def get_current_theme():
    setting = get_settings()
    return setting.theme if setting and setting.theme else 'light'


def log_movement(filament, action_type, weight):
    """Record a filament weight movement with cost calculation."""
    if weight <= 0:
        return
    cost_per_gram = filament.price / filament.weight_total if filament.weight_total > 0 else 0
    total_cost = cost_per_gram * weight
    currency = get_current_currency()

    brand_name = filament.brand.name if filament.brand else ""
    mat_name = filament.material.name if filament.material else ""
    filament_name = f"{filament.name} | {brand_name} {mat_name}".strip(" | ")

    movement = MovementHistory(
        filament_name=filament_name,
        action_type=action_type,
        weight=weight,
        cost=total_cost,
        currency=currency,
    )
    db.session.add(movement)


def _is_public_ip(address):
    ip_obj = ipaddress.ip_address(address)
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def is_safe_external_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    lowered = hostname.lower()
    if lowered in {'localhost', 'localhost.localdomain'} or lowered.endswith('.localhost'):
        return False

    try:
        ip_obj = ipaddress.ip_address(hostname)
        return _is_public_ip(ip_obj)
    except ValueError:
        pass

    try:
        addrinfos = socket.getaddrinfo(hostname, parsed.port or None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    resolved = {item[4][0] for item in addrinfos}
    if not resolved:
        return False

    try:
        return all(_is_public_ip(address) for address in resolved)
    except ValueError:
        return False


def _strip_fragment(url):
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ''))


def _follow_safe_redirects(url, headers, timeout, max_redirects=5):
    current_url = url

    for _ in range(max_redirects + 1):
        if not is_safe_external_url(current_url):
            raise ValueError('Unsafe redirect target')

        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=False,
        )

        if 300 <= response.status_code < 400:
            location = response.headers.get('Location')
            if not location:
                return response, current_url
            current_url = urljoin(current_url, location)
            continue

        return response, current_url

    raise ValueError('Too many redirects')


def _extract_meta_content(soup, key, attr='property'):
    tag = soup.find('meta', attrs={attr: key})
    if tag:
        return tag.get('content')
    return None


def _pick_preview_image(soup, base_url):
    candidates = [
        _extract_meta_content(soup, 'og:image'),
        _extract_meta_content(soup, 'og:image', attr='name'),   # Printables & sites using name= instead of property=
        _extract_meta_content(soup, 'og:image:url'),
        _extract_meta_content(soup, 'og:image:url', attr='name'),
        _extract_meta_content(soup, 'twitter:image', attr='name'),
        _extract_meta_content(soup, 'twitter:image:src', attr='name'),
    ]

    link_tag = soup.find('link', rel=lambda value: value and 'image_src' in value)
    if link_tag:
        candidates.append(link_tag.get('href'))

    itemprop_image = soup.find(attrs={'itemprop': 'image'})
    if itemprop_image:
        candidates.append(itemprop_image.get('content') or itemprop_image.get('src'))

    for image in soup.find_all('img'):
        src = image.get('src')
        if not src:
            continue
        width = image.get('width')
        height = image.get('height')
        if width and height:
            try:
                if int(width) < 120 or int(height) < 120:
                    continue
            except ValueError:
                pass
        candidates.append(src)

    for candidate in candidates:
        if not candidate:
            continue
        absolute = urljoin(base_url, candidate.strip())
        if is_safe_external_url(absolute):
            return absolute
    return None


def _iter_nested_values(payload, keys):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys:
                yield value
            yield from _iter_nested_values(value, keys)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_nested_values(item, keys)


def _normalize_image_candidate(candidate, base_url):
    if isinstance(candidate, str) and candidate.strip():
        absolute = urljoin(base_url, candidate.strip())
        if is_safe_external_url(absolute):
            return absolute
        return None

    if isinstance(candidate, list):
        for item in candidate:
            normalized = _normalize_image_candidate(item, base_url)
            if normalized:
                return normalized
        return None

    if isinstance(candidate, dict):
        for key in ('url', 'contentUrl', 'thumbnailUrl', 'src'):
            if key in candidate:
                normalized = _normalize_image_candidate(candidate[key], base_url)
                if normalized:
                    return normalized
    return None


def _normalize_text_candidate(candidate):
    if isinstance(candidate, str):
        cleaned = ' '.join(candidate.split())
        return cleaned or None
    if isinstance(candidate, list):
        for item in candidate:
            normalized = _normalize_text_candidate(item)
            if normalized:
                return normalized
    if isinstance(candidate, dict):
        for key in ('name', 'headline', 'title', 'description', 'text'):
            if key in candidate:
                normalized = _normalize_text_candidate(candidate[key])
                if normalized:
                    return normalized
    return None


def _extract_script_json_candidates(soup):
    json_payloads = []

    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        content = script.string or script.get_text(strip=True)
        if not content:
            continue
        try:
            json_payloads.append(json.loads(content))
        except json.JSONDecodeError:
            continue

    pattern = re.compile(r'({.*})', re.DOTALL)
    for script in soup.find_all('script'):
        content = script.string or script.get_text()
        if not content or ('image' not in content and 'title' not in content and 'description' not in content):
            continue
        if len(content) > 1_000_000:
            continue

        direct_candidate = content.strip()
        if direct_candidate.startswith('{') and direct_candidate.endswith('}'):
            candidates = [direct_candidate]
        else:
            candidates = [match.group(1) for match in pattern.finditer(content)]

        for candidate in candidates[:5]:
            try:
                json_payloads.append(json.loads(candidate))
            except json.JSONDecodeError:
                continue

    return json_payloads


def _extract_preview_from_json_payloads(payloads, base_url):
    preview = {
        'title': None,
        'description': None,
        'image': None,
    }

    title_keys = {'headline', 'name', 'title'}
    description_keys = {'description', 'summary', 'abstract', 'text'}
    image_keys = {'image', 'images', 'thumbnail', 'thumbnailUrl', 'cover', 'coverImage', 'banner'}

    for payload in payloads:
        if not preview['title']:
            preview['title'] = _normalize_text_candidate(next(_iter_nested_values(payload, title_keys), None))
        if not preview['description']:
            preview['description'] = _normalize_text_candidate(next(_iter_nested_values(payload, description_keys), None))
        if not preview['image']:
            preview['image'] = _normalize_image_candidate(next(_iter_nested_values(payload, image_keys), None), base_url)
        if all(preview.values()):
            break

    return preview


def _extract_markdown_preview(markdown, base_url):
    preview = {
        'title': None,
        'description': None,
        'image': None,
    }

    title_match = re.search(r'^Title:\s*(.+)$', markdown, flags=re.MULTILINE)
    if title_match:
        preview['title'] = _normalize_text_candidate(title_match.group(1))

    image_candidates = re.findall(r'!\[[^\]]*\]\((https?://[^)\s]+)\)', markdown)
    preferred_images = []
    fallback_images = []
    for candidate in image_candidates:
        normalized = _normalize_image_candidate(candidate, base_url)
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(marker in lowered for marker in ('avatar/', 'favicon', 'icon for ')):
            continue
        if any(marker in lowered for marker in ('/design/', '/model/', 'makerworld.bblmw.com')):
            preferred_images.append(normalized)
        else:
            fallback_images.append(normalized)
    preview['image'] = (preferred_images or fallback_images or [None])[0]

    description_match = re.search(
        r'#+\s*Description\s*(.+?)(?:\n#+\s|\Z)',
        markdown,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if description_match:
        description_lines = []
        for line in description_match.group(1).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('![') or stripped.startswith('['):
                continue
            description_lines.append(stripped)
        if description_lines:
            preview['description'] = _normalize_text_candidate(' '.join(description_lines))

    lines = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith('Title:')
            or stripped.startswith('URL Source:')
            or stripped.startswith('Markdown Content:')
            or stripped.startswith('#')
            or stripped.startswith('*')
            or stripped.startswith('![')
            or stripped.startswith('[')
        ):
            continue
        lines.append(stripped)

    if not preview['description'] and lines:
        preview['description'] = _normalize_text_candidate(lines[0])

    return preview


def _fetch_reader_fallback(url, headers, timeout):
    reader_url = f"https://r.jina.ai/http://{_strip_fragment(url).replace('https://', '').replace('http://', '')}"
    response = requests.get(reader_url, headers=headers, timeout=timeout)
    if response.status_code != 200 or 'text/plain' not in response.headers.get('Content-Type', ''):
        return None
    return _extract_markdown_preview(response.text, _strip_fragment(url))


def _is_weak_preview_value(value, kind):
    if not value:
        return True

    lowered = value.lower()
    if kind == 'title':
        return lowered in {'just a moment...', 'makerworld'}
    if kind == 'description':
        return lowered in {'explore', 'home', 'community'} or len(value.strip()) < 12
    if kind == 'image':
        return any(marker in lowered for marker in ('avatar/', 'favicon', '/user/'))
    return False


def fetch_link_metadata(url):
    meta = {
        'og_title': None,
        'og_image': None,
        'og_description': None,
        'domain': None,
    }

    clean_url = _strip_fragment(url)
    if not is_safe_external_url(clean_url):
        return meta

    try:
        parsed_uri = urlparse(clean_url)
        meta['domain'] = parsed_uri.netloc

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml',
        }
        response, final_url = _follow_safe_redirects(clean_url, headers=headers, timeout=5)
        if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
            soup = BeautifulSoup(response.text, 'html.parser')

            meta['domain'] = urlparse(final_url).netloc
            meta['og_title'] = (
                _extract_meta_content(soup, 'og:title')
                or _extract_meta_content(soup, 'twitter:title', attr='name')
            )
            if not meta['og_title']:
                title_tag = soup.find('title')
                meta['og_title'] = title_tag.get_text(strip=True) if title_tag else None

            meta['og_description'] = (
                _extract_meta_content(soup, 'og:description')
                or _extract_meta_content(soup, 'twitter:description', attr='name')
                or _extract_meta_content(soup, 'description', attr='name')
            )
            meta['og_image'] = _pick_preview_image(soup, final_url)

            if not (meta['og_title'] and meta['og_description'] and meta['og_image']):
                json_preview = _extract_preview_from_json_payloads(
                    _extract_script_json_candidates(soup),
                    final_url,
                )
                meta['og_title'] = meta['og_title'] or json_preview['title']
                meta['og_description'] = meta['og_description'] or json_preview['description']
                meta['og_image'] = meta['og_image'] or json_preview['image']

        if not (meta['og_title'] and meta['og_image']):
            markdown_preview = _fetch_reader_fallback(clean_url, headers=headers, timeout=10)
            if markdown_preview:
                if markdown_preview['title'] and _is_weak_preview_value(meta['og_title'], 'title'):
                    meta['og_title'] = markdown_preview['title']
                if markdown_preview['description'] and _is_weak_preview_value(meta['og_description'], 'description'):
                    meta['og_description'] = markdown_preview['description']
                if markdown_preview['image'] and _is_weak_preview_value(meta['og_image'], 'image'):
                    meta['og_image'] = markdown_preview['image']

    except Exception:
        return meta

    if meta['og_title'] and len(meta['og_title']) > 250:
        meta['og_title'] = meta['og_title'][:250] + '...'
    if meta['og_description'] and len(meta['og_description']) > 400:
        meta['og_description'] = meta['og_description'][:400] + '...'
    if meta['og_image'] and len(meta['og_image']) > 490:
        meta['og_image'] = meta['og_image'][:490] + '...'

    return meta
