#!/usr/bin/env python3
import argparse
import re
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag
from html import escape

DONBOSCO_URL = 'https://donbosco.org.ar/home/evangelio'
EVANGELI_URL = 'https://evangeli.net/evangelio'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36'

EVANGELISTAS = {
    'Mt': 'Mateo',
    'Mc': 'Marcos',
    'Lc': 'Lucas',
    'Jn': 'Juan',
}


def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def fetch(url):
    print('Consultando:', url)
    req = Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'es-AR,es;q=0.9',
    })
    with urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8', errors='replace')


def extract_donbosco_gospel(html):
    """Extrae solo cita y Evangelio desde DonBosco Argentina."""
    soup = BeautifulSoup(html, 'html.parser')

    heading = None
    for tag in soup.find_all(['h1', 'h2', 'h3']):
        if clean(tag.get_text(' ', strip=True)).lower() == 'evangelio del dia':
            heading = tag
            break

    if heading is None:
        raise RuntimeError('No encontré el título "Evangelio del Dia" en Don Bosco.')

    citation_tag = None
    citation_match = None

    for el in heading.find_all_next():
        if not isinstance(el, Tag):
            continue

        if el.name in ['h1', 'h2', 'h3'] and el is not heading:
            title = clean(el.get_text(' ', strip=True))
            if title.lower() == 'la palabra me dice':
                break

        text = clean(el.get_text(' ', strip=True))
        m = re.fullmatch(
            r'(Mt|Mc|Lc|Jn)\.?\s*([0-9]+\s*,\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?)',
            text,
            re.I,
        )
        if m:
            citation_tag = el
            citation_match = m
            break

    if citation_tag is None or citation_match is None:
        raise RuntimeError('No pude localizar la cita bíblica en Don Bosco.')

    abrev = citation_match.group(1).title()
    evangelista = EVANGELISTAS.get(abrev, abrev)
    cita = citation_match.group(2)
    cita = re.sub(r'\s*,\s*', ', ', cita)
    cita = re.sub(r'\s*[-–]\s*', '-', cita)

    paragraphs = []
    for el in citation_tag.find_all_next(['p', 'h1', 'h2', 'h3']):
        if el.name in ['h1', 'h2', 'h3']:
            title = clean(el.get_text(' ', strip=True))
            if title.lower() == 'la palabra me dice':
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
    """Extrae solo 'Pensamientos para el Evangelio de hoy' desde Evangeli.net."""
    soup = BeautifulSoup(html, 'html.parser')

    heading = None
    for tag in soup.find_all(['h2', 'h3', 'h4']):
        if clean(tag.get_text(' ', strip=True)).lower() == 'pensamientos para el evangelio de hoy':
            heading = tag
            break

    if heading is None:
        raise RuntimeError('No encontré "Pensamientos para el Evangelio de hoy" en Evangeli.net.')

    thoughts = []

    # Normalmente aparecen como elementos de lista; este recorrido conserva el texto y su atribución.
    for el in heading.find_all_next():
        if not isinstance(el, Tag):
            continue

        if el.name in ['h1', 'h2', 'h3', 'h4'] and el is not heading:
            break

        if el.name == 'li':
            text = clean(el.get_text(' ', strip=True))
            if text and text not in thoughts:
                thoughts.append(text)

    # Fallback para cambios menores de HTML: leer párrafos relevantes tras el encabezado.
    if not thoughts:
        for el in heading.find_all_next(['p', 'h1', 'h2', 'h3', 'h4']):
            if el.name in ['h1', 'h2', 'h3', 'h4']:
                break
            text = clean(el.get_text(' ', strip=True))
            if text and (text.startswith('«') or text.startswith('“')):
                thoughts.append(text)

    if not thoughts:
        raise RuntimeError('Encontré la sección de pensamientos, pero no pude extraer su contenido.')

    return thoughts[:3]


def make_html(output, evangelista, cita, evangelio, pensamientos):
    bloques = [b.strip() for b in evangelio.split('\n\n') if b.strip()]
    evangelio_html = "\n".join(f"<p>{escape(b)}</p>" for b in bloques)
    pensamientos_html = "\n".join(
        f'<div class="thought"><span class="bullet">•</span><p>{escape(p)}</p></div>'
        for p in pensamientos
    )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light">
<title>Evangelio del día</title>
<style>
:root {{ --ink:#252525; --muted:#6c665d; --accent:#8b2635; --paper:#fffdf8; --line:#e8dfd2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f3eee6; color:var(--ink); font-family:Georgia, 'Times New Roman', serif; line-height:1.62; }}
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
.share {{ display:block; width:100%; margin:30px 0 12px; padding:14px 18px; border:0; border-radius:14px; background:#25D366; color:#fff; font:bold 1rem Arial,sans-serif; text-align:center; text-decoration:none; cursor:pointer; box-shadow:0 5px 16px rgba(37,211,102,.22); }}
.share:active {{ transform:scale(.99); }}
footer {{ text-align:center; color:var(--muted); font:0.8rem Arial,sans-serif; margin-top:24px; }}
</style>
</head>
<body>
<main>
<header>
  <div class="cross">✠</div>
  <h1>Santo Evangelio según san {escape(evangelista)}</h1>
  <div class="cita">({escape(cita)})</div>
</header>
<section class="gospel">{evangelio_html}</section>
<div class="word">Palabra del Señor.</div>
<hr class="separator">
<section>
  <h2>Pensamientos para el Evangelio de hoy</h2>
  {pensamientos_html}
</section>
<button class="share" type="button" onclick="compartirWhatsApp()">Compartir por WhatsApp</button>
</main>
<script>
function compartirWhatsApp() {{
  const titulo = `✠ Santo Evangelio según san {escape(evangelista)} ({escape(cita)})`;
  const evangelio = {repr(chr(10).join(b.strip() for b in []))};
  const gospelParas = Array.from(document.querySelectorAll('.gospel p')).map(p => p.innerText.trim()).filter(Boolean).join('\n\n');
  const pensamientos = Array.from(document.querySelectorAll('.thought p')).map(p => '• ' + p.innerText.trim()).join('\n\n');
  const mensaje = `*${{titulo}}*\n\n${{gospelParas}}\n\n_Palabra del Señor._\n\n*Pensamientos para el Evangelio de hoy*\n\n${{pensamientos}}`;
  window.location.href = 'https://wa.me/?text=' + encodeURIComponent(mensaje);
}}
</script>
</body>
</html>
"""
    Path(output).write_text(html, encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(
        description='Evangelio desde Don Bosco Argentina + pensamientos desde Evangeli.net.'
    )
    parser.add_argument('--salida', help='Nombre del archivo HTML de salida.')
    args = parser.parse_args()

    today = date.today()
    output = args.salida or 'evangelio.html'

    donbosco_html = fetch(DONBOSCO_URL)
    evangeli_html = fetch(EVANGELI_URL)

    evangelista, cita, evangelio = extract_donbosco_gospel(donbosco_html)
    pensamientos = extract_evangeli_thoughts(evangeli_html)

    make_html(output, evangelista, cita, evangelio, pensamientos)
    
    print(f'OK | Evangelio Don Bosco: {evangelista} {cita}')
    print(f'OK | Pensamientos Evangeli.net: {len(pensamientos)}')
    print(f'Creado: {Path(output).resolve()}')

if __name__ == '__main__':
    main()
