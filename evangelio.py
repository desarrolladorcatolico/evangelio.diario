#!/usr/bin/env python3
import argparse
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
from html import escape

DONBOSCO_URL = 'https://donbosco.org.ar/home/evangelio'
EVANGELI_URL = 'https://evangeli.net/evangelio'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36'
TIMEZONE = 'America/Argentina/La_Rioja'
DEFAULT_RETRIES = 8
DEFAULT_RETRY_MINUTES = 30

EVANGELISTAS = {'Mt': 'Mateo', 'Mc': 'Marcos', 'Lc': 'Lucas', 'Jn': 'Juan'}
MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def fetch(url):
    print('Consultando:', url)
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'es-AR,es;q=0.9'})
    with urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8', errors='replace')


def parse_spanish_date(text, with_de):
    day = r'(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)'
    if with_de:
        pattern = day + r'\s+(\d{1,2})\s+de\s+([A-Za-záéíóúñ]+)\s+de\s+(\d{4})'
    else:
        pattern = day + r'\s+(\d{1,2})\s+([A-Za-záéíóúñ]+)\s+(\d{4})'
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    month = MESES.get(m.group(2).lower())
    if not month:
        return None
    return datetime(int(m.group(3)), month, int(m.group(1))).date()


def extract_donbosco_date(html):
    soup = BeautifulSoup(html, 'html.parser')
    text = clean(soup.get_text(' ', strip=True))
    found = parse_spanish_date(text, with_de=True)
    if not found:
        raise RuntimeError('No pude detectar la fecha publicada por Don Bosco.')
    return found


def extract_evangeli_date(html):
    soup = BeautifulSoup(html, 'html.parser')
    text = clean(soup.get_text(' ', strip=True))
    found = parse_spanish_date(text, with_de=False)
    if not found:
        raise RuntimeError('No pude detectar la fecha publicada por Evangeli.net.')
    return found


def extract_donbosco_gospel(html):
    soup = BeautifulSoup(html, 'html.parser')
    heading = next((t for t in soup.find_all(['h1', 'h2', 'h3'])
                    if clean(t.get_text(' ', strip=True)).lower() == 'evangelio del dia'), None)
    if heading is None:
        raise RuntimeError('No encontré el título "Evangelio del Dia" en Don Bosco.')

    citation_tag = citation_match = None
    for el in heading.find_all_next():
        if not isinstance(el, Tag):
            continue
        if el.name in ['h1', 'h2', 'h3'] and el is not heading:
            if clean(el.get_text(' ', strip=True)).lower() == 'la palabra me dice':
                break
        text = clean(el.get_text(' ', strip=True))
        m = re.fullmatch(
            r'(Mt|Mc|Lc|Jn)\.?\s*([0-9]+\s*,\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?)',
            text, re.I
        )
        if m:
            citation_tag, citation_match = el, m
            break

    if citation_tag is None:
        raise RuntimeError('No pude localizar la cita bíblica en Don Bosco.')

    abrev = citation_match.group(1).title()
    evangelista = EVANGELISTAS.get(abrev, abrev)
    cita = re.sub(r'\s*[-–]\s*', '-', re.sub(r'\s*,\s*', ', ', citation_match.group(2)))

    paragraphs = []
    for el in citation_tag.find_all_next(['p', 'h1', 'h2', 'h3']):
        if el.name in ['h1', 'h2', 'h3']:
            if clean(el.get_text(' ', strip=True)).lower() == 'la palabra me dice':
                break
            continue
        text = clean(el.get_text(' ', strip=True))
        if text and text not in paragraphs:
            paragraphs.append(text)

    evangelio = '\n\n'.join(paragraphs).strip()
    if len(evangelio) < 80:
        raise RuntimeError('El Evangelio extraído de Don Bosco parece incompleto.')
    return evangelista, cita, evangelio


def extract_evangeli_thoughts(html):
    soup = BeautifulSoup(html, 'html.parser')
    heading = next((t for t in soup.find_all(['h2', 'h3', 'h4'])
                    if clean(t.get_text(' ', strip=True)).lower() == 'pensamientos para el evangelio de hoy'), None)
    if heading is None:
        raise RuntimeError('No encontré "Pensamientos para el Evangelio de hoy" en Evangeli.net.')

    thoughts = []
    for el in heading.find_all_next():
        if not isinstance(el, Tag):
            continue
        if el.name in ['h1', 'h2', 'h3', 'h4'] and el is not heading:
            break
        if el.name == 'li':
            text = clean(el.get_text(' ', strip=True))
            if text and text not in thoughts:
                thoughts.append(text)

    if not thoughts:
        for el in heading.find_all_next(['p', 'h1', 'h2', 'h3', 'h4']):
            if el.name in ['h1', 'h2', 'h3', 'h4']:
                break
            text = clean(el.get_text(' ', strip=True))
            if text and (text.startswith('«') or text.startswith('“')):
                thoughts.append(text)

    if not thoughts:
        raise RuntimeError('No pude extraer los pensamientos de Evangeli.net.')
    return thoughts[:3]


def make_html(output, evangelista, cita, evangelio, pensamientos):
    bloques = [b.strip() for b in evangelio.split('\n\n') if b.strip()]
    evangelio_html = '\n'.join(f'<p>{escape(b)}</p>' for b in bloques)
    pensamientos_html = '\n'.join(
        f'<div class="thought"><span class="bullet">•</span><p>{escape(p)}</p></div>'
        for p in pensamientos
    )

    mensaje_whatsapp = (
        f'*✠ Santo Evangelio según san {evangelista}* ({cita})'
        f'\n\n{evangelio}'
        f'\n\n_Palabra del Señor._'
        f'\n\n*Pensamientos para el Evangelio de hoy*'
        f'\n\n' + '\n\n'.join(f'• {p}' for p in pensamientos)
    )
    whatsapp_url = 'https://api.whatsapp.com/send?text=' + quote(mensaje_whatsapp, safe='')

    html = f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light">
