"""
Test del sito koreshelf.github.io: servono la cartella site/ in locale e la usano in Chromium.
GitHub è simulato: l'ultima release la decidiamo noi (o la facciamo fallire).

    pip install playwright && playwright install chromium
    python tests/test_site.py

Variabili utili: ONLY=tema,lingua (solo alcuni test), KEEP_SHOTS=1 (salva gli screenshot).
"""

import asyncio
import functools
import json
import os
import re
import sys
import tempfile
import threading
import time
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SHOTS = Path(tempfile.gettempdir()) / "koreshelf-site-shots"
REPO = "https://github.com/GabrieleTrovato01/KoreShelf"
RELEASES = REPO + "/releases/latest"
API = "https://api.github.com/repos/GabrieleTrovato01/KoreShelf/releases/latest"

FILES = {   # i nomi che produce .github/workflows/release.yml del repository dell'app
    "win": "KoreShelf-4.0.0-windows-x64.exe",
    "mac": "KoreShelf-4.0.0-macos-universal.dmg",
    "linux": "KoreShelf-4.0.0-x86_64.AppImage",
    "android": "KoreShelf-4.0.0-android.apk",
    "ios": "KoreShelf-4.0.0-ios-unsigned.ipa",
}
URL = {os_: f"{REPO}/releases/download/v4.0.0/{name}" for os_, name in FILES.items()}
RELEASE_4 = {"tag_name": "v4.0.0", "html_url": REPO + "/releases/tag/v4.0.0",
             "assets": [{"name": n, "browser_download_url": URL[k]} for k, n in FILES.items()]}
# L'ultima release di oggi (versione Node): file .zip che il sito non deve proporre come app
RELEASE_3 = {"tag_name": "v3.0.0", "html_url": REPO + "/releases/tag/v3.0.0",
             "assets": [{"name": "KoreShelf-macOS-AppleSilicon.zip", "browser_download_url": REPO + "/x.zip"}]}

UA = {
    "win": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "android": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36",
    "ios": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
}
OS_NAME_IT = {"win": "Windows", "mac": "Mac", "linux": "Linux", "android": "Android", "ios": "iPhone"}


class Site:
    """La cartella site/ servita su una porta libera, come farebbe GitHub Pages."""

    def __enter__(self):
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(SITE))
        handler.log_message = lambda *a, **k: None
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()


