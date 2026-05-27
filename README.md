# Bot de lojas para Discord

Este projeto e um bot em Python para criar lojas dentro de um servidor do Discord. Agora ele tambem permite abrir um painel interativo para navegar pelas lojas, escolher produtos e registrar pedidos sem depender apenas de comandos digitados manualmente.

## O que o bot faz

- Permite que qualquer usuario crie a propria loja.
- Permite que o dono da loja cadastre produtos com nome, descricao e preco.
- Permite alterar o preco dos proprios produtos.
- Mostra as lojas e os produtos em embeds mais organizados.
- Abre um painel interativo com select menus para navegar pelas lojas.
- Registra pedidos de compra no SQLite e envia um resumo para o comprador.
- Tenta avisar o dono da loja por DM quando um pedido novo e criado.

## Comandos disponiveis

| Comando | Quem usa | Para que serve |
| --- | --- | --- |
| `/criar_loja` | Qualquer usuario | Cria uma loja no servidor. |
| `/lojas` | Qualquer usuario | Lista as lojas do servidor. |
| `/painel_loja` | Qualquer usuario | Abre o painel interativo para navegar e comprar. |
| `/ver_loja` | Qualquer usuario | Mostra os produtos de uma loja. |
| `/criar_produto` | Dono da loja | Cria um produto com o preco escolhido pelo dono. |
| `/alterar_preco` | Dono da loja | Altera o preco de um produto da propria loja. |
| `/comprar_produto` | Qualquer usuario | Faz um pedido manualmente pelo ID do produto. |
| `/meus_pedidos` | Comprador | Lista os pedidos que voce fez. |
| `/pedidos_loja` | Dono da loja | Lista os pedidos recebidos nas suas lojas. |

## Como funciona o painel

1. Use `/painel_loja`.
2. Escolha uma loja no menu.
3. O bot abre uma vitrine da loja em mensagem privada para voce dentro do Discord.
4. Escolha um produto no menu da vitrine.
5. Preencha o modal com quantidade e detalhes do pedido.
6. O bot salva o pedido e mostra um resumo.

## O que voce precisa para testar

1. Python 3.10 ou mais recente.
2. Uma conta no Discord.
3. Permissao para adicionar bots em um servidor de teste.
4. Um bot criado no [Discord Developer Portal](https://discord.com/developers/applications).

## Como criar o bot no Discord

1. Entre no [Discord Developer Portal](https://discord.com/developers/applications).
2. Clique em **New Application**.
3. De um nome para a aplicacao.
4. Va em **Bot** e clique em **Add Bot**.
5. Copie o token do bot. Esse token vai no arquivo `.env`.
6. Em **OAuth2 > URL Generator**, marque:
   - `bot`
   - `applications.commands`
7. Em permissoes do bot, para testar, marque pelo menos:
   - `Send Messages`
   - `Use Slash Commands`
   - `Embed Links`
8. Abra a URL gerada e adicione o bot ao seu servidor de teste.

## Como rodar localmente

Crie e ative um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

Instale as dependencias:

```bash
pip install -r requirements.txt
```

Crie o arquivo `.env` baseado no exemplo:

```bash
cp .env.example .env
```

Edite o `.env` e coloque o token real do bot:

```env
DISCORD_TOKEN=seu_token_aqui
```

Opcionalmente, coloque o ID do seu servidor de teste em `GUILD_ID`. Isso faz os comandos aparecerem mais rapido durante o desenvolvimento:

```env
GUILD_ID=123456789012345678
```

Para descobrir o ID do servidor, ative o modo desenvolvedor no Discord em **Configuracoes > Avancado > Modo desenvolvedor**, clique com o botao direito no servidor e escolha **Copiar ID**.

Inicie o bot:

```bash
python bot.py
```

Quando aparecer `Bot conectado como ...`, voce ja pode abrir `/painel_loja`.

## Fluxo de teste recomendado

1. Use `/criar_loja nome: Design do Joao descricao: Banners, molduras e thumbnails`.
2. Use `/criar_produto id_loja: 1 nome: Banner simples preco: 15,00 descricao: Banner estatico para perfil`.
3. Use `/criar_produto id_loja: 1 nome: Moldura personalizada preco: 25,50 descricao: Moldura para avatar`.
4. Use `/painel_loja` e escolha a loja.
5. Escolha um produto e envie um pedido pelo modal.
6. Use `/meus_pedidos` para confirmar o registro do pedido.
7. Entre com a conta dona da loja e use `/pedidos_loja`.

## Observacoes importantes

- O banco local padrao e `lojas.db`.
- O arquivo `.env` e o banco `.db` ficam ignorados pelo Git para nao vazar token nem dados locais.
- Este bot ainda nao faz pagamento automatico. O pedido serve para registrar interesse e facilitar o contato entre cliente e vendedor.
- Se a DM do vendedor estiver bloqueada, o pedido continua salvo normalmente, mas o aviso privado pode nao chegar.
- Nunca compartilhe o token do seu bot. Se ele vazar, gere outro no Developer Portal.
