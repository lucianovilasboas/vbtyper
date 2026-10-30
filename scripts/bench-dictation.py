"""Mede o tempo de um ditado ponta a ponta pela API, fase por fase.

Não é teste automatizado: gasta centavos (cada execução é um job de verdade) e
serve para comparar mudanças de latência com números, não com impressão. O
cliente desktop faz o mesmo caminho — áudio, job, consulta — então o que aparece
aqui é o tempo até o texto ficar pronto; a inserção no cursor é medida pelo
``insert_ms`` do histórico.

Uso (com o áudio de um ditado real, para valer também a segunda chamada):

    cd backend
    uv run python ../scripts/bench-dictation.py --file /caminho/ditado.wav

Sem ``--file`` ele gera um tom de ``--seconds`` segundos: serve para medir envio,
fila e reconhecimento, mas o job provavelmente termina em "não reconheceu fala"
— e aí não há segunda chamada do perfil.

A URL vem de ``desktop.json`` (a mesma do cliente) e o token de
``~/.config/vb-typer/api-token``; nem a URL nem o token são impressos.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import struct
import sys
import time
import wave
from pathlib import Path

import httpx

DEFAULT_URL = "http://127.0.0.1:8765"
POLL_S = 0.05
TIMEOUT_S = 180.0


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "vb-typer"


def base_url(cli_value: str | None) -> str:
    """Mesma precedência do cliente: flag > ambiente > desktop.json > local."""
    if cli_value:
        return cli_value.rstrip("/")
    env_value = os.environ.get("VB_TYPER_API_BASE_URL", "").strip()
    if env_value:
        return env_value.rstrip("/")
    try:
        stored = json.loads((config_dir() / "desktop.json").read_text(encoding="utf-8"))
        value = str(stored.get("base_url") or "").strip()
    except (OSError, ValueError):
        value = ""
    return (value or DEFAULT_URL).rstrip("/")


def api_token() -> str:
    env_value = os.environ.get("VB_TYPER_API_TOKEN", "").strip()
    if env_value:
        return env_value
    try:
        return (config_dir() / "api-token").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def tone_wav(path: Path, seconds: float) -> Path:
    """WAV de um tom suave: fala de verdade é melhor, mas isto mede o caminho."""
    frames = bytearray()
    for index in range(int(16000 * seconds)):
        sample = int(6000 * math.sin(2 * math.pi * 220 * index / 16000))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as handle:
        handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        handle.writeframes(bytes(frames))
    return path


def run_once(client: httpx.Client, audio: Path, options: dict) -> dict:
    data = audio.read_bytes()
    started = time.monotonic()
    response = client.post(
        "/api/v1/transcription-jobs",
        files={"file": (audio.name, data, "audio/wav")},
        data=options,
    )
    response.raise_for_status()
    job = response.json()
    uploaded = time.monotonic() - started

    seen: list[tuple[str, float]] = []
    deadline = time.monotonic() + TIMEOUT_S
    while True:
        current = job.get("phase") or job.get("status") or ""
        if not seen or seen[-1][0] != current:
            seen.append((current, time.monotonic() - started))
        if job.get("status") in {"succeeded", "failed", "canceled"}:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("tempo limite excedido")
        time.sleep(POLL_S)
        job = client.get(f"/api/v1/transcription-jobs/{job['id']}").json()

    return {
        "upload_s": uploaded,
        "phases": seen,
        "total_s": time.monotonic() - started,
        "status": job.get("status"),
        "error": job.get("error"),
        "text": (job.get("result") or {}).get("text") or "",
        "bytes": len(data),
        "transcription_id": job.get("transcription_id"),
    }


def phase_ms(result: dict) -> dict[str, float]:
    """Quanto durou cada fase, pelo que o servidor publicou no job."""
    marks = result["phases"]
    timeline: dict[str, float] = {}
    for index, (name, at) in enumerate(marks):
        following = marks[index + 1][1] if index + 1 < len(marks) else result["total_s"]
        timeline[name or "?"] = max(0.0, (following - at) * 1000)
    return timeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Mede a latência de um ditado pela API.")
    parser.add_argument("--file", type=Path, help="WAV de um ditado real (melhor medição).")
    parser.add_argument("--seconds", type=float, default=4.0, help="duração do tom sintético.")
    parser.add_argument("--base-url", help="sobrepõe a URL do cliente.")
    parser.add_argument("--model", default="", help="modelo pedido no job (vazio = servidor).")
    parser.add_argument("--profile", default="", help="perfil do job (vazio = padrão).")
    parser.add_argument("--language", default="pt")
    parser.add_argument("--runs", type=int, default=1, help="quantas vezes medir.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="apaga as transcrições criadas (o job fica no banco, invisível no histórico).",
    )
    args = parser.parse_args()

    token = api_token()
    if not token:
        print("Token não encontrado: configure a conexão no cliente.", file=sys.stderr)
        return 2

    audio = args.file or tone_wav(Path("/tmp/opencode/bench-ditado.wav"), args.seconds)
    if not audio.is_file():
        print(f"Áudio não encontrado: {audio}", file=sys.stderr)
        return 2

    options = {"language": args.language}
    if args.model:
        options["model"] = args.model
    if args.profile:
        options["profile"] = args.profile

    results = []
    with httpx.Client(
        base_url=base_url(args.base_url),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    ) as client:
        for run in range(max(1, args.runs)):
            result = run_once(client, audio, options)
            results.append(result)
            timeline = " · ".join(
                f"{name} {milliseconds:.0f} ms" for name, milliseconds in phase_ms(result).items()
            )
            print(
                f"[{run + 1}] {result['status']} em {result['total_s'] * 1000:.0f} ms "
                f"({result['bytes'] / 1024:.0f} KB) — envio {result['upload_s'] * 1000:.0f} ms"
            )
            print(f"     fases: {timeline}")
            if result["text"]:
                print(f"     texto: {result['text'][:80]}")
            if result["error"]:
                print(f"     erro: {result['error']}")
            if args.cleanup and result["transcription_id"] is not None:
                client.delete(f"/api/v1/transcriptions/{result['transcription_id']}")
                print("     histórico limpo (transcrição apagada)")

    if len(results) > 1:
        totals = [item["total_s"] * 1000 for item in results]
        print(
            f"mediana {statistics.median(totals):.0f} ms · "
            f"mínimo {min(totals):.0f} ms · máximo {max(totals):.0f} ms"
        )
    return 0 if all(item["status"] == "succeeded" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
