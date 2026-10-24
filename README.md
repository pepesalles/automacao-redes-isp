# Automação da Ativação de Clientes em Roteadores Cisco

Código, dados e registros do Trabalho de Conclusão de Curso **"Aplicação de Ferramentas de Automação (Netmiko, NAPALM e Jinja2) na Configuração de Roteadores Cisco em Ambiente Simulado de Provedor de Serviços de Internet"**, da Pós-Graduação em Engenharia de Redes e Telecomunicações da PUCPR (linha de Projeto).

- **Autor:** Gabriel Henrique de Salles
- **Orientador:** Prof. Luis Jose Rohling
- **Banca:** aprovado em 24/10/2026

📄 **Artigo completo:** [artigo/TCC_Gabriel_Henrique_de_Salles.pdf](artigo/TCC_Gabriel_Henrique_de_Salles.pdf)

O projeto automatiza a **ativação de clientes corporativos** em roteadores de borda de um ISP e compara o resultado com o processo manual, medindo tempo, erros e capacidade de detectar falhas. Também automatiza a **auditoria de conformidade** da configuração dos roteadores.

## Principais resultados

| ID | Pergunta | Resultado |
|---|---|---|
| D1 | A automação é mais rápida e erra menos? | Tempo médio de 162,0 s (manual) para 5,7 s (automatizado), redução de 96,5%; mediana de 105,9 s para 5,6 s; 5 erros manuais × 0 |
| D2 | O fluxo detecta dados errados e falhas de rede? | 7 de 7 erros injetados barrados ou revertidos, sem configuração incorreta nos roteadores |
| D3 | O fluxo escala? | 48 de 48 ativações OK; crescimento linear, cerca de 5,7 s por cliente (R² = 0,97) |
| D4 | A automação ajuda a manter a rede padronizada? | Auditoria automatizada: 9 de 9 desvios em 4,3 s (média); manual: 7 de 9 em 346,1 s (média) / 371,2 s (mediana); 0 falsos positivos nos dois |
| D5 | O que acontece se uma borda falha? | Clientes com acesso redundante ativados na contingência, cliente sem redundância em falha segura (nada aplicado), demais normais; detecção imediata, nenhuma configuração parcial |

Identificadores: D = experimento; R = repetição ou rodada; E = erro injetado (D2); L = lote (D3); C = regra de conformidade e A = aviso (D4).

## Ambiente de laboratório

- Cisco Modeling Labs 2.10 (Free), roteadores IOL-XE (IOS XE 17.18.2)
- Topologia core/borda: 1 roteador *core* (Route Reflector), 3 roteadores de borda e 1 servidor Linux de automação
- OSPF área 0 para a infraestrutura; iBGP AS 65001 entre loopbacks, com o *core* como Route Reflector
- NTP a partir do *core*; registro de comandos de configuração (`archive log config`) nos 4 roteadores

| Roteador | Função | Gerência (Loopback0) |
|---|---|---|
| core-router | Core / Route Reflector / servidor NTP | 1.1.1.1 |
| edge-router-1 | Borda — clientes corporativos | 2.2.2.2 |
| edge-router-2 | Borda — clientes residenciais | 3.3.3.3 |
| edge-router-3 | Borda — peering e contingência | 4.4.4.4 |

## Papel de cada ferramenta

- **YAML:** fonte da verdade (inventário e dados dos clientes)
- **Jinja2:** gera a configuração padronizada a partir dos templates
- **Netmiko:** aplica a configuração e executa os comandos de verificação via SSH
- **NAPALM:** leitura estruturada (inventário, backup e auditoria de conformidade)

## Fluxo de ativação (`03_ativar_cliente.py`)

1. **Validação dos dados**, sem acessar a rede (campos obrigatórios, prefixo IPv4 válido, roteador existente)
2. **Pré-check na rede** (prefixo já em uso? cliente já ativado?)
3. **Geração e aplicação** da configuração (Jinja2 + Netmiko)
4. **Verificação pós-mudança** no Route Reflector (prefixo no BGP + ping ao gateway do cliente)
5. **Decisão:** salva a configuração se a verificação passar; **rollback automático** se falhar

