import ipaddress
import socket
from urllib.parse import urljoin, urlparse

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
        _extract_meta_content(soup, 'og:image:url'),
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


def fetch_link_metadata(url):
    meta = {
        'og_title': None,
        'og_image': None,
        'og_description': None,
        'domain': None,
    }

    if not is_safe_external_url(url):
        return meta

    try:
        parsed_uri = urlparse(url)
        meta['domain'] = parsed_uri.netloc

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml',
        }
        response, final_url = _follow_safe_redirects(url, headers=headers, timeout=5)
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

    except Exception:
        return meta

    if meta['og_title'] and len(meta['og_title']) > 250:
        meta['og_title'] = meta['og_title'][:250] + '...'
    if meta['og_description'] and len(meta['og_description']) > 400:
        meta['og_description'] = meta['og_description'][:400] + '...'
    if meta['og_image'] and len(meta['og_image']) > 490:
        meta['og_image'] = meta['og_image'][:490] + '...'

    return meta
