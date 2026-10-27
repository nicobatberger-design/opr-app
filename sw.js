/* Service worker OPR Chantier — l'appli fonctionne sans réseau (chantier, sous-sol).
   Page : réseau d'abord (mises à jour automatiques), copie locale si pas de réseau.
   Le reste (icônes, lecteur PDF) : copie locale d'abord. */
const CACHE = 'opr-chantier-v3.0';
const CORE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon.svg',
  './icons/favicon.ico',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/maskable-512.png',
  './icons/apple-touch-icon.png'
];
const LIB = ['./lib/pdf.min.js', './lib/pdf.worker.min.js'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(CORE).then(() => c.addAll(LIB).catch(() => {})))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function pageReseauDabord(req) {
  return new Promise(resolve => {
    let fini = false;
    const copieLocale = () => caches.match('./index.html');
    const minuteur = setTimeout(() => {
      copieLocale().then(r => { if (r && !fini) { fini = true; resolve(r); } });
    }, 3500);
    fetch(req).then(res => {
      if (res && res.ok) {
        const copie = res.clone();
        caches.open(CACHE).then(c => c.put('./index.html', copie)).catch(() => {});
      }
      if (!fini) { fini = true; clearTimeout(minuteur); resolve(res); }
    }).catch(() => {
      copieLocale().then(r => { if (!fini) { fini = true; clearTimeout(minuteur); resolve(r || Response.error()); } });
    });
  });
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (req.mode === 'navigate') { e.respondWith(pageReseauDabord(req)); return; }
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then(hit => hit || fetch(req).then(res => {
      if (res && res.ok) { const copie = res.clone(); caches.open(CACHE).then(c => c.put(req, copie)).catch(() => {}); }
      return res;
    }))
  );
});
