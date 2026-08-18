# Loja DC — marketplace para Discord

Bot de marketplace construído com `discord.py`. Ele permite que lojistas criem vitrines e catálogos, recebam pedidos em atendimentos privados e acompanhem histórico, avaliações e estatísticas. Os dados são persistidos localmente em SQLite.

## Recursos

- vitrines personalizáveis com emoji, cores, imagens, textos e temas prontos;
- catálogo dividido por categorias e compra de um ou vários produtos;
- ativação e desativação de produtos sem apagar o histórico;
- arquivamento de lojas com pedidos, ocultando-as dos clientes sem apagar pedidos, itens, avaliações ou transcripts;
- termos obrigatórios com registro do aceite do comprador;
- disponibilidade da loja e contagem de pedidos ativos;
- tickets em thread privada, com fallback para canal privado;
- etapas de atendimento, logs e transcript persistente;
- avaliações de 1 a 5 estrelas vinculadas ao pedido e ao vendedor;
- solicitação e aprovação do cargo de lojista;
- publicação de vitrines em canais do servidor;
- atualização da publicação existente, sem duplicar a vitrine no mesmo canal;
- agradecimento automático por boosts;
- restauração dos controles persistentes depois de reinicializações;
- IDs públicos de lojas e pedidos separados por servidor.

## Requisitos

- Python 3.12 ou mais recente;
- um bot criado no Discord Developer Portal;
- intents privilegiadas **Server Members Intent** e **Message Content Intent** habilitadas;
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

Copie `.env.example` para `.env`, preencha a configuração e execute:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe bot.py
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
| `SERVICE_DESK_CHANNEL_ID` | Não | Canal de texto usado como central de atendimento. O bot tenta criar uma thread privada; se falhar, cria um canal privado. Não use canal de fórum. |
| `TICKET_LOG_CHANNEL_ID` | Não | Canal que recebe eventos e uma prévia do transcript ao concluir ou fechar pedidos. |
| `BOOST_THANK_CHANNEL_ID` | Não | Canal onde novos boosts são agradecidos. |
| `SELLER_APPLICATION_CHANNEL_ID` | Para solicitações | Canal onde administradores analisam pedidos de cargo de lojista. |

Todos os IDs opcionais devem ser numéricos quando preenchidos. O `.env` e arquivos de banco estão ignorados pelo Git; não publique o token nem bancos de produção.

Na inicialização, o bot registra avisos no console quando um ID aponta para o tipo errado de canal, quando faltam permissões ou quando a hierarquia impede a entrega do cargo.

## Configuração no Discord

1. No Developer Portal, habilite **Server Members Intent** e **Message Content Intent** na página do bot. O segundo é necessário para salvar o texto completo dos transcripts.
2. Convide o bot com os escopos `bot` e `applications.commands`.
3. Conceda as permissões necessárias aos recursos que você pretende usar.
4. Crie o cargo de lojista e confira se o nome coincide com `LOJISTA_ROLE_NAME`.
5. Posicione o cargo do bot acima do cargo de lojista.
6. Preencha no `.env` os IDs dos canais e categorias desejados.

Para copiar um ID no Discord, ative o Modo Desenvolvedor em **Configurações → Avançado**, clique com o botão direito no servidor, canal ou categoria e escolha **Copiar ID**.

### Canais, categorias e privacidade

| Nome sugerido | Tipo | Acesso | Função |
| --- | --- | --- | --- |
| `Tickets` | Categoria | Privado | Recebe os canais privados de pedidos ativos quando a thread não pode ser criada. |
| `Tickets arquivados` | Categoria | Privado | Recebe canais concluídos ou fechados. |
| `mesa-de-atendimento` | Canal de texto | Aberto | Canal-base para threads privadas. O canal pode ser público; cada thread continua restrita ao cliente, lojista e bot. |
| `avaliacoes` | Canal de texto | Aberto | Publica notas e comentários deixados pelos compradores. |
| `logs-pedidos` | Canal de texto | Privado | Recebe resumos e prévias de transcript; deve ser visível apenas para a equipe. |
| `agradecimento-boost` | Canal de texto | Aberto | Publica agradecimentos por novos boosts. |
| `solicitacoes-lojista` | Canal de texto | Privado | Contém portfólios e controles administrativos de aprovação e recusa. |
| `vitrines` | Canal de texto | Aberto | Destino escolhido pelo lojista em **Divulgar loja**; não possui variável fixa no `.env`. |

