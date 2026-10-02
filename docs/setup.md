# Instalação

Passos para instalar o clarify-pipeline-runner do zero num Mac. Testado em 01/10/2026 com macOS 26.5.1, Python 3.14.6 e Claude Code 2.1.286.

## Pré-requisitos

- Uma key do plano GLM Coding (Z.ai).
- Acesso de edição ao banco de inbox no Notion.
- Python 3 instalado no Mac.

## 1. Instalar o Claude Code

```bash
curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude --version
```

O instalador nativo coloca o programa em `~/.local/bin/claude`. Esse caminho fixo é necessário porque o `launchd` não carrega o nvm.

## 2. (Opcional) Configurar o GLM para uso interativo

Este passo serve só para usar o Claude Code no terminal. O runner passa as próprias variáveis e não depende deste arquivo.

Crie `~/.claude/settings.json` conforme o [guia da Z.ai](https://docs.z.ai/devpack/tool/claude):

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sua_key_glm",
    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3[1m]",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3[1m]",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash[1m]",
    "API_TIMEOUT_MS": "3000000"
  }
}
```

Teste: `claude -p "Responda só: ok" --output-format json`. Esperado: campo `result` igual a `ok`. Confira no painel da Z.ai se o uso do Coding Plan aumentou.

## 3. Criar a conexão do Notion

1. Abra o Developer portal do Notion → Connections → New connection.
2. Tipo Internal. Nome: `clarify-pipeline-runner`.
3. Capacidades: Read content, Update content, Insert content. Sem comentários e sem informação de usuários.
4. Copie o token.
5. Abra o banco original de inbox (e não uma visão vinculada) → menu ⋯ → Connections → adicione `clarify-pipeline-runner`.

## 4. Criar as propriedades no banco

Os nomes precisam ser exatamente estes, porque o `config.py` usa esses textos.

| Propriedade | Tipo | Opções |
| --- | --- | --- |
| Pipeline | Select | BACKLOG, TO REFINE, REFINED, PLAN, HUMAN EXECUTE, AI EXECUTE, REVIEW, DONE, ARCHIVED |
| Executor | Select | Humano, IA |
| IA status | Select | ⏳ rodando, ❓ precisa de você, ⚠️ erro |
| IA atualizado em | Data com horário | (nenhuma) |
| Avaliação | Select | 👍, 👎 |

O runner também lê `Name`, `Details`, `Type`, `Area`, `Due Date` e `Created`. O banco precisa ter essas propriedades com esses nomes.

## 5. Baixar o código e criar o ambiente Python

```bash
git clone https://github.com/Grazinascito/clarify-pipeline-runner.git ~/clarify-pipeline-runner
cd ~/clarify-pipeline-runner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

`chmod 600` deixa o `.env` legível só pelo seu usuário, porque ele guarda chaves secretas.

## 6. Preencher o `.env`

| Variável | Valor |
| --- | --- |
| `NOTION_TOKEN` | Token da conexão criada no passo 3 |
| `GLM_API_KEY` | Key do plano GLM Coding |
| `NOTION_DATA_SOURCE_ID` | ID da data source do banco de inbox (data source é a tabela de dados dentro do banco; a API nova consulta a data source) |

Se faltar uma variável, o runner para com a mensagem `Falta NOME no .env`.

Não é preciso configurar os MCPs da Z.ai. O runner gera `run/mcp.json` sozinho a partir da `GLM_API_KEY`.

## 7. Verificar

```bash
.venv/bin/pytest -q
.venv/bin/python runner.py --dry-run
```

Esperado: todos os testes passam, e o dry-run lista os cards das colunas ⚡ (ou `nenhum card para processar`) sem gravar nada no Notion.

Teste da API, se o dry-run falhar:

```bash
curl -X POST https://api.notion.com/v1/data_sources/$NOTION_DATA_SOURCE_ID/query \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Notion-Version: 2026-03-11" \
  -H "Content-Type: application/json" \
  -d '{"page_size": 1}'
```

Esperado: HTTP 200 com 1 item em `results`.

## 8. Ligar o agendamento (só depois de 3 rodadas manuais sem erro)

O `launchd` não entende `~` e exige caminhos completos. Por isso o modelo usa o texto `{{HOME}}`, e o comando abaixo troca esse texto pelo `$HOME` de quem instala.

Ligar:

```bash
sed "s|{{HOME}}|$HOME|g" launchd/clarify-pipeline-runner.plist.template > ~/Library/LaunchAgents/local.clarify-pipeline-runner.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.clarify-pipeline-runner.plist
```

Conferir: `launchctl print gui/$(id -u)/local.clarify-pipeline-runner`. Esperado: `run interval = 300`.

Desligar:

```bash
launchctl bootout gui/$(id -u)/local.clarify-pipeline-runner
```
