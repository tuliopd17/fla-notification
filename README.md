# Flamengo Daily Briefing 🔴⚫

Boletim diário sobre o Mengão direto no seu WhatsApp toda manhã.

**O que vem na mensagem:**
- 📊 Último resultado (com placar e tag de vitória/empate/derrota)
- 📈 Forma recente — série dos últimos 5 jogos (✅✅➖❌✅)
- ⏰ Próximo jogo (com destaque "🔥 HOJE TEM MENGÃO!" quando for hoje)
- 📋 Brasileirão completo — posição, pontos, V/E/D, saldo, gols pró/contra
- 📈 Distância pro líder + zona da tabela (G4 Libertadores, G6, Sul-Americana, Z4)
- 🌎 Competições ativas (Libertadores, Copa do Brasil quando entrar)
- 👨 Técnico atual
- 📅 Próximos 3 jogos no calendário

**Custo:** zero. Roda no GitHub Actions (cron gratuito), busca dados na Football-Data.org (free tier, só pede email) e envia via CallMeBot (gratuito).

Não precisa deixar nada ligado no seu computador.

---

## Como funciona

Todo dia às **08:00 (horário de Brasília)** o GitHub Actions executa o script `flamengo_notifier.py`. Ele:

1. Busca o último resultado e o próximo jogo do Flamengo na Football-Data.org.
2. Puxa a tabela atualizada do Brasileirão.
3. Monta o boletim do dia e envia no seu WhatsApp via CallMeBot.

Você recebe **1 mensagem por dia, sempre**. Em dia de jogo o boletim destaca "HOJE TEM MENGÃO!".

---

## Setup (uma vez só, ~10 minutos)

### 1. Pegar a chave do CallMeBot (WhatsApp)

1. Salve o número **+34 644 51 95 23** nos seus contatos como "CallMeBot".
2. Mande **`I allow callmebot to send me messages`** no WhatsApp para esse número.
3. Em poucos minutos você recebe uma resposta com sua **APIKEY**. Guarde.
4. Anote também o seu número no formato internacional sem `+`, ex: `5521988887777`.

> Documentação oficial: https://www.callmebot.com/blog/free-api-whatsapp-messages/

### 2. Token da Football-Data.org

1. Acesse https://www.football-data.org/client/register
2. Preencha email + nome (não pede cartão, não pede telefone). Marque "Personal" como caso de uso.
3. Na hora você recebe um email com seu **API token**. Guarde.

Free tier: 10 requisições/minuto. O boletim faz 3 por dia — está folgado.

### 3. Subir esse projeto no GitHub

```bash
cd "C:\Users\tulio\projetos-pessoais\FlaApp"
git init
git add .
git commit -m "Flamengo notifier inicial"
gh repo create flamengo-notifier --private --source=. --push
```

(Se preferir, crie o repo manualmente no github.com e faça push.)

### 4. Configurar os Secrets do GitHub

No repo no GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

Crie estes três:

| Nome                  | Valor                                                |
|-----------------------|------------------------------------------------------|
| `FOOTBALL_DATA_TOKEN` | o token que veio no email da Football-Data.org       |
| `CALLMEBOT_PHONE`     | seu número, ex: `5521988887777` (sem `+`, sem espaço)|
| `CALLMEBOT_APIKEY`    | a apikey que o CallMeBot te mandou                   |

### 5. Testar agora

No GitHub: **Actions → Flamengo Daily Briefing → Run workflow**.

Se quiser só ver no log sem enviar WhatsApp, marque **`dry_run = 1`**. Caso contrário, deixe `0` e você já recebe o boletim de hoje.

Pronto. Daqui pra frente roda automático todo dia às 8h.

---

## Customizando

**Horário do aviso:** edite o cron em `.github/workflows/flamengo-notifier.yml`. Lembre que o GitHub usa UTC (BRT = UTC−3).

```yaml
- cron: "0 11 * * *"   # 08:00 BRT (atual)
- cron: "0 12 * * *"   # 09:00 BRT
- cron: "30 10 * * *"  # 07:30 BRT
```

Obs: o cron do GitHub Actions é *best-effort* — em horários de pico pode atrasar 1–15 minutos. Em geral chega entre 08:00 e 08:05 BRT.

**Quer um lembrete extra perto do kickoff?** Dá pra adicionar uma segunda execução no cron que dispara só se houver jogo nas próximas 2h. Me avisa que eu faço.

**Quer cobertura de Libertadores/Copa do Brasil?** O free tier da Football-Data não cobre essas competições. Para incluí-las, ou pagamos o plano TIER_TWO (~$10/mês) ou complementamos com scraping pontual. Avise se quiser.

---

## Por que GitHub Actions e não um servidor 24/7?

Sua dúvida foi boa: a intuição é "preciso de um servidor sempre ligado". Mas não — o que você precisa é de **alguém que rode o script 1x por dia**. GitHub Actions faz exatamente isso de graça (até 2.000 minutos/mês em repo privado, ilimitado em público — você vai usar ~30 segundos por dia).

Vantagens vs. deixar rodando no PC:
- Não depende do seu PC estar ligado.
- Não consome luz nem CPU sua.
- Logs ficam guardados no histórico do Actions.
- Se quebrar, o GitHub te manda email.

---

## Estrutura

```
FlaApp/
├── flamengo_notifier.py        # script principal
├── requirements.txt            # dependências (só "requests")
├── .github/
│   └── workflows/
│       └── flamengo-notifier.yml   # agendamento do GitHub Actions
└── README.md
```
