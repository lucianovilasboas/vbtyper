"""Checagem de layout responsivo do SPA contra uma instância real.

Sai com código 1 se alguma tela provocar rolagem horizontal. Serve para pegar
regressões do tipo "o select de 210px empurrou a página no celular".

    python3 web/tests/check_layout.py [--url http://127.0.0.1:8765] [--widths 320,360,390,768,1024]

Requer Playwright (o mesmo usado pelos testes da introdução):
    uv run --with playwright python3 web/tests/check_layout.py
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

VIEWS = ["dictate", "activity", "history", "settings"]

# Rolagem horizontal dentro de um contêiner próprio (.nav, .side) é intencional;
# o que não pode existir é a página inteira passar da largura da tela.
PROBE = """(() => {
  const root = document.documentElement;
  const vw = root.clientWidth;
  const inScroller = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === "auto" || ox === "scroll") return true;
    }
    return false;
  };
  const leaking = [];
  for (const el of document.querySelectorAll("body *")) {
    const box = el.getBoundingClientRect();
    if (!(box.width || box.height)) continue;
    if (box.right > vw + 1 && !inScroller(el)) {
      leaking.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ")[0]}`);
    }
  }
  return { vw, scroll: root.scrollWidth, leaking: leaking.slice(0, 5) };
})()"""


def check(url: str, widths: list[int]) -> int:
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in widths:
            context = browser.new_context(
                viewport={"width": width, "height": 844},
                is_mobile=width < 600,
                has_touch=True,
            )
            page = context.new_page()
            page.goto(url, wait_until="load")
            page.wait_for_timeout(1200)
            for view in VIEWS:
                page.click(f'button[data-view="{view}"]', timeout=8000)
                page.wait_for_timeout(400)
                result = page.evaluate(PROBE)
                ok = result["scroll"] <= result["vw"] and not result["leaking"]
                print(
                    f'{"OK  " if ok else "FALHA"} {width}px {view:9s} '
                    f'scroll={result["scroll"]}/{result["vw"]} {result["leaking"]}'
                )
                failures += 0 if ok else 1
            context.close()
        browser.close()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--widths", default="320,360,390,430,768,1024,1280")
    args = parser.parse_args()
    widths = [int(value) for value in args.widths.split(",") if value.strip()]
    failures = check(args.url, widths)
    print(f"\n{failures} falha(s)" if failures else "\nLayout sem rolagem horizontal.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
