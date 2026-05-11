# Flamengo Daily Briefing 🔴⚫

Boletim diário sobre o Mengão direto no seu WhatsApp toda manhã.

**O que vem na mensagem:**
- 📊 Último resultado (com placar e indicação de vitória/empate/derrota)
- ⏰ Próximo jogo (com destaque especial se for HOJE)
- 📋 Situação nas competições (posição no Brasileirão, fase em mata-matas, ligas ativas)

**Custo:** zero. Roda no GitHub Actions (cron gratuito), busca dados na TheSportsDB (gratuita, sem chave) e envia via CallMeBot (gratuito).

Não precisa deixar nada ligado no seu computador.

---

## Como funciona

Todo dia às **09:00 (horário de Brasília)** o GitHub Actions executa o script `flamengo_notifier.py`. Ele:

1. Busca os próximos e últimos jogos do Flamengo na TheSportsDB.
2. Puxa a tabela do Brasileirão e identifica as competições em que o time está.
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

### 2. API de futebol

Não precisa de nada. Usamos a [TheSportsDB](https://www.thesportsdb.com/), que é totalmente gratuita e não exige cadastro ou chave de API. O Flamengo tem ID fixo `134301` lá.

### 3. Subir esse projeto no GitHub

```bash
cd "C:\Users\tulio\OneDrive\Documentos\Claude\Projects\FlaApp"
git init
git add .
git commit -m "Flamengo notifier inicial"
gh repo create flamengo-notifier --private --source=. --push
```

(Se preferir, crie o repo manualmente no github.com e faça push.)

### 4. Configurar os Secrets do GitHub

No repo no GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

Crie estes dois:

| Nome                  | Valor                                                |
|-----------------------|------------------------------------------------------|
| `CALLMEBOT_PHONE`     | seu número, ex: `5521988887777` (sem `+`, sem espaço)|
| `CALLMEBOT_APIKEY`    | a apikey que o CallMeBot te mandou                   |

### 5. Testar agora

No GitHub: **Actions → Flamengo Daily Briefing → Run workflow**.

Se quiser só ver no log sem enviar WhatsApp, marque **`dry_run = 1`**. Caso contrário, deixe `0` e você já recebe o boletim de hoje.

Pronto. Daqui pra frente roda automático todo dia às 9h.

---

## Customizando

**Horário do aviso:** edite o cron em `.github/workflows/flamengo-notifier.yml`. Lembre que o GitHub usa UTC (BRT = UTC−3).

```yaml
- cron: "0 12 * * *"   # 09:00 BRT
- cron: "0 10 * * *"   # 07:00 BRT
- cron: "30 11 * * *"  # 08:30 BRT
```

**Quer um lembrete extra perto do kickoff?** Dá pra adicionar uma segunda execução no cron que dispara só se houver jogo nas próximas 2h. Me avisa que eu faço.

**Quer placar quase em tempo real (notificação no fim do jogo)?** A TheSportsDB tem endpoint de eventos ao vivo (`/eventslivescore.php`). Posso adicionar um job que roda a cada 30min só nos dias de jogo.

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
