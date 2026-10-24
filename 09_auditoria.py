"""Experimento D4 - Auditoria de conformidade (NAPALM get_config).

Uso (na ordem do experimento):
  python 09_auditoria.py baseline          # 1. audita a rede como esta
  python 09_auditoria.py --injetar         # 2. gera e aplica de 2 a 4 desvios aleatorios SEM mostrar quais
  python 09_auditoria.py --manual desvios  # 3. auditoria MANUAL (as cegas): cronometro + registro dos achados
  python 09_auditoria.py desvios           # 4. auditoria automatizada
  python 09_auditoria.py --gabarito        # 5. revela os desvios e compara manual x automatizado
  python 09_auditoria.py --reverter        # 6. desfaz os desvios da rodada
  python 09_auditoria.py pos-reversao      # 7. confirma a volta ao padrao
  python 09_auditoria.py --resumo          # ao final: media e mediana de todas as rodadas

Desvios: sorteados na hora entre 20 combinacoes (roteador x regra), com variacoes em cada regra.
C04 e C05 sao auditadas, mas nao injetadas: altera-las cortaria o acesso SSH do proprio script.

Resultados (sem data de execucao):
  logs/resultados_D4_auditoria.csv   -> uma linha por roteador x regra
  logs/resultados_D4_resumo.csv      -> uma linha por execucao automatizada (tempo e totais)
  logs/resultados_D4_manual.csv      -> auditorias manuais (tempo e desvios apontados)
  logs/resultados_D4_comparacao.csv  -> manual x automatizado contra o gabarito, por rodada
"""
import csv
import json
import random
import re
import statistics
import sys
import time

from common import BASE, carregar_inventario, conectar_napalm, conectar_netmiko

LOG_REGRAS = BASE / "logs" / "resultados_D4_auditoria.csv"
LOG_RESUMO = BASE / "logs" / "resultados_D4_resumo.csv"
LOG_MANUAL = BASE / "logs" / "resultados_D4_manual.csv"
LOG_COMP = BASE / "logs" / "resultados_D4_comparacao.csv"
GABARITO = BASE / "logs" / ".d4_gabarito.json"
ROTULO_DESVIOS = "desvios"
MIN_DESVIOS, MAX_DESVIOS = 2, 4

# Atalhos usados no registro da auditoria manual
ATALHOS = {"core": "core-router", "e1": "edge-router-1", "e2": "edge-router-2", "e3": "edge-router-3"}
VTY = "line vty 0 4"


def variantes(regra):
    """Formas possiveis de violar cada regra: lista de (comandos para aplicar, comandos para reverter)."""
    if regra == "C01":
        return [(["ip domain lookup"], ["no ip domain lookup"])]
    if regra == "C02":
        rev = ["logging buffered 64000 debugging"]
        return [(["no logging buffered"], rev), (["logging buffered 4096"], rev)]
    if regra == "C03":
        rev = ["service timestamps log datetime msec"]
        return [(["no service timestamps log datetime msec"], rev), (["service timestamps log uptime"], rev)]
    if regra == "C06":
        rev = [VTY, "transport input ssh"]
        return [([VTY, "transport input ssh telnet"], rev), ([VTY, "transport input all"], rev)]
    if regra == "C07":
        return [(["no ntp master"], ["ntp master 3"])]
    if regra == "C08":
        n = random.randint(150, 199)
        lo, rev = f"interface Loopback{n}", [f"no interface Loopback{n}"]
        return [([lo, "description teste"], rev), ([lo], rev),
                ([lo, f"description CLIENTE:EMPRESA-{n}"], rev),
                ([lo, f"description EMPRESA-{n} CIRCUITO:CORP-0{n}"], rev)]
    return []


REGRAS_INJETAVEIS = ["C01", "C02", "C03", "C06", "C07", "C08"]


def blocos(cfg):
    """Divide a configuracao em blocos: {'line vty 0 4': ['login local', ...], ...}."""
    res, atual = {}, None
    for linha in cfg.splitlines():
        if not linha.strip() or linha.startswith("!"):
            continue
        if not linha.startswith(" "):
            atual = linha.strip()
            res.setdefault(atual, [])
        elif atual:
            res[atual].append(linha.strip())
    return res


def tem(cfg, texto):
    return any(l.strip() == texto for l in cfg.splitlines())


def vty(cfg):
    return [l for k, v in blocos(cfg).items() if k.startswith("line vty") for l in v]


