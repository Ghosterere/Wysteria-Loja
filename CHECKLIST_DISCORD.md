# Checklist final de validação no Discord — LojaDC

Este roteiro valida as partes que não podem ser comprovadas apenas com testes locais. Execute em um servidor de homologação ou em canais privados do servidor real, usando uma cópia do banco e os mesmos cargos/permissões da produção.

## Preparação

- Faça backup de `lojas.db` e use um `DATABASE_PATH` separado durante a homologação.
- Separe quatro contas: **ADM** com Gerenciar Servidor, **LOJISTA**, **CLIENTE** e **TERCEIRO** sem acesso ao pedido.
- Deixe o cargo do bot acima do cargo configurado em `LOJISTA_ROLE_NAME`.
- Habilite **Server Members Intent** e **Message Content Intent** no Discord Developer Portal.
- Convide o bot com os escopos `bot` e `applications.commands`.
- Configure no `.env` todas as categorias e canais. Não registre o token em evidências ou capturas.
- Mantenha o terminal visível e salve o traceback completo de qualquer falha.

Permissões mínimas do bot: Ver canal, Enviar mensagens, Enviar mensagens em threads, Inserir links, Anexar arquivos, Ler histórico, Criar threads privadas, Gerenciar threads, Gerenciar canais, Gerenciar mensagens e Gerenciar cargos.

## 1. Inicialização e configuração

### [ ] T01 — Inicialização e comandos sincronizados — OBRIGATÓRIO

- **Fazer:** iniciar com `.\.venv\Scripts\python.exe bot.py`; aguardar `Bot conectado` e a sincronização. Digitar `/painel` e confirmar que todos os comandos aparecem.
- **Esperado:** nenhuma exceção; conexão mantida; comandos do `GUILD_ID` aparecem imediatamente.
- **Erro:** `4014`, `Missing Access`, loop de reconexão, comando inexistente ou aviso de ID/tipo inválido. `4014` normalmente indica intent privilegiado não habilitado/aprovado.
- **Provável ponto:** configuração no topo de `bot.py`, `setup_hook`, `on_ready` e `validate_guild_configuration`.

### [ ] T02 — Permissões e privacidade — OBRIGATÓRIO

- **Fazer:** conferir o terminal após iniciar e testar os canais com a conta TERCEIRO. `mesa-de-atendimento`, avaliações, boost e vitrines podem ser abertos; categorias de tickets, logs e solicitações devem ser privados.
- **Esperado:** nenhum aviso de permissão; TERCEIRO não vê tickets, logs ou candidaturas.
- **Erro:** aviso de permissão, canal administrativo público ou bot incapaz de enviar embed/anexo.
- **Provável ponto:** `validate_guild_configuration`, permissões dos canais/categorias no Discord e IDs do `.env`.

### [ ] T03 — Painel e isolamento entre usuários — OBRIGATÓRIO

- **Fazer:** CLIENTE executa `/painel`, navega por lojas e pedidos. TERCEIRO tenta usar os componentes do painel do CLIENTE.
- **Esperado:** painel efêmero abre; navegação responde uma vez; TERCEIRO recebe “Esse painel pertence a outra pessoa”.
- **Erro:** “A interação falhou”, `InteractionResponded`, painel público ou outro usuário controla o painel.
- **Provável ponto:** `send_main_panel`, `HomePanelView`, `HomeActionSelect` e `BasePanelView.interaction_check`.

## 2. Candidatura e habilitação do lojista

### [ ] T04 — Envio e duplicidade de candidatura — OBRIGATÓRIO

- **Fazer:** CLIENTE usa `/solicitar_lojista`, preenche os dois campos e envia; tenta enviar novamente antes da análise.
- **Esperado:** uma mensagem com Aprovar/Recusar aparece no canal privado; a segunda tentativa é recusada como pendente.
- **Erro:** mensagem duplicada, candidatura salva sem mensagem, campos vazios aceitos ou exposição pública.
- **Provável ponto:** `SellerApplicationModal`, `StoreDatabase.create_seller_application` e `SellerApplicationReviewView`.

### [ ] T05 — Recusa com motivo — OBRIGATÓRIO

- **Fazer:** TERCEIRO tenta recusar; depois ADM recusa, primeiro com motivo vazio e depois com motivo válido.
- **Esperado:** TERCEIRO é bloqueado; motivo vazio é recusado; a mensagem final mostra status recusado e perde os botões.
- **Erro:** usuário comum revisa, recusa sem motivo, botões continuam ativos ou status não persiste.
- **Provável ponto:** `SellerApplicationActionButton`, `SellerApplicationRejectModal` e `review_seller_application`.