async def open_site(p, site, os_="win", release=RELEASE_4, api_status=200, locale="it-IT",
                    scheme="light", viewport=(1280, 800), storage=None):
    browser = await p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
    phone = os_ in ("android", "ios")
    ctx = await browser.new_context(user_agent=UA[os_], locale=locale, color_scheme=scheme,
                                    viewport={"width": viewport[0], "height": viewport[1]},
                                    is_mobile=phone, has_touch=phone)
    ctx.calls = []

    async def fake_github(route):
        ctx.calls.append(route.request.url)
        if api_status != 200:
            await route.fulfill(status=api_status, body="{}")
        else:
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(release))
    await ctx.route("https://api.github.com/**", fake_github)
    ctx.hosts = set()
    ctx.on("request", lambda r: ctx.hosts.add(re.sub(r"^https?://([^/:]+).*$", r"\1", r.url)))
    if storage:
        await ctx.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
                                          for k, v in storage.items()))
    page = await ctx.new_page()
    await page.goto(site.url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(300)
    return browser, ctx, page


async def shot(page, name):
    if os.environ.get("KEEP_SHOTS"):
        SHOTS.mkdir(exist_ok=True)
        await page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


async def link(page, sel):
    el = await page.query_selector(sel)
    if not el:
        return None
    return {"text": " ".join((await el.inner_text()).split()), "href": await el.get_attribute("href"),
            "visible": await el.is_visible()}


# ----------------------------------------------------------------------- test

async def test_hero_button_follows_the_visitor_device(p):
    """Il pulsante grande in alto propone il file giusto per il dispositivo di chi visita:
    .exe su Windows, .dmg su Mac, AppImage su Linux, .apk su Android. Su iPhone non c'è un file da
    scaricare e basta: porta alle istruzioni."""
    problems = []
    with Site() as site:
        for os_ in ("win", "mac", "linux", "android", "ios"):
            phone = os_ in ("android", "ios")
            browser, ctx, page = await open_site(p, site, os_=os_, viewport=(390, 844) if phone else (1280, 800))
            hero = await link(page, "#hero-download")
            await shot(page, f"hero_{os_}")
            await browser.close()
            if not hero or not hero["visible"]:
                problems.append(f"{os_}: manca il pulsante principale #hero-download")
                continue
            if OS_NAME_IT[os_] not in hero["text"]:
                problems.append(f"{os_}: il pulsante deve nominare {OS_NAME_IT[os_]}: {hero['text']!r}")
            expected = "#ios" if os_ == "ios" else URL[os_]
            if not (hero["href"] or "").endswith(expected):
                problems.append(f"{os_}: il pulsante deve portare a {expected}, porta a {hero['href']}")
    assert not problems, "\n".join(problems)


async def test_download_index_links_every_file_of_the_latest_release(p):
    """L'indice dei download ha una riga per dispositivo, con il link al file dell'ultima release
    (presa da GitHub, così il sito non va aggiornato a ogni versione) e la versione in vista.
    La riga del dispositivo di chi visita è messa in evidenza."""
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site, os_="mac")
        for os_ in FILES:
            a = await link(page, f'#downloads [data-os="{os_}"] a.dl')
            if not a:
                problems.append(f"Manca la riga {os_} con il suo link a.dl")
            elif os_ != "ios" and a["href"] != URL[os_]:
                problems.append(f"{os_}: link {a['href']} invece di {URL[os_]}")
        ios_file = await link(page, '#ios a.dl-ipa')
        if not ios_file or ios_file["href"] != URL["ios"]:
            problems.append(f"Le istruzioni per iPhone devono linkare il file .ipa: {ios_file}")
        version = await page.inner_text("#version") if await page.query_selector("#version") else ""
        if "4.0.0" not in version:
            problems.append(f"La versione 4.0.0 deve essere visibile: {version!r}")
        current = await page.get_attribute('#downloads [data-os="mac"]', "aria-current") \
            if await page.query_selector('#downloads [data-os="mac"]') else None
        if current != "true":
            problems.append("La riga Mac (dispositivo di chi visita) va evidenziata con aria-current=true")
        await shot(page, "downloads_mac")
        await browser.close()
    assert not problems, "\n".join(problems)


async def test_without_github_the_buttons_still_work(p):
    """Se GitHub non risponde (limite di richieste, rete) o l'ultima release non ha i file
    dell'app (come oggi la v3.0.0), nessun pulsante si rompe: portano alla pagina delle release."""
    problems = []
    with Site() as site:
        for label, kwargs in (("GitHub in errore", {"api_status": 503}), ("release senza file", {"release": RELEASE_3})):
            browser, ctx, page = await open_site(p, site, os_="win", **kwargs)
            hrefs = await page.eval_on_selector_all("#hero-download, #downloads a.dl",
                                                    "els => els.map(e => e.getAttribute('href'))")
            text = await page.inner_text("body")
            await browser.close()
            if len(hrefs) < 6:
                problems.append(f"{label}: mancano pulsanti ({len(hrefs)})")
            bad = [h for h in hrefs if h != RELEASES and not (h or "").endswith("#ios")]
            if bad:
                problems.append(f"{label}: questi link non portano alla pagina delle release: {bad}")
            for word in ("undefined", "null", "NaN", "{v}"):
                if word in text:
                    problems.append(f"{label}: nella pagina compare {word!r}")
    assert not problems, "\n".join(problems)


async def test_github_is_asked_once_per_visit(p):
    """Le richieste a GitHub senza account sono limitate (60 all'ora per indirizzo): la risposta si
    ricorda per la visita, così ricaricare la pagina o cambiare lingua non fa nuove richieste."""
    with Site() as site:
        browser, ctx, page = await open_site(p, site)
        await page.reload()
        await page.wait_for_load_state("networkidle")
        calls = [c for c in ctx.calls if c.startswith(API)]
        await browser.close()
    assert len(calls) == 1, f"GitHub interpellato {len(calls)} volte invece di una"