def loopbacks_cliente_ok(cfg):
    ruins = []
    for k, v in blocos(cfg).items():
        m = re.match(r"interface Loopback(1\d\d)$", k)
        if m:
            desc = next((l for l in v if l.startswith("description ")), "")
            if not re.match(r"description CLIENTE:\S+ \| CIRCUITO:\S+ \| VEL:\S+$", desc):
                ruins.append(f"Loopback{m.group(1)}")
    return (not ruins), ("sem descricao padrao: " + ", ".join(ruins)) if ruins else ""


# (id, descricao, nivel, escopo, funcao) - escopo: "todos", "core" ou "bordas"
REGRAS = [
    ("C01", "no ip domain lookup", "FALHA", "todos", lambda c: (tem(c, "no ip domain lookup"), "")),
    ("C02", "logging buffered 64000", "FALHA", "todos",
     lambda c: (any(l.startswith("logging buffered 64000") for l in c.splitlines()), "")),
    ("C03", "timestamps de log com data e ms", "FALHA", "todos",
     lambda c: (tem(c, "service timestamps log datetime msec"), "")),
    ("C04", "usuario admin com privilege 15", "FALHA", "todos",
     lambda c: (any(l.startswith("username admin privilege 15") for l in c.splitlines()), "")),
    ("C05", "vty com login local", "FALHA", "todos", lambda c: ("login local" in vty(c), "")),
    ("C06", "vty somente SSH", "FALHA", "todos",
     lambda c: ([l for l in vty(c) if l.startswith("transport input")] == ["transport input ssh"],
                " / ".join(l for l in vty(c) if l.startswith("transport input")))),
    ("C07", "core como servidor NTP", "FALHA", "core",
     lambda c: (any(l.startswith("ntp master") for l in c.splitlines()), "")),
    ("C08", "loopbacks de cliente com descricao padrao", "FALHA", "bordas", loopbacks_cliente_ok),
    ("A01", "servidor HTTP desabilitado (recomendacao)", "AVISO", "todos",
     lambda c: (not tem(c, "ip http server"), "ip http server habilitado")),
]
ESCOPO = {r[0]: r[3] for r in REGRAS if r[2] == "FALHA"}


def aplica(escopo, nome):
    return escopo == "todos" or (escopo == "core") == (nome == "core-router")


