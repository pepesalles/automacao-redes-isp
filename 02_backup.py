"""Etapa 2 - Backup da running-config de todos os roteadores (NAPALM get_config)."""
from datetime import datetime
from common import BASE, carregar_inventario, conectar_napalm

pasta = BASE / "backups"
pasta.mkdir(exist_ok=True)
carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
for nome, d in carregar_inventario()["roteadores"].items():
    try:
        dev = conectar_napalm(d["host"])
        cfg = dev.get_config(retrieve="running")["running"]
        dev.close()
        arq = pasta / f"{nome}_{carimbo}.cfg"
        arq.write_text(cfg)
        print(f"[OK]   {nome}: backups/{arq.name} ({len(cfg.splitlines())} linhas)")
    except Exception as e:
        print(f"[ERRO] {nome}: {e}")
