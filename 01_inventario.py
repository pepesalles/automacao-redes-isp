"""Etapa 1 - Inventario automatizado com NAPALM (get_facts)."""
import json
from common import BASE, carregar_inventario, conectar_napalm

inv = carregar_inventario()["roteadores"]
resultado = {}
print(f"{'Roteador':15} {'Gerencia':9} {'Hostname':15} {'Modelo':14} {'Uptime(min)':>11}  Versao")
for nome, d in inv.items():
    try:
        dev = conectar_napalm(d["host"])
        f = dev.get_facts()
        dev.close()
        resultado[nome] = f
        print(f"{nome:15} {d['host']:9} {f['hostname'][:15]:15} {str(f['model'])[:14]:14} "
              f"{int(f['uptime']) // 60:>11}  {str(f['os_version'])[:45]}")
    except Exception as e:
        print(f"{nome:15} {d['host']:9} ERRO: {e}")
(BASE / "logs").mkdir(exist_ok=True)
(BASE / "logs" / "inventario.json").write_text(json.dumps(resultado, indent=2, default=str))
print("\nInventario salvo em logs/inventario.json")
