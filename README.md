# Inscrições em eventos do campus

Atividade 06 de Rapid Application Development (RAD), curso de Sistemas para Internet, IFPB: uma API REST ao lado do sistema de inscrições em eventos do campus.

## Integrantes

- Francisco Viana Maia Neto.
- Murilo Maciel Rodrigues.

Divisão do trabalho:

- Francisco: configuração do DRF, token, serializers e ViewSets de salas, eventos, atividades e inscrições, permissões, tratamento de erros, testes da escrita e este README.
- Murilo: a ideia de mover as regras e as operações de inscrição das views para uma camada de serviços compartilhada com a API, com o rascunho dessa camada (`obter_agenda_participante` e `obter_dados_evento` vêm dele), e a parte de leitura da API, com a programação do evento, a agenda do participante, a busca e a ordenação das atividades, a documentação OpenAPI e os testes dessa parte.

## Como executar

O projeto usa Python 3.10 ou superior e Django 5.2.17. O banco `db.sqlite3` já contém as migrations aplicadas e os dados de teste.

```bash
git clone https://github.com/franciscovmn/radEventos.git
cd radEventos
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

No Windows, ative o ambiente com `.venv\Scripts\activate`.

Abra http://127.0.0.1:8000/ para consultar os eventos e http://127.0.0.1:8000/admin/ para acessar o Admin.

Para recriar os dados de teste em um banco novo:

```bash
python manage.py migrate
python manage.py cadastrar_dados
```

O comando não apaga dados existentes nem troca senhas de contas já cadastradas.

## Contas de teste

Todas as contas abaixo usam a senha `Eventos@2026`.

| Conta | Usuário | Papel | Token da API |
| --- | --- | --- | --- |
| Uma | `admin` | Superusuário, cadastra salas pelo Admin | `f3df960941f96bdbeb317f9a18b5aa80906117e3` |
| Duas | `organizador2` | Organizador da Semana de Tecnologia e do Encontro de Egressos | `1d6f8fc09a452de40accdf08bb1eb544213ec247` |
| Três | `organizador3` | Organizador da Jornada Científica | `2e7c83980f36ad7404fbc26f02cea6a3d8cb49cb` |
| Quatro | `participante4` | Participante com atividades na agenda | `2a76783415d3f7834dd54081085db647599833ab` |
| Cinco | `participante5` | Participante para ocupar a última vaga da Sala 101 | `599b412f3bba66ca11c7015d52525c14feef607b` |

Os tokens estão no `db.sqlite3` entregue. Em um banco novo, `cadastrar_dados` cria tokens diferentes para as mesmas contas, que podem ser consultados com `python manage.py shell` ou obtidos em `POST /api/token/`.

Os organizadores pertencem ao grupo `Organizadores`, com a permissão `inscricoes.organizar_eventos`. Contas criadas no cadastro público não recebem permissões de organização. Qualquer usuário autenticado pode participar dos eventos.

## Salas

| Sala | Bloco | Capacidade |
| --- | --- | --- |
| Sala 101 | A | 2 |
| Laboratório de Informática | B | 25 |
| Auditório | C | 80 |

Salas são cadastradas somente no Admin. A capacidade vem da sala e não é duplicada na atividade.

## Eventos e programação

Todos os horários usam o fuso de Fortaleza.

| Evento | Período | Inscrições |
| --- | --- | --- |
| Semana de Tecnologia | 19/10/2026 - 21/10/2026 | Abertas |
| Jornada Científica | 19/10/2026 - 20/10/2026 | Abertas |
| Encontro de Egressos | 22/10/2026 | Fechadas |

| Evento | Atividade | Tipo | Sala | Data | Horário |
| --- | --- | --- | --- | --- | --- |
| Semana de Tecnologia | Django na prática | Treinamento | Sala 101 | 19/10/2026 | 09:00 - 10:00 |
| Semana de Tecnologia | Apresentação de projetos | Apresentação | Sala 101 | 19/10/2026 | 10:00 - 11:00 |
| Semana de Tecnologia | Acessibilidade na web | Palestra | Laboratório de Informática | 19/10/2026 | 09:30 - 10:30 |
| Jornada Científica | Pesquisa e inovação | Palestra | Auditório | 19/10/2026 | 09:00 - 10:00 |
| Jornada Científica | Comunicação científica | Treinamento | Auditório | 20/10/2026 | 14:00 - 15:00 |

`Django na prática` e `Pesquisa e inovação` acontecem no mesmo horário, em salas e eventos diferentes. `Acessibilidade na web` se sobrepõe a `Django na prática` e a `Apresentação de projetos`. As duas atividades da Sala 101 são consecutivas e não conflitam: uma termina exatamente quando a outra começa.

`participante4` já está inscrito na Semana de Tecnologia e na Jornada Científica, com inscrições em `Django na prática` e `Comunicação científica`. Sua agenda demonstra atividades de eventos diferentes em ordem cronológica. A Sala 101 começa com uma vaga disponível em `Django na prática`.

`participante5` já está inscrito na Semana de Tecnologia, sem atividades escolhidas. Use essa conta para preencher a última vaga de `Django na prática`. Para testar a recusa de uma terceira inscrição, cadastre outra conta pela tela pública e inscreva-a primeiro no evento.

## Modelagem e regras

- `Sala` contém nome, bloco e capacidade.
- `Evento` contém período, estado das inscrições e organizador.
- `Atividade` pertence a um evento e usa uma sala em um intervalo de data e hora.
- `InscricaoEvento` associa um participante a um evento, sem duplicidade.
- `InscricaoAtividade` liga uma inscrição no evento a uma atividade do mesmo evento, sem duplicidade.

Excluir a inscrição no evento remove suas inscrições em atividades por `CASCADE`. Salas utilizadas e usuários responsáveis por eventos usam `PROTECT`. Excluir um evento remove suas atividades e inscrições.

Dois horários conflitam quando `inicio_a < fim_b` e `fim_a > inicio_b`. Essa consulta cobre intervalos iguais, parcialmente sobrepostos e inteiramente contidos. A agenda é consultada pelo participante, incluindo todos os eventos. Atividades precisam ter duração positiva e caber integralmente no período do evento.

As validações estão nos models e também são executadas ao salvar. Os formulários reaproveitam essas regras para apresentar os erros. Alterações de período, horário ou capacidade que invalidariam inscrições existentes são recusadas.

As operações de inscrição consultam o banco dentro de `transaction.atomic()`. O SQLite está configurado com `transaction_mode="IMMEDIATE"`, que serializa as transações de escrita desde o início. Assim, dois envios simultâneos não usam a mesma última vaga nem inserem atividades conflitantes após uma consulta desatualizada. Vagas são calculadas por contagem das inscrições, sem campo persistido.

As páginas de organização exigem a permissão do grupo e conferem a propriedade do evento. As páginas autenticadas usam mixins, e as inscrições e cancelamentos usam o decorador `login_required`. O organizador e o participante são definidos a partir do usuário autenticado, sem campos para escolhê-los.

## Método HTTP

Inscrever, cancelar, salvar, excluir e sair da conta usam POST com token CSRF. GET consulta páginas e apresenta formulários ou confirmações, sem alterar o estado do sistema. A confirmação de exclusão exige um segundo envio por POST.

## API REST

A API vive sob `/api/` e usa os mesmos models do site. O site HTML continua como antes, com sessão e formulários. A API identifica o usuário somente pelo cabeçalho `Authorization: Token <token>`, sem sessão e sem CSRF.

```bash
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "participante5", "password": "Eventos@2026"}'

