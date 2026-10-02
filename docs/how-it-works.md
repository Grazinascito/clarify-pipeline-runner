# Como o fluxo funciona

O board do Notion agrupa os cards pela propriedade `Pipeline`. Cada grupo é uma coluna. ⚡ marca as colunas que acionam a IA.

## Colunas

| Coluna | Quem age | O que acontece | Para onde o card vai |
| --- | --- | --- | --- |
| BACKLOG | Você | Registro capturado, ainda sem tratamento | Você move para TO REFINE |
| TO REFINE ⚡ | IA | Escreve a seção "🔍 Refinamento" e renomeia o card. Sugere o Executor quando ele está vazio | REFINED, sempre |
| REFINED | Você | Lê o refinamento, responde as perguntas e escolhe o Executor | PLAN, HUMAN EXECUTE ou AI EXECUTE |
| PLAN ⚡ | IA | Escreve a seção "🗺️ Plano" | Executor Humano: HUMAN EXECUTE. Executor IA sem pergunta que bloqueia: AI EXECUTE. Executor vazio ou pergunta que bloqueia: REFINED com ❓ |
| HUMAN EXECUTE | Você | Você faz a tarefa | REVIEW ou DONE |
| AI EXECUTE ⚡ | IA | Escreve a seção "✅ Resultado" | REVIEW, sempre |
| REVIEW | Você | Aprova, ou escreve ajustes e devolve | DONE, ou AI EXECUTE com a seção `## ✏️ Ajustes` |
| DONE | Ninguém | Tarefa concluída | Fim |
| ARCHIVED | Ninguém | Item descartado. Não aciona a IA | Fim |

O card sai do PLAN direto para AI EXECUTE quando o Executor é IA e o plano não tem pergunta que bloqueia. A IA executa esse card na rodada seguinte, até 5 minutos depois.

## IA status

| Valor | Significado | Quem grava | O que você faz |
| --- | --- | --- | --- |
| (vazio) | Tudo certo | Runner | Nada |
| ⏳ rodando | O runner está processando o card agora | Runner | Esperar. Depois de 30 minutos, o runner troca para ⚠️ |
| ❓ precisa de você | A IA tem uma pergunta que bloqueia o próximo passo | Runner, a partir da resposta da IA | Responder na página e mover o card |
| ⚠️ erro | A rodada falhou ou o card ficou travado | Só o runner. A IA nunca grava esse valor | Ler a nota de erro no fim da página e o [operations.md](operations.md). Para tentar de novo, apagar o valor |

## Quais cards entram numa rodada

Um card entra quando as duas condições são verdadeiras:

1. `Pipeline` é TO REFINE, PLAN ou AI EXECUTE.
2. `IA status` está vazio ou é ❓. Cards com ⏳ ou ⚠️ ficam de fora.

Ordem: primeiro TO REFINE, depois PLAN, depois AI EXECUTE. Dentro de cada coluna, o card com o `Created` mais antigo vem primeiro. Cada rodada processa no máximo 3 cards, somando todas as colunas. Com a opção `--page`, a rodada processa só aquele card.

Atenção: um card com ❓ numa coluna ⚡ roda de novo. Escreva a resposta na página antes de mover o card.

## O que o runner escreve na página

- **"📝 Registro original"**: vai para o início da página, só na primeira passagem. Guarda o título e o `Details` originais. Ninguém edita essa seção.
- **Seção da etapa**: vai para o fim da página, com o título `## 🔍 Refinamento — dd/mm/aaaa HH:mm` (ou 🗺️ Plano, ou ✅ Resultado). O runner escreve o título. A IA escreve o corpo. Uma nova rodada cria uma nova seção com outra data e não apaga a anterior. A IA usa a seção com a data mais recente.
- **Nota de erro**: uma linha no fim da página, no formato `⚠️ Falha da IA em dd/mm HH:mm: tipo do erro. Log: nome do arquivo.`

## Propriedades que o runner altera

- **Pipeline**: move o card para a próxima coluna.
- **IA status** e **IA atualizado em**: em toda rodada.
- **Name**: só na etapa Refine, quando a IA devolve um título novo.
- **Executor**: só quando está vazio. A escolha manual nunca é sobrescrita.

O runner não altera `Type`, `Area`, `Details`, `Due Date`, `Status` nem `Avaliação`.

## Como pedir ajustes

1. Escreva uma seção `## ✏️ Ajustes` na página do card, com o que deve mudar.
2. Mova o card para a coluna que deve rodar de novo: AI EXECUTE depois do Review, ou TO REFINE e PLAN para refazer essas etapas.
3. A IA lê a página inteira, incluindo os Ajustes, e cria uma seção nova.

## Regras que a IA segue

Resumo dos prompts. O texto completo está em [`prompts/`](../prompts/).

- Faz só trabalho que dá para desfazer: pesquisa, resumo, rascunho e lista de links. Nunca envia mensagem, nunca compra e nunca contata ninguém.
- Separa as afirmações em Fato, Hipótese e Pergunta.
- Em saúde, direito e finanças, dá só informação com fonte, sem orientação.
- Usa só busca na web e leitura de página. Não tem terminal, arquivos nem acesso ao Notion.
- Respeita limites de tamanho: Refine com cerca de 250 palavras, Plan com cerca de 250 palavras e até 7 passos, Execute com cerca de 600 palavras nos Entregáveis.
- Cards do Type 🔁 Recorrente não são refinados. Eles entram só na revisão diária.

## Avaliação

Depois de ler o resultado, marque 👍 ou 👎 na propriedade `Avaliação`. Esse valor mede a qualidade do piloto. A meta é pelo menos 70% de 👍.
