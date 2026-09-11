/* Service worker for the badge scanner.
 *
 * Its only job is to make the scanner page itself open with no network - a worker at a gate
 * with no signal must still be able to capture a badge photograph, because the capture is the
 * part that cannot be repeated later. The reading is queued in IndexedDB by the page and sent
 * when signal returns.
 *
 * What it deliberately does NOT do:
 *   - cache /scan or anything under /api. A cached exposure reading is a wrong exposure
 *     reading, and serving a stale one would be worse than serving none.
 *   - cache the dashboard. That page is useless without live data.
 */
const CACHE = 'h2s-scanner-v1';
const SHELL = ['/', '/webapp/index.html', '/manifest.webmanifest', '/webapp/icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      // addAll rejects the whole install if any one request fails, which would leave the
      // scanner with no offline shell at all; individual puts degrade instead.
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;                       // /scan posts: never touched
  if (url.origin !== self.location.origin) return;
  if (url.pathname === '/scan' || url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/dashboard')) return;

  // Network first, cache as fallback: during a shift the page should pick up a deployed fix,
  // and a stale scanner UI is the most confusing failure mode there is.
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(e.request).then(hit => hit || caches.match('/')))
  );
});