async def test_theme_follows_system_and_remembers_choice(p):
    """Tema: alla prima visita segue il dispositivo (chiaro o scuro). Il pulsante sole/luna lo
    cambia e la scelta resta alla visita dopo. Il tema si decide prima di disegnare la pagina
    (niente lampo bianco al caricamento in modalità scura)."""
    problems = []
    head = (SITE / "index.html").read_text()
    head = head[:head.find("</head>")] if "</head>" in head else head
    css_at = head.find('rel="stylesheet"')
    script_at = head.find("data-theme")
    if script_at < 0 or css_at < 0 or script_at > css_at:
        problems.append("Lo script che sceglie il tema deve stare nell'<head>, prima del foglio di stile")
    with Site() as site:
        for scheme in ("light", "dark"):
            browser, ctx, page = await open_site(p, site, scheme=scheme)
            theme = await page.evaluate("document.documentElement.dataset.theme")
            bg = await page.evaluate("getComputedStyle(document.body).backgroundColor")
            await shot(page, f"theme_{scheme}")
            if theme != scheme:
                problems.append(f"Dispositivo {scheme}: tema {theme!r}")
            dark_bg = bg == "rgb(15, 24, 34)"            # #0f1822, il blu notte dell'app
            if dark_bg != (scheme == "dark"):
                problems.append(f"Dispositivo {scheme}: sfondo {bg}")
            if scheme == "dark":
                toggle = await page.query_selector("#theme-toggle")
                if not toggle:
                    problems.append("Manca il pulsante #theme-toggle")
                else:
                    label = await toggle.get_attribute("aria-label")
                    if not label:
                        problems.append("Il pulsante del tema deve dire a cosa serve (aria-label)")
                    await toggle.click()
                    await page.wait_for_timeout(200)
                    after = await page.evaluate("document.documentElement.dataset.theme")
                    if after != "light":
                        problems.append(f"Dopo il clic il tema deve diventare chiaro: {after!r}")
                    await page.reload()
                    await page.wait_for_load_state("networkidle")
                    kept = await page.evaluate("document.documentElement.dataset.theme")
                    if kept != "light":
                        problems.append(f"La scelta va ricordata: dopo il ricaricamento il tema è {kept!r}")
            await browser.close()
    assert not problems, "\n".join(problems)


async def test_language_follows_browser_and_can_be_changed(p):
    """Lingua: quella del browser se è una delle 5 dell'app (it, en, de, fr, es), altrimenti inglese.
    Si cambia dal menu, la scelta resta, e anche lang di <html> cambia (lettori di schermo)."""
    problems = []
    with Site() as site:
        for locale, lang in (("it-IT", "it"), ("de-DE", "de"), ("es-MX", "es"), ("ja-JP", "en")):
            browser, ctx, page = await open_site(p, site, locale=locale)
            got = await page.evaluate("""() => ({ lang: document.documentElement.lang,
                h1: document.querySelector('h1') && document.querySelector('h1').innerText.trim(),
                want: window.KS_I18N && window.KS_I18N[document.documentElement.lang] && window.KS_I18N[document.documentElement.lang].hero_title })""")
            await browser.close()
            if got["lang"] != lang:
                problems.append(f"Browser {locale}: lingua {got['lang']!r} invece di {lang!r}")
            elif not got["want"] or got["h1"] != got["want"]:
                problems.append(f"Browser {locale}: titolo {got['h1']!r} invece di {got['want']!r}")
        browser, ctx, page = await open_site(p, site, locale="it-IT")
        if not await page.query_selector("#lang"):
            problems.append("Manca il menu della lingua #lang")
        else:
            await page.select_option("#lang", "fr")
            await page.wait_for_timeout(200)
            await page.reload()
            await page.wait_for_load_state("networkidle")
            lang = await page.evaluate("document.documentElement.lang")
            hero = await link(page, "#hero-download")
            if lang != "fr":
                problems.append(f"La lingua scelta va ricordata: dopo il ricaricamento è {lang!r}")
            if hero and URL["win"] != hero["href"]:
                problems.append(f"Cambiare lingua non deve rompere il download: {hero['href']}")
        await browser.close()
    assert not problems, "\n".join(problems)


