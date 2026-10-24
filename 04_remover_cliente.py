"""Etapa 4 - Remocao (desativacao) de clientes. Usada para zerar o lab entre as repeticoes.

Uso: python 04_remover_cliente.py 101   |   python 04_remover_cliente.py --todos
"""
import argparse
import time

from common import (carregar_inventario, carregar_yaml, conectar_netmiko, dados_template,
                    registrar, renderizar, validar_cliente)

ap = argparse.ArgumentParser()
ap.add_argument("ids", nargs="*", type=int)
ap.add_argument("--todos", action="store_true")
ap.add_argument("--arquivo", default="clientes.yaml")
a = ap.parse_args()
inv = carregar_inventario()
clientes = carregar_yaml(a.arquivo)["clientes"]
for c in (clientes if a.todos else [c for c in clientes if c.get("id") in a.ids]):
    erros, rede = validar_cliente(c, inv["roteadores"])
    if erros:
        print(f"cliente-{c.get('id')}: ignorado ({'; '.join(erros)})")
        continue
    t0 = time.perf_counter()
    d = dados_template(c, rede, inv["asn"])
    conn = conectar_netmiko(inv["roteadores"][c["roteador"]]["host"])
    conn.send_config_set(renderizar("cliente_remover.j2", **d))
    conn.save_config()
    conn.disconnect()
    dt = time.perf_counter() - t0
    registrar("remocao", f"cliente-{c['id']}", dt, "OK")
    print(f"cliente-{c['id']}: removido de {c['roteador']} ({dt:.1f} s)")
