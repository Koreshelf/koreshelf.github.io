// KoreShelf — sito: lingua, tema, dispositivo di chi visita e link all'ultima release.
(function () {
  'use strict';

  var REPO = 'https://github.com/GabrieleTrovato01/KoreShelf';
  var RELEASES = REPO + '/releases/latest';
  var API = 'https://api.github.com/repos/GabrieleTrovato01/KoreShelf/releases/latest';
  var LANGS = ['it', 'en', 'de', 'fr', 'es'];
  // Nomi dei file prodotti dal workflow delle release dell'app
  var FILES = { win: /windows.*\.exe$/i, mac: /\.dmg$/i, linux: /\.appimage$/i, android: /\.apk$/i, ios: /\.ipa$/i };

  var store = {
    get: function (k, s) { try { return (s || localStorage).getItem(k); } catch (e) { return null; } },
    set: function (k, v, s) { try { (s || localStorage).setItem(k, v); } catch (e) { /* modalità privata */ } }
  };
  var $ = function (sel) { return document.querySelector(sel); };
  var $$ = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); };

  // --- Dispositivo ----------------------------------------------------------
  function detectOS() {
    var ua = navigator.userAgent || '';
    var platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
    if (/iPhone|iPad|iPod/.test(ua) || (/Mac/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios';   // iPadOS si presenta come Mac
    if (/Android/i.test(ua)) return 'android';
    if (/Windows/.test(ua) || /^Win/.test(platform)) return 'win';
    if (/Macintosh/.test(ua)) return 'mac';
    if (/CrOS/.test(ua)) return null;                    // Chromebook: si sceglie dall'indice
    if (/Linux|X11/.test(ua)) return 'linux';
    return null;
  }

  // --- Lingua ---------------------------------------------------------------
  function pickLang() {
    var saved = store.get('ks-lang');
    if (LANGS.indexOf(saved) >= 0) return saved;
    var wanted = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || 'en'];
    for (var i = 0; i < wanted.length; i++) {
      var base = String(wanted[i]).slice(0, 2).toLowerCase();
      if (LANGS.indexOf(base) >= 0) return base;
    }
    return 'en';
  }

  var lang = 'en';
  function t(key, vars) {
    var dict = window.KS_I18N || {};
    var s = (dict[lang] && dict[lang][key]) || (dict.en && dict.en[key]) || '';
    if (vars) Object.keys(vars).forEach(function (k) { s = s.split('{' + k + '}').join(vars[k]); });
    return s;
  }

  // --- Tema -----------------------------------------------------------------
  var media = window.matchMedia ? matchMedia('(prefers-color-scheme: dark)') : null;
  function currentTheme() { return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }
  function setTheme(theme, remember) {
    document.documentElement.setAttribute('data-theme', theme);
    if (remember) store.set('ks-theme', theme);
    var btn = $('#theme-toggle');
    if (btn) btn.setAttribute('aria-label', t(theme === 'dark' ? 'theme_light' : 'theme_dark'));
  }

  // --- Ultima release ---------------------------------------------------------
  // GitHub senza account concede 60 richieste all'ora per indirizzo: una sola per visita.
  function loadRelease() {
    var cached = store.get('ks-release', window.sessionStorage);
    if (cached) {
      try { return Promise.resolve(JSON.parse(cached)); } catch (e) { /* si richiede di nuovo */ }
    }
    return fetch(API, { headers: { Accept: 'application/vnd.github+json' } })
      .then(function (res) { if (!res.ok) throw new Error('GitHub ' + res.status); return res.json(); })
      .then(function (json) {
        var info = { version: String(json.tag_name || '').replace(/^v/, ''), files: {} };
        (json.assets || []).forEach(function (asset) {
          Object.keys(FILES).forEach(function (os) {
            if (!info.files[os] && FILES[os].test(asset.name || '')) info.files[os] = asset.browser_download_url;
          });
        });
        store.set('ks-release', JSON.stringify(info), window.sessionStorage);
        return info;
      })
      .catch(function () { return null; });            // i link restano sulla pagina delle release
  }


  // --- Telefono: sigla della lingua e carosello dei capitoli -------------------------
  var phone = window.matchMedia ? matchMedia('(max-width: 640px)') : { matches: false };
  var reduceMotion = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  var langNames = {};

  function langLabels() {          // sul telefono la sigla (IT), su computer il nome (Italiano)
    var select = $('#lang');
    if (!select) return;
    Array.prototype.forEach.call(select.options, function (o) {
      if (!langNames[o.value]) langNames[o.value] = o.text;
      o.text = phone.matches ? o.value.toUpperCase() : langNames[o.value];
    });
  }

  var carousel = { paused: false, quietUntil: 0, visible: true };

  function carouselCards() { var c = $('#chapters'); return c ? Array.prototype.slice.call(c.children).filter(function (e) { return e.tagName === 'ARTICLE'; }) : []; }
  function carouselIndex() {
    var track = $('#chapters'), cards = carouselCards(), mid = track.scrollLeft + track.clientWidth / 2, best = 0, dist = Infinity;
    cards.forEach(function (card, i) {
      var d = Math.abs(card.offsetLeft + card.offsetWidth / 2 - mid);
      if (d < dist) { dist = d; best = i; }
    });
    return best;
  }
  function carouselGo(i) {
    var track = $('#chapters'), card = carouselCards()[i];
    if (!card) return;
    track.scrollTo({ left: card.offsetLeft - (track.clientWidth - card.offsetWidth) / 2, behavior: reduceMotion.matches ? 'auto' : 'smooth' });
  }
  function carouselDots() {
    var active = carouselIndex();
    $$('.carousel-dots button').forEach(function (b, i) {
      if (i === active) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
  }
  function carouselLabels() {
    var btn = $('#carousel-pause');
    if (!btn) return;
    btn.setAttribute('aria-label', t(carousel.paused ? 'carousel_play' : 'carousel_pause'));
    btn.classList.toggle('paused', carousel.paused);
  }
  function carouselQuiet() { carousel.quietUntil = Date.now() + 15000; }   // chi tocca le schede le sta leggendo

  function setupCarousel() {
    var track = $('#chapters');
    if (!track || !carouselCards().length) return;
    var ticking = false;
    track.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; carouselDots(); });
    }, { passive: true });
    ['pointerdown', 'touchstart', 'wheel', 'keydown', 'focusin'].forEach(function (ev) {
      track.addEventListener(ev, carouselQuiet, { passive: true });
    });
    $$('.carousel-dots button').forEach(function (b, i) {
      b.addEventListener('click', function () { carouselQuiet(); carouselGo(i); });
    });
    var btn = $('#carousel-pause');
    if (btn) btn.addEventListener('click', function () { carousel.paused = !carousel.paused; carouselLabels(); });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) { carousel.visible = entries[0].isIntersecting; }, { threshold: 0.4 }).observe(track);
    }
    setInterval(function () {
      if (!phone.matches || reduceMotion.matches || carousel.paused || !carousel.visible || document.hidden) return;
      if (Date.now() < carousel.quietUntil) return;
      carouselGo((carouselIndex() + 1) % carouselCards().length);
    }, window.__ksCarouselMs || 5000);
  }

  // --- Disegno della pagina -----------------------------------------------------
  var os = detectOS();
  var release = null;

  function render() {
    document.documentElement.lang = lang;
    $$('[data-i18n]').forEach(function (el) {
      var s = t(el.getAttribute('data-i18n'));
      if (s) el.textContent = s;
    });
    $$('[data-i18n-attr]').forEach(function (el) {
      el.getAttribute('data-i18n-attr').split(',').forEach(function (pair) {
        var parts = pair.split(':');
        var s = t(parts[1]);
        if (s) el.setAttribute(parts[0], s);
      });
    });
    document.title = t('meta_title');
    var desc = $('meta[name="description"]');
    if (desc) desc.setAttribute('content', t('meta_description'));
    var select = $('#lang');
    if (select) select.value = lang;
    langLabels();
    carouselLabels();
    setTheme(currentTheme(), false);

    var files = (release && release.files) || {};
    var hasApp = Object.keys(files).length > 0;
    $('#version').textContent = hasApp && release.version ? t('version', { v: release.version }) : '';

    $$('#downloads [data-os]').forEach(function (row) {
      var rowOs = row.getAttribute('data-os');
      if (rowOs === os) row.setAttribute('aria-current', 'true'); else row.removeAttribute('aria-current');
      var a = row.querySelector('a.dl');
      if (a && rowOs !== 'ios') a.href = files[rowOs] || RELEASES;
    });
    var ipa = $('#ios a.dl-ipa');
    if (ipa) ipa.href = files.ios || RELEASES;

    var hero = $('#hero-download');
    var label = $('#hero-label');
    if (os === 'ios') {
      hero.href = '#ios';
      label.textContent = t('hero_btn_ios');
    } else if (os) {
      hero.href = files[os] || RELEASES;
      label.textContent = t('hero_btn', { os: t('os_' + os) });
    } else {
      hero.href = '#downloads';
      label.textContent = t('hero_btn_generic');
    }
  }

  function start() {
    lang = pickLang();
    render();

    var select = $('#lang');
    if (select) select.addEventListener('change', function () {
      if (LANGS.indexOf(select.value) < 0) return;
      lang = select.value;
      store.set('ks-lang', lang);
      render();
    });
    var toggle = $('#theme-toggle');
    if (toggle) toggle.addEventListener('click', function () {
      setTheme(currentTheme() === 'dark' ? 'light' : 'dark', true);
    });
    // Senza una scelta salvata, il tema segue il dispositivo anche mentre la pagina è aperta
    if (media && media.addEventListener) media.addEventListener('change', function (e) {
      if (!store.get('ks-theme')) setTheme(e.matches ? 'dark' : 'light', false);
    });

    setupCarousel();
    if (phone.addEventListener) phone.addEventListener('change', langLabels);

    loadRelease().then(function (info) { release = info; render(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
