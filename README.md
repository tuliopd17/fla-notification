# Flamengo Notifier 🔴⚫

Recebe um WhatsApp toda manhã quando o Flamengo joga, com horário, adversário, competição e local.

**Custo:** zero. Roda no GitHub Actions (cron gratuito), busca jogos na API-Football (free tier) e envia via CallMeBot (gratuito).

Não precisa deixar nada ligado no seu computador.

---

## Como funciona

Todo dia às **09:00 (horário de Brasília)** o GitHub Actions executa o script `flamengo_notifier.py`. Ele:

1. Pergunta pra API-Football se o Flamengo joga hoje.
2. Se joga, monta uma mensagem bonitinha.
3. Te envia via WhatsApp pelo CallMeBot.
4. Se não joga, não envia nada (assim você não recebe spam).

---

## Setup (uma vez só, ~10 minutos)

### 1. Pegar a chave do CallMeBot (WhatsApp)

1. Salve o número **+34 644 51 95 23** nos seus contatos como "CallMeBot".
2. Mande **`I allow callmebot to send me messages`** no WhatsApp para esse número.
3. Em poucos minutos você recebe uma resposta com sua **APIKEY**. Guarde.
4. Anote também o seu número no formato internacional sem `+`, ex: `5521988887777`.

> Documentação oficial: https://www.callmebot.com/blog/free-api-whatsapp-messages/

### 2. Pegar a chave da API-Football

1. Vá em https://www.api-football.com/ e crie uma conta gratuita.
2. No dashboard, copie sua **API key**. O free tier dá 100 requisições/dia — mais que suficiente (a gente faz 1 por dia).

> Alternativa: dá pra pegar via RapidAPI também, mas direto pelo site é mais simples.

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

Crie estes três:

| Nome                  | Valor                                                |
|-----------------------|------------------------------------------------------|
| `API_FOOTBALL_KEY`    | sua chave da API-Football                            |
| `CALLMEBOT_PHONE`     | seu número, ex: `5521988887777` (sem `+`, sem espaço)|
| `CALLMEBOT_APIKEY`    | a apikey que o CallMeBot te mandou                   |

### 5. Testar agora

No GitHub: **Actions → Flamengo Notifier → Run workflow**.

Marque **`force_send = 1`** se quiser receber a mensagem mesmo sem jogo hoje (pra confirmar que tá funcionando).

Pronto. Daqui pra frente roda automático todo dia.

---

## Customizando

**Horário do aviso:** edite o cron em `.github/workflows/flamengo-notifier.yml`. Lembre que o GitHub usa UTC (BRT = UTC−3).

```yaml
- cron: "0 12 * * *"   # 09:00 BRT
- cron: "0 10 * * *"   # 07:00 BRT
- cron: "30 11 * * *"  # 08:30 BRT
```

**Múltiplos avisos por dia (ex: manhã + 1h antes):** dá pra adicionar lógica no script pra calcular distância até o kickoff. Me avisa que eu faço.

**Quer também resumo semanal na segunda?** Adicione uma segunda entrada no cron e um flag pro script. Posso implementar.

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