Nas categorias privadas, negue **Ver canal** para `@everyone`. Ao criar um canal de pedido, o bot aplica permissões específicas para cliente, lojista e bot. Administradores com permissão global continuam podendo acessar conforme a configuração do servidor.

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
2. Use `/painel_loja` e clique em **Criar loja**.
3. Selecione a loja para personalizar a vitrine, definir termos e status e administrar o catálogo.
4. No catálogo, produtos desativados deixam de aparecer para clientes e podem ser reativados depois.
5. Use **Divulgar loja** para publicar uma vitrine em um canal.
6. Acompanhe pedidos, histórico e estatísticas pelo mesmo painel.

No ticket, somente o lojista pode alterar o atendimento para **Em atendimento**, **Concluído**, **Fechado** ou **Reaberto**. Cliente e lojista podem consultar o transcript; somente o cliente pode avaliar um pedido concluído ou fechado.

### Solicitação de lojista

1. Configure `SELLER_APPLICATION_CHANNEL_ID`.
2. O candidato usa `/painel` → **Solicitar lojista** ou `/solicitar_lojista`.
3. Um membro com permissão **Gerenciar Servidor** aprova ou recusa a solicitação no canal configurado.
4. Ao aprovar, o bot atribui o cargo de lojista; ao recusar, registra o motivo.

Uma pessoa só pode ter uma solicitação pendente. Se o canal estiver inacessível, a criação é desfeita para que o candidato possa tentar novamente. O bot não aprova se o candidato saiu do servidor ou se não puder entregar o cargo.

## Comandos

| Comando | Finalidade |
| --- | --- |
| `/painel` | Abre a central do cliente. |
| `/painel_loja` | Abre a central de gerenciamento do lojista, incluindo lojas arquivadas e histórico. |
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

Os comandos funcionam apenas dentro de servidores, não em mensagens diretas.

## Pedidos e tickets

O fluxo tenta abrir uma thread privada em `SERVICE_DESK_CHANNEL_ID`. Quando o canal não está configurado ou a criação falha, o bot abre um canal privado na categoria configurada em `TICKET_CATEGORY_ID`; na ausência dela, tenta criar uma categoria exclusiva para o lojista.

O pedido é salvo antes da tentativa de abrir o atendimento. Se o Discord impedir a criação do ticket, o pedido permanece no banco e o cliente recebe uma orientação sobre as permissões necessárias.

Os estados possíveis são `pendente`, `em_andamento`, `concluido` e `fechado`. Ao concluir ou fechar um atendimento, o bot:

- deixa o canal privado em modo de leitura para o cliente;
- move o canal para `TICKET_ARCHIVE_CATEGORY_ID`, se configurada;
- salva o histórico de mensagens no banco;
- publica o evento em `TICKET_LOG_CHANNEL_ID`, se configurado.

Threads concluídas ou fechadas são arquivadas e bloqueadas. Ao reabrir, o bot tenta desbloquear a thread ou mover o canal de volta para a categoria ativa. As transições são validadas novamente no clique, impedindo que um botão antigo sobrescreva um estado mais recente.

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

As migrações preservam o histórico. Referências antigas a produtos já removidos são convertidas em `NULL`, e os pedidos continuam exibindo `[produto removido]`. IDs públicos possuem unicidade por servidor e candidaturas mantêm apenas uma entrada pendente por usuário.

Lojas que já receberam qualquer pedido não podem ser excluídas. No `/painel_loja`, a ação passa a ser **Arquivar loja**: ela sai do marketplace e das vitrines públicas, mas continua disponível ao lojista para consulta do histórico e pode ser reativada.

## Validação e desenvolvimento

