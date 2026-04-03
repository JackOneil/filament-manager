import ipaddress
import json
import math
import os
import re
import socket
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from database import db
from models import (
    AppSetting, BambuJobMaterial, BambuPrintJob, MovementHistory,
    Project, PrusaPrintJob, PrusaPrinter,
)


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


def build_filament_history_name(filament):
    brand_name = filament.brand.name if filament.brand else ""
    mat_name = filament.material.name if filament.material else ""
    return f"{filament.name} | {brand_name} {mat_name}".strip(" | ")


def parse_tags(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        values = raw_value
    else:
        values = re.split(r'[,;\n]+', str(raw_value))
    tags = []
    seen = set()
    for value in values:
        tag = ' '.join(str(value).strip().split())
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(tag)
    return tags


def format_tags(raw_value):
    return ', '.join(parse_tags(raw_value))


def remove_tag(raw_value, tag_to_remove):
    tag_to_remove = ' '.join(str(tag_to_remove or '').strip().split()).lower()
    if not tag_to_remove:
        return format_tags(raw_value)
    return ', '.join(
        tag for tag in parse_tags(raw_value)
        if tag.lower() != tag_to_remove
    )


def get_filament_tags(filament):
    return parse_tags(getattr(filament, 'tag_text', ''))


def movement_action_label(action_type):
    return {
        'add': 'Add',
        'remove': 'Use',
        'bambu_print': 'Bambu print',
        'bulk_add_weight': 'Bulk add weight',
        'bulk_delete': 'Bulk delete',
        'bulk_add_spool': 'Bulk add spool',
        'bulk_remove_spool': 'Bulk remove spool',
    }.get(action_type, action_type.replace('_', ' ').title())


def compute_stock_status(filament, usage_30=0.0, usage_90=0.0):
    min_stock = max(float(getattr(filament, 'min_stock_grams', 0.0) or 0.0), 0.0)
    max_stock = max(float(getattr(filament, 'max_stock_grams', 0.0) or 0.0), 0.0)
    remaining = max(float(getattr(filament, 'weight_remaining', 0.0) or 0.0), 0.0)
    usage_30 = max(float(usage_30 or 0.0), 0.0)
    usage_90 = max(float(usage_90 or 0.0), 0.0)

    target_stock = max(min_stock, usage_30 * 1.15, (usage_90 / 3.0) * 1.10 if usage_90 > 0 else 0.0)
    if max_stock > 0:
        target_stock = min(target_stock, max_stock)
    recommended_grams = max(0.0, target_stock - remaining)
    spool_weight = float(getattr(filament, 'weight_total', 0.0) or 0.0)
    recommended_spools = math.ceil(recommended_grams / spool_weight) if spool_weight > 0 and recommended_grams > 0 else 0
    recommended_order_grams = recommended_spools * spool_weight if recommended_spools > 0 and spool_weight > 0 else 0.0
    spool_price = float(getattr(filament, 'price', 0.0) or 0.0)
    recommended_order_price = recommended_spools * spool_price if recommended_spools > 0 and spool_price > 0 else 0.0

    critical_usage_threshold = usage_30 / 4.0 if usage_30 > 0 else 0.0

    if remaining <= 0 or (min_stock > 0 and remaining < min_stock * 0.5) or (critical_usage_threshold > 0 and remaining <= critical_usage_threshold):
        status = 'critical'
    elif min_stock > 0 and remaining < min_stock:
        status = 'warning'
    elif usage_30 > 0 and remaining < usage_30:
        status = 'warning'
    else:
        status = 'stable'

    return {
        'remaining': round(remaining, 1),
        'min_stock': round(min_stock, 1),
        'max_stock': round(max_stock, 1),
        'usage_30': round(usage_30, 1),
        'usage_90': round(usage_90, 1),
        'target_stock': round(target_stock, 1),
        'recommended_grams': round(recommended_grams, 1),
        'recommended_spools': recommended_spools,
        'recommended_order_grams': round(recommended_order_grams, 1),
        'recommended_order_price': round(recommended_order_price, 2),
        'spool_price': round(spool_price, 2),
        'status': status,
    }


def encrypt_token(plaintext: str) -> str:
    """Encrypt a sensitive token using FERNET_KEY env var.

    Returns the plaintext unchanged when FERNET_KEY is not configured
    (preserves backward compatibility for existing installations).
    """
    if not plaintext:
        return plaintext
    raw_key = os.environ.get('FERNET_KEY', '').strip().encode()
    if not raw_key:
        return plaintext
    try:
        from cryptography.fernet import Fernet
        return Fernet(raw_key).encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token encrypted with encrypt_token().

    When FERNET_KEY is not set, or when decryption fails (e.g. legacy
    plaintext token), the value is returned as-is so existing deployments
    are not broken.
    """
    if not ciphertext:
        return ciphertext
    raw_key = os.environ.get('FERNET_KEY', '').strip().encode()
    if not raw_key:
        return ciphertext
    try:
        from cryptography.fernet import Fernet
        return Fernet(raw_key).decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext  # legacy plaintext or wrong key — return as-is


def collect_usage_windows(filaments, now=None):
    if now is None:
        from datetime import datetime as _dt
        now = _dt.utcnow()
    by_id = {fil.id: {'usage_30': 0.0, 'usage_90': 0.0} for fil in filaments}
    by_name = {build_filament_history_name(fil): fil.id for fil in filaments}
    since_90 = now - timedelta(days=90)
    rows = MovementHistory.query.filter(
        MovementHistory.created_at >= since_90,
        MovementHistory.action_type.in_(('remove', 'bambu_print')),
    ).all()
    for row in rows:
        filament_id = row.filament_id
        if filament_id not in by_id:
            filament_id = by_name.get(row.filament_name)
        if filament_id not in by_id:
            continue
        by_id[filament_id]['usage_90'] += row.weight or 0.0
        if row.created_at and row.created_at >= now - timedelta(days=30):
            by_id[filament_id]['usage_30'] += row.weight or 0.0
    return by_id


def parse_sync_status(raw_value):
    if not raw_value:
        return {
            'ok': None,
            'error': None,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'label': None,
        }

    raw_text = str(raw_value).strip()
    if raw_text.lower().startswith('error:'):
        return {
            'ok': False,
            'error': raw_text[6:].strip(),
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'label': raw_text,
        }

    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            'ok': None,
            'error': None,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'label': raw_text,
        }

    return {
        'ok': True,
        'error': None,
        'added': int(payload.get('added', 0) or 0),
        'updated': int(payload.get('updated', 0) or 0),
        'skipped': int(payload.get('skipped', 0) or 0),
        'label': raw_text,
    }


def build_project_metrics(project, setting=None):
    setting = setting or get_settings()
    kwh_price = setting.kwh_price if setting else 5.0
    printer_power = setting.printer_power if setting else 150

    estimated_material_cost = 0.0
    estimated_weight = 0.0
    planned_items = 0
    completed_plans = 0
    for item in getattr(project, 'filaments', []) or []:
        planned_items += 1
        estimated_weight += float(item.estimated_weight or 0.0)
        if item.is_used:
            completed_plans += 1
        if item.filament and item.filament.weight_total > 0:
            estimated_material_cost += (item.filament.price / item.filament.weight_total) * (item.estimated_weight or 0.0)

    actual_material_cost = 0.0
    actual_weight = 0.0
    actual_seconds = 0

    for job in getattr(project, 'bambu_jobs', []) or []:
        actual_seconds += int(job.cost_time or 0)
        if job.materials:
            slot_total = 0.0
            for slot in job.materials:
                if slot.weight_grams:
                    actual_weight += float(slot.weight_grams or 0.0)
                if slot.filament and slot.filament.weight_total > 0 and slot.weight_grams:
                    slot_total += (slot.filament.price / slot.filament.weight_total) * slot.weight_grams
            if slot_total > 0:
                actual_material_cost += slot_total
            elif job.filament and job.filament.weight_total > 0 and job.weight_grams:
                actual_material_cost += (job.filament.price / job.filament.weight_total) * job.weight_grams
        elif job.filament and job.filament.weight_total > 0 and job.weight_grams:
            actual_weight += float(job.weight_grams or 0.0)
            actual_material_cost += (job.filament.price / job.filament.weight_total) * job.weight_grams
        elif job.weight_grams:
            actual_weight += float(job.weight_grams or 0.0)

    for job in getattr(project, 'prusa_jobs', []) or []:
        actual_seconds += int(job.cost_time or 0)
        if job.weight_grams:
            actual_weight += float(job.weight_grams or 0.0)
        if job.filament and job.filament.weight_total > 0 and job.weight_grams:
            actual_material_cost += (job.filament.price / job.filament.weight_total) * job.weight_grams

    energy_cost = (actual_seconds / 3600.0) * (printer_power / 1000.0) * kwh_price
    actual_total_cost = actual_material_cost + energy_cost
    latest_quote = None
    if getattr(project, 'quotes', None):
        latest_quote = max(project.quotes, key=lambda item: item.created_at or datetime.min)

    quote_price = float(latest_quote.final_price or 0.0) if latest_quote else 0.0
    profit = quote_price - actual_total_cost if latest_quote else None
    estimated_seconds = int((project.estimated_print_time or 0) * 60)

    return {
        'estimated_material_cost': round(estimated_material_cost, 2),
        'estimated_weight': round(estimated_weight, 1),
        'estimated_seconds': estimated_seconds,
        'actual_material_cost': round(actual_material_cost, 2),
        'actual_weight': round(actual_weight, 1),
        'actual_seconds': actual_seconds,
        'energy_cost': round(energy_cost, 2),
        'actual_total_cost': round(actual_total_cost, 2),
        'quote_price': round(quote_price, 2) if latest_quote else None,
        'profit': round(profit, 2) if profit is not None else None,
        'planned_items': planned_items,
        'completed_plans': completed_plans,
        'completion_ratio': round((completed_plans / planned_items) * 100) if planned_items else 0,
        'has_quote': latest_quote is not None,
    }


def build_action_center(now=None):
    now = now or datetime.utcnow()
    setting = get_settings()

    low_stock_rows = []
    from models import Filament

    usage_windows = collect_usage_windows(Filament.query.all(), now=now)
    for filament in Filament.query.all():
        stock = compute_stock_status(
            filament,
            usage_windows.get(filament.id, {}).get('usage_30', 0.0),
            usage_windows.get(filament.id, {}).get('usage_90', 0.0),
        )
        if stock['status'] in ('critical', 'warning') and not filament.reorder_alert_snoozed:
            low_stock_rows.append({
                'filament': filament,
                'status': stock['status'],
                'recommended_spools': stock['recommended_spools'],
                'recommended_grams': stock['recommended_grams'],
            })
    low_stock_rows.sort(key=lambda item: (0 if item['status'] == 'critical' else 1, -item['recommended_grams']))

    overdue_projects = (
        Project.query
        .filter(Project.status != 'DONE', Project.due_date.is_not(None), Project.due_date < now)
        .order_by(Project.due_date.asc())
        .limit(6)
        .all()
    )

    unmapped_bambu = (
        BambuPrintJob.query
        .filter(
            db.or_(
                BambuPrintJob.filament_id.is_(None),
                BambuPrintJob.materials.any(BambuJobMaterial.filament_id.is_(None)),
            )
        )
        .order_by(BambuPrintJob.started_at.desc().nullslast(), BambuPrintJob.synced_at.desc())
        .limit(6)
        .all()
    )
    unmapped_prusa = (
        PrusaPrintJob.query
        .filter(
            db.or_(PrusaPrintJob.project_id.is_(None), PrusaPrintJob.filament_id.is_(None)),
            PrusaPrintJob.status.in_(('PRINTING', 'FINISHED')),
        )
        .order_by(PrusaPrintJob.synced_at.desc())
        .limit(6)
        .all()
    )

    printer_issues = []
    bambu_status = parse_sync_status(setting.bambu_last_sync_status if setting else None)
    if setting and setting.bambu_token:
        stale_minutes = max(int(setting.bambu_auto_sync_interval_minutes or 60) * 2, 15)
        is_stale = not setting.bambu_last_sync_at or setting.bambu_last_sync_at < now - timedelta(minutes=stale_minutes)
        if bambu_status['ok'] is False or is_stale:
            printer_issues.append({
                'type': 'bambu',
                'name': 'Bambu Cloud',
                'last_sync_at': setting.bambu_last_sync_at,
                'last_success_at': setting.bambu_last_sync_at if bambu_status['ok'] else None,
                'status': bambu_status,
                'is_stale': is_stale,
            })

    for printer in PrusaPrinter.query.filter_by(enabled=True).order_by(PrusaPrinter.name.asc()).all():
        status = parse_sync_status(printer.last_sync_status)
        is_stale = not printer.last_sync_at or printer.last_sync_at < now - timedelta(minutes=15)
        if status['ok'] is False or is_stale:
            printer_issues.append({
                'type': 'prusa',
                'name': printer.name,
                'printer': printer,
                'last_sync_at': printer.last_sync_at,
                'last_success_at': printer.last_success_at,
                'status': status,
                'is_stale': is_stale,
            })

    # Recent completed print jobs (Bambu + Prusa) for the overview activity feed
    recent_bambu = (
        BambuPrintJob.query
        .filter(BambuPrintJob.status == 'FINISH')
        .order_by(BambuPrintJob.finished_at.desc().nullslast(), BambuPrintJob.synced_at.desc())
        .limit(8)
        .all()
    )
    recent_prusa = (
        PrusaPrintJob.query
        .filter(PrusaPrintJob.status == 'FINISHED')
        .order_by(PrusaPrintJob.finished_at.desc().nullslast(), PrusaPrintJob.synced_at.desc())
        .limit(8)
        .all()
    )
    # Merge and sort by timestamp, keep latest 6
    recent_prints = []
    for job in recent_bambu:
        recent_prints.append({
            'source': 'bambu',
            'title': job.model_name or job.external_id or f'Job #{job.id}',
            'printer_name': job.printer_name,
            'timestamp': job.finished_at or job.started_at or job.synced_at,
            'weight_grams': job.weight_grams,
            'detail_url': '/bambu',
        })
    for job in recent_prusa:
        recent_prints.append({
            'source': 'prusa',
            'title': job.display_name or job.file_name or f'Job #{job.id}',
            'printer_name': job.printer.name if getattr(job, 'printer', None) else job.printer_name,
            'timestamp': job.finished_at or job.started_at or job.synced_at,
            'weight_grams': job.weight_grams,
            'detail_url': '/prusa',
        })
    recent_prints.sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)
    recent_prints = recent_prints[:6]

    return {
        'low_stock': low_stock_rows[:6],
        'overdue_projects': overdue_projects,
        'unmapped_bambu': unmapped_bambu,
        'unmapped_prusa': unmapped_prusa,
        'printer_issues': printer_issues[:6],
        'recent_prints': recent_prints,
        'counts': {
            'low_stock': len(low_stock_rows),
            'overdue_projects': len(overdue_projects),
            'unmapped_jobs': len(unmapped_bambu) + len(unmapped_prusa),
            'printer_issues': len(printer_issues),
        },
    }


def top_tags(items, attr_name='tag_text', limit=10):
    counter = Counter()
    for item in items:
        counter.update(parse_tags(getattr(item, attr_name, '')))
    return counter.most_common(limit)


def log_movement(filament, action_type, weight, project_id=None, bambu_job_id=None, note=None):
    """Record a filament weight movement with cost calculation."""
    if weight <= 0:
        return
    cost_per_gram = filament.price / filament.weight_total if filament.weight_total > 0 else 0
    total_cost = cost_per_gram * weight
    currency = get_current_currency()

    filament_name = build_filament_history_name(filament)

    movement = MovementHistory(
        filament_id=filament.id if getattr(filament, 'id', None) else None,
        project_id=project_id,
        bambu_job_id=bambu_job_id,
        filament_name=filament_name,
        action_type=action_type,
        weight=weight,
        cost=total_cost,
        currency=currency,
        note=note,
    )
    db.session.add(movement)


def deduct_filament_stock(filament, requested_weight):
    """Deduct stock safely and keep weight/quantity consistent.

    Returns the actually deducted weight after clamping to zero.
    """
    if not filament or requested_weight <= 0:
        return 0.0

    old_weight = filament.weight_remaining
    filament.weight_remaining = max(0.0, filament.weight_remaining - requested_weight)
    actual_amount = old_weight - filament.weight_remaining

    if filament.weight_total > 0:
        expected_quantity = math.ceil(filament.weight_remaining / filament.weight_total)
        if expected_quantity < filament.quantity:
            filament.quantity = expected_quantity

    return actual_amount


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
