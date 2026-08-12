# Loja DC — marketplace para Discord

Bot de marketplace construído com `discord.py`. Ele permite que lojistas criem vitrines e catálogos, recebam pedidos em atendimentos privados e acompanhem histórico, avaliações e estatísticas. Os dados são persistidos localmente em SQLite.

## Recursos

- vitrines personalizáveis com emoji, cores, imagens, textos e temas prontos;
- catálogo dividido por categorias e compra de um ou vários produtos;
- termos obrigatórios com registro do aceite do comprador;
- disponibilidade da loja e contagem de pedidos ativos;
- tickets em thread privada, com fallback para canal privado;
- etapas de atendimento, logs e transcript persistente;
- avaliações de 1 a 5 estrelas vinculadas ao pedido e ao vendedor;
- solicitação e aprovação do cargo de lojista;
- publicação de vitrines em canais do servidor;
- agradecimento automático por boosts;
- IDs públicos de lojas e pedidos separados por servidor.

## Requisitos

- Python 3.12 ou mais recente;
- um bot criado no Discord Developer Portal;
- intent privilegiada **Server Members Intent** habilitada;
- permissões do bot para ver e enviar mensagens, incorporar links, anexar arquivos, ler histórico, criar threads privadas, gerenciar canais, mensagens e cargos.

O cargo do bot deve ficar acima do cargo configurado em `LOJISTA_ROLE_NAME` para que aprovações consigam atribuí-lo.

## Instalação

```bash
python -m venv .venv
```

Ative o ambiente virtual:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source .venv/bin/activate
```

Instale as dependências:

```bash
python -m pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz do projeto e, por fim, execute:

```bash
python bot.py
```

Na primeira inicialização, o banco e suas tabelas são criados automaticamente. Inicializações posteriores também aplicam as migrações previstas pelo código.

## Configuração

Exemplo de `.env`:

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

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `DISCORD_TOKEN` | Sim | Token usado para conectar o bot. |
| `GUILD_ID` | Não | ID do servidor de desenvolvimento. Sincroniza os comandos imediatamente nesse servidor; sem ele, a sincronização é global e pode demorar a aparecer. |
| `DATABASE_PATH` | Não | Caminho do SQLite. O padrão é `lojas.db`. |
| `LOJISTA_ROLE_NAME` | Não | Nome exato do cargo autorizado a criar e administrar lojas. O padrão é `Lojista`. |
| `ADMIN_TESTER_IDS` | Não | IDs de usuários, separados por vírgula, que podem comprar na própria loja para testes. |
| `TICKET_CATEGORY_ID` | Não | Categoria usada para canais privados de atendimento. Se não existir, o bot tenta criar uma categoria por lojista. |
| `TICKET_ARCHIVE_CATEGORY_ID` | Não | Categoria para a qual canais concluídos ou fechados são movidos. |
| `FEEDBACK_CHANNEL_ID` | Não | Canal que recebe avaliações publicadas. |
| `SERVICE_DESK_CHANNEL_ID` | Não | Canal de texto ou fórum usado como central de atendimento. Em canal de texto, o bot tenta criar uma thread privada; se falhar, cria um canal privado. |
| `TICKET_LOG_CHANNEL_ID` | Não | Canal que recebe eventos e uma prévia do transcript ao concluir ou fechar pedidos. |
| `BOOST_THANK_CHANNEL_ID` | Não | Canal onde novos boosts são agradecidos. |
| `SELLER_APPLICATION_CHANNEL_ID` | Para solicitações | Canal onde administradores analisam pedidos de cargo de lojista. |

Todos os IDs opcionais devem ser numéricos quando preenchidos. O `.env` e arquivos de banco estão ignorados pelo Git; não publique o token nem bancos de produção.

## Configuração no Discord

1. No Developer Portal, habilite **Server Members Intent** na página do bot.
2. Convide o bot com os escopos `bot` e `applications.commands`.
3. Conceda as permissões necessárias aos recursos que você pretende usar.
4. Crie o cargo de lojista e confira se o nome coincide com `LOJISTA_ROLE_NAME`.
5. Posicione o cargo do bot acima do cargo de lojista.
6. Preencha no `.env` os IDs dos canais e categorias desejados.

Para copiar um ID no Discord, ative o Modo Desenvolvedor em **Configurações → Avançado**, clique com o botão direito no servidor, canal ou categoria e escolha **Copiar ID**.

## Uso

### Fluxo do cliente

1. Use `/painel` e escolha **Explorar lojas**.
2. Abra uma vitrine e selecione um ou mais produtos.
3. Confira preços e avaliações, aceite os termos quando existirem e envie quantidade e briefing.
4. Continue o atendimento no ticket criado pelo bot.
5. Consulte compras em `/meus_pedidos` e avalie o serviço depois da conclusão.

O dono de uma loja não pode comprar nela, exceto quando seu ID estiver em `ADMIN_TESTER_IDS`.

### Fluxo do lojista

1. Obtenha o cargo configurado em `LOJISTA_ROLE_NAME`.
2. Use `/loja` e clique em **Criar loja**.
3. Selecione a loja para personalizar a vitrine, definir termos e status e administrar o catálogo.
4. Use **Divulgar loja** para publicar uma vitrine em um canal.
5. Acompanhe pedidos, histórico e estatísticas pelo mesmo painel.