## Estrutura

| Arquivo | Função |
|---|---|
| `artigo/` | Artigo completo do TCC (PDF) |
| `inventario.yaml` | Roteadores, IPs de gerência e ASN |
| `clientes.yaml` | 10 clientes corporativos (101–110) |
| `clientes_erros.yaml` | 5 clientes com erros injetados de propósito (E1–E5) |
| `clientes_contingencia.yaml` | Clientes do D5 (111–115), com e sem acesso redundante |
| `templates/` | Templates Jinja2 de ativação e remoção |
| `common.py` | Funções compartilhadas: conexão, validação, renderização e log |
| `requirements.txt` | Dependências Python (Netmiko, NAPALM, Jinja2, PyYAML) |
| `rotas.sh` | Rotas do servidor Linux para a rede do laboratório (rodar após cada reinício do nó) |
| `01_inventario.py` | Inventário dos roteadores (NAPALM `get_facts`) |
| `02_backup.py` | Backup da running-config (NAPALM `get_config`) |
| `03_ativar_cliente.py` | Ativação com validação, verificação e rollback |
| `04_remover_cliente.py` | Remoção de clientes (limpa o lab entre repetições) |
| `05_resumo.py` | Estatísticas: automatizado × manual |
| `06_cronometro_manual.py` | Cronômetro do procedimento manual (D1), grava em `logs/manual.csv` |
| `07_d3_lotes.py` | Experimento D3: ativação em lotes de 1, 5 e 10 clientes |
| `08_ativar_contingencia.py` | Experimento D5: ativação com contingência em falha de borda |
| `09_auditoria.py` | Experimento D4: auditoria de conformidade (NAPALM), injeção de desvios às cegas, comparação manual × automatizada |
| `logs/` | Resultados dos experimentos (CSV); `logs/d4_piloto/` guarda a rodada piloto do D4, descartada |
| `evidencias/` | Saídas de console dos experimentos, com o hash de senha removido |

Por segurança, esta versão pública **não inclui** os backups de configuração dos roteadores nem o arquivo de topologia do laboratório, porque ambos contêm hashes de senha.

## Como executar

Requer um laboratório equivalente (CML ou outro ambiente com roteadores IOS XE acessíveis por SSH) e Python 3 com as dependências de `requirements.txt`.

```
source ~/automation-env/bin/activate
pip install -r requirements.txt
export LAB_USER=admin
read -s -p "Senha: " LAB_PASS && export LAB_PASS
python 01_inventario.py
python 02_backup.py
python 03_ativar_cliente.py 101
```

As credenciais são lidas de variáveis de ambiente; nenhuma senha fica gravada no código.

Roteiro do D4 (auditoria):

```
python 09_auditoria.py baseline
python 09_auditoria.py --injetar          # 2 a 4 desvios aleatórios, sem revelar quais
python 09_auditoria.py --manual desvios   # auditoria manual cronometrada, com registro dos achados
python 09_auditoria.py desvios            # auditoria automatizada
python 09_auditoria.py --gabarito         # revela os desvios e compara manual x automatizado
python 09_auditoria.py --reverter
python 09_auditoria.py pos-reversao
python 09_auditoria.py --resumo           # ao final das rodadas
```

Roteiro do D5 (contingência):

```
python 08_ativar_contingencia.py controle    # rede normal
python 08_ativar_contingencia.py --remover
# no core: interface Ethernet0/1 -> shutdown (isola o edge-1)
python 08_ativar_contingencia.py falha
# no core: no shutdown; depois:
python 08_ativar_contingencia.py --remover
```

## Limitações

O limite de 5 nós do CML Free impede simular o roteador do cliente (representado por uma interface Loopback) e um AS externo para peering eBGP. As medições manuais foram feitas por um único operador, responsável também pela automação, o que representa o melhor caso do processo manual. No D4, as regras C04 e C05 são auditadas, mas não são usadas como desvios, porque alterá-las cortaria o acesso SSH do próprio script. MPLS, QoS e NETCONF/YANG estão fora do escopo prático e são indicados como trabalhos futuros.
