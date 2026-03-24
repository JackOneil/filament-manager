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

def fetch_link_metadata(url):
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse

    meta = {
        'og_title': None,
        'og_image': None,
        'og_description': None,
        'domain': None
    }
    
    try:
        parsed_uri = urlparse(url)
        meta['domain'] = '{uri.netloc}'.format(uri=parsed_uri)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            og_title = soup.find('meta', property='og:title')
            if og_title:
                meta['og_title'] = og_title.get('content')
            else:
                title_tag = soup.find('title')
                meta['og_title'] = title_tag.text if title_tag else None
                
            og_image = soup.find('meta', property='og:image')
            if og_image:
                meta['og_image'] = og_image.get('content')
                
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                meta['og_description'] = og_desc.get('content')
            else:
                desc_tag = soup.find('meta', attrs={'name': 'description'})
                if desc_tag:
                    meta['og_description'] = desc_tag.get('content')
                    
    except Exception:
        pass
        
    if meta['og_title'] and len(meta['og_title']) > 250:
        meta['og_title'] = meta['og_title'][:250] + "..."
    if meta['og_image'] and len(meta['og_image']) > 490:
        meta['og_image'] = meta['og_image'][:490] + "..."
        
    return meta
