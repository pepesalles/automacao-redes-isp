"""Experimento D5 - Ativacao com contingencia (falha de roteador de borda).

Uso:
  python 08_ativar_contingencia.py controle   # rede normal: todos no roteador principal
  python 08_ativar_contingencia.py falha      # com o edge-1 fora do ar
  python 08_ativar_contingencia.py --remover  # remove os clientes 111-115 de onde estiverem

Regra de decisao (por cliente):
  principal acessivel            -> ativa no principal (fluxo completo do 03)
  principal fora + tem backup    -> CONTINGENCIA: ativa no roteador de backup
  principal fora + sem backup    -> FALHA SEGURA: nada e aplicado, erro registrado
Resultados (sem data de execucao):
  logs/resultados_D5_contingencia.csv -> uma linha por cliente
  logs/resultados_D5_detalhe.csv      -> log padrao do 03 (ativacoes realizadas)
"""
import csv
import importlib
import socket
import sys
import time

import common
from common import (BASE, carregar_inventario, carregar_yaml, conectar_netmiko,
                    dados_template, renderizar, validar_cliente)

ARQ = BASE / "logs" / "resultados_D5_contingencia.csv"
common.LOG_CSV = BASE / "logs" / "resultados_D5_detalhe.csv"
ativacao = importlib.import_module("03_ativar_cliente")
TIMEOUT_SSH = 5  # segundos para considerar o roteador inacessivel


def acessivel(host):
    try:
        socket.create_connection((host, 22), timeout=TIMEOUT_SSH).close()
        return True
    except OSError:
        return False


def ultimo_resultado(alvo):
    if not common.LOG_CSV.exists():
        return "ERRO"
    with open(common.LOG_CSV, encoding="utf-8") as f:
        linhas = [r for r in csv.DictReader(f) if r["alvo"] == alvo]
    return linhas[-1]["resultado"] if linhas else "ERRO"


def executar(cenario):
    inv = carregar_inventario()
    rot = inv["roteadores"]
    clientes = carregar_yaml("clientes_contingencia.yaml")["clientes"]
    print(f"===== [D5-{cenario.upper()}] INICIO =====")
    linhas = []
    for c in clientes:
        alvo = f"cliente-{c['id']}"
        backup = c.get("roteador_backup")
        if backup and backup not in rot:
            print(f"\n{alvo}: roteador_backup inexistente no inventario ({backup})")
            continue
        t0 = time.perf_counter()
        ok_principal = acessivel(rot[c["roteador"]]["host"])
        t_det = time.perf_counter() - t0
        if ok_principal:
            decisao, usado = "PRINCIPAL", c["roteador"]
        elif backup:
            decisao, usado = "CONTINGENCIA", backup
        else:
            decisao, usado = "FALHA_SEGURA", "-"
        print(f"\n>>> {alvo}: principal {c['roteador']} "
              f"{'acessivel' if ok_principal else 'INACESSIVEL'} ({t_det:.1f} s) -> {decisao}")
        if decisao == "FALHA_SEGURA":
            resultado = "NAO_APLICADO"
            print(f"  [FALHA SEGURA] {c['roteador']} fora do ar e cliente sem acesso redundante: "
                  f"nenhuma configuracao aplicada; abrir chamado")
        else:
            ativacao.ativar(dict(c, roteador=usado), inv)
            resultado = ultimo_resultado(alvo)
        dt = time.perf_counter() - t0
        linhas.append([cenario, c["id"], c["roteador"], backup or "-", decisao, usado,
                       resultado, f"{t_det:.2f}", f"{dt:.2f}"])
    novo = not ARQ.exists()
    with open(ARQ, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["cenario", "cliente", "principal", "backup", "decisao", "roteador_usado",
                        "resultado", "deteccao_s", "total_s"])
        w.writerows(linhas)
    print(f"\n===== RESUMO D5-{cenario.upper()} =====")
    print(f"{'Cliente':>7} {'Decisao':13} {'Roteador usado':15} {'Resultado':13} {'Total (s)':>9}")
    for l in linhas:
        print(f"{l[1]:>7} {l[4]:13} {l[5]:15} {l[6]:13} {l[8]:>9}")
    print(f"===== [D5-{cenario.upper()}] FIM =====")


def remover():
    inv = carregar_inventario()
    for c in carregar_yaml("clientes_contingencia.yaml")["clientes"]:
        _, rede = validar_cliente(c, inv["roteadores"])
        d = dados_template(c, rede, inv["asn"])
        for r in filter(None, {c["roteador"], c.get("roteador_backup")}):
            host = inv["roteadores"][r]["host"]
            if not acessivel(host):
                print(f"cliente-{c['id']}: {r} inacessivel, pulando")
                continue
            conn = conectar_netmiko(host)
            conn.send_config_set(renderizar("cliente_remover.j2", **d))
            conn.save_config()
            conn.disconnect()
        print(f"cliente-{c['id']}: removido")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python 08_ativar_contingencia.py controle | falha | --remover")
    remover() if sys.argv[1] == "--remover" else executar(sys.argv[1])
