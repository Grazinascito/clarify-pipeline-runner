# Operação

Como rodar o runner, ler os logs e resolver cards com erro. Todos os comandos rodam dentro de `~/clarify-pipeline-runner`.

## Comandos

| Comando | O que faz |
| --- | --- |
| `.venv/bin/python runner.py --dry-run` | Lista os cards que seriam processados. Não grava nada no Notion e não chama o Claude |
| `.venv/bin/python runner.py --page ID_DO_CARD` | Processa só esse card, se ele estiver numa coluna ⚡ e com IA status vazio ou ❓ |
| `.venv/bin/python runner.py` | Rodada completa: até 3 cards. É o mesmo comando que o `launchd` executa |
| `.venv/bin/pytest -q` | Roda os testes automáticos |
| `tail -f logs/runner.log` | Mostra o log em tempo real |

O ID do card é a parte final da URL da página, com ou sem hífens.

## Logs

| Arquivo | Conteúdo |
| --- | --- |
| `logs/runner.log` | Uma linha por evento: data, hora, ID do card, etapa e resultado. Girado a cada 1 MB, guarda 5 arquivos |
| `logs/runs/AAAAMMDDTHHMMSS-ID.json` | Saída bruta de cada chamada ao Claude: etapa, código de saída, stdout e stderr. As chaves aparecem como `[redacted]` |
| `logs/launchd.out.log` e `logs/launchd.err.log` | Saída capturada pelo `launchd`, quando ele está ligado |

Resultados que aparecem no `runner.log`:

| Resultado | Significado |
| --- | --- |
| `ok` | Etapa concluída, card movido |
| `precisa_de_voce` | Etapa concluída, card com ❓ |
| `dry-run TÍTULO` | Card que seria processado |
| `nenhum card para processar` | Nenhum card nas colunas ⚡ com IA status vazio ou ❓ |
| `fora da rodada` | O card do `--page` não está numa coluna ⚡, ou está com ⏳ ou ⚠️ |
| `rodada anterior ainda em andamento` | Outra rodada está com a trava. Nada foi feito |
| `travado` | Card ficou com ⏳ por mais de 30 minutos e recebeu ⚠️ |
| `falha na rodada: ...` | Erro antes de processar os cards, por exemplo `.env` incompleto ou falha na consulta ao Notion |

## Tipos de erro na nota ⚠️

| Tipo | Causa | O que fazer |
| --- | --- | --- |
| `timeout` | O Claude passou de 900 segundos | Ver o arquivo em `logs/runs/`. Talvez a tarefa seja grande demais para uma rodada |
| `exit_code` | O Claude saiu com erro e sem JSON válido | Ler o stderr no arquivo de `logs/runs/` |
| `invalid_json` | A saída do Claude não é JSON | Ler o stdout no arquivo de `logs/runs/` |
| `max_turns` | O Claude atingiu o limite de turnos da etapa | Tentar de novo. Se repetir, simplificar o card ou aumentar `max_turns` em `config.py` |
| `schema` | A resposta veio sem `structured_output` ou fora do formato | Ver o arquivo de `logs/runs/`. Se repetir, revisar o prompt |
| `api_error` | O Claude devolveu erro: cota do GLM esgotada ou falha de autenticação | Conferir o painel da Z.ai e a `GLM_API_KEY` |
| `rede` | Sem conexão com o Notion depois de 4 tentativas | Conferir a internet e tentar de novo |
| `notion` | A API do Notion recusou a gravação, por exemplo markdown inválido | Ver o `runner.log`. O texto da IA fica em `logs/runs/` |
| `travado` | O card ficou com ⏳ por mais de 30 minutos | Ver se a rodada foi interrompida (Mac dormiu, terminal fechado) |
| Outro nome, como `ValueError` | Erro inesperado no código | Ver o `runner.log` e registrar como bug |

## Tentar de novo um card com ⚠️

1. Leia a nota de erro no fim da página do card.
2. Corrija a causa, se for possível.
3. Apague o valor de `IA status`. O card continua na mesma coluna e roda na próxima rodada.

A nota de erro fica na página, e a IA lê essa nota na rodada seguinte. Se ela confundir a IA, apague a nota antes de tentar de novo.

## Card com ❓

1. Leia as perguntas na seção mais recente.
2. Escreva as respostas embaixo das perguntas ou numa seção `## ✏️ Ajustes`.
3. Mova o card para a coluna certa. Se o card já estiver numa coluna ⚡, ele roda de novo na próxima rodada.

## Um card não foi processado

Confira nesta ordem:

1. `Pipeline` é TO REFINE, PLAN ou AI EXECUTE?
2. `IA status` está vazio ou é ❓?
3. Já havia 3 cards à frente dele na fila? O limite é de 3 cards por rodada.
4. O `launchd` está ligado e o Mac estava acordado?
5. O `runner.log` mostra `falha na rodada`?

## Consumo da cota

O painel da Z.ai mostra o uso do Coding Plan. Cada chamada ao Claude gasta alguns prompts da cota. Confira o painel uma vez por semana durante o piloto. Nenhuma cobrança avulsa deve aparecer.
