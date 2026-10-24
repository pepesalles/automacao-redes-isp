"""Experimento D3 - Escala em lotes (1, 5 e 10 clientes, 3 repeticoes cada).

Uso: python 07_d3_lotes.py            (roda tudo: cerca de 8 a 10 minutos)
     python 07_d3_lotes.py --reps 1   (rodada curta de teste, 1 repeticao)

Para cada repeticao e tamanho de lote:
  marcador nos roteadores -> ativa os clientes do lote (fluxo completo do 03)
  -> mede o tempo total -> remove os clientes -> proximo lote.
Resultados (sem data de execucao):
  logs/resultados_D3_lotes.csv    -> uma linha por lote
  logs/resultados_D3_detalhe.csv  -> uma linha por cliente (log padrao do 03)
"""
import argparse
import csv
import importlib
import statistics as st
import time

import common
from common import (BASE, carregar_inventario, carregar_yaml, conectar_netmiko,
                    dados_template, renderizar, validar_cliente)

LOTES = (1, 5, 10)
ARQ_LOTES = BASE / "logs" / "resultados_D3_lotes.csv"
common.LOG_CSV = BASE / "logs" / "resultados_D3_detalhe.csv"   # separa do log do D1
ativacao = importlib.import_module("03_ativar_cliente")


def marcador(inv, texto):
    """Grava o marcador no log dos roteadores envolvidos (fora da medicao de tempo)."""
    for nome in ("core-router", "edge-router-1", "edge-router-2"):
        try:
            conn = conectar_netmiko(inv["roteadores"][nome]["host"])
            conn.send_command(f'send log "{texto}"', expect_string=r"#")
            conn.disconnect()
        except Exception as e:
            print(f"  (aviso: marcador nao enviado para {nome}: {e})")
    print(texto)


def remover(clientes, inv):
    for c in clientes:
        _, rede = validar_cliente(c, inv["roteadores"])
        d = dados_template(c, rede, inv["asn"])
        conn = conectar_netmiko(inv["roteadores"][c["roteador"]]["host"])
        conn.send_config_set(renderizar("cliente_remover.j2", **d))
        conn.save_config()
        conn.disconnect()


def linhas_log():
    if not common.LOG_CSV.exists():
        return []
    with open(common.LOG_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    inv = carregar_inventario()
    clientes = carregar_yaml("clientes.yaml")["clientes"]

    print("Limpeza inicial (remove clientes 101-110 caso algum tenha ficado ativo)...")
    remover(clientes, inv)

    novo = not ARQ_LOTES.exists()
    resultados = []
    for rep in range(1, a.reps + 1):
        for n in LOTES:
            rotulo = f"D3-L{n:02d}-R{rep}"
            lote = clientes[:n]
            marcador(inv, f"===== [{rotulo}] INICIO - lote de {n} cliente(s) =====")
            antes = len(linhas_log())
            t0 = time.perf_counter()
            for c in lote:
                ativacao.ativar(c, inv)
            total = time.perf_counter() - t0
            novas = linhas_log()[antes:]
            ok = sum(1 for r in novas if r["resultado"] == "OK")
            print(f"  [{rotulo}] {ok}/{n} OK em {total:.1f} s ({total / n:.1f} s por cliente)")
            resultados.append({"repeticao": rep, "lote": n, "clientes_ok": ok,
                               "duracao_total_s": f"{total:.2f}",
                               "media_por_cliente_s": f"{total / n:.2f}"})
            remover(lote, inv)
            marcador(inv, f"===== [{rotulo}] FIM =====")

    with open(ARQ_LOTES, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resultados[0]))
        if novo:
            w.writeheader()
        w.writerows(resultados)

    print("\n===== RESUMO D3 =====")
    print(f"{'Lote':>5} {'Reps':>5} {'Tempo total medio (s)':>22} {'Por cliente (s)':>16} {'OK':>8}")
    for n in LOTES:
        rs = [r for r in resultados if r["lote"] == n]
        tot = [float(r["duracao_total_s"]) for r in rs]
        ok = sum(r["clientes_ok"] for r in rs)
        print(f"{n:>5} {len(rs):>5} {st.mean(tot):>22.1f} {st.mean(tot) / n:>16.1f} {ok:>4}/{n * len(rs)}")
    print(f"\nDetalhes: {ARQ_LOTES.relative_to(BASE)} e {common.LOG_CSV.relative_to(BASE)}")


if __name__ == "__main__":
    main()