async def test_every_language_has_every_text(p):
    """Ogni testo della pagina esiste in tutte e 5 le lingue: niente chiavi mancanti o vuote."""
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site)
        data = await page.evaluate("""() => ({ dict: window.KS_I18N || null,
            used: [...document.querySelectorAll('[data-i18n],[data-i18n-attr]')].flatMap(el => [
                ...(el.dataset.i18n ? [el.dataset.i18n] : []),
                ...(el.dataset.i18nAttr ? el.dataset.i18nAttr.split(',').map(p => p.split(':')[1]) : [])]) })""")
        await browser.close()
    if not data["dict"]:
        raise AssertionError("Manca il dizionario window.KS_I18N")
    langs = ("it", "en", "de", "fr", "es")
    for lang in langs:
        if lang not in data["dict"]:
            problems.append(f"Manca la lingua {lang}")
    keys = set(data["dict"].get("it", {}))
    if len(data["used"]) < 30:
        problems.append(f"Troppo pochi testi traducibili nella pagina ({len(data['used'])})")
    for key in data["used"]:
        if key not in keys:
            problems.append(f"La pagina usa la chiave {key!r} che non esiste nel dizionario")
    for lang in langs:
        d = data["dict"].get(lang, {})
        missing = [k for k in keys if not str(d.get(k, "")).strip()]
        extra = [k for k in d if k not in keys]
        if missing:
            problems.append(f"{lang}: testi mancanti {missing[:6]}{'…' if len(missing) > 6 else ''}")
        if extra:
            problems.append(f"{lang}: chiavi in più {extra[:6]}")
    assert not problems, "\n".join(problems)


async def test_phone_layout_fits_and_is_thumb_friendly(p):
    """Sul telefono (tema chiaro e scuro) niente scorrimento laterale, e i pulsanti di download
    sono grandi abbastanza per il pollice (almeno 44 px di altezza)."""
    problems = []
    with Site() as site:
        for scheme in ("light", "dark"):
            browser, ctx, page = await open_site(p, site, os_="android", scheme=scheme, viewport=(390, 844))
            widths = await page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
            sizes = await page.eval_on_selector_all("#hero-download, #downloads a.dl, #theme-toggle, #lang",
                                                    "els => els.map(e => [e.id || e.className, Math.round(e.getBoundingClientRect().height)])")
            await shot(page, f"phone_{scheme}")
            await browser.close()
            if widths[0] > widths[1]:
                problems.append(f"{scheme}: la pagina scorre di lato ({widths[0]} px su {widths[1]})")
            small = [s for s in sizes if s[1] < 44]
            if len(sizes) < 8:
                problems.append(f"{scheme}: mancano dei controlli ({sizes})")
            if small:
                problems.append(f"{scheme}: controlli troppo piccoli per il pollice: {small}")
    assert not problems, "\n".join(problems)


async def test_only_github_is_contacted(p):
    """Privacy: il sito non chiama servizi esterni (niente Google Fonts, statistiche o CDN).
    L'unica richiesta fuori dal sito è quella a GitHub per sapere qual è l'ultima versione."""
    with Site() as site:
        browser, ctx, page = await open_site(p, site, scheme="dark")
        hosts = ctx.hosts - {"127.0.0.1", "api.github.com"}
        font = await page.evaluate("getComputedStyle(document.querySelector('h1') || document.body).fontFamily")
        # fonts.check() dice "vero" anche se Literata non esiste: contiamo i caratteri caricati davvero
        loaded = await page.evaluate("""async () => { await document.fonts.ready;
            return [...document.fonts].some(f => f.family.replace(/["']/g, '') === 'Literata' && f.status === 'loaded'); }""")
        await browser.close()
    problems = []
    if hosts:
        problems.append(f"Richieste verso servizi esterni: {sorted(hosts)}")
    if "Literata" not in font or not loaded:
        problems.append(f"Il carattere Literata va servito dal sito stesso (font: {font}, caricato: {loaded})")
    assert not problems, "\n".join(problems)


async def test_footer_links_author_and_every_community(p):
    """Piè di pagina: il nome dell'autore porta al suo profilo GitHub (anche dopo aver cambiato
    lingua) e ci sono tutti i canali della comunità, TikTok compreso."""
    want = {"https://github.com/GabrieleTrovato01/KoreShelf", "https://discord.gg/S2jqFGK7wJ",
            "https://www.reddit.com/r/KoreShelf/", "https://www.instagram.com/koreshelf/",
            "https://www.tiktok.com/@koreshelf1"}
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site)
        for lang in ("it", "de", "en"):
            await page.select_option("#lang", lang)
            await page.wait_for_timeout(150)
            author = await page.eval_on_selector_all(".colophon a", "els => els.map(e => [e.innerText.trim(), e.href])")
            if ["GabrieleTrovato01", "https://github.com/GabrieleTrovato01"] not in author:
                problems.append(f"{lang}: nel colophon il nome dell'autore deve portare al suo profilo GitHub: {author}")
        links = set(await page.eval_on_selector_all(".community a", "els => els.map(e => e.href)"))
        await browser.close()
    missing = want - links
    if missing:
        problems.append(f"Mancano nel piè di pagina: {sorted(missing)}")
    assert not problems, "\n".join(problems)


