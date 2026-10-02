# Arquitetura

## Os papéis

| Papel | Quem faz | O que faz |
| --- | --- | --- |
| Modelo | GLM (`glm-5.3` e `glm-5.3-flash`), pelo plano GLM Coding | Interpreta o card e escreve o texto |
| Agente | Claude Code CLI apontado para o endpoint da Z.ai (`https://api.z.ai/api/anthropic`) | Usa ferramentas: busca na web e leitura de página |
| Gatilho | `launchd` mais `runner.py` | Inicia o trabalho a cada 5 minutos |
| Controle do board | `runner.py`, pela API do Notion | Escolhe os cards, trava, escreve na página, move e marca erro |

O controle do board fica no código, e não na IA, por 3 motivos. Consultar o board pela API não gasta token. A IA não consegue marcar o próprio erro quando falha. As regras de estado ficam cobertas por testes automáticos.

## Módulos

Função pura: só transforma dados, sem rede nem disco. Função imperativa: acessa rede, disco ou outro processo.

| Arquivo | Responsabilidade | Tipo |
| --- | --- | --- |
| `config.py` | Constantes (versão da API `2026-03-11`, 3 cards por rodada, 30 min para travado, 900 s de tempo limite), caminhos, nomes das propriedades, as 3 etapas e `load_settings()` para ler o `.env` | Dados |
| `items.py` | `Item`, `parse_item`, `is_stale`, `select_items`, `next_column`, `props_running`, `props_success`, `props_error` | Pura |
| `page_writer.py` | `needs_original_record`, `build_original_record`, `build_section`, `build_error_note`, `build_context` | Pura |
| `notion_api.py` | `NotionClient`: consulta com paginação, leitura e escrita em markdown, atualização de propriedades. Até 4 tentativas: erro 429 espera o `Retry-After`; erro 5xx e falha de rede esperam 1 s, 2 s e 4 s | Imperativa |
| `claude_runner.py` | `build_command`, `build_env` e `parse_output` (puras); `write_mcp_config` e `run_claude` (imperativas) | Misto |
| `runner.py` | `main`, `fetch_candidates`, `mark_stale_items`, `process_item`, `setup_logging` | Imperativa |

As etapas ficam em `config.py`:

| Coluna | Prompt | Título da seção | Limite de turnos | Pode renomear |
| --- | --- | --- | --- | --- |
| TO REFINE | `refine.md` | 🔍 Refinamento | 15 | Sim |
| PLAN | `plan.md` | 🗺️ Plano | 10 | Não |
| AI EXECUTE | `execute.md` | ✅ Resultado | 25 | Não |

## Sequência de uma rodada

`main` faz isto:

1. Pega a trava `run/runner.lock` (com `fcntl.flock`), sem esperar. Se outra rodada estiver ativa, grava "rodada anterior ainda em andamento" no log e sai.
2. Lê o `.env` e grava `run/mcp.json` com os 2 MCPs da Z.ai.
3. Busca os cards das 3 colunas ⚡.
4. Marca ⚠️ nos cards com ⏳ há mais de 30 minutos (travados).
5. Escolhe até 3 cards e chama `process_item` para cada um, um de cada vez.

`process_item` faz isto com um card:

1. Grava ⏳ rodando e o horário. Essa é a trava contra duplicação.
2. Lê a página em markdown.
3. Se a página não tem "📝 Registro original", escreve essa seção no início. Isso acontece antes de mudar o título, para guardar o texto original.
4. Chama o Claude Code, com o contexto pela entrada padrão (stdin).
5. Escreve a seção da etapa no fim da página.
6. Atualiza as propriedades e move o card.
7. Se qualquer passo falhar, escreve a nota de erro e grava ⚠️. Se essa gravação também falhar (por exemplo, sem internet), a detecção de card travado marca ⚠️ depois de 30 minutos.

## Como o Claude Code é chamado

```bash
~/.local/bin/claude -p --bare \
  --model sonnet \
  --append-system-prompt "TEXTO DE base.md + ARQUIVO DA ETAPA" \
  --output-format json \
  --json-schema "CONTEÚDO DE output_schema.json" \
  --mcp-config run/mcp.json --strict-mcp-config \
  --permission-mode dontAsk \
  --allowedTools "mcp__web-search-prime,mcp__web-reader" \
  --disallowedTools "Bash,Edit,Write,WebSearch,WebFetch,NotebookEdit" \
  --max-turns 15 \
  --no-session-persistence
```