No ticket, somente o lojista pode alterar o atendimento para **Em atendimento**, **Concluído**, **Fechado** ou **Reaberto**. Cliente e lojista podem consultar o transcript; somente o cliente pode avaliar um pedido concluído ou fechado.

### Solicitação de lojista

1. Configure `SELLER_APPLICATION_CHANNEL_ID`.
2. O candidato usa `/painel` → **Solicitar lojista** ou `/solicitar_lojista`.
3. Um membro com permissão **Gerenciar Servidor** aprova ou recusa a solicitação no canal configurado.
4. Ao aprovar, o bot atribui o cargo de lojista; ao recusar, registra o motivo.

## Comandos

| Comando | Finalidade |
| --- | --- |
| `/painel` | Abre a central do cliente. |
| `/loja` | Abre a central de gerenciamento do lojista. |
| `/lojas` | Lista as lojas do servidor e seus IDs. |
| `/ver_loja` | Abre uma vitrine pelo ID. |
| `/meus_pedidos` | Lista pedidos feitos pelo usuário. |
| `/pedidos_loja` | Lista pedidos recebidos pelo lojista. |
| `/solicitar_lojista` | Abre o formulário de candidatura. |
| `/criar_loja` | Cria uma loja pelo fluxo legado. |
| `/criar_produto` | Adiciona um produto pelo fluxo legado. |
| `/personalizar_loja` | Edita a identidade visual pelo fluxo legado. |
| `/status_loja` | Altera abertura e disponibilidade. |
| `/termos_loja` | Define ou remove termos. |
| `/tema_loja` | Aplica os temas `booster`, `dark_red`, `gold` ou `neon_blue`. |
| `/alterar_preco` | Atualiza o preço de um produto. |
| `/comprar_produto` | Inicia diretamente a compra de um produto. |
| `/excluir_loja` | Exclui uma loja que ainda não possui pedidos. |
| `/painel_loja` | Alias legado de `/painel`. |
| `/gerenciar_lojas` | Alias legado de `/loja`. |

Os comandos funcionam apenas dentro de servidores, não em mensagens diretas.

## Pedidos e tickets

O fluxo tenta abrir uma thread privada em `SERVICE_DESK_CHANNEL_ID`. Quando o canal não está configurado ou a criação falha, o bot abre um canal privado na categoria configurada em `TICKET_CATEGORY_ID`; na ausência dela, tenta criar uma categoria exclusiva para o lojista.

Os estados possíveis são `pendente`, `em_andamento`, `concluido` e `fechado`. Ao concluir ou fechar um atendimento, o bot:

- deixa o canal privado em modo de leitura para o cliente;
- move o canal para `TICKET_ARCHIVE_CATEGORY_ID`, se configurada;
- salva o histórico de mensagens no banco;
- publica o evento em `TICKET_LOG_CHANNEL_ID`, se configurado.

Anexos aparecem no transcript como URLs. O transcript completo pode ser consultado no ticket e é enviado como arquivo quando ultrapassa o limite de uma mensagem.

## Persistência

O SQLite contém as tabelas:

- `shops` e `products`: lojas, aparência, disponibilidade e catálogo;
- `orders` e `order_items`: pedidos e seus itens;
- `order_logs`: eventos do atendimento;
- `ratings`: avaliações;
- `term_acceptances`: aceites de termos;
- `seller_applications`: solicitações e revisões de lojistas;
- `shop_publications`: mensagens públicas vinculadas às vitrines;
- `boost_events`: agradecimentos por boost.

Views persistentes de tickets, solicitações pendentes e vitrines publicadas são registradas novamente quando o bot inicia. Faça backup do arquivo definido em `DATABASE_PATH` antes de atualizar ou alterar dados manualmente.

## Validação e desenvolvimento

O projeto não possui uma suíte automatizada de testes. As verificações locais disponíveis são:

```bash
python -m py_compile bot.py
python -c "import bot"
```

O segundo comando inicializa a camada de banco e pode aplicar migrações no arquivo configurado. Para uma verificação isolada, use um banco temporário:

```powershell
$env:DATABASE_PATH = "teste-local.db"
python -c "import bot"
Remove-Item -LiteralPath "teste-local.db"
```

Depois, valide em um servidor de testes:

1. sincronização e abertura de `/painel` e `/loja`;
2. criação, edição, publicação e exclusão de uma loja sem pedidos;
3. compra com um e com vários produtos;
4. aceite de termos e bloqueio de loja fechada;
5. criação de thread e fallback para canal privado;
6. transições do ticket, transcript e arquivamento;
7. envio único de avaliação;
8. aprovação e recusa de solicitação de lojista.

## Deploy na Discloud

O repositório inclui `discloud.config`, configurado para executar `bot.py` com 300 MB de RAM. Cadastre pelo painel da hospedagem as mesmas variáveis do `.env` e inclua no pacote os arquivos necessários:

- `bot.py`;
- `requirements.txt`;
- `discloud.config`;
- o banco SQLite, somente se quiser preservar dados existentes.

O token deve ser configurado como variável segura na hospedagem, nunca incluído no repositório ou no pacote público.

## Estrutura do projeto

```text
.
├── bot.py              # bot, interfaces, regras de negócio e acesso ao SQLite
├── requirements.txt    # dependências Python
├── discloud.config     # configuração de hospedagem
├── PROJETO_MAPA.md     # índice técnico de comandos, views e tabelas
└── README.md            # instalação e operação
```