async def test_reading_chapter_shows_the_highlights_board(p):
    """Capitolo II (la lettura): oltre al lettore si vede la bacheca con le frasi sottolineate."""
    with Site() as site:
        browser, ctx, page = await open_site(p, site)
        await page.locator(".plate-phones").scroll_into_view_if_needed()
        await page.wait_for_timeout(500)
        imgs = await page.eval_on_selector_all(".plate-phones img",
                                               "els => els.map(e => [e.getAttribute('src'), e.naturalWidth, e.alt])")
        await browser.close()
    board = [i for i in imgs if "board" in (i[0] or "")]
    assert board, f"Nel capitolo II manca la bacheca: {imgs}"
    assert board[0][1] > 0, f"L'immagine della bacheca non si carica: {board[0]}"
    assert "bacheca" in board[0][2].lower(), f"Il testo alternativo deve dire che è la bacheca: {board[0][2]!r}"


PHONE = (390, 844)


async def test_phone_header_is_one_compact_row(p):
    """Telefono: l'intestazione sta su una riga (nome, lingua compatta, tema). Niente pulsante
    "Scarica" in alto: il pulsante grande è subito sotto. Il menu lingua mostra la sigla (IT)."""
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site, os_="android", viewport=PHONE)
        got = await page.evaluate("""() => { const h = document.querySelector('.top'), s = document.querySelector('#lang');
            const nav = document.querySelector('.top .btn-small');
            return { height: Math.round(h.getBoundingClientRect().height), shown: s.options[s.selectedIndex].text,
                     label: s.getAttribute('aria-label'), navBtn: nav ? getComputedStyle(nav).display : 'none' }; }""")
        await browser.close()
    if got["height"] > 72:
        problems.append(f"L'intestazione è alta {got['height']} px: deve stare su una riga (≤ 72 px)")
    if got["shown"] != "IT":
        problems.append(f"Il menu lingua deve mostrare la sigla 'IT', mostra {got['shown']!r}")
    if not got["label"]:
        problems.append("Con la sola sigla, il menu lingua deve avere un aria-label (es. 'Lingua')")
    if got["navBtn"] != "none":
        problems.append("Sul telefono il pulsante 'Scarica' dell'intestazione va nascosto")
    assert not problems, "\n".join(problems)


CAROUSEL = """() => { const c = document.querySelector('#chapters');
    const cards = [...c.querySelectorAll(':scope > article')];
    const order = cards.map(card => {
        const top = sel => { const e = card.querySelector(sel); if (!e || !e.offsetParent) return null;
                             return Math.round(e.getBoundingClientRect().top); };
        const img = [...card.querySelectorAll('img')].find(i => i.offsetParent);
        return { label: top('.label'), title: top('h2'), image: img ? Math.round(img.getBoundingClientRect().top) : null,
                 text: top('p:not(.label)') }; });
    const cs = getComputedStyle(c);
    return { scrollable: c.scrollWidth > c.clientWidth + 10, snap: cs.scrollSnapType, left: Math.round(c.scrollLeft),
             cardW: Math.round(cards[0].getBoundingClientRect().width), secondLeft: Math.round(cards[1].getBoundingClientRect().left),
             order, active: [...document.querySelectorAll('.carousel-dots button')].findIndex(b => b.getAttribute('aria-current') === 'true'),
             dots: [...document.querySelectorAll('.carousel-dots button')].map(b => { const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }) }; }"""