| Opção | Para que serve |
| --- | --- |
| `-p` | Modo não interativo: recebe o texto, responde e sai |
| `--bare` | Ignora CLAUDE.md, hooks, plugins e MCPs configurados no usuário. Assim o comportamento não muda quando a configuração interativa muda |
| `--model sonnet` | O nome "sonnet" é traduzido para `glm-5.3[1m]` pela variável `ANTHROPIC_DEFAULT_SONNET_MODEL` |
| `--append-system-prompt` | Junta `base.md` com o arquivo da etapa |
| `--json-schema` | Obriga a resposta a seguir `output_schema.json`, no campo `structured_output` |
| `--mcp-config` e `--strict-mcp-config` | Libera só os 2 MCPs da Z.ai: busca e leitura de página |
| `--permission-mode dontAsk` | Nega qualquer ferramenta que não esteja liberada, sem perguntar |
| `--allowedTools` e `--disallowedTools` | Libera os 2 MCPs. Bloqueia terminal, edição de arquivos e a busca nativa do Claude Code |
| `--max-turns` | 15, 10 ou 25, conforme a etapa |
| `--no-session-persistence` | Não guarda a sessão no disco |

Outras proteções em `claude_runner.py`:

- O processo recebe só as variáveis de ambiente listadas em `build_env`. O runner não depende do `~/.claude/settings.json`.
- O Claude roda dentro de `workspace/`, uma pasta vazia, e não enxerga outros arquivos do usuário.
- O tempo limite é de 900 segundos.
- As chaves que aparecerem na saída são trocadas por `[redacted]` no log de cada chamada.

## Contrato de saída

[`output_schema.json`](../output_schema.json):

```json
{
  "type": "object",
  "properties": {
    "markdown": { "type": "string", "minLength": 1 },
    "new_title": { "type": ["string", "null"], "maxLength": 120 },
    "ia_status": { "enum": ["ok", "precisa_de_voce"] },
    "suggested_executor": { "enum": ["Humano", "IA", null] }
  },
  "required": ["markdown", "new_title", "ia_status", "suggested_executor"],
  "additionalProperties": false
}
```

- `markdown`: corpo da seção, sem o título. O runner escreve o título com a data.
- `new_title`: título novo. Só é usado na etapa Refine.
- `ia_status`: `ok` deixa o IA status vazio. `precisa_de_voce` grava ❓.
- `suggested_executor`: só é usado quando o Executor do card está vazio.

O `parse_output` confere esse formato uma segunda vez com a biblioteca `jsonschema`. Se a resposta vier fora do formato, o card recebe ⚠️ e não muda de coluna.

## Decisões

| Decisão | Motivo |
| --- | --- |
| Usar o GLM pelo Coding Plan | Muitos tokens disponíveis, sem custo extra |
| Usar o Claude Code como agente | É uma ferramenta oficialmente suportada pelo Coding Plan e já traz o ciclo de agente pronto |
| Não chamar a API do GLM direto do Python | Os [termos do Coding Plan](https://docs.z.ai/legal-agreement/subscription-terms) proíbem usar a cota a partir de aplicações próprias |
| Consultar o Notion a cada 5 minutos (polling) | Um webhook exigiria uma URL pública |
| Usar uma conexão interna do Notion com token | O Notion MCP exige login interativo (OAuth) e não roda sozinho |
| Usar os endpoints de markdown da API do Notion | A API já aceita markdown, então não é preciso converter para blocos |
| IA status como select, e não fórmula | A API não grava valores em propriedades de fórmula |
| Instalador nativo do Claude Code | O `launchd` não carrega o nvm. O instalador nativo usa um caminho fixo: `~/.local/bin/claude` |
| No máximo 3 cards por rodada | Protege a cota do GLM e o tempo de revisão |
| Bloquear a busca nativa do Claude Code | Comportamento previsível no piloto. Os MCPs da Z.ai fazem a busca |
| Harness próprio, e não Hermes Agent | Valor de portfólio, controle total do fluxo e baixo custo para adicionar canais depois |
| Rodar manual antes de ligar o `launchd` | Os erros aparecem na tela, e não escondidos num log |

## Alternativas descartadas

- **Hermes Agent (Nous Research):** pouco valor de portfólio, menos controle sobre o fluxo e um bug aberto com o endpoint do Coding Plan.
- **Script Python chamando a API do GLM direto:** proibido pelos termos do Coding Plan.
- **Notion Custom Agents e Claude agents do Notion:** consomem créditos do Notion e não usam o GLM.
- **Notion Workers:** grátis só durante o beta.
- **Automações do ZCode:** intervalo mínimo de 1 hora, presas a uma pasta local, e a IA passaria a controlar o board. Ficam como plano C.

## Riscos conhecidos

- **Termos do Coding Plan.** Rodar o Claude Code por agendamento pode ser interpretado como uso automatizado. Mitigação: no máximo 3 chamadas a cada 5 minutos, sempre com revisão humana.
- **Markdown recusado pela API do Notion.** O card fica com ⚠️ e o texto bruto fica em `logs/runs/`. O `base.md` lista a sintaxe permitida.
- **`insert_content` está marcado como obsoleto na API.** Ainda funciona. Se for removido, a troca é `replace_content` com a página inteira mais a seção nova.
- **Mac desligado ou dormindo.** Nenhuma rodada acontece nesse tempo.
- **Sites que bloqueiam leitura** (LinkedIn, Shopee, Mercado Livre). A IA guarda o link e escreve "não consegui abrir".
