"""
Flamengo Match Notifier
-----------------------
Consulta a API-Football, verifica se o Flamengo joga HOJE (timezone America/Sao_Paulo)
e, em caso positivo, envia uma mensagem no WhatsApp via CallMeBot.

Variáveis de ambiente esperadas (configuradas como GitHub Secrets):
    API_FOOTBALL_KEY  -> chave da API-Football (RapidAPI ou api-football.com)
    CALLMEBOT_PHONE   -> seu número no formato internacional, ex: 5521999999999
    CALLMEBOT_APIKEY  -> apikey gerada pelo CallMeBot
    FORCE_SEND        -> (opcional) "1" envia mensagem mesmo sem jogo (útil para teste)
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

# Flamengo team ID na API-Football
FLAMENGO_TEAM_ID = 127
BR_TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo (sem DST atualmente)

API_FOOTBALL_URL = "https://v3.football.api-sports.io/fixtures"
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def get_today_br() -> str:
    """Retorna a data de hoje no fuso BR no formato YYYY-MM-DD."""
    return datetime.now(BR_TZ).strftime("%Y-%m-%d")


def fetch_fixtures(api_key: str, date_str: str) -> list[dict[str, Any]]:
    """Busca jogos do Flamengo numa data específica."""
    headers = {"x-apisports-key": api_key}
    params = {
        "team": FLAMENGO_TEAM_ID,
        "date": date_str,
        "timezone": "America/Sao_Paulo",
    }
    resp = requests.get(API_FOOTBALL_URL, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        # API-Football devolve erros como dict ou lista
        raise RuntimeError(f"Erro da API-Football: {data['errors']}")
    return data.get("response", []) or []


def format_message(fixtures: list[dict[str, Any]]) -> str:
    """Monta a mensagem que vai pro WhatsApp."""
    today_br = datetime.now(BR_TZ).strftime("%d/%m/%Y")
    if not fixtures:
        return f"🔴⚫ Mengão hoje ({today_br}): sem jogo. Descansa, Mengão."

    lines = [f"🔴⚫ *Jogo do Flamengo hoje* ({today_br})", ""]
    for fx in fixtures:
        # Horário em ISO com timezone -> converte pro BR
        kickoff_iso = fx["fixture"]["date"]
        kickoff = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).astimezone(BR_TZ)
        hora = kickoff.strftime("%H:%M")

        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        league = fx["league"]["name"]
        round_ = fx["league"].get("round", "")
        venue = (fx["fixture"].get("venue") or {}).get("name") or "Local a confirmar"

        lines.append(f"⏰ {hora} — {home} x {away}")
        lines.append(f"🏆 {league}" + (f" ({round_})" if round_ else ""))
        lines.append(f"📍 {venue}")
        lines.append("")

    lines.append("VAMO MENGÃO! 🔥")
    return "\n".join(lines).strip()


def send_whatsapp(phone: str, apikey: str, message: str) -> None:
    """Envia mensagem via CallMeBot WhatsApp API."""
    params = {
        "phone": phone,
        "text": message,
        "apikey": apikey,
    }
    # CallMeBot espera GET com query string urlencoded
    url = f"{CALLMEBOT_URL}?{urllib.parse.urlencode(params)}"
    resp = requests.get(url, timeout=30)
    # CallMeBot retorna 200 mesmo com erro às vezes; logamos a resposta
    print(f"CallMeBot status={resp.status_code}")
    print(f"CallMeBot body={resp.text[:500]}")
    resp.raise_for_status()


def main() -> int:
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
        print(f"ERRO: variáveis de ambiente faltando: {', '.join(missing)}", file=sys.stderr)
        return 2

    today = get_today_br()
    print(f"Buscando jogos do Flamengo em {today}...")

    try:
        fixtures = fetch_fixtures(api_key, today)
    except Exception as e:
        print(f"ERRO ao buscar fixtures: {e}", file=sys.stderr)
        # Falha de API não deve quebrar o cron — só loga
        return 1

    print(f"Encontrados {len(fixtures)} jogo(s) hoje.")

    if not fixtures and not force_send:
        print("Sem jogo hoje. Não enviando mensagem.")
        return 0

    msg = format_message(fixtures)
    print("Mensagem que será enviada:\n" + msg)

    try:
        send_whatsapp(phone, apikey, msg)
        print("Mensagem enviada com sucesso.")
    except Exception as e:
        print(f"ERRO ao enviar WhatsApp: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