curl http://127.0.0.1:8000/api/atividades/

curl -X POST http://127.0.0.1:8000/api/inscricoes/atividades/ \
  -H "Authorization: Token 599b412f3bba66ca11c7015d52525c14feef607b" \
  -H "Content-Type: application/json" \
  -d '{"atividade": 1}'
```

### Endpoints

| Método | Caminho | Quem pode | Resultado |
| --- | --- | --- | --- |
| POST | `/api/token/` | Qualquer pessoa | Token do usuário e senha enviados |
| GET | `/api/salas/` e `/api/salas/{id}/` | Qualquer pessoa | Salas e capacidades |
| GET | `/api/eventos/` e `/api/eventos/{id}/` | Qualquer pessoa | Eventos |
| POST | `/api/eventos/` | Organizador | Cria evento do usuário do token |
| PUT, PATCH, DELETE | `/api/eventos/{id}/` | Organizador do evento | Altera ou exclui o evento |
| GET | `/api/eventos/{id}/programacao/` | Qualquer pessoa | O evento e suas atividades em ordem cronológica, com nome da sala e vagas restantes |
| GET | `/api/atividades/` e `/api/atividades/{id}/` | Qualquer pessoa | Atividades com nome da sala e vagas restantes. A lista é paginada e aceita `search` e `ordering` |
| POST | `/api/atividades/` | Organizador do evento informado | Cria atividade |
| PUT, PATCH, DELETE | `/api/atividades/{id}/` | Organizador do evento da atividade | Altera ou exclui a atividade |
| GET, POST | `/api/inscricoes/eventos/` | Usuário autenticado | Lista as próprias inscrições ou se inscreve em um evento |
| GET | `/api/inscricoes/eventos/{id}/` | Dono da inscrição | Detalha a inscrição |
| DELETE | `/api/inscricoes/eventos/{id}/` | Dono da inscrição | Cancela e remove as inscrições nas atividades |
| GET, POST | `/api/inscricoes/atividades/` | Usuário autenticado | Lista as próprias inscrições ou se inscreve em uma atividade |
| GET | `/api/inscricoes/atividades/{id}/` | Dono da inscrição | Detalha a inscrição |
| DELETE | `/api/inscricoes/atividades/{id}/` | Dono da inscrição | Cancela e devolve a vaga |
| GET | `/api/agenda/` | Usuário autenticado | Atividades em que o usuário está inscrito, de todos os eventos, por data e hora |
| GET | `/api/schema/` | Qualquer pessoa | Schema OpenAPI. Use `?format=json` para receber JSON |
| GET | `/api/docs/` | Qualquer pessoa | Página de documentação navegável, em http://127.0.0.1:8000/api/docs/ |

A lista de atividades usa 10 itens por página e a resposta traz `count`, `next`, `previous` e `results`. O parâmetro `search` procura o termo no título ou na descrição, e `ordering` aceita `inicio` ou `-inicio`.

```bash
curl "http://127.0.0.1:8000/api/atividades/?search=Django"
curl "http://127.0.0.1:8000/api/atividades/?ordering=-inicio"
curl "http://127.0.0.1:8000/api/eventos/1/programacao/"
curl -H "Authorization: Token 2a76783415d3f7834dd54081085db647599833ab" "http://127.0.0.1:8000/api/agenda/"
```

Sem token, as operações protegidas respondem 401. Com token de quem não tem permissão, respondem 403. Erros de regra de negócio respondem 400 com JSON no formato `{"campo": ["mensagem"]}` ou `{"non_field_errors": ["mensagem"]}`.

### Onde as regras de negócio moram, e por quê

Havia duas saídas: reescrever as regras nos serializers ou mover cada regra para um lugar que o site e a API enxerguem. A escolha foi não escrever regra nenhuma na camada da API.

| Regra | Onde está |
| --- | --- |
| 1. Vagas limitadas pela capacidade da sala | `InscricaoAtividade.clean` em `inscricoes/models.py` |
| 2. Sem duas atividades no mesmo horário | `InscricaoAtividade.clean`, e `Atividade.clean` quando o horário da atividade muda |
| 3. Sem sobreposição na mesma sala | `Atividade.clean` |
| 4. Atividade só para inscritos no evento | `InscricaoAtividade.clean` exige o mesmo evento, e `servicos.inscrever_em_atividade` recusa quem não tem inscrição no evento |
| 5. Cancelar no evento cancela nas atividades | `on_delete=CASCADE` em `InscricaoAtividade.inscricao_evento` |

- `ModeloValidado.save()` executa `full_clean()` dentro de uma transação. Qualquer caminho que grave no banco passa pelas mesmas validações: formulário, Admin, serializer ou shell.
- Os serializers apenas declaram campos. O `ModelSerializer` chama o `save()` do model, e `api/excecoes.py` converte o `ValidationError` do Django em resposta 400 com JSON. Nenhuma mensagem de regra é escrita na API.
- A ideia de extrair as operações para uma camada de serviços foi do Murilo. Operações que envolvem mais de um model ficam em `inscricoes/servicos.py`: inscrever no evento, inscrever em atividade e os dois cancelamentos. As views do site e os serializers e viewsets da API chamam essas mesmas funções, que fazem a consulta e a gravação em uma única transação.
- A permissão de organizador usa `Evento.pode_ser_gerenciado_por`, chamada pelas views do site e pela permissão `OrganizadorDoEvento` da API.
- O organizador do evento e o participante da inscrição vêm de `request.user`. Os campos são somente leitura nos serializers, e qualquer valor enviado no corpo é ignorado.
- As vagas restantes são calculadas por `Count` sobre as inscrições, na consulta `com_vagas()`, ou contadas na hora após uma gravação. Nenhum campo guarda esse número.

### ViewSet e view de função

- `SalaViewSet`, `EventoViewSet` e `AtividadeViewSet` usam ViewSet com router. São recursos com listagem, detalhe e alteração, e o `ModelViewSet` entrega os endpoints padronizados. As permissões variam por ação em `get_permissions`.
- `InscricaoEventoViewSet` e `InscricaoAtividadeViewSet` também usam router, com `GenericViewSet` e apenas criar, listar e detalhar. O `destroy` é escrito à mão porque criar e cancelar chamam as funções de `servicos.py` em vez de gravar direto pelo serializer, o que mantém a consulta e a gravação na mesma transação.
- `obter_token` usa `@api_view`. É uma ação sem recurso e sem model: recebe usuário e senha e devolve um token. A view de função é o caminho mais curto e dispensa autenticação e permissão padrão.
- `programacao_evento` e `agenda_participante` também usam `@api_view`. São consultas específicas e não um CRUD de um único recurso: uma reúne o evento e suas atividades em uma resposta, e a outra cruza as inscrições do usuário autenticado com as atividades de todos os eventos. A agenda filtra pelo usuário do token e não aceita participante no JSON.
- A busca, a ordenação e a paginação operam sobre o `QuerySet`, antes da serialização, e os parâmetros aparecem na página de documentação.

### Teste da seção 8

Regra escolhida: a número 1, a atividade não passa da capacidade da sala. A `Django na prática` acontece na Sala 101, que tem 2 vagas. `participante4` já ocupava uma e `participante5` ocupou a última. `participante6`, já inscrito no evento, tentou entrar.

```bash
curl -i -X POST http://127.0.0.1:8000/api/inscricoes/atividades/ \
  -H "Authorization: Token <token do participante6>" \
  -H "Content-Type: application/json" \
  -d '{"atividade": 1}'
