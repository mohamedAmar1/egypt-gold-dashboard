#!/usr/bin/env python3
"""Collect verified current gold prices from FoudaLens rendered page.

No derived prices, fabricated fallback, or reuse of cached prices as a new reading.
Fails closed when the source page cannot provide all four karats.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'history.json'
URL = 'https://foudalens.com/ar/rates/gold'
KARATS = ('24', '21', '18', '14')


def clean_digits(text):
    return text.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬', '01234567890123456789.,'))


def numeric_candidates(text):
    text = clean_digits(text)
    # Egyptian gold price is a 4 or 5 digit number; avoid percentages and timestamps.
    result = []
    for m in re.finditer(r'(?<![\d])\d{1,2}(?:,\d{3})+(?:\.\d{1,2})?(?!\d)|(?<![\d])\d{4,5}(?:\.\d{1,2})?(?!\d)', text):
        try:
            v = float(m.group().replace(',', ''))
            if 1000 <= v <= 50000:
                result.append(v)
        except ValueError:
            pass
    return result


def extract_cards(page):
    """Find short DOM blocks starting at each 'عيار N' label and its visible price.

    Restrict to visible elements. Avoid huge ancestors/footers/technical forecasts.
    Require coherent karat ratios, but never derive one price from another.
    """
    blocks = page.evaluate('''() => {
      const result = [];
      const rx = /(?:عيار\\s*|\\b)(24|21|18|14)(?:\\s*عيار|\\s*(?:K|k|قيراط))?/;
      const els = document.querySelectorAll('main *, section *, article *, div *');
      for (const el of els) {
        if (el.children.length) continue;
        const txt = (el.innerText || el.textContent || '').trim();
        if (!txt || txt.length > 70 || !/عيار\\s*(24|21|18|14)/.test(txt)) continue;
        let p = el;
        for (let i=0; i<4 && p; i++, p=p.parentElement) {
          const t=(p.innerText || '').trim();
          if (t.length>350) break;
          if (t.length > txt.length && /[0-9٠-٩]/.test(t))
            result.push({label:txt, text:t, depth:i, tag:p.tagName});
        }
      }
      return result;
    }''')
    options = {k: [] for k in KARATS}
    for block in blocks:
        match = re.search(r'عيار\s*(24|21|18|14)', clean_digits(block['label']))
        if not match:
            continue
        k = match.group(1)
        text = clean_digits(block['text'])
        # Label followed by the most prominent next price in the compact card.
        # Tight price range excludes all common non-price numbers.
        label_match = re.search(r'عيار\s*' + k + r'\b', text)
        if not label_match:
            continue
        trailing = text[label_match.end():]
        candidates = numeric_candidates(trailing[:145])
        for v in candidates[:2]:
            options[k].append((block['depth'],len(text),v,text[:140]))
    return options


def choose_prices(options):
    # Prefer the smallest text container because it tends to expose the main price.
    choices = {k: sorted(options[k], key=lambda x:(x[0],x[1])) for k in KARATS}
    for k in KARATS:
        if not choices[k]:
            raise ValueError(f'Missing verified price for karat {k}; layout may have changed')
    from itertools import product
    for selection in product(*[choices[k][:12] for k in KARATS]):
        vals = {k: selection[i][2] for i,k in enumerate(KARATS)}
        ratio = {k:int(k)/24 for k in KARATS}
        if all(abs(vals[k] / vals['24'] - ratio[k]) < .035 for k in KARATS):
            return vals
    raise ValueError('Karat candidates fail consistency checks; refusing to save ambiguous prices')


def collect():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(locale='ar-EG', timezone_id='Africa/Cairo', user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36')
        page = context.new_page()
        response = page.goto(URL, wait_until='domcontentloaded', timeout=60_000)
        if not response or response.status >= 400:
            raise RuntimeError(f'Source returned HTTP {response.status if response else "none"}')
        # Allow React client-side prices to load; do not pretend a load implies success.
        for _ in range(8):
            page.wait_for_timeout(2500)
            try:
                prices = choose_prices(extract_cards(page))
                break
            except ValueError:
                prices = None
        if prices is None:
            evidence = ROOT / 'data' / 'scraper-debug.txt'
            evidence.write_text(page.locator('body').inner_text()[:10000], encoding='utf-8')
            raise RuntimeError('Could not reliably extract all four displayed prices; see data/scraper-debug.txt in the job workspace')
        # Source date text is informative but not reliably machine-readable; use verified capture time.
        captured = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        browser.close()
        return {'timestamp': captured, 'fetched_at': captured, 'source_updated_at': None, 'prices': prices}


def main():
    item = collect()
    data = {'source': URL, 'updated_at': None, 'records': []}
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding='utf-8'))
    history = data.get('records', [])
    # Store every successful scheduled observation, including unchanged prices.
    # Equal prices correctly yield a neutral (0 EGP / 0%) change in the dashboard.
    history.append(item)
    data = {'source': URL, 'updated_at': item['fetched_at'], 'records': history}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved verified prices:',item['prices'])

if __name__=='__main__':
    main()
