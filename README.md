# Pipefy Young Guns — Credit Ledger Idempotency Challenge

Solução para aplicação idempotente de créditos com Python e SQLite, cobrindo restart, concorrência, múltiplas instâncias e validação de entrada.

## Resumo da solução

O código original mantinha em memória os IDs dos eventos processados. Esse controle era perdido após um restart e não era compartilhado entre instâncias concorrentes.

A solução usa o SQLite como fonte de verdade: `event_id` é a `PRIMARY KEY` de `applied_events`, e `INSERT OR IGNORE` resolve atomicamente a disputa por um evento. O valor de `cursor.rowcount` informa se esta chamada inseriu o registro; a conta só é criada ou atualizada quando isso acontece. O registro do evento e o crédito ficam na mesma transação, depois da validação da entrada.

## Problemas corrigidos

| Problema | Correção |
|----------|----------|
| Estado de idempotência apenas em memória | O histórico passou para `applied_events` no SQLite. |
| Perda do histórico no restart | Eventos persistem no arquivo do banco. |
| Múltiplas instâncias com memória separada | Todas consultam a mesma restrição persistente. |
| Ausência de unicidade de `event_id` | `event_id` tornou-se `PRIMARY KEY`. |
| Race condition de *check-then-act* | `INSERT OR IGNORE` combina tentativa e decisão no banco. |
| Decisão idempotente fora do banco | `cursor.rowcount` identifica o vencedor da inserção. |
| Inputs inválidos | `InvalidCreditError` é lançado antes de qualquer mutação. |
| `applied` não refletia o resultado persistente | O retorno agora deriva do resultado real do `INSERT`. |

## Como funciona

O fluxo de `CreditLedger.apply_credit` é:

1. Valida `event_id`, `account_id` e `amount_cents`.
2. Abre uma transação no SQLite.
3. Tenta registrar o `event_id` com `INSERT OR IGNORE`.
4. O SQLite aplica a unicidade definida pela `PRIMARY KEY`.
5. Verifica `cursor.rowcount` para saber se esta chamada inseriu o evento.
6. Somente o vencedor cria a conta, se necessário, e atualiza o saldo.
7. Chamadas duplicadas não alteram o saldo.
8. Retorna `CreditResult` com `applied` e `balance_cents` correspondentes ao estado persistido.

A concorrência funciona porque a restrição de unicidade está no SQLite compartilhado: threads e instâncias diferentes disputam a mesma fonte persistente de verdade.

## Comportamentos atendidos

- [x] Mesmo `event_id` aplicado uma única vez
- [x] Idempotência após restart
- [x] Concorrência entre threads
- [x] Duas instâncias utilizando o mesmo banco
- [x] Validação de inputs inválidos
- [x] Reutilização de `event_id` após tentativa inválida
- [x] Eventos diferentes continuam acumulando
- [x] Testes isolados por arquivo SQLite

## Testes

Além dos testes básicos e do teste de restart `test_duplicate_event_is_ignored_after_restart`, foram adicionados:

- `test_concurrent_duplicate_event_is_applied_only_once`
- `test_concurrent_duplicate_event_across_instances_is_applied_once`
- `test_invalid_credit_has_no_effect`
- `test_event_id_can_be_reused_after_invalid_credit`
- `test_different_events_accumulate_when_applied_concurrently`

Os testes concorrentes usam `threading.Barrier` para sincronizar o início das chamadas e aumentar a chance real de colisão. Nos cenários de evento duplicado, verificam que exatamente uma chamada retorna `applied=True`, as demais retornam `False` e o saldo final contém um único crédito.

Cada teste recebe um arquivo SQLite temporário e isolado por meio da fixture `database_path`.

## Como executar

Requisito: Python 3.11 ou superior.

No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

No Prompt de Comando (`cmd`):

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m pytest
```

O workflow de CI em `.github/workflows/ci.yml` também instala as dependências e executa `pytest` com Python 3.12 em pull requests e pushes para `main`.

## Uso de IA

Usei o Codex como apoio para revisar a implementação e os testes e para organizar esta documentação. As sugestões aceitas foram confrontadas com o código e com os requisitos do desafio. Evitei adicionar mecanismos não implementados, dependências ou refatorações fora do escopo; a decisão de idempotência permanece simples e centralizada no SQLite.

## Limitação reconhecida

A solução depende de todas as instâncias acessarem o mesmo arquivo SQLite. Ela atende ao cenário proposto, inclusive com múltiplas instâncias no mesmo banco, mas não é uma arquitetura para execução distribuída em máquinas sem um arquivo compartilhado. Além disso, contenção prolongada de escrita pode exceder o timeout configurado de 5 segundos.

## Vídeo técnico

[Assista à apresentação técnica no YouTube](https://youtu.be/_NOs10y3AVE).
