# koreshelf.github.io

Il sito di [KoreShelf](https://github.com/GabrieleTrovato01/KoreShelf): da qui le persone scaricano l'app.

- **Un'unica pagina** (`site/`), senza framework né strumenti di build: HTML, CSS e un po' di JavaScript.
- **5 lingue** (it, en, de, fr, es), scelte dal browser e cambiabili dal menu.
- **Tema chiaro e scuro**: segue il dispositivo, si cambia con il pulsante sole/luna, la scelta viene ricordata.
- **Download sempre aggiornati**: i pulsanti chiedono a GitHub qual è l'ultima release e puntano ai suoi file.
  Se GitHub non risponde portano alla pagina delle release, quindi non si rompono mai.
- **Il dispositivo di chi visita** viene riconosciuto: il pulsante grande propone il file giusto.
- **Animazioni leggere**: il frontespizio entra in sequenza e le sezioni compaiono scorrendo. Niente
  movimento con "riduci movimento" attivo; senza JavaScript tutto resta visibile.
- **Telefono**: intestazione compatta, capitoli in schede da sfogliare (scorrono da sole, con pausa)
  e pulsanti "Scarica" chiari, con quello del proprio dispositivo in evidenza.
- **Privacy**: nessun servizio esterno (niente Google Fonts, statistiche o CDN). L'unica richiesta
  fuori dal sito è quella a GitHub per conoscere l'ultima versione.

## Struttura

```
site/                 Quello che viene pubblicato
  index.html          La pagina (testi di riserva in inglese)
  assets/i18n.js      Tutti i testi nelle 5 lingue
  assets/site.js      Lingua, tema, dispositivo, link all'ultima release
  assets/style.css    Stile (tema chiaro: carta e inchiostro; scuro: i colori dell'app)
  assets/fonts/       Literata, servito dal sito stesso (licenza SIL OFL 1.1, vedi OFL.txt)
  assets/img/         Logo, icone e schermate dell'app
tests/test_site.py    Test end-to-end (Playwright)
.github/workflows/pages.yml   Test e pubblicazione su GitHub Pages
```

## Test

```
pip install playwright
python -m playwright install chromium
python tests/test_site.py
```

Con `ONLY=tema,lingua` lancia solo alcuni test; con `KEEP_SHOTS=1` salva gli screenshot.

## Pubblicazione

Ogni push su `main` esegue i test e, se passano, pubblica la cartella `site/` su
https://koreshelf.github.io (Settings → Pages → Source: GitHub Actions).

## Aggiungere un testo o una lingua

Ogni testo ha una chiave (`data-i18n="chiave"` nella pagina) e un valore per ogni lingua in
`assets/i18n.js`. Il test `test_every_language_has_every_text` controlla che non manchi niente.

## Licenza

MIT, © GabrieleTrovato01. Il carattere Literata è distribuito con licenza SIL Open Font License 1.1.
