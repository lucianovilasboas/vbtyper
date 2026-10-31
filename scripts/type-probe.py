"""Mede se a inserção no cursor entrega o texto na ordem certa.

Abre uma janela GTK descartável, digita a mesma frase com vários ritmos de
inserção (teclas por lote e pausa por tecla) e compara **esperado × recebido**.
É o teste que separa "o método de entrada não acompanhou" de "o texto chegou
errado": com IBus, um lote rápido faz o commit de uma tecla chegar depois da
seguinte e o texto sai trocado ("está" → "esát").

Não é teste automatizado: precisa de sessão X real, rouba o foco por alguns
segundos e não roda na suíte. Uso:

    cd desktop
    uv run python ../scripts/type-probe.py            # todos os ritmos
    uv run python ../scripts/type-probe.py --batch 16 --delay 0

Sai com código 1 quando algum ritmo embaralha o texto. O ritmo que passa aqui é
o que pode ir para ``typing_batch``/``typing_delay_ms`` no ``desktop.json``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from vb_typer_desktop.platform.linux_x11 import _toplevel, type_text

HERE = Path(__file__).resolve().parent
WINDOW_SCRIPT = HERE / "type-probe-window.py"
SYSTEM_PYTHON = "/usr/bin/python3"
# Frase com os caracteres que o layout br não produz direto (á, ã, ç, é): são
# eles que passam pelo método de entrada e denunciam a rajada.
PHRASE = "Está aprovada a atualização do sistema. Ação, coração e páginas."
WINDOW_SECONDS = 4.0
STARTUP_TIMEOUT_S = 8.0
COMBOS = ((1, 4), (1, 0), (4, 2), (16, 0))


def first_difference(expected: str, received: str) -> str:
    for index, (want, got) in enumerate(zip(expected, received, strict=False)):
        if want != got:
            start = max(0, index - 12)
            return (
                f"posição {index}: esperado {want!r}, veio {got!r}\n"
                f"    esperado: …{expected[start : index + 12]}…\n"
                f"    recebido: …{received[start : index + 12]}…"
            )
    if len(received) != len(expected):
        return f"tamanho diferente: esperado {len(expected)}, recebido {len(received)}"
    return ""


def focus_toplevel(toplevel_id: int) -> None:
    """Dá o foco de entrada à janela do teste sem depender do gerenciador.

    ``present()`` nem sempre é honrado na hora (o gerenciador pode negar foco a
    uma janela que acabou de aparecer); o teste não pode depender disso, então o
    foco é posto explicitamente. A janela é descartável e morre em seguida.
    """
    from Xlib import X, display

    connection = display.Display()
    try:
        window = connection.create_resource_object("window", toplevel_id)
        connection.set_input_focus(window, X.RevertToParent, X.CurrentTime)
        connection.sync()
    except Exception:
        pass
    finally:
        connection.close()


def focused_within(toplevel_id: int) -> int | None:
    """Id do foco atual se ele estiver dentro da janela informada.

    O cliente digita no que estiver em foco (pode ser a janela filha do widget);
    o alvo é justamente esse id, e a janela de teste é conferida pelo topo.
    """
    from Xlib import display

    connection = display.Display()
    try:
        focus = connection.get_input_focus().focus
        focus_id = getattr(focus, "id", None)
        if focus_id is None:
            return None
        if focus_id == toplevel_id:
            return focus_id
        return focus_id if _toplevel(connection, focus).id == toplevel_id else None
    except Exception:
        return None
    finally:
        connection.close()


def run_combo(text: str, batch: int, delay_ms: int) -> tuple[bool, str, float]:
    """Digita numa janela nova e devolve (passou, detalhe, ms por caractere)."""
    with tempfile.TemporaryDirectory(prefix="vb-typer-probe-") as tmp:
        dump = Path(tmp) / "recebido.txt"
        xid_file = Path(tmp) / "xid.txt"
        process = subprocess.Popen(
            [SYSTEM_PYTHON, str(WINDOW_SCRIPT), str(dump), str(xid_file), str(WINDOW_SECONDS)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_S
            toplevel = 0
            while time.monotonic() < deadline:
                if xid_file.exists() and xid_file.read_text(encoding="utf-8").strip():
                    toplevel = int(xid_file.read_text(encoding="utf-8").strip())
                    break
                if process.poll() is not None:
                    detail = (process.stderr.read() or b"").decode("utf-8", "replace")
                    return False, f"a janela de teste não abriu: {detail.strip()}", 0.0
                time.sleep(0.05)
            else:
                return False, "a janela de teste não apareceu a tempo", 0.0

            # O gerenciador de janelas precisa dar o foco depois de mapear.
            focus_toplevel(toplevel)
            target = None
            focus_deadline = time.monotonic() + 3.0
            while time.monotonic() < focus_deadline:
                target = focused_within(toplevel)
                if target is not None:
                    break
                focus_toplevel(toplevel)
                time.sleep(0.05)
            if target is None:
                return (
                    False,
                    ("a janela de teste não recebeu o foco; feche outras janelas e rode de novo"),
                    0.0,
                )
            started = time.monotonic()
            type_text(text, target, key_delay=delay_ms / 1000, batch=batch)
            elapsed = (time.monotonic() - started) * 1000
            process.wait(timeout=WINDOW_SECONDS + 5)
        except Exception as exc:  # a falha vira linha do relatório, não stack trace
            return False, f"{type(exc).__name__}: {exc}", 0.0
        finally:
            if process.poll() is None:
                process.kill()
            if process.stderr is not None:
                process.stderr.close()

        received = dump.read_text(encoding="utf-8") if dump.exists() else ""
        detail = first_difference(text, received)
        return (detail == ""), detail, elapsed / max(1, len(text))


def type_into_focus(
    text: str, batch: int, delay_ms: int, countdown: int
) -> tuple[bool, str, float]:
    """Digita na janela que o usuário deixar em foco (sem ler de volta)."""
    from vb_typer_desktop.platform.linux_x11 import read_active_window

    for remaining in range(countdown, 0, -1):
        print(f"  foque o aplicativo… {remaining}", flush=True)
        time.sleep(1)
    target = read_active_window()
    if target is None:
        return False, "não há janela em foco", 0.0
    started = time.monotonic()
    type_text(text, target, key_delay=delay_ms / 1000, batch=batch)
    elapsed = (time.monotonic() - started) * 1000
    return (
        True,
        "confira o texto no aplicativo (este modo não lê de volta)",
        (elapsed / max(1, len(text))),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mede a inserção no cursor.")
    parser.add_argument("--batch", type=int, help="teclas por lote (padrão: varre 4 ritmos)")
    parser.add_argument("--delay", type=int, help="pausa por tecla em ms")
    parser.add_argument("--text", default=PHRASE, help="frase a digitar")
    parser.add_argument(
        "--in-focus",
        action="store_true",
        help="digitar na janela em foco (para testar o seu aplicativo de verdade)",
    )
    parser.add_argument(
        "--countdown", type=int, default=3, help="segundos para focar a janela (--in-focus)"
    )
    args = parser.parse_args()

    if not Path(SYSTEM_PYTHON).exists():
        print(
            f"Sem {SYSTEM_PYTHON}: o teste precisa do Python do sistema com GTK.",
            file=sys.stderr,
        )
        return 2
    if not os.environ.get("DISPLAY"):
        print("Sem DISPLAY: rode numa sessão gráfica X11.", file=sys.stderr)
        return 2

    if args.in_focus:
        if args.batch is None:
            parser.error("--in-focus exige --batch (e, se quiser, --delay)")
        passed, detail, rate = type_into_focus(
            args.text, args.batch, max(0, args.delay or 0), max(1, args.countdown)
        )
        print(f"lote {args.batch} · pausa {max(0, args.delay or 0)}ms · {rate:.2f} ms/char")
        print(detail)
        return 0 if passed else 1

    combos = ((args.batch, args.delay if args.delay is not None else 0),) if args.batch else COMBOS
    print(f"Frase: {args.text}")
    print(f"{'lote':>4} {'pausa':>6} {'ms/char':>8}  resultado")
    failures = 0
    for batch, delay in combos:
        passed, detail, rate = run_combo(args.text, batch, max(0, delay))
        status = "ok" if passed else "TEXTO TROCADO"
        print(f"{batch:>4} {delay:>5}ms {rate:>7.2f}  {status}")
        if not passed:
            failures += 1
            for line in detail.splitlines():
                print(f"      {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
