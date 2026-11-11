# Inscrições em eventos do campus

Projeto de Rapid Application Development (RAD), curso de Sistemas para Internet, IFPB: site em HTML e API REST do sistema de inscrições em eventos do campus. A atividade 08 acrescentou a suíte de testes automatizados, sem nenhuma funcionalidade nova.

## Integrantes

- Francisco Viana Maia Neto.
- Murilo Maciel Rodrigues.

Como dividimos o trabalho:

Na atividade 06, fiquei com a configuração do DRF, o token, os serializers e ViewSets de salas, eventos, atividades e inscrições, as permissões, o tratamento de erros, os testes da escrita e este README. Minha dupla propôs mover as regras e as operações de inscrição das views para uma camada de serviços compartilhada com a API, fez o rascunho dessa camada (`obter_agenda_participante` e `obter_dados_evento`) e cuidou da leitura da API: programação do evento, agenda do participante, busca e ordenação das atividades, documentação OpenAPI e os testes dessa parte.

Na atividade 08, minha dupla escreveu os primeiros testes das regras pela API, da validação, da porta aberta, da porta fechada e das consultas. Fiquei com a organização do pacote `tests/`, os testes de models, formulários e site e a tabela de sabotagem.

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
- Os serializers apenas declaram campos. O `ModelSerializer` chama o `save()` do model, e `api/excecoes.py` converte o `ValidationError` do Django em resposta 400 com JSON. Nenhuma mensagem das cinco regras é escrita na API.
- Operações que envolvem mais de um model ficam em `inscricoes/servicos.py`: inscrever no evento, inscrever em atividade e os dois cancelamentos. As views do site e os serializers e viewsets da API chamam essas mesmas funções, que fazem a consulta e a gravação em uma única transação.
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

## Testes automatizados

```bash
python manage.py test
python manage.py test --shuffle
python manage.py test inscricoes.tests.test_models
coverage run manage.py test
coverage report
```

A suíte tem 177 testes e leva cerca de 13 segundos. Cada teste cria os próprios dados em um banco separado, então ela passa com o `db.sqlite3` apagado.

| Arquivo em `inscricoes/tests/` | Testes | Assunto |
| --- | --- | --- |
| `test_models.py` | 27 | Cinco regras no model, validação com `full_clean()` e edições com inscritos |
| `test_forms.py` | 9 | `EventoForm` e `AtividadeForm` instanciados sem view |
| `test_views.py` | 60 | Cinco regras pelo site, programação, inscrição e cancelamento, anônimo, autorização e consultas |
| `test_api.py` | 76 | Cinco regras pela API, porta aberta, porta fechada e consultas |
| `test_concorrencia.py` | 5 | Envios simultâneos para a última vaga, a mesma agenda e a mesma sala |

`base.py` guarda os cenários compartilhados. Os testes das cinco regras começam com `test_regra1` a `test_regra5`: são 30, sendo 10 de recusa e 10 de aceite pelas duas portas e mais 10 no model.

### Tabela de sabotagem

Fiz cada linha em uma cópia do projeto, uma sabotagem por vez: apliquei a alteração, rodei a suíte inteira e desfiz. A coluna do meio traz o teste de cada porta na suíte final e o total de testes que caem. Fiz a primeira rodada na suíte de 102 testes que existia antes do pacote `tests/`.

| Sabotagem | Teste que falhou | Verde na 1ª rodada? |
| --- | --- | --- |
| 1. Capacidade da sala | `test_regra1_site_recusa_quando_a_sala_esta_cheia`, `test_regra1_api_recusa_quando_a_sala_esta_cheia` (8 no total) | não |
| 2. Horário sobreposto | `test_regra2_site_recusa_atividade_em_horario_sobreposto`, `test_regra2_api_recusa_atividade_em_horario_sobreposto` (8 no total) | não |
| 3. Sala ocupada | `test_regra3_site_recusa_mesma_sala_em_horario_sobreposto`, `test_regra3_api_recusa_mesma_sala_em_horario_sobreposto` (9 no total) | não |
| 4. Inscrição prévia no evento | `test_regra4_site_recusa_quem_nao_esta_inscrito_no_evento`, `test_regra4_api_recusa_quem_nao_esta_inscrito_no_evento` (4 no total) | não |
| 5. Cancelamento em cascata | `test_regra5_site_cancelar_no_evento_cancela_as_atividades`, `test_regra5_api_cancelar_no_evento_cancela_as_atividades` (5 no total) | não |
| 6. `render` depois do POST | `test_inscrever_na_atividade_grava_redireciona_e_confirma`, `test_inscrever_no_evento_grava_redireciona_e_confirma` | não, mas na atividade só por acidente |
| 7. Verificação de dono | `test_organizador_nao_edita_evento_de_outro_organizador` (site), `test_organizador_nao_edita_evento_de_outro` (API) | não |
| 8. Campo extra na porta aberta | `test_lista_de_atividades_e_publica_e_retorna_so_os_campos_esperados`, `test_programacao_publica_retorna_dados_esperados_e_nada_privado` | sim, no `AtividadeSerializer` |
| 9. `select_related` da programação | `test_programacao_publica_usa_numero_fixo_de_consultas` (API), `test_programacao_do_site_faz_as_mesmas_consultas_com_mais_atividades` (site) | não, mas só a API tinha teste |