### [ ] T06 — Aprovação e atribuição do cargo — OBRIGATÓRIO

- **Fazer:** enviar nova candidatura; ADM aprova; conferir o cargo no candidato e reiniciar o bot.
- **Esperado:** cargo atribuído uma vez, mensagem marcada como aprovada e candidatura não volta após reinício.
- **Erro:** cargo não chega, pedido continua pendente, botão responde duas vezes ou candidatura reaparece.
- **Provável ponto:** `SellerApplicationActionButton.callback`, `find_lojista_role`, `claim_seller_application` e `setup_hook`.

### [ ] T07 — Falhas seguras na aprovação — OBRIGATÓRIO

- **Fazer:** repetir em candidaturas de teste com: cargo inexistente, cargo acima do bot, permissão Gerenciar Cargos retirada e candidato fora do servidor.
- **Esperado:** mensagem clara em todos os casos; nenhum status aprovado sem cargo; candidatura permanece pendente quando recuperável.
- **Erro:** cargo parcial, status preso em `processando`, traceback sem resposta ou aprovação de usuário ausente.
- **Provável ponto:** bloco `approve` de `SellerApplicationActionButton`, `release_seller_application_claim` e hierarquia de cargos do servidor.

## 3. Loja, produtos e termos

### [ ] T08 — Criação e autorização da loja — OBRIGATÓRIO

- **Fazer:** sem cargo, tentar `/criar_loja` e `/painel_loja`; depois, como LOJISTA, criar uma loja pelo comando e outra pelo botão do painel. Tentar repetir o nome.
- **Esperado:** usuário sem cargo é bloqueado; ambas as criações funcionam; nome vazio/duplicado é rejeitado.
- **Erro:** criação sem cargo, modal sem resposta, loja duplicada ou loja criada sem aparecer no painel.
- **Provável ponto:** `ensure_lojista_member`, `create_shop`, `CreateShopModal` e `StoreDatabase.create_shop`.

### [ ] T09 — Produtos e ativação — OBRIGATÓRIO

- **Fazer:** criar dois produtos com preços diferentes; editar um; desativá-lo; abrir a loja como CLIENTE; reativá-lo; atualizar o catálogo.
- **Esperado:** preço/descrição atualizam; produto desativado some para CLIENTE mas permanece no gerenciamento; reativado volta.
- **Erro:** produto inativo comprável, edição na loja errada, preço divergente ou produto perdido após reinício.
- **Provável ponto:** `ProductCreateModal`, `ProductEditModal`, `ToggleSelectedProductButton`, `list_products` e `get_product`.

### [ ] T10 — Status e termos da loja — OBRIGATÓRIO

- **Fazer:** configurar termos; fechar a loja; tentar comprar; reabrir; alternar disponibilidade entre disponível, ocupado, ausente e fechado.
- **Esperado:** vitrine reflete as mudanças; loja fechada/indisponível não aceita compra; termos aparecem antes do formulário.
- **Erro:** compra em loja fechada, termos antigos na vitrine ou estado diferente entre painel e banco.
- **Provável ponto:** `ShopTermsModal`, `ShopStatusModal`, `set_shop_terms`, `set_shop_status` e `create_order_and_ticket`.

## 4. Vitrines públicas

### [ ] T11 — Publicação inicial — OBRIGATÓRIO

- **Fazer:** usar Divulgar loja e escolher um canal aberto. Repetir em um canal onde o bot não tenha Enviar mensagens/Inserir links.
- **Esperado:** uma vitrine aparece no canal permitido; o canal bloqueado gera resposta clara e não cria registro inválido.
- **Erro:** “A interação falhou”, publicação parcial, canal incorreto ou traceback de `AppCommandChannel`.
- **Provável ponto:** `PublishShopChannelSelect.callback`, `PublishShopView` e `upsert_shop_publication`.

### [ ] T12 — Atualização e ausência de duplicatas — OBRIGATÓRIO

- **Fazer:** publicar duas vezes no mesmo canal; alterar nome, preço, status, termos e produto; observar a mensagem pública. Excluir manualmente a mensagem e publicar novamente.
- **Esperado:** existe uma mensagem por loja/canal; ela usa dados atuais; mensagem apagada é recriada e registrada.
- **Erro:** duplicatas, dados antigos reaparecem, botão abre loja errada ou mensagem apagada impede nova publicação.
- **Provável ponto:** `PublishShopChannelSelect`, `sync_shop_public_panels`, `shop_publications` e `PublicPublishedShopView`.

## 5. Compra e criação do atendimento

### [ ] T13 — Compra simples e comando direto — OBRIGATÓRIO

