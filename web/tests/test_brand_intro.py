"""Real Chromium checks; run with Python + playwright (no frontend build).

python -m unittest discover -s web/tests -v
Optional VB_INTRO_SCREENSHOTS=/absolute/path saves visual evidence.
The isolated server never touches the user's backend or data.
"""
import os
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from serve_preview import make_server


class BrandIntroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(service_workers='block')
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def test_intro_starts_without_backend_and_finishes(self):
        api_requests = []
        self.page.on('request', lambda r: api_requests.append(r.url)
                     if '/api/' in r.url else None)
        self.page.goto(self.url)
        self.page.locator('#brand-intro').wait_for(state='visible', timeout=1000)
        self.assertTrue(api_requests, 'API initialization must not wait for intro')
        self.page.locator('#brand-intro').wait_for(state='detached', timeout=2300)
        self.assertTrue(self.page.locator('#record').is_visible())

    def test_reduced_motion_skips_intro(self):
        self.page.emulate_media(reduced_motion='reduce')
        self.page.goto(self.url)
        self.assertEqual(self.page.locator('#brand-intro').count(), 0)
        self.assertTrue(self.page.locator('#record').is_visible())

    def test_fail_open_when_assets_or_javascript_are_unavailable(self):
        for asset in ('brand-intro.js', 'brand-intro.css', 'logo.png'):
            with self.subTest(asset=asset), self.browser.new_context() as context:
                page = context.new_page()
                page.route('**/static/' + asset, lambda route: route.abort())
                page.goto(self.url)
                page.locator('#brand-intro').wait_for(state='detached', timeout=2300)
                self.assertTrue(page.locator('#record').is_visible())
        with self.browser.new_context(java_script_enabled=False) as context:
            page = context.new_page()
            page.goto(self.url)
            self.assertEqual(page.locator('#brand-intro').count(), 0)
            self.assertTrue(page.locator('#record').is_visible())

    def test_css_hides_intro_even_if_javascript_cleanup_fails(self):
        self.page.add_init_script("""
            const original = window.setTimeout;
            window.setTimeout = (fn, ms, ...args) => ms === 1800
                ? 0 : original(fn, ms, ...args);
        """)
        self.page.goto(self.url)
        self.page.locator('#brand-intro').wait_for(state='visible')
        self.page.locator('#brand-intro').wait_for(state='hidden', timeout=2300)
        self.assertEqual(self.page.locator('#brand-intro').count(), 1)
        self.assertEqual(self.page.locator('#brand-intro').evaluate(
            '(el) => getComputedStyle(el).pointerEvents'), 'none')

    def test_hidden_document_skips_intro(self):
        self.page.add_init_script("Object.defineProperty(document, 'hidden', {get: () => true})")
        self.page.goto(self.url)
        self.assertEqual(self.page.locator('#brand-intro').count(), 0)

    def test_preference_change_dismisses_intro(self):
        self.page.goto(self.url)
        self.page.locator('#brand-intro').wait_for(state='visible')
        self.page.emulate_media(reduced_motion='reduce')
        self.page.locator('#brand-intro').wait_for(state='detached', timeout=1000)

    def test_visual_themes_and_mobile(self):
        errors = []
        self.page.on('pageerror', lambda error: errors.append(str(error)))
        for theme, width, height in (('light', 1280, 800), ('dark', 1280, 800),
                                     ('dark', 390, 844)):
            with self.subTest(theme=theme, width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.page.add_init_script(f"localStorage.setItem('vb-typer-theme', '{theme}')")
                self.page.goto(self.url)
                self.page.locator('#brand-intro').wait_for(state='visible')
                self.assertEqual(self.page.locator('html').get_attribute('data-theme'), theme)
                # Freeze real CSS animation frames for reproducible screenshots.
                self.page.locator('#brand-intro').evaluate('''el => {
                    for (const animation of el.getAnimations({subtree: true})) {
                        animation.pause(); animation.currentTime = 470;
                    }
                }''')
                self.assertTrue(self.page.locator('.brand-intro__mark img').evaluate(
                    '(img) => img.complete && img.naturalWidth > 0'))
                self.assertTrue(self.page.evaluate(
                    'document.documentElement.scrollWidth <= innerWidth'))
                if folder := os.environ.get('VB_INTRO_SCREENSHOTS'):
                    target = Path(folder)
                    target.mkdir(parents=True, exist_ok=True)
                    self.page.screenshot(path=str(target / f'intro-{theme}-{width}.png'))
                    self.page.locator('#brand-intro').evaluate('''el => {
                        for (const animation of el.getAnimations({subtree: true})) {
                            animation.currentTime = 1250;
                        }
                    }''')
                    self.page.screenshot(path=str(target / f'reveal-{theme}-{width}.png'))
                self.page.keyboard.press('Escape')
                if folder:
                    self.page.screenshot(path=str(Path(folder) / f'app-{theme}-{width}.png'))
        self.assertEqual(errors, [])

    def test_name_reveals_after_the_first_ripple_without_looping(self):
        self.page.goto(self.url)
        title = self.page.locator('.brand-intro__title')
        title.wait_for(state='visible')
        title.evaluate('''el => {
            for (const animation of el.getAnimations()) {
                animation.pause(); animation.currentTime = 100;
            }
        }''')
        self.assertEqual(title.evaluate('(el) => getComputedStyle(el).opacity'), '0')
        title.evaluate('''el => {
            for (const animation of el.getAnimations()) animation.currentTime = 1200;
        }''')
        self.assertEqual(title.evaluate('(el) => getComputedStyle(el).opacity'), '1')
        self.assertEqual(title.inner_text(), 'VB Typer')
        self.assertTrue(self.page.locator('#brand-intro').evaluate('''el =>
            el.getAnimations({subtree: true}).every(a => a.effect.getTiming().iterations === 1)
        '''))

    def test_ripple_anchors_lie_on_the_untouched_ribbon(self):
        """Decorative rings must stay on the real river mark, which stays unmodified."""
        self.page.goto(self.url)
        self.page.locator('#brand-intro').wait_for(state='visible')
        origins = self.page.locator('#brand-intro .brand-intro__ripple').evaluate_all(
            'els => els.map(el => el.style.transformOrigin)')
        anchors = [tuple(int(part.rstrip('px')) for part in value.split()) for value in origins]
        self.assertEqual(len(anchors), 3)
        on_ribbon = self.page.evaluate("""async anchors => {
            const img = new Image();
            img.src = '/static/logo.png';
            await img.decode();
            const N = 128, canvas = new OffscreenCanvas(N, N);
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, N, N);
            const {data} = ctx.getImageData(0, 0, N, N);
            return anchors.map(([x, y]) => data[(y * N + x) * 4 + 3] > 40);
        }""", [list(anchor) for anchor in anchors])
        self.assertEqual(on_ribbon, [True, True, True])
        self.assertEqual(self.page.locator('#brand-intro img').evaluate(
            '(img) => img.currentSrc.endsWith("/static/logo.png")'), True)

    def test_dismiss_does_not_consume_navigation_or_keyboard(self):
        for interaction in ('skip', 'escape', 'navigate', 'focus'):
            with self.subTest(interaction=interaction):
                self.page.goto(self.url)
                self.page.locator('#brand-intro').wait_for(state='visible')
                if interaction == 'skip':
                    self.page.get_by_role('button', name='Pular introdução').click()
                elif interaction == 'escape':
                    self.page.keyboard.press('Escape')
                elif interaction == 'focus':
                    self.page.locator('[data-view="settings"]').focus()
                    self.assertEqual(self.page.evaluate(
                        'document.activeElement.dataset.view'), 'settings')
                else:
                    self.page.get_by_role('button', name='Configurações', exact=True).click()
                    self.assertTrue(self.page.locator('#view-settings').is_visible())
                self.assertEqual(self.page.locator('#brand-intro').count(), 0)
                self.page.evaluate("window.dispatchEvent(new Event('focus'))")
                self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
                self.page.evaluate("import('/static/brand-intro.js').then(m => m.startBrandIntro())")
                self.assertEqual(self.page.locator('#brand-intro').count(), 0)

    def test_pwa_upgrade_caches_intro_and_keeps_unrelated_caches(self):
        with self.browser.new_context(service_workers='allow') as context:
            page = context.new_page()
            # Hold automatic registration until old caches have been seeded.
            page.route('**/static/app.js', lambda route: route.abort())
            page.goto(self.url)
            page.evaluate("""async () => {
                await caches.open('vb-typer-v1');
                await caches.open('another-app');
                await navigator.serviceWorker.register('/sw.js');
                await navigator.serviceWorker.ready;
            }""")
            page.wait_for_function('navigator.serviceWorker.controller !== null')
            keys = page.evaluate('caches.keys()')
            self.assertNotIn('vb-typer-v1', keys)
            self.assertIn('another-app', keys)
            for asset in ('brand-intro.js', 'brand-intro.css', 'icon-maskable-512.png'):
                self.assertTrue(page.evaluate(
                    "async asset => Boolean(await caches.match('/static/' + asset))", asset))
            context.set_offline(True)
            page.reload()
            page.locator('#brand-intro').wait_for(state='visible', timeout=1000)
            page.locator('#brand-intro').wait_for(state='detached', timeout=2300)
            self.assertTrue(page.locator('.brand img').evaluate('(img) => img.naturalWidth > 0'))


if __name__ == '__main__':
    unittest.main()
