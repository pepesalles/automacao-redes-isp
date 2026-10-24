# Rodada piloto do D4 (29/09/2026) — descartada da estatística

Logs da rodada piloto do experimento D4 (auditoria de conformidade), mantidos como registro.

Motivo do descarte: a lista de verificação entregue ao operador tinha duas ambiguidades — a regra C02 citava
`logging buffered 64000 debugging`, mas o IOS omite `debugging` (nível padrão) na running-config; e a regra C08
não deixava claro que só se aplica quando existe interface de cliente (`Loopback1xx`). O operador encontrou os
3 desvios reais em 461,8 s, mas registrou 7 falsos positivos causados pela lista. A lista foi corrigida e o
gerador de desvios passou a ser aleatório (2 a 4 desvios entre 20 combinações) antes das rodadas válidas.

Observações sobre os arquivos:

- `resultados_D4_manual.csv`: a primeira linha de dados (`desvios,255.66,0`) é de uma execução anterior da versão
  antiga do modo manual, que não registrava os achados; não faz parte da rodada piloto. Por isso o cabeçalho tem
  3 colunas e a segunda linha tem 4.
- `resultados_D4_comparacao.csv`: a linha `manual` (0/3) está errada por um defeito de leitura causado por esse
  cabeçalho antigo, corrigido depois no `09_auditoria.py`. Conferência correta: manual 3/3 com 7 falsos
  positivos (461,8 s); automatizado 3/3 sem falsos positivos (4,3 s).

Evidências completas: `evidencias/evidencias_D4.txt`.