- **Fazer:** CLIENTE compra um produto pelo `/painel`; depois usa `/comprar_produto` com quantidade e briefing explícitos.
- **Esperado:** preço é preço unitário × quantidade; briefing permanece; pedido aparece em `/meus_pedidos` e `/pedidos_loja`; ticket é criado.
- **Erro:** quantidade volta para 1, briefing some, total incorreto, pedido duplicado ou sucesso sem pedido salvo.
- **Provável ponto:** `PurchaseModal`, `buy_product`, `create_order_and_ticket` e `StoreDatabase.create_order`.

### [ ] T14 — Aceite e alteração concorrente dos termos — OBRIGATÓRIO

- **Fazer:** iniciar compra com termos; aceitar; antes de enviar o modal, LOJISTA altera os termos; CLIENTE envia o formulário antigo. Depois refaz com os termos novos.
- **Esperado:** formulário antigo é rejeitado; o novo pedido registra texto e horário dos termos atuais. Quantidade/briefing do comando direto são preservados após o aceite.
- **Erro:** compra aceita termos antigos, pedido sem termos, quantidade perdida ou duas respostas à mesma interação.
- **Provável ponto:** `TermsAcceptanceButton`, `TermsAcceptanceView`, `PurchaseModal` e validação de `accepted_terms_text` em `create_order_and_ticket`.

### [ ] T15 — Múltiplos produtos — OBRIGATÓRIO

- **Fazer:** selecionar de dois a cinco produtos, informar quantidades diferentes no formato exibido e enviar briefing. Repetir com ID ausente, duplicado, texto, zero e 100.
- **Esperado:** todos os itens aparecem uma vez; soma e quantidade total estão corretas; entradas inválidas são rejeitadas sem pedido.
- **Erro:** item omitido, produto duplicado, total incorreto ou pedido criado após validação falhar.
- **Provável ponto:** `ProductSelect`, `PurchaseModal.on_submit`, `create_order_and_ticket` e `StoreDatabase.create_order`.

### [ ] T16 — Mudanças durante a compra — OBRIGATÓRIO

- **Fazer:** abrir o modal e, antes de enviá-lo, desativar/excluir o produto, alterar o preço e fechar a loja em tentativas separadas.
- **Esperado:** produto removido/desativado e loja fechada são rejeitados; preço alterado é recalculado pelo valor atual.
- **Erro:** compra de item indisponível, preço antigo cobrado ou pedido ligado à loja errada.
- **Provável ponto:** revalidação no início de `create_order_and_ticket`, `get_product` e `get_shop`.

### [ ] T17 — Thread privada preferencial — OBRIGATÓRIO

- **Fazer:** restaurar as permissões da mesa e comprar. Conferir a thread com CLIENTE, LOJISTA, TERCEIRO e ADM.
- **Esperado:** thread privada criada na mesa; cliente e lojista são membros; TERCEIRO não vê; mensagem inicial contém pedido e controles.
- **Erro:** thread pública, participante ausente, controles ausentes ou pedido salvo com canal incorreto.
- **Provável ponto:** `resolve_service_desk_channel`, `create_ticket_channel`, `Thread.add_user` e permissões da mesa.

### [ ] T18 — Fallback para canal privado — OBRIGATÓRIO

- **Fazer:** retirar temporariamente Criar threads privadas da mesa e fazer outra compra.
- **Esperado:** pedido continua salvo; um canal privado é criado em Tickets; somente CLIENTE, LOJISTA, bot e administradores acessam.
- **Erro:** canal público, pedido apagado, sucesso sem canal e sem aviso, ou categoria criada visível para todos.
- **Provável ponto:** exceções de `create_ticket_channel`, `get_or_create_owner_ticket_category` e overwrites do fallback.

## 6. Ciclo do atendimento

### [ ] T19 — Iniciar atendimento e chamar cliente — OBRIGATÓRIO

- **Fazer:** CLIENTE e TERCEIRO tentam Em atendimento/Chamar cliente; depois LOJISTA usa os dois botões.
- **Esperado:** somente lojista altera status e chama; cliente é mencionado; cliques repetidos não repetem transição.
- **Erro:** cliente muda status, menção a `@everyone`, status duplicado ou botão sem resposta.
- **Provável ponto:** `TicketActionButton`, `CallCustomerButton` e `update_order_status`.

### [ ] T20 — Concluir, transcript e logs — OBRIGATÓRIO

