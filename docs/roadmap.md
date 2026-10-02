# Roadmap e status

> Este é o único lugar com o status do projeto. Atualize este arquivo no fim de cada sessão de trabalho. Última atualização: 01/10/2026.

## Onde estamos

A etapa Refine funciona de ponta a ponta com um card real. O próximo marco é ligar o `launchd`, depois de 3 rodadas manuais sem erro.

## Pronto

- [x] Fase 0: Claude Code com GLM, MCPs da Z.ai, conexão do Notion e ambiente Python
- [x] Passo 1: propriedades no banco de inbox e migração de 164 cards para o `Pipeline`
- [x] Passos 2 a 6: `config.py`, `items.py`, `page_writer.py`, `notion_api.py`, `claude_runner.py` e testes
- [x] Prompts v1: `base.md`, `refine.md`, `plan.md`, `execute.md`
- [x] Passo 7: `runner.py`. Primeiro card real refinado em 01/10/2026
- [x] Documentação: `README.md` e pasta `docs/`

## Próximos passos, em ordem

- [ ] Fazer mais 2 rodadas manuais sem erro. A regra pede 3 antes de ligar o `launchd`
- [ ] Decidir o aviso `unrecognized_model`: aceitar o aviso ou testar o nome do modelo sem o sufixo `[1m]`
- [ ] Reler os [termos do Coding Plan](https://docs.z.ai/legal-agreement/subscription-terms) antes de ligar o `launchd`
- [ ] Passo 9: ligar o `launchd`
- [ ] Testar os casos de teste restantes: contato no LinkedIn e pesquisa sobre medicamento
- [ ] Testar as etapas Plan e AI execute com um card real
- [ ] Rodar o piloto de 2 semanas e registrar as métricas

## Para conferir

- No primeiro card de teste, a nota `⚠️ Falha da IA em 01/10 20:56: travado` apareceu 1 minuto depois do primeiro Refinamento. Se foi o teste manual de card travado, está tudo certo. Se não foi, ver o `runner.log` antes das próximas rodadas.
- A segunda rodada escreveu "Re-execução: a rodada anterior travou por falha técnica" no Contexto. A IA leu a nota de erro como parte do card. Avaliar se o `build_context` deve tirar as notas de erro do texto enviado à IA.

## Métricas do piloto

| Métrica | Meta |
| --- | --- |
| Itens refinados | Pelo menos 10 reais em 2 semanas |
| Qualidade | Pelo menos 70% de 👍 |
| Tempo de revisão | Menos de 3 minutos por item |
| Itens que saem do Backlog | Mais do que antes |
| Falhas | Menos de 10%, nenhuma duplicação |
| Manutenção | Menos de 30 minutos por semana |
| Custo extra | Zero (conferir no painel da Z.ai) |

## Depois do piloto

1. Fase 2: página "Revisão de hoje" no Notion, com no máximo 3 decisões por dia, sem notificações.
2. Fase 3: Plan e AI execute para pesquisa e documentação.
3. Fase 4: tarefas de código dentro de um repositório, numa branch nova, sem push nem merge.

## v2

- Editar o workspace: criar e editar itens, notas e projetos em outros bancos do Notion.
- Enviar email, por exemplo uma candidatura para um recrutador.
- Enviar mensagem no WhatsApp, por exemplo para marcar uma consulta.

Regra: ações que não dão para desfazer passam pelo Review antes de acontecer. Fluxo: AI EXECUTE (só rascunho) → REVIEW (aprovação humana) → coluna nova, por exemplo "Enviar" (o runner envia) → DONE.

Pendências da v2: escolher o canal do WhatsApp, achar um MCP do Notion que funcione só com token e conectar a integração aos outros bancos.

## Ideias registradas (não decididas)

- Rodar na nuvem para não depender do Mac ligado: GitHub Actions com agendamento, ou Cloud Scheduler com Cloud Run Jobs no GCP. O código já não tem caminhos pessoais, então a mudança é principalmente empacotar o programa num container.
- Automações do ZCode como plano C: mais simples, mas com intervalo mínimo de 1 hora e com a IA controlando o board.
