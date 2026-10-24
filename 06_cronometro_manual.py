"""Cronometro do procedimento MANUAL (experimento D1).

Uso: python 06_cronometro_manual.py <repeticao> <cliente>
Ex.: python 06_cronometro_manual.py 1 101

Fluxo: ENTER inicia -> faca a configuracao manual nos consoles dos roteadores
-> ENTER para -> informe erros e se a configuracao ficou correta.
Grava em logs/manual.csv (sem data/hora de execucao).
"""
import csv
import sys
import threading
import time

from common import BASE

ARQ = BASE / "logs" / "manual.csv"
CABECALHO = ["repeticao", "cliente", "duracao_s", "erros_digitacao", "config_correta"]


def mostrar_tempo(inicio, parar):
    while not parar.is_set():
        s = int(time.perf_counter() - inicio)
        print(f"\r  Tempo decorrido: {s // 60:02d}:{s % 60:02d}  (ENTER para parar) ", end="", flush=True)
        parar.wait(1)


def main():
    if len(sys.argv) != 3 or not sys.argv[1].isdigit() or not sys.argv[2].isdigit():
        sys.exit("Uso: python 06_cronometro_manual.py <repeticao> <cliente>   (ex.: 1 101)")
    rep, cliente = int(sys.argv[1]), int(sys.argv[2])
    rotulo = f"D1-R{rep:02d}"

    print(f"===== [{rotulo}] MANUAL - cliente {cliente} =====")
    input("Pressione ENTER para INICIAR o cronometro...")
    inicio = time.perf_counter()
    parar = threading.Event()
    threading.Thread(target=mostrar_tempo, args=(inicio, parar), daemon=True).start()
    input()
    duracao = time.perf_counter() - inicio
    parar.set()
    print(f"\n  Tempo total: {duracao:.1f} s")

    erros = input("Erros de digitacao corrigidos (numero, ENTER = 0): ").strip() or "0"
    while not erros.isdigit():
        erros = input("Digite apenas o numero de erros: ").strip() or "0"
    correta = ""
    while correta not in ("s", "n"):
        correta = input("Configuracao final ficou correta? (s/n): ").strip().lower()

    novo = not ARQ.exists() or ARQ.stat().st_size == 0
    with open(ARQ, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(CABECALHO)
        w.writerow([rep, cliente, f"{duracao:.2f}", erros, correta])
    print(f"===== [{rotulo}] MANUAL - registrado em logs/manual.csv =====")


if __name__ == "__main__":
    main()
