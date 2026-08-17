# PROJETO_MAPA

## Comandos

| Nome | Localização no código | Função | Como acessar |
| --- | --- | --- | --- |
| `/painel` | `send_main_panel` / `main_panel_alias` em `bot.py` | Central principal do cliente e atalho para solicitação de lojista | Slash command |
| `/loja` | `manage_store_alias` em `bot.py` | Central gráfica do lojista | Slash command |
| `/criar_loja` | `create_shop` em `bot.py` | Cria loja por comando legado | Slash command |
| `/lojas` | `list_shops` em `bot.py` | Lista lojas cadastradas | Slash command |
| `/painel_loja` | `store_panel` em `bot.py` | Alias antigo do painel principal | Slash command |
| `/gerenciar_lojas` | `manage_shops_command` em `bot.py` | Alias antigo do painel do lojista | Slash command |
| `/solicitar_lojista` | `request_seller_role` em `bot.py` | Abre o formulário de lojista | Slash command |
| `/ver_loja` | `view_shop` em `bot.py` | Abre a vitrine de uma loja específica | Slash command |
| `/criar_produto` | `create_product` em `bot.py` | Cria produto por comando legado | Slash command |
| `/personalizar_loja` | `customize_shop` em `bot.py` | Ajusta visual da loja por comando legado | Slash command |
| `/status_loja` | `set_shop_status` em `bot.py` | Atualiza abertura e disponibilidade | Slash command |
| `/termos_loja` | `set_shop_terms` em `bot.py` | Define termos obrigatórios | Slash command |
| `/tema_loja` | `set_shop_theme` em `bot.py` | Aplica tema pronto | Slash command |
| `/excluir_loja` | `delete_shop_command` em `bot.py` | Exclui loja sem histórico | Slash command |
| `/alterar_preco` | `update_price` em `bot.py` | Ajusta preço de produto | Slash command |
| `/comprar_produto` | `buy_product` em `bot.py` | Compra manual de um produto | Slash command |
| `/meus_pedidos` | `my_orders` em `bot.py` | Lista pedidos do comprador | Slash command |
| `/pedidos_loja` | `store_orders` em `bot.py` | Lista pedidos recebidos pelo lojista | Slash command |

## Tabelas SQL

| Nome | Localização no código | Função | Como acessar |
| --- | --- | --- | --- |
| `shops` | `StoreDatabase._setup` em `bot.py` | Guarda vitrines, tema, status e termos | SQLite |
| `products` | `StoreDatabase._setup` em `bot.py` | Guarda catálogo de cada loja | SQLite |
| `orders` | `StoreDatabase._setup` em `bot.py` | Guarda pedidos, status, datas, transcript e aceite de termos | SQLite |
| `order_items` | `StoreDatabase._setup` em `bot.py` | Guarda múltiplos itens por pedido | SQLite |
| `order_logs` | `StoreDatabase._setup` em `bot.py` | Guarda eventos do atendimento | SQLite |
| `ratings` | `StoreDatabase._setup` em `bot.py` | Guarda avaliações de pedidos | SQLite |
| `term_acceptances` | `StoreDatabase._setup` em `bot.py` | Guarda aceite de termos por cliente | SQLite |
| `seller_applications` | `StoreDatabase._setup` em `bot.py` | Guarda solicitações de lojista e revisão | SQLite |
| `shop_publications` | `StoreDatabase._setup` em `bot.py` | Guarda painéis públicos publicados | SQLite |
| `boost_events` | `StoreDatabase._setup` em `bot.py` | Guarda boosts recebidos | SQLite |

## Painéis

| Nome | Localização no código | Função | Como acessar |
| --- | --- | --- | --- |
| Painel principal | `HomePanelView` em `bot.py` | Entrada do sistema para cliente e solicitante de lojista | `/painel` |
| Explorador de vitrines | `ShopBrowserView` em `bot.py` | Lista e navega entre lojas | `/painel` -> `Explorar lojas` |
| Catálogo da loja | `ShopDetailView` em `bot.py` | Mostra categorias e produtos da loja | `/painel` ou painel público |
| Prévia de compra | `ProductPurchaseView` em `bot.py` | Mostra compra antes do modal final | Seleção de produtos |
| Painel do vendedor | `OwnerShopBrowserView` em `bot.py` | Lista lojas do lojista e permite criar loja | `/loja` |
| Gestão da loja | `OwnerShopManageView` em `bot.py` | Centraliza personalização, catálogo, histórico, estatísticas e publicação | `/loja` -> selecionar loja |
| Gestão do catálogo | `OwnerProductManageView` em `bot.py` | Cria, edita, ativa, desativa e remove produtos | `/loja` → `Gerenciar catálogo` |
| Histórico da loja | `OwnerShopHistoryView` em `bot.py` | Mostra pedidos da loja e acesso aos logs | `/loja` → `Histórico` |
| Estatísticas do editor | `EditorStatsView` em `bot.py` | Mostra total de pedidos, concluídos e tempo médio | `/loja` → `Estatísticas` |
| Painel público da loja | `PublicPublishedShopView` em `bot.py` | Post público sincronizado com botão para abrir a loja | `/loja` -> `Divulgar loja` |
| Aprovação de lojista | `SellerApplicationReviewView` em `bot.py` | Aprova ou recusa solicitações | Canal de solicitações |

## Views