async def test_phone_chapters_are_a_carousel_of_cards(p):
    """Telefono: i tre capitoli sono schede da sfogliare di lato (aggancio a ogni scheda), la scheda
    dopo sbuca dal bordo, e in ogni scheda l'ordine è occhiello, titolo, immagine, testo (oggi nel
    Capitolo II le immagini finiscono sopra il titolo). Pallini toccabili (44 px). Su computer niente carosello."""
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site, os_="android", viewport=PHONE)
        await page.locator("#chapters").scroll_into_view_if_needed()
        got = await page.evaluate(CAROUSEL)
        await shot(page, "phone_carousel")
        await browser.close()
        if not got["scrollable"] or "x" not in (got["snap"] or ""):
            problems.append(f"I capitoli devono scorrere di lato con aggancio (scroll-snap x): {got['snap']}, scorrevole {got['scrollable']}")
        if not (got["cardW"] < PHONE[0] - 40 and got["secondLeft"] < PHONE[0]):
            problems.append(f"La scheda dopo deve sbucare dal bordo (larghezza {got['cardW']}, seconda a {got['secondLeft']})")
        for i, o in enumerate(got["order"], 1):
            seq = [o["label"], o["title"]] + ([o["image"]] if o["image"] is not None else []) + [o["text"]]
            if None in seq[:2] or o["text"] is None or seq != sorted(seq):
                problems.append(f"Capitolo {i}: ordine sbagliato (occhiello, titolo, immagine, testo): {o}")
        if len(got["dots"]) != 3 or any(w < 44 or h < 44 for w, h in got["dots"]):
            problems.append(f"Servono 3 pallini toccabili da almeno 44 px: {got['dots']}")
        browser, ctx, page = await open_site(p, site, os_="win")
        desk = await page.evaluate("() => { const c = document.querySelector('#chapters'); return [c.scrollWidth > c.clientWidth + 10, !!document.querySelector('.carousel-dots') && document.querySelector('.carousel-dots').offsetParent !== null]; }")
        await browser.close()
        if any(desk):
            problems.append(f"Su computer i capitoli non devono essere un carosello: {desk}")
    assert not problems, "\n".join(problems)