Como refazer cada uma:

1. `InscricaoAtividade.clean`: comentar o `if` que levanta `Esta atividade está lotada.`
2. `InscricaoAtividade.clean`: comentar o `if` que levanta `Esta atividade conflita com outra inscrição na sua agenda.`
3. `Atividade.clean`: comentar o `if` que usa `sobrepostas`.
4. `servicos.inscrever_em_atividade`: comentar o `if inscricao is None`.
5. `InscricaoAtividade.inscricao_evento`: trocar `models.CASCADE` por `models.DO_NOTHING`. O teste aparece como F e como E, porque os registros órfãos também quebram a chave estrangeira no fim do teste.
6. `inscrever_atividade` e, em outra execução, `inscrever_evento`: trocar o `redirect` por `render` de `eventos/detalhe.html`.
7. `EventoUpdateView`: tirar `ObjetoDoOrganizadorMixin`. Na API: tirar `OrganizadorDoEvento()` de `get_permissions`.
8. `AtividadeSerializer`: acrescentar `organizador_id` com `source="evento.organizador_id"`. Em outra execução, `EventoSerializer`: acrescentar `organizador_email`.
9. `AtividadeQuerySet.com_vagas`: tirar o `select_related`. Em outra execução, `programacao_evento`: tirar o `select_related("organizador")`.

### O que a primeira rodada mostrou

- Sabotagem 8: o campo novo no `AtividadeSerializer` não derrubou nada. Três testes do commit `6360b9a` estavam com a indentação errada, fora da classe, e o Django nunca os executou. Corrigi a indentação e eles agora são `test_programacao_publica_retorna_dados_esperados_e_nada_privado`, `test_lista_de_atividades_e_publica_e_retorna_so_os_campos_esperados` e `test_consulta_de_salas_e_publica_e_retorna_so_os_campos_esperados`.
- Sabotagem 6: no POST de inscrição em atividade, só caíram os dois testes de concorrência, que comparam o código 302 por outro motivo. Acrescentei a classe `InscricaoECancelamentoTests`, que confere o banco, o redirecionamento e a mensagem.
- Sabotagem 9: a programação do site não tinha nenhum teste de consultas. Acrescentei `test_programacao_do_site_faz_as_mesmas_consultas_com_mais_atividades`.
- Sabotagem 4: sem a verificação do serviço, o model ainda recusa porque `inscricao_evento` fica nulo. A resposta continua sendo 400, com outra mensagem, e por isso o teste que olhava só o status passou. Fiz esse teste conferir a mensagem.

### Cobertura

Medi 97% de cobertura: 622 instruções, 16 sem execução, sem contar migrations e testes. A suíte de 102 testes da primeira rodada também dava 97%, e o `api/serializers.py` já estava em 100%. Ou seja, o número não mudou com 75 testes a mais, e foi com esses mesmos 97% que um campo novo no serializer passou despercebido. Cobertura diz que a linha rodou, não que alguém conferiu o resultado. O que a tabela de sabotagem mediu foi outra coisa, e os testes que ela me fez escrever não moveram o percentual. As 16 linhas restantes são os dois `save_model` do Admin, a ordenação padrão quando a API recebe um `ordering` inválido e validações de edição, como a troca para uma sala menor que o número de inscritos (`Atividade.clean`). Elas continuam sem teste.

### Regras escritas em dois lugares

Nenhuma das cinco regras tinha a recusa escrita duas vezes. As sabotagens de 1 a 5 mostram isso: uma única alteração derrubou ao mesmo tempo os testes do site e os da API. O que existe é uma cópia parcial: `servicos.obter_dados_evento` repete a comparação de horário da regra 2 para esconder o botão de inscrição. Ela só decide o que aparece na tela, e quem recusa é `InscricaoAtividade.clean`. Como esta atividade não muda comportamento, mantive a cópia e registrei aqui.

Fora das cinco regras, `AtividadeSerializer.validate_evento` recusa qualquer troca de evento, enquanto `Atividade.clean` só recusa quando há inscritos. O formulário do site não tem esse campo, então a recusa mais rígida só existe na API.

## Requisitos pendentes

Nenhum dos requisitos obrigatórios. Não fiz os desafios opcionais da atividade 06 nem os desafios A e B da atividade 08.

## Entrega

O repositório público no GitHub traz o projeto completo, `requirements.txt`, migrations, este README e o `db.sqlite3`. A pasta `.venv` fica fora do controle de versão. Mantive o banco no repositório por exigência da atividade 06.
