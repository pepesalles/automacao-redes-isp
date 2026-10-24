"""Funcoes compartilhadas pelos scripts do TCC."""
import csv
import datetime
import ipaddress
import os
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

BASE = Path(__file__).resolve().parent
LOG_CSV = BASE / "logs" / "resultados.csv"
CAMPOS_OBRIGATORIOS = ("id", "nome", "circuito", "velocidade", "roteador", "prefixo")


def credenciais():
    """Le usuario e senha de variaveis de ambiente (nunca do codigo)."""
    user, pwd = os.environ.get("LAB_USER"), os.environ.get("LAB_PASS")
    if not user or not pwd:
        sys.exit("Defina LAB_USER e LAB_PASS antes de rodar (ver passo B3).")
    return user, pwd


def carregar_yaml(nome):
    with open(BASE / nome, encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_inventario():
    return carregar_yaml("inventario.yaml")


def conectar_netmiko(host):
    from netmiko import ConnectHandler
    user, pwd = credenciais()
    conn = ConnectHandler(device_type="cisco_ios", host=host, username=user,
                          password=pwd, secret=pwd, conn_timeout=15)
    if not conn.check_enable_mode():
        conn.enable()
    return conn


def conectar_napalm(host):
    from napalm import get_network_driver
    user, pwd = credenciais()
    driver = get_network_driver("ios")
    dev = driver(hostname=host, username=user, password=pwd,
                 optional_args={"secret": pwd})
    dev.open()
    return dev


def renderizar(template, **dados):
    env = Environment(loader=FileSystemLoader(BASE / "templates"),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    return env.get_template(template).render(**dados).splitlines()


def validar_cliente(c, roteadores):
    """Validacao dos dados ANTES de tocar na rede. Retorna (erros, rede)."""
    erros = [f"campo obrigatorio ausente: {k}" for k in CAMPOS_OBRIGATORIOS if k not in c]
    if erros:
        return erros, None
    if c["roteador"] not in roteadores:
        erros.append(f"roteador inexistente no inventario: {c['roteador']}")
    rede = None
    try:
        rede = ipaddress.ip_network(str(c["prefixo"]), strict=True)
        if rede.version != 4 or rede.prefixlen > 30:
            erros.append("prefixo deve ser IPv4 entre /8 e /30")
            rede = None
    except ValueError as e:
        erros.append(f"prefixo invalido: {e}")
    return erros, rede


def dados_template(c, rede, asn):
    return {"c": c, "asn": asn, "rede": str(rede.network_address),
            "mascara": str(rede.netmask), "gateway": str(next(rede.hosts()))}


def registrar(operacao, alvo, duracao, resultado, detalhe=""):
    """Grava uma linha no CSV usado na analise de resultados (Parte D)."""
    LOG_CSV.parent.mkdir(exist_ok=True)
    novo = not LOG_CSV.exists()
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["data_hora", "operacao", "alvo", "duracao_s", "resultado", "detalhe"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), operacao,
                    alvo, f"{duracao:.2f}", resultado, detalhe])