def gravar(arq, cab, linhas):
    novo = not arq.exists()
    with open(arq, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(cab)
        w.writerows(linhas)


def ler(arq):
    if not arq.exists():
        return []
    with open(arq, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ler_gabarito():
    return json.loads(GABARITO.read_text()) if GABARITO.exists() else None


def rotulo_da_rodada(rotulo):
    """'desvios' vira 'desvios-rN' quando ha uma rodada em andamento."""
    gab = ler_gabarito()
    if rotulo == ROTULO_DESVIOS and gab:
        return f"{ROTULO_DESVIOS}-r{gab['rodada']}"
    return rotulo


def auditoria(rotulo):
    rotulo = rotulo_da_rodada(rotulo)
    print(f"===== [D4-{rotulo.upper()}] INICIO - AUDITORIA =====")
    inv = carregar_inventario()["roteadores"]
    t0 = time.perf_counter()
    linhas, falhas, avisos = [], 0, 0
    for nome, d in inv.items():
        dev = conectar_napalm(d["host"])
        cfg = dev.get_config(retrieve="running")["running"]
        dev.close()
        print(f"\n{nome}")
        for rid, desc, nivel, escopo, f in REGRAS:
            if not aplica(escopo, nome):
                continue
            ok, det = f(cfg)
            status = "OK" if ok else nivel
            falhas += status == "FALHA"
            avisos += status == "AVISO"
            print(f"  [{status:5}] {rid} {desc}" + (f" -> {det}" if det and not ok else ""))
            linhas.append([rotulo, nome, rid, desc, status, det if not ok else ""])
    dt = time.perf_counter() - t0
    gravar(LOG_REGRAS, ["execucao", "roteador", "regra", "descricao", "status", "detalhe"], linhas)
    gravar(LOG_RESUMO, ["execucao", "roteadores", "verificacoes", "falhas", "avisos", "duracao_s"],
           [[rotulo, len(inv), len(linhas), falhas, avisos, f"{dt:.2f}"]])
    print(f"\nResumo: {len(linhas)} verificacoes em {len(inv)} roteadores | "
          f"{falhas} FALHA(s) | {avisos} AVISO(s) | {dt:.1f} s")
    print(f"===== [D4-{rotulo.upper()}] FIM - AUDITORIA =====")


def relogio(inicio):
    s = int(time.perf_counter() - inicio)
    return f"{s // 60:02d}:{s % 60:02d}"


def manual(rotulo):
    rotulo = rotulo_da_rodada(rotulo)
    print(f"===== [D4-{rotulo.upper()}] AUDITORIA MANUAL =====")
    print("Durante a auditoria, registre aqui cada desvio encontrado:")
    print("  formato : <roteador> <regra>      ex.: e1 C01")
    print("  roteador: core | e1 | e2 | e3     regra: C01 a C08")
    print("  apagar  : remove o ultimo registro")
    print("  fim     : para o cronometro e grava")
    input("\nPressione ENTER para INICIAR o cronometro...")
    inicio, achados = time.perf_counter(), []
    while True:
        s = input(f"[{relogio(inicio)}] desvio> ").strip()
        if not s:
            continue
        if s.lower() == "fim":
            break
        if s.lower() == "apagar":
            if achados:
                r, g = achados.pop()
                print(f"  removido: {r} {g}  (total: {len(achados)})")
            else:
                print("  nada a remover")
            continue
        partes = s.split()
        if len(partes) != 2 or partes[0].lower() not in ATALHOS or partes[1].upper() not in ESCOPO:
            print("  formato invalido (ex.: e1 C01)")
            continue
        rot, reg = ATALHOS[partes[0].lower()], partes[1].upper()
        if not aplica(ESCOPO[reg], rot):
            print(f"  a regra {reg} nao se aplica a {rot}")
            continue
        if (rot, reg) in achados:
            print("  ja registrado")
            continue
        achados.append((rot, reg))
        print(f"  registrado: {rot} {reg}  (total: {len(achados)})")
    dt = time.perf_counter() - inicio
    texto = "; ".join(f"{r}:{g}" for r, g in achados)
    gravar(LOG_MANUAL, ["execucao", "duracao_s", "desvios_encontrados", "achados"],
           [[rotulo, f"{dt:.2f}", len(achados), texto]])
    print(f"\n  Tempo total: {dt:.1f} s | desvios apontados: {len(achados)}")
    for r, g in achados:
        print(f"    - {r} {g}")
    print(f"===== [D4-{rotulo.upper()}] MANUAL - registrado em logs/resultados_D4_manual.csv =====")


def aplicar(roteador, comandos):
    inv = carregar_inventario()["roteadores"]
    conn = conectar_netmiko(inv[roteador]["host"])
    conn.send_config_set(comandos)
    conn.disconnect()


def injetar():
    if ler_gabarito():
        sys.exit("Ja existe uma rodada em andamento. Rode --gabarito e --reverter antes de injetar de novo.")
    inv = carregar_inventario()["roteadores"]
    possiveis = [(r, g) for r in inv for g in REGRAS_INJETAVEIS if aplica(ESCOPO[g], r)]
    escolhidos = random.sample(possiveis, random.randint(MIN_DESVIOS, MAX_DESVIOS))
    rodada = len({l["rodada"] for l in ler(LOG_COMP)}) + 1
    desvios = []
    for roteador, regra in escolhidos:
        cmd, rev = random.choice(variantes(regra))
        aplicar(roteador, cmd)
        desvios.append({"roteador": roteador, "regra": regra, "aplicar": cmd, "reverter": rev})
    GABARITO.write_text(json.dumps({"rodada": rodada, "desvios": desvios}, indent=1))
    print(f"===== [D4-{ROTULO_DESVIOS.upper()}-R{rodada}] DESVIOS APLICADOS "
          f"(quantos, quais e onde ficam em segredo ate o --gabarito) =====")


def ultimo_manual(rotulo):
    """Le por posicao (execucao, duracao_s, desvios_encontrados, achados), independente do cabecalho."""
    if not LOG_MANUAL.exists():
        return None
    with open(LOG_MANUAL, newline="", encoding="utf-8") as f:
        linhas = [l for l in csv.reader(f) if l and l[0] == rotulo]
    if not linhas:
        return None
    ult = linhas[-1]
    achados = ult[3] if len(ult) > 3 else ""
    pares = {tuple(p.split(":")) for p in achados.split("; ") if ":" in p}
    return pares, float(ult[1])


def ultimo_automatizado(rotulo):
    linhas = ler(LOG_REGRAS)
    idx = [i for i, l in enumerate(linhas) if l["execucao"] == rotulo]
    if not idx:
        return None
    fim = idx[-1]
    ini = fim
    while ini > 0 and linhas[ini - 1]["execucao"] == rotulo:
        ini -= 1
    pares = {(l["roteador"], l["regra"]) for l in linhas[ini:fim + 1] if l["status"] == "FALHA"}
    res = [l for l in ler(LOG_RESUMO) if l["execucao"] == rotulo]
    return pares, float(res[-1]["duracao_s"]) if res else 0.0


def gabarito():
    gab = ler_gabarito()
    print("===== [D4] GABARITO =====")
    if not gab:
        print("  Nenhuma rodada em andamento (o --injetar foi executado? o --reverter ja apagou?)")
        return
    rodada, desvios = gab["rodada"], gab["desvios"]
    rotulo = f"{ROTULO_DESVIOS}-r{rodada}"
    for d in desvios:
        print(f"  {d['roteador']:14} regra {d['regra']}  ->  {' / '.join(d['aplicar'])}")
    certo = {(d["roteador"], d["regra"]) for d in desvios}
    if any(l["rodada"] == str(rodada) for l in ler(LOG_COMP)):
        print(f"\n  Rodada {rodada} ja comparada (ver logs/resultados_D4_comparacao.csv).")
        return

    print(f"\n===== [D4] RODADA {rodada} - COMPARACAO COM O GABARITO ({len(certo)} desvios injetados) =====")
    print(f"  {'Metodo':13} {'Tempo':>9}  {'Acertos':>7}  {'Falsos+':>7}  Nao encontrados")
    linhas = []
    for metodo, dados in (("manual", ultimo_manual(rotulo)), ("automatizado", ultimo_automatizado(rotulo))):
        if dados is None:
            print(f"  {metodo:13} sem registro da execucao '{rotulo}'")
            continue
        apontados, dur = dados
        acertos, falsos, faltou = certo & apontados, apontados - certo, certo - apontados
        txt_faltou = ", ".join(f"{r} {g}" for r, g in sorted(faltou)) or "-"
        print(f"  {metodo:13} {dur:8.1f}s  {len(acertos)}/{len(certo):<5}  {len(falsos):>7}  {txt_faltou}")
        if falsos:
            print(f"  {'':13} falsos positivos: " + ", ".join(f"{r} {g}" for r, g in sorted(falsos)))
        linhas.append([rodada, metodo, len(certo), len(apontados), len(acertos), len(falsos), len(faltou),
                       f"{dur:.2f}", "; ".join(f"{r}:{g}" for r, g in sorted(faltou)),
                       "; ".join(f"{r}:{g}" for r, g in sorted(falsos))])
    gravar(LOG_COMP, ["rodada", "metodo", "desvios_injetados", "apontados", "acertos", "falsos_positivos",
                      "nao_encontrados", "duracao_s", "detalhe_nao_encontrados", "detalhe_falsos_positivos"],
           linhas)
    print("===== [D4] COMPARACAO - registrada em logs/resultados_D4_comparacao.csv =====")


def reverter():
    gab = ler_gabarito()
    if not gab:
        sys.exit("Nenhuma rodada em andamento: nada a reverter.")
    for d in gab["desvios"]:
        aplicar(d["roteador"], d["reverter"])
    GABARITO.unlink()
    print(f"===== [D4-{ROTULO_DESVIOS.upper()}-R{gab['rodada']}] DESVIOS REVERTIDOS =====")


def resumo():
    linhas = ler(LOG_COMP)
    if not linhas:
        sys.exit("Nenhuma rodada registrada.")
    print("===== [D4] RESUMO DAS RODADAS =====")
    print(f"  {'Metodo':13} {'Rodadas':>7}  {'Deteccao':>12}  {'Falsos+':>7}  {'Media':>8}  {'Mediana':>8}")
    for metodo in ("manual", "automatizado"):
        ls = [l for l in linhas if l["metodo"] == metodo]
        if not ls:
            continue
        inj = sum(int(l["desvios_injetados"]) for l in ls)
        ac = sum(int(l["acertos"]) for l in ls)
        fp = sum(int(l["falsos_positivos"]) for l in ls)
        t = [float(l["duracao_s"]) for l in ls]
        print(f"  {metodo:13} {len(ls):>7}  {ac:>3}/{inj:<3}{100 * ac / inj:5.0f}%  {fp:>7}  "
              f"{statistics.mean(t):7.1f}s  {statistics.median(t):7.1f}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit("Uso: python 09_auditoria.py <rotulo> | --injetar | --manual <rotulo> | --gabarito "
                 "| --reverter | --resumo")
    if args[0] == "--manual":
        manual(args[1] if len(args) > 1 else ROTULO_DESVIOS)
    elif args[0] == "--injetar":
        injetar()
    elif args[0] == "--gabarito":
        gabarito()
    elif args[0] == "--reverter":
        reverter()
    elif args[0] == "--resumo":
        resumo()
    else:
        auditoria(args[0])
