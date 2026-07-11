# Flamengo Daily Briefing 🔴⚫

Boletim diário sobre o Mengão direto no seu WhatsApp toda manhã.

**O que vem na mensagem:**
- 📊 Último resultado (com placar e tag de vitória/empate/derrota)
- 📈 Forma recente — série dos últimos 5 jogos (✅✅➖❌✅)
- ⏰ Próximo jogo (com destaque "🔥 HOJE TEM MENGÃO!" quando for hoje)
- ⚽ Confrontos diretos recentes contra o próximo adversário
- 📅 Próximos 3 jogos no calendário
- 📋 Tabela completa do Brasileirão (mensagem separada)

Em dia de jogo, um lembrete extra dispara perto do kickoff (janela de -10min a +2h).

---

## Como funciona

Roda self-hosted numa VM (Oracle Cloud), sem depender de GitHub Actions:

1. **cron** na VM chama `flamengo_notifier.py` todo dia às **08:00 BRT** (boletim) e a cada 15min (checagem de pré-jogo, que só dispara mensagem se houver jogo na janela).
2. O script busca dados na **Football-Data.org** (free tier): último resultado, próximo jogo, H2H, tabela do Brasileirão.
3. Monta o boletim + a tabela (duas mensagens) e envia via **wa-bridge**, uma ponte local em Node.js (Baileys) que fala direto com o WhatsApp — sem API paga, sem CallMeBot.

### Estrutura na VM

```
~/flaapp/
├── flamengo_notifier.py
├── requirements.txt
├── venv/                  # Python 3.12 virtualenv
├── run.sh                 # carrega .env e roda o script
├── .env                   # FOOTBALL_DATA_TOKEN, WA_GROUP_JID, WA_BRIDGE_DIR
├── logs/                  # daily.log, prematch.log
└── wa-bridge/
    ├── index.js           # ponte WhatsApp (Baileys)
    └── auth/               # sessão pareada (não versionar)
```

Crontab (`crontab -l` na VM):
```cron
0 8 * * * /home/ubuntu/flaapp/run.sh --mode daily >> /home/ubuntu/flaapp/logs/daily.log 2>&1
*/15 * * * * /home/ubuntu/flaapp/run.sh --mode prematch >> /home/ubuntu/flaapp/logs/prematch.log 2>&1
```

VM já roda em `America/Sao_Paulo`, então os horários do cron já são BRT direto (sem conversão UTC).

### wa-bridge

Ponte standalone em `~/flaapp/wa-bridge` (não versionada neste repo). Modos:
- `node index.js` — pareia (QR ou `--pair <numero>`) e mantém sessão viva em `./auth`.
- `node index.js --list-groups` — lista JIDs dos grupos acessíveis.
- `node index.js --send <jid> <arquivo>` — manda o conteúdo do arquivo pro JID e sai.

A sessão pareada fica em `./auth` — se for deslogada do WhatsApp, apague a pasta e pareie de novo.

---

## Setup em nova VM

### 1. Token da Football-Data.org

1. Acesse https://www.football-data.org/client/register
2. Preencha email + nome. Marque "Personal" como caso de uso.
3. Você recebe um email com seu **API token**.

Free tier: 10 requisições/minuto. O boletim faz poucas por dia — folgado.

### 2. Deploy do código

```bash
scp flamengo_notifier.py requirements.txt ubuntu@<VM>:~/flaapp/
ssh ubuntu@<VM> "cd ~/flaapp && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
```

### 3. wa-bridge

Suba `wa-bridge/index.js` pra `~/flaapp/wa-bridge/`, `npm install` as deps do Baileys, e pareie:

```bash
ssh ubuntu@<VM> "cd ~/flaapp/wa-bridge && node index.js --pair 5521988887777"
```

Digite o código de pareamento no celular: WhatsApp → Aparelhos conectados → Conectar dispositivo → Conectar com número de telefone.

Depois, descubra o JID do grupo alvo:

```bash
ssh ubuntu@<VM> "cd ~/flaapp/wa-bridge && node index.js --list-groups"
```

### 4. `.env` e `run.sh`

```bash
cat > ~/flaapp/.env <<'EOF'
FOOTBALL_DATA_TOKEN=xxxx
WA_GROUP_JID=1203xxxxxxxx@g.us
WA_BRIDGE_DIR=/home/ubuntu/flaapp/wa-bridge
EOF
chmod 600 ~/flaapp/.env
```

`run.sh` carrega o `.env` e chama o script com o `venv`:

```bash
#!/bin/bash
set -a
source /home/ubuntu/flaapp/.env
set +a
cd /home/ubuntu/flaapp
exec ./venv/bin/python flamengo_notifier.py "$@"
```

### 5. Testar

```bash
ssh ubuntu@<VM> "cd ~/flaapp && DRY_RUN=1 ./run.sh --mode daily"   # só imprime
ssh ubuntu@<VM> "cd ~/flaapp && ./run.sh --mode daily"             # envia de verdade
```

### 6. Crontab

```bash
ssh ubuntu@<VM> "crontab -l" # editar/adicionar as duas linhas do bloco acima
```

---

## Customizando

**Horário do boletim:** edite a linha `0 8 * * *` no crontab da VM.

**Cobertura de Libertadores/Copa do Brasil:** o free tier da Football-Data não cobre essas competições. Precisaria do plano TIER_TWO (~$10/mês) ou scraping pontual.

---

## Por que self-hosted e não GitHub Actions?

GitHub Actions (`ubuntu-latest`) não consegue rodar o wa-bridge — a sessão do Baileys precisa de um processo Node.js persistente com estado local (`./auth`), e cada job do Actions começa do zero. Por isso a execução foi movida pra uma VM sempre ligada (Oracle Cloud free tier), com cron cuidando do agendamento.