- **Fazer:** trocar mensagens e anexos; LOJISTA conclui. Conferir permissões, transcript salvo, canal de logs e botão Ver transcript. Faça também um histórico maior que 3.800 caracteres.
- **Esperado:** cliente fica em somente leitura; transcript inclui o texto das mensagens e anexos; log recebe resumo; transcript longo vira `.txt`; avaliação é habilitada.
- **Erro:** linhas “[sem texto]” em mensagens que possuíam conteúdo, perda do histórico, log público/ausente, cliente ainda envia ou erro ao gerar arquivo.
- **Provável ponto:** `intents.message_content`, configuração do Developer Portal, `persist_transcript_and_logs`, `build_transcript_text`, `TranscriptButton`, `set_ticket_participants_visibility` e `TICKET_LOG_CHANNEL_ID`.

### [ ] T21 — Fechar pedido — OBRIGATÓRIO

- **Fazer:** fechar um pedido pendente e outro concluído, tanto em thread quanto em canal.
- **Esperado:** status fechado; canal vai para arquivados; thread fica arquivada e bloqueada; transcript/log são atualizados.
- **Erro:** canal continua ativo, thread permite mensagens, status diverge ou ação repetida altera novamente.
- **Provável ponto:** transição `close` em `TicketActionButton.callback`, `resolve_ticket_archive_category` e `Thread.edit`.

### [ ] T22 — Reabrir canal privado — OBRIGATÓRIO

- **Fazer:** no ticket fallback fechado, LOJISTA usa Reabrir.
- **Esperado:** status volta a pendente; canal retorna à categoria ativa; cliente recupera envio e recebe menção.
- **Erro:** canal continua arquivado, cliente continua bloqueado ou banco muda sem o Discord acompanhar.
- **Provável ponto:** bloco `reopen` de `TicketActionButton`, `resolve_ticket_category` e `set_ticket_participants_visibility`.

### [ ] T23 — Reabrir thread bloqueada — OBRIGATÓRIO CRÍTICO

- **Fazer:** abrir a thread privada arquivada na lista de threads e clicar Reabrir como LOJISTA.
- **Esperado:** o componente responde; bot remove `archived` e `locked`; cliente e lojista voltam a enviar mensagens.
- **Erro:** Discord não permite clicar no componente arquivado, interação falha ou thread permanece bloqueada embora o banco fique pendente.
- **Provável ponto:** ordem das operações no bloco `reopen` de `TicketActionButton.callback` e permissão Gerenciar threads.

### [ ] T24 — Avaliação — OBRIGATÓRIO

- **Fazer:** antes da conclusão tentar avaliar; depois CLIENTE avalia com 1 e 5 em pedidos diferentes. TERCEIRO e LOJISTA tentam avaliar; CLIENTE tenta repetir.
- **Esperado:** apenas comprador e pedido concluído/fechado; uma avaliação; publicação no canal; média/quantidade atualizam na vitrine.
- **Erro:** duplicidade, nota fora de 1–5, usuário indevido, avaliação salva mas média não muda ou falha sem feedback.
- **Provável ponto:** `RateOrderButton`, `RateOrderModal`, `StoreDatabase.create_rating`, `FEEDBACK_CHANNEL_ID` e builders da vitrine.

## 7. Reinício e eventos

### [ ] T25 — Persistência após reinício — OBRIGATÓRIO

- **Fazer:** deixe um ticket ativo, um fechado, uma candidatura pendente e uma vitrine publicada. Reinicie o processo sem trocar o banco; teste todos os botões existentes.
- **Esperado:** controles de tickets, candidatura e Abrir loja respondem; status e mensagens não duplicam.
- **Erro:** “Esta interação falhou”, `custom_id` duplicado, candidatura desaparece, vitrine não abre ou status reinicia.
- **Provável ponto:** `setup_hook`, `list_ticket_orders`, `list_pending_seller_applications`, `list_published_shops` e `custom_id` das views persistentes.

### [ ] T26 — Agradecimento de boost — OBRIGATÓRIO SE O RECURSO SERÁ USADO

- **Fazer:** com Server Members Intent ativo, um membro que não estava impulsionando inicia um boost.
- **Esperado:** uma mensagem é enviada no canal configurado e um evento é gravado; outras atualizações do membro não geram agradecimento.
- **Erro:** nenhuma mensagem, mensagens duplicadas ou desconexão `4014` na inicialização.
- **Provável ponto:** `intents.members`, `on_member_update`, `BOOST_THANK_CHANNEL_ID` e configuração do Developer Portal.

## Critério para liberar aos usuários

Todos os testes marcados **OBRIGATÓRIO** devem passar. T23 é bloqueador: uma falha pode deixar o banco como reaberto enquanto a thread continua inacessível. T26 só pode ser adiado se o agradecimento de boost for desabilitado removendo `BOOST_THANK_CHANNEL_ID` até ser validado.

Para cada teste, registre: data, executor, conta usada, ID do pedido/loja, resultado, captura de tela e trecho do log sem token.
