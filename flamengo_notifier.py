# -*- coding: utf-8 -*-
"""
Flamengo Match Notifier
-----------------------
Consulta a API-Football, verifica se o Flamengo joga HOJE (timezone America/Sao_Paulo)
e, em caso positivo, envia uma mensagem no WhatsApp via CallMeBot.

Variaveis de ambiente esperadas (configuradas como GitHub Secrets):
    API_FOOTBALL_KEY  -> chave da API-Football (api-football.com)
    CALLMEBOT_PHONE   -> seu numero no formato internacional, ex: 5521999999999
    CALLMEBOT_APIKEY  -> apikey gerada pelo CallMeBot
    FORCE_SEND        -> (opcional) "1" envia mensagem mesmo sem jogo (util para teste)
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

FLAMENGO_TEAM_ID = 127
BR_TZ = timezone(timedelta(hours=-3))

API_FOOTBALL_URL = "https://v3.football.api-sports.io/fixtures"
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# Emojis em escape Unicode para evitar qualquer problema de encoding na pipeline.
EMOJI_RED   = "\U0001F534"  # circulo vermelho
EMOJI_BLACK = "⚫"      # circulo preto
EMOJI_CLOCK = "⏰"      # despertador
EMOJI_CUP   = "\U0001F3C6"  # trofeu
EMOJI_PIN   = "\U0001F4CD"  # pin de localizacao
EMOJI_FIRE  = "\U0001F525"  # fogo
EMOJI_RUBRO = EMOJI_RED + EMOJI_BLACK


def get_today_br():
    return datetime.now(BR_TZ).strftime("%Y-%m-%d")


def fetch_fixtures(api_key, date_str):
    """Busca jogos do Flamengo numa data especifica.

    A API-Football exige `season` quando se filtra por `team`. Usamos o ano da
    propria data consultada (calendario brasileiro = ano civil).
    """
    headers = {"x-apisports-key": api_key}
    season = int(date_str.split("-")[0])
    params = {
        "team": FLAMENGO_TEAM_ID,
        "season": season,
        "date": date_str,
        "timezone": "America/Sao_Paulo",
    }
    resp = requests.get(API_FOOTBALL_URL, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    errors = data.get("errors")
    if errors and (isinstance(errors, dict) or len(errors) > 0):
        raise RuntimeError("Erro da API-Football: {}".format(errors))
    return data.get("response", []) or []


def format_message(fixtures):
    today_br = datetime.now(BR_TZ).strftime("%d/%m/%Y")
    if not fixtures:
        return u"{} Mengão hoje ({}): sem jogo. Descansa, Mengão.".format(EMOJI_RUBRO, today_br)

    lines = [u"{} *Jogo do Flamengo hoje* ({})".format(EMOJI_RUBRO, today_br), ""]
    for fx in fixtures:
        kickoff_iso = fx["fixture"]["date"]
        kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).astimezone(BR_TZ)
        hora = kickoff.strftime("%H:%M")

        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        league = fx["league"]["name"]
        round_ = fx["league"].get("round", "")
        venue = (fx["fixture"].get("venue") or {}).get("name") or "Local a confirmar"

        lines.append(u"{} {} - {} x {}".format(EMOJI_CLOCK, hora, home, away))
        lines.append(u"{} {}".format(EMOJI_CUP, league) + (u" ({})".format(round_) if round_ else ""))
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
    api_key = os.environ.get("API_FOOTBALL_KEY")
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    force_send = os.environ.get("FORCE_SEND") == "1"

    missing = [k for k, v in {
        "API_FOOTBALL_KEY": api_key,
        "CALLMEBOT_PHONE": phone,
        "CALLMEBOT_APIKEY": apikey,
    }.items() if not v]
    if missing:
        print("ERRO: variaveis de ambiente faltando: {}".format(", ".join(missing)), file=sys.stderr)
        return 2

    today = get_today_br()
    print("Buscando jogos do Flamengo em {}...".format(today))

    try:
        fixtures = fetch_fixtures(api_key, today)
    except Exception as e:
        print("ERRO ao buscar fixtures: {}".format(e), file=sys.stderr)
        return 1

    print("Encontrados {} jogo(s) hoje.".format(len(fixtures)))

    if not fixtures and not force_send:
        print("Sem jogo hoje. Nao enviando mensagem.")
        return 0

    msg = format_message(fixtures)
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
