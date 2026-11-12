# Checklist de testes — AI Maintenance Copilot

O projeto faz 2 tipos de verificação distintos: **testes automatizados das regras Python** (24 testes nesta versão) e **avaliação manual de respostas do Gemini**. Não confunda os dois: os testes Python não validam automaticamente a qualidade de todas as respostas da IA.

## A. Dados de demonstração, sem upload

- Dashboard: 10 equipamentos, 96,7% de disponibilidade média, 84.000 u.m. em custos, quatro equipamentos de criticidade A.
- Maior score: **Pump P-04 — 88,2**.
- Menor score: **Steam Valve V-08 — 11,4**.
- Menor custo: **Steam Valve V-08 — 1.300 u.m.**.
- O Pareto de falhas decorre de eventos sintéticos gerados separadamente, não dos KPIs de confiabilidade.

## B. Teste do CSV (foco na importação)

1. Envie SOMENTE `data/exemplo_indicadores.csv` no primeiro uploader: os 10 KPIs continuam; a aba Pareto deve informar que não há histórico de falhas. **Não deve reutilizar os eventos fictícios antigos**.
2. Envie também `data/exemplo_eventos.csv` no segundo uploader: o Pareto, o mix CORR/PREV e a evolução mensal passam a aparecer.
3. Troque os dois uploads por `data/cenario2_indicadores.csv` + `data/cenario2_eventos.csv`: aparecerão **14 ativos inteiramente diferentes** e o ranking mudará.
4. Teste `data/exemplo_indicadores_ponto_virgula.csv` no primeiro uploader: valores numéricos com vírgula decimal devem ser lidos corretamente.
5. Teste `data/exemplo_invalido.csv`: a aplicação deve bloquear a importação, explicar o erro e não enviar nada ao Gemini.

## C. Perguntas de validação do Gemini

As respostas podem ser escritas de formas diferentes. Verifique o **conteúdo factual**, não palavras exatas.

| Pergunta | Esperado |
|---|---|
| Qual ativo tem maior prioridade? | Pump P-04, score 88,2 na demo original. |
| Qual ativo tem o menor custo? | Steam Valve V-08, 1.300 **u.m.**, jamais 'R$' sem origem confirmada. |
| Quais tipos de falha aparecem com maior frequência? | Usar as contagens do Pareto (empates devem ser mencionados); sem histórico, declarar que não há dados. |
| Qual ROI de modernizar a Pump P-04? | Não calcular sem investimento previsto, economia/benefícios e período. |
| Qual foi a causa-raiz da falha? | Não inferir diagnóstico a partir de apenas score, MTBF, MTTR ou frequência de famílias. |

## D. Relatório

- Exportar PDF após uma consulta Gemini.
- Confirmar KPI, ranking, Pareto, mix, questionamento e análise atualizados.
- No modo sem eventos, o relatório **não** pode exibir o Pareto fictício.
- O relatório deve identificar dados sintéticos e explicar as limitações de confiabilidade.

## E. Limites

- A IA pode errar, mesmo com prompt estruturado. Conferência humana ainda é necessária.
- O ranking usa pesos heurísticos, não modelo de previsão de falhas.
- O aplicativo não executa agentes autônomos, nem n8n, nem API REST própria (funcionalidades posteriores).


## Visual inspection for V4 (manual browser check)

- In **Falhas & Pareto**, confirm there is only one quantitative axis and no overlapping cumulative curve. Percentual acumulado should display in the table.
- In **Confiabilidade**, check that all filtered assets with both MTBF and MTTR appear as points in the same scatter chart and the median reference rules remain within the plotted axes.
- In **Dados & metodologia**, confirm the number of imported assets, KPI completeness and source names update after CSV uploads and that no recruitment-oriented test prompts are shown.
- Verify the PDF, Gemini integration and original CSV upload as before.

## V5: Agente Gemini com funções Python

Execute com `Agente com ferramentas` selecionado:

1. **Qual equipamento tem maior custo?** → deve consultar `get_equipment_ranking` e retornar Pump P-04 (18.300 u.m.) na demo.
2. **Qual é o MTBF e MTTR da Pump P-04?** → deve consultar `get_equipment_details` e mencionar 112 h e 9,3 h.
3. **Quais famílias de falha são mais comuns?** → deve consultar `get_failure_analysis`; observar os valores do CSV de eventos ativo.
4. Com `cenario2_indicadores.csv` apenas (sem eventos), a resposta NÃO pode inventar famílias de falhas.
5. Em cada consulta do agente, expandir **Execução verificável do agente** e conferir o nome, argumentos e resultado das funções realmente chamadas.

Lembrete: uma consulta de agente pode fazer mais de uma requisição ao modelo. Não é um sistema multiagente nem um modelo que sabe executar reparos.

## V6: Teste obrigatório do fluxo multiagente

1. Ative **Orquestração multiagente**.
2. Pergunte: "Qual ativo tem maior custo, qual tem menor MTBF e que verificações deveríamos priorizar?"
3. Confira: **Analista** realizou pelo menos uma chamada de ferramenta; **Coordenador Python** registrou `handoff`; **Consultor** produziu resposta.
4. Leia o log de ferramentas e verifique valores contra o dashboard.
5. Use CSV alternativo para conferir mudanças de rankings; sem histórico enviado, o consultor deve admitir a falta de dados para Pareto.
6. Baixe o PDF e confira se inclui a resposta final do Consultor, não apenas a intermediária do Analista.

**Limitações:** sem multi-modelos ou delegação dinâmica; testes unitários usam resposta simulada e não substituem a execução real da API Gemini.


## V6.1 — Correções finais de interface, rastreabilidade e histórico

1. No modo **Orquestração multiagente**, execute uma pergunta e confirme que o contador **Consultas concluídas** passa imediatamente de `0/3` para `1/3`, sem precisar atualizar manualmente. O contador não mede o número total de chamadas à API.
2. Abra **Orquestração verificável** e confira se a síntese do Analista está formatada (títulos e listas), e se as etapas do fluxo aparecem em uma tabela legível.
3. Com dados de demonstração, pergunte: **"Quais falhas registradas justificam investigar Pump P-04 e Compressor C-02? Diferencie histórico de causa-raiz e cite as famílias por equipamento."**
4. Verifique que as evidências complementares têm `get_equipment_failure_history` por ativo, e que as recomendações não atribuem o Pareto global a uma máquina específica.
5. Importe `data/cenario2_indicadores.csv` (14 ativos) e `data/cenario2_eventos.csv` (90 eventos) nos dois uploaders. Pergunte: **"Compare os dois equipamentos de maior prioridade e sugira verificações usando apenas famílias de falha registradas em cada um."** Confirme o histórico exibido contra o CSV.
6. Remova o CSV de eventos e pergunte sobre causas de falha de um ativo. A IA deve informar que não há histórico por equipamento e não atribuir um modo de falha.
7. Baixe o PDF e confira se inclui a resposta final do Consultor. Antes de publicar, abra o site numa janela anônima e repita ao menos uma consulta.

As recomendações continuam sendo hipóteses para inspeção; famílias registradas **não** comprovam causas-raiz. Os testes automatizados utilizam clientes Gemini simulados e não substituem o teste real da API.


## V6.2 - Final checks before publication

1. Upload both `data/cenario2_indicadores.csv` and `data/cenario2_eventos.csv`.
2. Select `Orquestração multiagente`. Ask the agents to prioritize CP-10 and MX-12 and relate registered failure categories to verification suggestions.
3. Check that any **Hydraulic** suggestion for `Compressor CP-10` starts by recommending checking the maintenance records and the equipment manual/configuration; the family label alone is not evidence of a hydraulic circuit.
4. Confirm that the **final consultant answer** is displayed, and the analyst synthesis and technical traces stay **collapsed** until expanded.
5. Download the PDF and verify the second page shows the selected AI mode and count of Gemini requests and tools. Confirm it includes the final answer, not the intermediate analyst's draft.
6. Open the PDF locally and check the pages for clipping or duplicated blocks.
7. Never publish `.streamlit/secrets.toml` or a real API key.
