const CACHE_NAME = 'tahmasebi-pwa-v1';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// استراتژی شبکه-اول (Network-First) برای داده‌های زنده مالی و صفحات سیستم
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // فایل‌های استاتیک و آیکون‌ها: Cache First
  if (url.pathname.startsWith('/static/') || url.hostname.includes('cdn')) {
    event.respondWith(
      caches.match(req).then(cached => {
        return cached || fetch(req).then(res => {
          if (res.status === 200) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then(c => c.put(req, clone));
          }
          return res;
        });
      })
    );
    return;
  }

  // سایر صفحات (اطلاعات فاکتورها، حسابداری و فرم‌ها): Network First
  event.respondWith(
    fetch(req)
      .then(res => {
        return res;
      })
      .catch(() => {
        return caches.match(req).then(cached => {
          return cached || caches.match('/');
        });
      })
  );
});
