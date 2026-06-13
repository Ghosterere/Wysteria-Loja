# Bot de Marketplace para Discord

Bot em `discord.py` com sistema de lojas, produtos, pedidos, tickets, avaliações, aprovação de lojistas, publicação pública de vitrines e histórico persistido em `SQLite`.

## Instalação

1. Instale o Python 3.12+.
2. Crie e ative uma virtualenv.
3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Inicie o bot:

```bash
python bot.py
```

## Configuração

Configure o arquivo `.env` com os IDs do seu servidor:

```env
DISCORD_TOKEN=
GUILD_ID=
DATABASE_PATH=lojas.db
LOJISTA_ROLE_NAME=Lojista
ADMIN_TESTER_IDS=
TICKET_CATEGORY_ID=
TICKET_ARCHIVE_CATEGORY_ID=
FEEDBACK_CHANNEL_ID=
SERVICE_DESK_CHANNEL_ID=
TICKET_LOG_CHANNEL_ID=
BOOST_THANK_CHANNEL_ID=
SELLER_APPLICATION_CHANNEL_ID=
```

### O que cada campo faz

- `DISCORD_TOKEN`: token do bot.
- `GUILD_ID`: servidor onde os slash commands serão sincronizados imediatamente.
- `DATABASE_PATH`: caminho do banco SQLite.
- `LOJISTA_ROLE_NAME`: nome do cargo exigido para criar e gerenciar lojas.
- `ADMIN_TESTER_IDS`: IDs separados por vírgula autorizados a testar compra na própria loja.
- `TICKET_CATEGORY_ID`: categoria usada no fallback de tickets por canal privado.
- `TICKET_ARCHIVE_CATEGORY_ID`: categoria para arquivar tickets concluídos/fechados.
- `FEEDBACK_CHANNEL_ID`: canal para publicar avaliações recebidas.
- `SERVICE_DESK_CHANNEL_ID`: canal-base onde o bot tenta abrir threads privadas de atendimento.
- `TICKET_LOG_CHANNEL_ID`: canal de logs dos pedidos e transcripts.
- `BOOST_THANK_CHANNEL_ID`: canal de agradecimento de boost.
- `SELLER_APPLICATION_CHANNEL_ID`: canal onde chegam solicitações de lojista para aprovação.

## Como criar loja

1. Garanta que o usuário tenha o cargo definido em `LOJISTA_ROLE_NAME`.
2. Use `/loja`.
3. Clique em `Criar loja`.
4. Preencha nome, descrição, emoji, headline e cor.

Também existe o comando `/criar_loja` por compatibilidade.

## Como criar produto

1. Use `/loja`.
2. Selecione a loja.
3. Clique em `Novo serviço`.
4. Preencha nome, categoria, preço e descrição.

Também existe o comando `/criar_produto`.

## Como configurar termos

1. Use `/loja`.
2. Selecione a loja.
3. Clique em `Termos da loja`.
4. Defina o texto dos termos.
5. Para limpar, digite `remover`.

Os termos são exibidos antes da compra e o aceite fica registrado no banco.

## Como solicitar cargo de lojista

1. Use `/painel`.
2. Escolha `Solicitar lojista`.
3. Preencha portfólio e especialidades.

Também existe o comando `/solicitar_lojista`.

## Como aprovar lojistas

1. Configure `SELLER_APPLICATION_CHANNEL_ID`.
2. Dê a um administrador a permissão `Gerenciar Servidor`.
3. No canal de solicitações, use o botão `Aprovar` ou `Recusar`.
4. Em caso de recusa, informe o motivo no modal.

Ao aprovar, o bot adiciona automaticamente o cargo definido em `LOJISTA_ROLE_NAME`.

## Como funciona o sistema de pedidos

1. O cliente usa `/painel` ou abre uma vitrine pública.
2. Seleciona um ou mais produtos.
3. Visualiza a prévia com avaliações.
4. Aceita os termos, se houver.
5. Informa quantidades e briefing.
6. O bot cria o pedido, registra itens no banco e abre um atendimento privado.
7. O lojista controla o fluxo com os botões:
   - `Em atendimento`
   - `Concluir`
   - `Fechar ticket`
   - `Reabrir`
   - `Chamar cliente`
   - `Ver transcript`
   - `Avaliar atendimento`

## Como funciona o sistema de avaliações

1. O comprador conclui o atendimento.
2. No ticket, o botão `Avaliar atendimento` fica disponível.
3. O cliente envia nota de 1 a 5 e comentário opcional.
4. A avaliação é vinculada ao editor responsável.
5. A média e a quantidade aparecem na loja e na prévia de compra.
6. Se `FEEDBACK_CHANNEL_ID` estiver configurado, o feedback também vai para o canal.

## Como funciona o sistema de disponibilidade

1. Use `/loja`.
2. Selecione a loja.
3. Clique em `Status da loja`.
4. Defina:
   - se a loja está aberta
   - a disponibilidade: `disponivel`, `ocupado`, `ausente` ou `fechado`

O status aparece nas listas e o sistema também mostra a quantidade de pedidos ativos da loja.

## Fluxos principais

- Cliente: `/painel` -> explorar lojas -> selecionar produtos -> comprar -> acompanhar em `Meus pedidos`.
- Lojista: `/loja` -> criar loja -> criar produtos -> ajustar vitrine/status/termos/tema -> acompanhar histórico e estatísticas.
- Admin: revisar solicitações no canal configurado e acompanhar logs de tickets/boosts.

## Tabelas do banco

- `shops`
- `products`
- `orders`
- `order_items`
- `order_logs`
- `ratings`
- `term_acceptances`
- `seller_applications`
- `shop_publications`
- `boost_events`

## Testes rápidos recomendados

```bash
python -m py_compile bot.py
python -c "import bot"
```

Depois valide manualmente:

1. `/painel` abre sem erro.
2. `/loja` permite criar loja pelo botão.
3. Compra com 1 produto funciona.
4. Compra com múltiplos produtos funciona.
5. Pedido concluído gera transcript completo.
6. Recusa de lojista pede motivo e bloqueia nova revisão.