async def positions(page, ms):
    """Posizione del carosello campionata ogni 150 ms: con 3 schede, confrontare solo inizio e fine
    non basta (in un giro completo si torna alla stessa scheda)."""
    out = []
    for _ in range(max(1, ms // 150)):
        out.append(await page.evaluate("Math.round(document.querySelector('#chapters').scrollLeft)"))
        await page.wait_for_timeout(150)
    return out


async def test_phone_carousel_moves_by_itself_and_can_be_stopped(p):
    """Le schede scorrono da sole. Il pulsante pausa le ferma (e dice cosa fa), toccarle le ferma,
    e con "riduci movimento" attivo nel telefono non partono. (Nel test il giro dura 0,8 s.)"""
    problems = []
    fast = "window.__ksCarouselMs = 800;"
    with Site() as site:
        browser = await p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        for motion in ("no-preference", "reduce"):
            ctx = await browser.new_context(user_agent=UA["android"], locale="it-IT", viewport={"width": PHONE[0], "height": PHONE[1]},
                                            is_mobile=True, has_touch=True, reduced_motion=motion)
            await ctx.route("https://api.github.com/**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RELEASE_4)))
            await ctx.add_init_script(fast)
            page = await ctx.new_page()
            await page.goto(site.url)
            await page.locator("#chapters").scroll_into_view_if_needed()
            seen = await positions(page, 1900)
            moved = len(set(seen)) > 1
            if motion == "reduce":
                if moved:
                    problems.append(f"Con 'riduci movimento' le schede non devono muoversi da sole: {seen}")
                await ctx.close()
                continue
            if not moved:
                problems.append(f"Le schede devono scorrere da sole: sempre ferme a {seen[0]}")
            btn = page.locator("#carousel-pause")
            if not await btn.count():
                problems.append("Manca il pulsante pausa #carousel-pause")
                await ctx.close()
                continue
            label_on = await btn.get_attribute("aria-label")
            await btn.click()
            label_off = await btn.get_attribute("aria-label")
            if not label_on or label_on == label_off:
                problems.append(f"Il pulsante pausa deve dire cosa fa e cambiare scritta: {label_on!r} → {label_off!r}")
            await page.wait_for_timeout(600)          # finisce lo scorrimento eventualmente in corso
            seen = await positions(page, 1900)
            if len(set(seen)) > 1:
                problems.append(f"Dopo la pausa le schede devono restare ferme: {seen}")
            await btn.click()                                   # riprende
            await page.wait_for_timeout(200)
            await page.locator("#chapters h2").first.scroll_into_view_if_needed()   # si tocca una scheda che si vede
            box = await page.locator("#chapters").bounding_box()
            assert 0 <= box["y"] + 60 <= PHONE[1], f"Il punto toccato deve essere sullo schermo: {box}"
            await page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + 60)   # chi legge tocca una scheda
            await page.wait_for_timeout(600)          # finisce l'eventuale scorrimento già partito prima del tocco
            seen = await positions(page, 1900)
            if len(set(seen)) > 1:
                problems.append(f"Quando si tocca una scheda lo scorrimento automatico deve fermarsi: {seen}")
            await ctx.close()
        await browser.close()
    assert not problems, "\n".join(problems)


async def test_phone_download_index_uses_clear_buttons(p):
    """Telefono: nell'indice ogni riga ha un vero pulsante "Scarica" (non il nome del file). Quello
    del dispositivo di chi visita è pieno e colorato, gli altri solo bordati, come nella proposta A.
    Il nome del file resta per i lettori di schermo; la nota di installazione si vede solo per il
    proprio dispositivo. Su computer le scritte restano quelle lunghe (Scarica .exe)."""
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site, os_="android", viewport=PHONE)
        await page.locator("#downloads").scroll_into_view_if_needed()
        rows = await page.evaluate("""() => [...document.querySelectorAll('#downloads [data-os]')].map(row => {
            const a = row.querySelector('a.dl'), cs = getComputedStyle(a), hint = row.querySelector('.hint');
            const leader = row.querySelector('.leader');
            return { os: row.dataset.os, text: a.innerText.trim(), aria: a.getAttribute('aria-label') || '',
                     bg: cs.backgroundColor, border: parseFloat(cs.borderTopWidth), height: Math.round(a.getBoundingClientRect().height),
                     hint: !!(hint && hint.offsetParent), leader: !!(leader && leader.offsetParent) }; })""")
        accent = await page.evaluate("getComputedStyle(document.querySelector('#hero-download')).backgroundColor")
        short = await page.evaluate("window.KS_I18N.it.dl_btn_short")
        await shot(page, "phone_downloads")
        await browser.close()
        for r in rows:
            want = short if r["os"] != "ios" else None
            if want and r["text"] != want:
                problems.append(f"{r['os']}: il pulsante deve dire {want!r}, dice {r['text']!r}")
            if r["os"] != "ios" and not re.search(r"\.(exe|dmg|apk)|AppImage", r["aria"]):
                problems.append(f"{r['os']}: il nome del file deve restare per i lettori di schermo (aria-label {r['aria']!r})")
            if r["height"] < 44:
                problems.append(f"{r['os']}: pulsante troppo basso ({r['height']} px)")
            filled = r["bg"] == accent
            if r["os"] == "android" and not filled:
                problems.append(f"android (il tuo): il pulsante deve essere pieno come quello grande ({r['bg']} ≠ {accent})")
            if r["os"] != "android" and (filled or r["border"] < 1):
                problems.append(f"{r['os']}: gli altri pulsanti vanno solo bordati (sfondo {r['bg']}, bordo {r['border']})")
            if r["hint"] != (r["os"] == "android"):
                problems.append(f"{r['os']}: la nota si vede solo per il proprio dispositivo (visibile: {r['hint']})")
            if r["leader"]:
                problems.append(f"{r['os']}: sul telefono niente puntini di guida")
        browser, ctx, page = await open_site(p, site, os_="win")
        desk = await page.evaluate("document.querySelector('#downloads [data-os=\"win\"] a.dl').innerText.trim()")
        await browser.close()
        if desk != "Scarica .exe":
            problems.append(f"Su computer il pulsante resta 'Scarica .exe', dice {desk!r}")
    assert not problems, "\n".join(problems)


REVEAL_STATE = """() => [...document.querySelectorAll('[data-reveal]')].map(e => {
    const r = e.getBoundingClientRect();
    return { op: parseFloat(getComputedStyle(e).opacity), onScreen: r.top < innerHeight && r.bottom > 0,
             what: (e.className || e.tagName) + ':' + (e.innerText || '').trim().slice(0, 20) }; })"""


async def test_sections_animate_into_view(p):
    """Animazioni: all'apertura il frontespizio entra in sequenza; scorrendo, ogni sezione compare
    quando arriva sullo schermo (prima è nascosta, poi visibile). Vale per capitoli, fregio, indice
    dei download e piè di pagina."""
    problems = []
    with Site() as site:
        browser, ctx, page = await open_site(p, site, os_="win", viewport=(1280, 800))
        hero = await page.evaluate("[...document.querySelectorAll('.hero > *')].map(e => getComputedStyle(e).animationName)")
        if not hero or any(n in ("", "none") for n in hero):
            problems.append(f"Il frontespizio deve entrare con un'animazione (animationName: {hero})")
        await page.wait_for_timeout(1500)
        before = await page.evaluate(REVEAL_STATE)
        if len(before) < 12:
            problems.append(f"Troppo pochi elementi animati ({len(before)}): capitoli, fregio, download, piè di pagina")
        below = [e for e in before if not e["onScreen"]]
        shown_early = [e["what"] for e in below if e["op"] > 0.05]
        if not below or shown_early:
            problems.append(f"Gli elementi fuori schermo devono aspettare di essere visti: già visibili {shown_early[:4]}")
        for y in range(0, 6000, 400):                       # si scorre come una persona
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(120)
        await page.wait_for_timeout(1200)
        after = await page.evaluate(REVEAL_STATE)
        hidden = [e["what"] for e in after if e["op"] < 0.99]
        if hidden:
            problems.append(f"Dopo aver scorso tutta la pagina devono essere tutti visibili: {hidden[:5]}")
        await browser.close()
    assert not problems, "\n".join(problems)


async def test_animations_respect_reduced_motion_and_never_hide_content(p):
    """Con "riduci movimento" nessuna animazione e tutto subito visibile. Senza JavaScript (o se lo
    script non parte) niente resta nascosto: si nasconde solo ciò che lo script è pronto ad animare."""
    problems = []
    with Site() as site:
        browser = await p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        for label, opts in (("riduci movimento", {"reduced_motion": "reduce"}), ("senza JavaScript", {"java_script_enabled": False})):
            ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="it-IT", **opts)
            await ctx.route("https://api.github.com/**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RELEASE_4)))
            page = await ctx.new_page()
            await page.goto(site.url)
            await page.wait_for_timeout(400)
            state = await page.evaluate(REVEAL_STATE)
            moving = await page.evaluate("""() => [...document.querySelectorAll('.hero > *, [data-reveal]')]
                .filter(e => { const cs = getComputedStyle(e); return (cs.animationName !== 'none' && parseFloat(cs.animationDuration) > 0)
                    || parseFloat(cs.transitionDuration) > 0; }).length""")
            hidden = [e["what"] for e in state if e["op"] < 0.99]
            if not state:
                problems.append(f"{label}: nessun elemento marcato data-reveal")
            if hidden:
                problems.append(f"{label}: contenuto nascosto senza motivo: {hidden[:5]}")
            if label == "riduci movimento" and moving:
                problems.append(f"{label}: {moving} elementi si muovono ancora")
            await ctx.close()
        await browser.close()
    assert not problems, "\n".join(problems)


def test_workflow_tests_then_publishes_only_the_site():
    """Il workflow pubblica su GitHub Pages solo dopo che questi test sono passati, solo dal ramo
    main e solo la cartella site/ (i test non finiscono online). Il download di Chromium ritenta
    da solo se i server rispondono con un errore temporaneo (5xx)."""
    wf_path = ROOT / ".github" / "workflows" / "pages.yml"
    assert wf_path.exists(), "Manca .github/workflows/pages.yml"
    wf = wf_path.read_text()
    problems = []
    checks = {
        "esegue i test": "python tests/test_site.py" in wf,
        "pubblica dopo i test (needs: test)": re.search(r"deploy:[\s\S]*needs:\s*test", wf) is not None,
        "pubblica solo da main": "refs/heads/main" in wf,
        "carica solo la cartella site/": re.search(r"upload-pages-artifact@v\d+[\s\S]*?path:\s*site\b", wf) is not None,
        "usa deploy-pages": "actions/deploy-pages@" in wf,
        "permessi di Pages solo dove servono": re.search(r"deploy:[\s\S]*pages:\s*write", wf) is not None
                                                and re.search(r"^permissions:\s*\n\s*contents:\s*read", wf, re.M) is not None,
        "ritenta l'installazione di Chromium": re.search(r"for i in [\d ]+;[\s\S]*playwright install[\s\S]*sleep", wf) is not None,
    }
    problems = [name for name, ok in checks.items() if not ok]
    assert not problems, "Workflow: " + "; ".join(problems)


async def main():
    only = [x for x in os.environ.get("ONLY", "").split(",") if x]
    tests = [v for k, v in globals().items() if k.startswith("test_") and (not only or any(o in k for o in only))]
    failed = 0
    async with async_playwright() as p:
        for test in tests:
            start = time.time()
            try:
                result = test(p) if test.__code__.co_argcount else test()
                if asyncio.iscoroutine(result):
                    await result
                print(f"PASS  {test.__name__} ({time.time() - start:.1f}s)")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {test.__name__}: {e}")
            except Exception as e:
                failed += 1
                print(f"ERROR {test.__name__}: {e!r}")
                traceback.print_exc(limit=2)
    print(f"\n{len(tests) - failed}/{len(tests)} test superati")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