| Nome | Localização no código | Função | Como acessar |
| --- | --- | --- | --- |
| `BasePanelView` | `bot.py` | Base com bloqueio por usuário e tratamento de erro | Interno |
| `SafeModal` | `bot.py` | Base dos formulários com resposta segura para erros esperados e inesperados | Interno |
| `HomePanelView` | `bot.py` | View do painel principal | `/painel` |
| `ShopBrowserView` | `bot.py` | Navegação entre lojas | `/painel` |
| `ShopDetailView` | `bot.py` | Navegação dentro da loja | Seleção de loja |
| `ProductPurchaseView` | `bot.py` | Ações antes da compra | Seleção de produto |
| `OrdersView` | `bot.py` | Lista de pedidos do comprador/lojista | `/painel` |
| `OwnerShopBrowserView` | `bot.py` | Lista de lojas do lojista | `/loja` |
| `OwnerShopManageView` | `bot.py` | Gestão central da loja | `/loja` |
| `OwnerProductManageView` | `bot.py` | Gestão do catálogo | `/loja` |
| `OwnerShopHistoryView` | `bot.py` | Histórico da loja | `/loja` -> `Historico` |
| `EditorStatsView` | `bot.py` | Estatísticas do editor | `/loja` -> `Estatisticas` |
| `ThemePresetView` | `bot.py` | Escolha de tema pronto | `/loja` -> `Tema visual` |
| `TermsAcceptanceView` | `bot.py` | Aceite de termos antes da compra | Fluxo de compra |
| `TicketControlsView` | `bot.py` | Controle do pedido dentro do atendimento | Ticket do pedido |
| `PublicPublishedShopView` | `bot.py` | Botão de abrir loja a partir de painel público | Mensagem pública |
| `SellerApplicationReviewView` | `bot.py` | Botões de aprovação/recusa | Canal de solicitações |
| `PublishShopView` | `bot.py` | Seleção do canal da divulgação | `/loja` -> `Divulgar loja` |

## Modals

| Nome | Localização no código | Função | Como acessar |
| --- | --- | --- | --- |
| `CreateShopModal` | `bot.py` | Cria loja pela interface | `/loja` -> `Criar loja` |
| `ShopStyleModal` | `bot.py` | Ajusta descrição, emoji, cor e mídia | `/loja` -> `Personalizar visual` |
| `ShopBioModal` | `bot.py` | Ajusta headline, subtítulo, vantagens e botão | `/loja` -> `Ajustar vitrine` |
| `ShopTermsModal` | `bot.py` | Ajusta termos da loja | `/loja` -> `Termos da loja` |
| `ShopStatusModal` | `bot.py` | Ajusta aberta/fechada e disponibilidade | `/loja` -> `Status da loja` |
| `ProductCreateModal` | `bot.py` | Cria produto | `/loja` -> `Novo serviço` |
| `ProductEditModal` | `bot.py` | Edita produto | `/loja` -> `Gerenciar catálogo` |
| `PurchaseModal` | `bot.py` | Finaliza a compra e registra briefing | Fluxo de compra |
| `RateOrderModal` | `bot.py` | Avalia o atendimento | Ticket concluído |
| `SellerApplicationModal` | `bot.py` | Solicita cargo de lojista | `/painel` ou `/solicitar_lojista` |
| `SellerApplicationRejectModal` | `bot.py` | Registra motivo da recusa | Botão `Recusar` |

## Permissões

| Nome | Localização no código | Função | Como acessar |
| --- | --- | --- | --- |
| Cargo `Lojista` | `ensure_lojista_member` em `bot.py` | Exigido para criar e gerenciar lojas | Configurar `LOJISTA_ROLE_NAME` |
| `Manage Guild` | `SellerApplicationActionButton` e `SellerApplicationRejectModal` em `bot.py` | Aprovar ou recusar lojistas | Botões no canal de solicitações |
| Dono da loja | Validações em `bot.py` | Só o dono edita loja, produtos e status | Painel `/loja` |
| Comprador do pedido | `RateOrderButton` em `bot.py` | Só o comprador avalia, uma vez e após conclusão/fechamento | Ticket e pedido |
| Comprador ou lojista do pedido | `TranscriptButton` em `bot.py` | Consulta o transcript do próprio atendimento | Ticket |
| Apenas lojista responsável | `TicketActionButton` em `bot.py` | Altera o estado do atendimento | Ticket |
| Apenas lojista responsável | `CallCustomerButton` em `bot.py` | Menciona o cliente no ticket | Ticket |

## Canais configuráveis

| Nome | Tipo | Acesso recomendado | Função |
| --- | --- | --- | --- |
| `TICKET_CATEGORY_ID` | Categoria | Privado | Fallback de tickets privados por canal. |
| `TICKET_ARCHIVE_CATEGORY_ID` | Categoria | Privado | Arquiva canais de pedidos concluídos ou fechados. |
| `FEEDBACK_CHANNEL_ID` | Canal de texto | Aberto | Recebe avaliações publicadas. |
| `SERVICE_DESK_CHANNEL_ID` | Canal de texto | Aberto | Canal-base para threads privadas; não deve ser fórum. |
| `TICKET_LOG_CHANNEL_ID` | Canal de texto | Privado | Recebe logs e prévia do transcript. |
| `BOOST_THANK_CHANNEL_ID` | Canal de texto | Aberto | Recebe mensagens de agradecimento de boost. |
| `SELLER_APPLICATION_CHANNEL_ID` | Canal de texto | Privado | Recebe portfólios e controles administrativos de solicitações. |