A suíte automatizada cobre preços, pedidos com vários produtos, totais, transições, avaliações, candidaturas, persistência de tickets e reparo de referências antigas:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m py_compile bot.py tests\test_bot.py
.\.venv\Scripts\python.exe -m pip check
```

Para testar a importação sem tocar no banco operacional, use um caminho temporário:

```powershell
$env:DATABASE_PATH = "$env:TEMP\lojadc-import.db"
.\.venv\Scripts\python.exe -c "import bot; print('Importação concluída')"
Remove-Item -LiteralPath "$env:TEMP\lojadc-import.db"
```

O roteiro detalhado, com resultado esperado, sinais de erro e ponto provável no código, está em [`CHECKLIST_DISCORD.md`](CHECKLIST_DISCORD.md).

Depois, valide em um servidor de testes:

1. sincronização e abertura de `/painel` e `/painel_loja`;
2. criação, edição, publicação e exclusão de uma loja sem pedidos;
3. compra com um e com vários produtos;
4. aceite de termos e bloqueio de loja fechada;
5. criação de thread e fallback para canal privado;
6. transições do ticket, transcript e arquivamento;
7. envio único de avaliação;
8. aprovação, recusa, candidatura duplicada, candidato ausente e erro de hierarquia;
9. publicação duas vezes no mesmo canal, confirmando que a mensagem é atualizada e não duplicada;
10. reinicialização do bot com ticket, candidatura e vitrine ativos;
11. boost, avaliação pública e envio de log com permissões concedidas e negadas.

## Backup e atualização

Antes de atualizar:

1. pare o bot para evitar gravações durante a cópia;
2. copie o arquivo indicado por `DATABASE_PATH` para um local seguro;
3. atualize o código e execute `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`;
4. rode os testes;
5. inicie o bot e confira os avisos de configuração no console.

Nunca restaure apenas arquivos `-wal` ou `-shm`; o backup principal é o arquivo `.db` com o bot parado.

## Deploy na Square Cloud

O arquivo `squarecloud.app` na raiz configura o deploy com:

- arquivo principal `bot.py` (início automático com `python bot.py`);
- Python na versão recomendada pela Square Cloud;
- 512 MB de memória;
- reinício automático em caso de falha.

A Square Cloud instala automaticamente as dependências de `requirements.txt`. Antes de iniciar o bot, cadastre no painel as variáveis listadas em `.env.example`; `DISCORD_TOKEN` é a única obrigatória para a conexão, e as demais habilitam ou direcionam recursos específicos do servidor.

O banco SQLite não faz parte do Git. Configure `DATABASE_PATH` para um caminho em armazenamento persistente da aplicação e preserve esse volume entre os deploys. Sem persistência, lojas, produtos, pedidos e tickets podem ser perdidos quando a aplicação for recriada.

Nunca envie `.env`, token, banco ou backup no repositório ou no pacote público.

## Solução de problemas

- `ModuleNotFoundError: No module named 'discord'`: use `.\.venv\Scripts\python.exe bot.py` ou instale `requirements.txt` nesse ambiente.
- desconexão `4014` ou transcripts com `[sem texto]`: habilite **Server Members Intent** e **Message Content Intent** no Developer Portal.
- comandos `/` não aparecem: confirme `GUILD_ID`, o escopo `applications.commands` e os avisos de sincronização no console.
- thread não é criada: confirme que a mesa é um canal de texto e conceda **Criar threads privadas**, **Enviar mensagens em threads** e **Gerenciar threads**.
- ticket privado não é criado: conceda **Gerenciar canais** e confira `TICKET_CATEGORY_ID`.
- cargo não é entregue: conceda **Gerenciar Cargos** e coloque o cargo do bot acima de `LOJISTA_ROLE_NAME`.
- vitrine não é publicada: conceda **Ver canal**, **Enviar mensagens** e **Inserir links** no canal escolhido.

## Estrutura do projeto

```text
.
├── bot.py              # bot, interfaces, regras de negócio e acesso ao SQLite
├── .env.example        # modelo seguro de configuração
├── squarecloud.app     # configuração de execução na Square Cloud
├── requirements.txt    # dependências Python
├── tests/              # testes automatizados dos invariantes principais
├── PROJETO_MAPA.md     # índice técnico de comandos, views e tabelas
└── README.md            # instalação e operação
```
