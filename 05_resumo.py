"""Etapa 5 - Resumo estatistico: automatizado (logs/resultados.csv) x manual (logs/manual.csv)."""
import csv
import statistics as st
from collections import Counter
from pathlib import Path

LOGS = Path(__file__).resolve().parent / "logs"


def ler(nome):
    p = LOGS / nome
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def descrever(rotulo, tempos):
    if not tempos:
        print(f"{rotulo}: sem dados")
        return None
    dp = st.stdev(tempos) if len(tempos) > 1 else 0.0
    print(f"{rotulo}: n={len(tempos)}  media={st.mean(tempos):.1f} s  desvio={dp:.1f} s  "
          f"min={min(tempos):.1f}  max={max(tempos):.1f}")
    return st.mean(tempos)


auto = [r for r in ler("resultados.csv") if r["operacao"] == "ativacao"]
print("Resultados da automacao:", dict(Counter(r["resultado"] for r in auto)))
m_auto = descrever("Automatizado (ativacoes OK)",
                   [float(r["duracao_s"]) for r in auto if r["resultado"] == "OK"])

manual = ler("manual.csv")
m_man = descrever("Manual", [float(r["duracao_s"]) for r in manual if r.get("duracao_s")])
if manual:
    erros = sum(int(r["erros_digitacao"] or 0) for r in manual)
    incorretas = sum(1 for r in manual if r["config_correta"].strip().lower() != "s")
    print(f"Manual: {erros} erro(s) de digitacao corrigidos; {incorretas} configuracao(oes) final(is) incorreta(s)")
if m_auto and m_man:
    print(f"Reducao de tempo: {100 * (1 - m_auto / m_man):.1f}%")