<title>Evangelio del día</title>
<style>
:root {{ --ink:#252525; --muted:#6c665d; --accent:#8b2635; --paper:#fffdf8; --line:#e8dfd2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f3eee6; color:var(--ink); font-family:Georgia,'Times New Roman',serif; line-height:1.62; }}
main {{ max-width:760px; margin:0 auto; min-height:100vh; background:var(--paper); padding:28px 20px 44px; }}
header {{ text-align:center; margin-bottom:26px; }}
.cross {{ color:var(--accent); font-size:30px; line-height:1; }}
h1 {{ font-size:clamp(1.35rem,5vw,2rem); line-height:1.22; margin:10px 0 5px; }}
.cita {{ color:var(--muted); font-style:italic; font-size:1.05rem; }}
.gospel p {{ margin:0 0 16px; font-size:1.08rem; }}
.word {{ text-align:center; font-style:italic; font-weight:600; margin:28px 0; }}
.separator {{ width:68px; height:2px; background:var(--accent); margin:28px auto; border:0; }}
h2 {{ color:var(--accent); text-align:center; font-size:1.18rem; margin:0 0 22px; }}
.thought {{ display:flex; gap:10px; padding:14px 0; border-bottom:1px solid var(--line); }}
.thought:last-child {{ border-bottom:0; }}
.thought p {{ margin:0; }}
.bullet {{ color:var(--accent); font-size:1.35rem; line-height:1.35; }}
.share {{ display:block; width:100%; margin:30px 0 12px; padding:14px 18px; border-radius:14px; background:#25D366; color:#fff; font:bold 1rem Arial,sans-serif; text-align:center; text-decoration:none; box-shadow:0 5px 16px rgba(37,211,102,.22); }}
footer {{ text-align:center; color:var(--muted); font:0.8rem Arial,sans-serif; margin-top:24px; }}
</style>
</head>
<body>
<main>
<header><div class="cross">✠</div><h1>Santo Evangelio según san {escape(evangelista)}</h1><div class="cita">({escape(cita)})</div></header>
<section class="gospel">{evangelio_html}</section>
<div class="word">Palabra del Señor.</div>
<hr class="separator">
<section><h2>Pensamientos para el Evangelio de hoy</h2>{pensamientos_html}</section>
<a class="share" href="{escape(whatsapp_url, quote=True)}" target="_blank" rel="noopener noreferrer">📤 Compartir por WhatsApp</a>
<footer>Desarrollador Católico © 2026</footer>
</main>
</body>
</html>
'''
    Path(output).write_text(html, encoding='utf-8')


def obtain_current_content(max_attempts, retry_minutes):
    argentina = ZoneInfo(TIMEZONE)

    for attempt in range(1, max_attempts + 1):
        now = datetime.now(argentina)
        today = now.date()
        print(f'\nIntento {attempt}/{max_attempts} - Argentina: {now:%d/%m/%Y %H:%M:%S}')

        donbosco_html = fetch(DONBOSCO_URL)
        evangeli_html = fetch(EVANGELI_URL)
        fecha_donbosco = extract_donbosco_date(donbosco_html)
        fecha_evangeli = extract_evangeli_date(evangeli_html)

        print(f'Fecha esperada:     {today:%d/%m/%Y}')
        print(f'Fecha Don Bosco:    {fecha_donbosco:%d/%m/%Y}')
        print(f'Fecha Evangeli.net: {fecha_evangeli:%d/%m/%Y}')

        if fecha_donbosco == today and fecha_evangeli == today:
            print('VALIDACIÓN OK: ambas fuentes corresponden al día actual.')
            return donbosco_html, evangeli_html

        if attempt < max_attempts:
            print(f'Fuentes aún atrasadas. Nuevo intento en {retry_minutes} minutos.')
            time.sleep(retry_minutes * 60)

    raise RuntimeError(
        f'PUBLICACIÓN CANCELADA: después de {max_attempts} intentos las fuentes no coinciden '
        'con la fecha actual de Argentina. No se genera un index.html nuevo.'
    )


def main():
    parser = argparse.ArgumentParser(description='Evangelio Don Bosco + pensamientos Evangeli.net con validación y reintentos.')
    parser.add_argument('--salida', default='evangelio.html', help='Nombre del HTML de salida.')
    parser.add_argument('--reintentos', type=int, default=DEFAULT_RETRIES, help='Cantidad total de intentos. Por defecto: 4.')
    parser.add_argument('--minutos-reintento', type=int, default=DEFAULT_RETRY_MINUTES, help='Minutos entre intentos. Por defecto: 30.')
    args = parser.parse_args()

    if args.reintentos < 1:
        raise ValueError('--reintentos debe ser al menos 1.')
    if args.minutos_reintento < 1:
        raise ValueError('--minutos-reintento debe ser al menos 1.')

    donbosco_html, evangeli_html = obtain_current_content(args.reintentos, args.minutos_reintento)
    evangelista, cita, evangelio = extract_donbosco_gospel(donbosco_html)
    pensamientos = extract_evangeli_thoughts(evangeli_html)
    make_html(args.salida, evangelista, cita, evangelio, pensamientos)

    print(f'OK | Evangelio Don Bosco: {evangelista} {cita}')
    print(f'OK | Pensamientos Evangeli.net: {len(pensamientos)}')
    print(f'Creado: {Path(args.salida).resolve()}')


if __name__ == '__main__':
    main()

