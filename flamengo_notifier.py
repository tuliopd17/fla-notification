# -*- coding: utf-8 -*-
"""
Flamengo Match Notifier
-----------------------
Consulta a TheSportsDB (gratuita, sem chave), verifica se o Flamengo joga HOJE
(timezone America/Sao_Paulo) e, em caso positivo, envia uma mensagem no WhatsApp
via CallMeBot.

Variaveis de ambiente esperadas (configuradas como GitHub Secrets):
    CALLMEBOT_PHONE   -> seu numero no formato internacional, ex: 5521999999999
    CALLMEBOT_APIKEY  -> apikey gerada pelo CallMeBot
    FORCE_SEND        -> (opcional) "1" envia mensagem mesmo sem jogo (util para teste)

Nao precisa mais de chave de API de futebol -- TheSportsDB e' aberto.
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

# Flamengo na TheSportsDB. ID estavel: 134301.
FLAMENGO_ID = "134301"
BR_TZ = timezone(timedelta(hours=-3))

# Endpoint publico, free tier usa a key "3"
SPORTSDB_NEXT_EVENTS = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php"
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# Emojis em escape Unicode para evitar problemas de encoding em pipelines.
EMOJI_RED   = "\U0001F534"
EMOJI_BLACK = "⚫"
EMOJI_CLOCK = "⏰"
EMOJI_CUP   = "\U0001F3C6"
EMOJI_PIN   = "\U0001F4CD"
EMOJI_FIRE  = "\U0001F525"
EMOJI_RUBRO = EMOJI_RED + EMOJI_BLACK


def get_today_br():
    return datetime.now(BR_TZ).strftime("%Y-%m-%d")


def fetch_fixtures(today_br_str):
    """Busca os proximos jogos do Flamengo na TheSportsDB e devolve so os de hoje.

    O endpoint /eventsnext.php?id=... retorna ate 15 proximos eventos.
    Filtramos pelos que caem na data de hoje no fuso BR.
    """
    params = {"id": FLAMENGO_ID}
    resp = requests.get(SPORTSDB_NEXT_EVENTS, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json() or {}
    events = data.get("events") or []
    today_matches = []
    for ev in events:
        kickoff = _event_kickoff_br(ev)
        if kickoff is None:
            continue
        if kickoff.strftime("%Y-%m-%d") == today_br_str:
            today_matches.append(ev)
    return today_matches


def _event_kickoff_br(ev):
    """Extrai o kickoff em horario de Brasilia a partir do evento da TheSportsDB.

    A API expoe 'strTimestamp' (UTC, ISO) e tambem 'dateEvent' + 'strTime'.
    Preferimos o timestamp UTC e convertemos.
    """
    ts = ev.get("strTimestamp")
    if ts:
        try:
            # Formato tipico: "2026-05-11 22:00:00" em UTC, sem timezone
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.astimezone(BR_TZ)
        except ValueError:
            pass
    date_ev = ev.get("dateEvent")
    time_ev = ev.get("strTime") or "00:00:00"
    if date_ev:
        try:
            dt = datetime.strptime(date_ev + " " + time_ev, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return dt.astimezone(BR_TZ)
        except ValueError:
            return None
    return None


def format_message(events):
    today_br = datetime.now(BR_TZ).strftime("%d/%m/%Y")
    if not events:
        return u"{} Mengão hoje ({}): sem jogo. Descansa, Mengão.".format(EMOJI_RUBRO, today_br)

    lines = [u"{} *Jogo do Flamengo hoje* ({})".format(EMOJI_RUBRO, today_br), ""]
    for ev in events:
        kickoff = _event_kickoff_br(ev)
        hora = kickoff.strftime("%H:%M") if kickoff else "horario a confirmar"

        home = ev.get("strHomeTeam") or "?"
        away = ev.get("strAwayTeam") or "?"
        league = ev.get("strLeague") or ""
        round_ = ev.get("intRound") or ""
        venue = ev.get("strVenue") or "Local a confirmar"

        lines.append(u"{} {} - {} x {}".format(EMOJI_CLOCK, hora, home, away))
        league_line = u"{} {}".format(EMOJI_CUP, league) if league else ""
        if round_:
            league_line += u" (Rodada {})".format(round_)
        if league_line:
            lines.append(league_line)
        lines.append(u"{} {}".format(EMOJI_PIN, venue))
        lines.append("")

    lines.append(u"VAMO MENGÃO! {}".format(EMOJI_FIRE))
    return "\n".join(lines).strip()


def send_whatsapp(phone, apikey, message):
    params = {"phone": phone, "text": message, "apikey": apikey}
    url = "{}?{}".format(CALLMEBOT_URL, urllib.parse.urlencode(params))
    resp = requests.get(url, timeout=30)
    print("CallMeBot status={}".format(resp.status_code))
    print("CallMeBot body={}".format(resp.text[:500]))
    resp.raise_for_status()


def main():
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    force_send = os.environ.get("FORCE_SEND") == "1"

    missing = [k for k, v in {
        "CALLMEBOT_PHONE": phone,
        "CALLMEBOT_APIKEY": apikey,
    }.items() if not v]
    if missing:
        print("ERRO: variaveis de ambiente faltando: {}".format(", ".join(missing)), file=sys.stderr)
        return 2

    today = get_today_br()
    print("Buscando jogos do Flamengo em {}...".format(today))

    try:
        events = fetch_fixtures(today)
    except Exception as e:
        print("ERRO ao buscar fixtures: {}".format(e), file=sys.stderr)
        return 1

    print("Encontrados {} jogo(s) hoje.".format(len(events)))

    if not events and not force_send:
        print("Sem jogo hoje. Nao enviando mensagem.")
        return 0

    msg = format_message(events)
    print(u"Mensagem que sera enviada:\n" + msg)

    try:
        send_whatsapp(phone, apikey, msg)
        print("Mensagem enviada com sucesso.")
    except Exception as e:
        print("ERRO ao enviar WhatsApp: {}".format(e), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
