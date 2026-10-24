"""Etapa 3 - Ativacao de cliente corporativo com validacao, verificacao e rollback.

Uso:
  python 03_ativar_cliente.py 101              # um cliente
  python 03_ativar_cliente.py 101 102 103      # varios
  python 03_ativar_cliente.py --todos          # todos do arquivo
  python 03_ativar_cliente.py --todos --arquivo clientes_erros.yaml
"""
import argparse
import re
import time

from common import (carregar_inventario, carregar_yaml, conectar_netmiko, dados_template,
                    registrar, renderizar, validar_cliente)

TEMPO_MAX_VERIFICACAO = 45   # segundos aguardando a convergencia do BGP
INTERVALO = 3


def verificar(core, d):
    """Pos-check no Route Reflector: prefixo no BGP + gateway do cliente respondendo."""
    limite = time.perf_counter() + TEMPO_MAX_VERIFICACAO
    while time.perf_counter() < limite:
        bgp = core.send_command(f"show ip bgp {d['rede']} {d['mascara']}")
        if "BGP routing table entry for" in bgp:
            ping = core.send_command(f"ping {d['gateway']} source Loopback0 repeat 5",
                                     read_timeout=30)
            m = re.search(r"Success rate is (\d+) percent", ping)
            if m and int(m.group(1)) >= 80:
                return True, f"BGP ok; ping {m.group(1)}%"
        time.sleep(INTERVALO)
    return False, "prefixo nao apareceu no BGP do core ou gateway sem resposta"


def ativar(c, inv):
    t0 = time.perf_counter()
    alvo = f"cliente-{c.get('id', '?')}"
    rot = inv["roteadores"]
    print(f"\n=== {alvo} {c.get('nome', '')} ===")

    # 1) Validacao dos dados (nenhum acesso a rede)
    erros, rede = validar_cliente(c, rot)
    if erros:
        for e in erros:
            print(f"  [REJEITADO] {e}")
        registrar("ativacao", alvo, time.perf_counter() - t0, "REJEITADO_VALIDACAO", "; ".join(erros))
        return
    d = dados_template(c, rede, inv["asn"])
    core = edge = None
    try:
        # 2) Pre-check na rede
        core = conectar_netmiko(rot[inv["roteador_verificacao"]]["host"])
        if "Routing entry for" in core.send_command(f"show ip route {d['rede']} {d['mascara']}"):
            motivo = f"prefixo {rede} ja esta em uso na rede"
            print(f"  [REJEITADO] {motivo}")
            registrar("ativacao", alvo, time.perf_counter() - t0, "REJEITADO_PRECHECK", motivo)
            return
        edge = conectar_netmiko(rot[c["roteador"]]["host"])
        if edge.send_command(f"show running-config | include ^interface Loopback{c['id']}$").strip():
            motivo = f"Loopback{c['id']} ja existe em {c['roteador']} (cliente ja ativado)"
            print(f"  [REJEITADO] {motivo}")
            registrar("ativacao", alvo, time.perf_counter() - t0, "REJEITADO_PRECHECK", motivo)
            return

        # 3) Geracao (Jinja2) e aplicacao (Netmiko)
        cmds = renderizar("cliente_ativar.j2", **d)
        print("  Configuracao gerada:\n    " + "\n    ".join(cmds))
        saida = edge.send_config_set(cmds)
        if "% Invalid" in saida or "% Incomplete" in saida:
            ok, detalhe = False, "roteador recusou algum comando"
        else:
            # 4) Pos-check
            ok, detalhe = verificar(core, d)

        # 5) Resultado: salva ou desfaz
        if ok:
            edge.save_config()
            resultado = "OK"
        else:
            edge.send_config_set(renderizar("cliente_remover.j2", **d))
            resultado = "FALHA_ROLLBACK"
        dt = time.perf_counter() - t0
        print(f"  [{resultado}] {detalhe} ({dt:.1f} s)")
        registrar("ativacao", alvo, dt, resultado, detalhe)
    except Exception as e:
        registrar("ativacao", alvo, time.perf_counter() - t0, "ERRO", str(e)[:200])
        print(f"  [ERRO] {e}")
    finally:
        for conn in (edge, core):
            if conn:
                conn.disconnect()


def main():
    ap = argparse.ArgumentParser(description="Ativacao de clientes corporativos")
    ap.add_argument("ids", nargs="*", type=int)
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--arquivo", default="clientes.yaml")
    a = ap.parse_args()
    clientes = carregar_yaml(a.arquivo)["clientes"]
    escolhidos = clientes if a.todos else [c for c in clientes if c.get("id") in a.ids]
    if not escolhidos:
        ap.error("informe IDs existentes no arquivo ou use --todos")
    inv = carregar_inventario()
    t0 = time.perf_counter()
    for c in escolhidos:
        ativar(c, inv)
    print(f"\nTotal: {len(escolhidos)} cliente(s) em {time.perf_counter() - t0:.1f} s. "
          f"Detalhes em logs/resultados.csv")


if __name__ == "__main__":
    main()
