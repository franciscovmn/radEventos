# Inscrições em eventos do campus

Atividade de ponto extra de Rapid Application Development (RAD), curso de Sistemas para Internet, IFPB.

## Integrante

Francisco Viana Maia Neto.

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

| Conta | Usuário | Papel |
| --- | --- | --- |
| Uma | `admin` | Superusuário, cadastra salas pelo Admin |
| Duas | `organizador2` | Organizador da Semana de Tecnologia e do Encontro de Egressos |
| Três | `organizador3` | Organizador da Jornada Científica |
| Quatro | `participante4` | Participante com atividades na agenda |
| Cinco | `participante5` | Participante para ocupar a última vaga da Sala 101 |

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

## Verificação

```bash
python manage.py check
python manage.py test
```

Os 29 testes usam um banco separado. Cobrem os 27 critérios de aceitação, autenticação, propriedade das rotas, lotação, conflitos entre eventos, cancelamentos, isolamento da agenda, painel e proteção CSRF. Também verificam intervalos adjacentes, os casos de sobreposição, edições que invalidariam inscrições e envios simultâneos para a última vaga, para horários conflitantes e para a mesma sala.

## Requisitos pendentes

Nenhum dos requisitos obrigatórios. O desafio opcional de lista de espera não foi implementado.

## Entrega

Inclua o projeto completo, `requirements.txt`, migrations, este README e `db.sqlite3` em um repositório público no GitHub. A pasta `.venv` fica fora do controle de versão. O banco está incluído por exigência desta atividade.