```

| Pergunta | Resposta |
| --- | --- |
| Código HTTP | 400 |
| Mensagem no corpo | `{"non_field_errors": ["Esta atividade está lotada."]}` |
| Arquivo e método | `inscricoes/models.py`, `InscricaoAtividade.clean` |
| O site usa o mesmo código? | Sim |

No site, o mesmo participante enviou `POST /atividades/1/inscrever/` e foi redirecionado ao evento com a mensagem "Esta atividade está lotada.". Os dois caminhos chamam `servicos.inscrever_em_atividade`, que cria a inscrição com `InscricaoAtividade.objects.create`. Esse `create` chama `save()`, que executa `full_clean()` e chega ao mesmo `InscricaoAtividade.clean`. Há uma única cópia da regra.

## Verificação

```bash
python manage.py check
python manage.py test
```

Os testes usam um banco separado. Os 29 de `inscricoes/tests.py` cobrem o site: os 27 critérios de aceitação, autenticação, propriedade das rotas, lotação, conflitos entre eventos, cancelamentos, isolamento da agenda, painel e proteção CSRF. Também verificam intervalos adjacentes, os casos de sobreposição, edições que invalidariam inscrições e envios simultâneos para a última vaga, para horários conflitantes e para a mesma sala.

Os 7 de `api/tests_leitura.py` cobrem a leitura: lista de eventos e programação públicas, nome da sala e vagas restantes, agenda com token, isolada por usuário e em ordem, vagas da agenda considerando outros inscritos, paginação, busca, ordenação e documentação OpenAPI.

Os 43 de `api/tests.py` cobrem a escrita e as inscrições na API: obtenção de token, recusa de sessão e de token inválido, leitura pública, permissões de organizador, propriedade de eventos e atividades, erros de validação em JSON, inscrição e cancelamento no evento e nas atividades, lotação, conflitos de horário, dono da inscrição e envios simultâneos para a última vaga e para horários conflitantes.

## Requisitos pendentes

Nenhum dos requisitos obrigatórios. O desafio opcional da programação em uma única requisição não foi implementado.

## Entrega

Inclua o projeto completo, `requirements.txt`, migrations, este README e `db.sqlite3` em um repositório público no GitHub. A pasta `.venv` fica fora do controle de versão. O banco está incluído por exigência desta atividade.
