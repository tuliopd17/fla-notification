# -*- coding: utf-8 -*-
"""
Flamengo Daily Briefing
-----------------------
Boletim diario sobre o Flamengo, enviado por WhatsApp via CallMeBot.
Dados: Football-Data.org v4 (free tier, requer token gratuito).

A API foi confirmada via probe:
  - Brasileirao Serie A (BSA) acessivel no free tier (TIER_ONE)
  - Flamengo: id=1783, shortName='Flamengo'
  - Matches expostos com homeTeam, awayTeam, score.fullTime, utcDate, competition
  - Standings com position, points, playedGames, won/draw/lost, goalDifference

Variaveis de ambiente:
    FOOTBALL_DATA_TOKEN -> token de https://www.football-data.org/client/register
    CALLMEBOT_PHONE     -> seu numero internacional, ex: 5521999999999
    CALLMEBOT_APIKEY    -> apikey gerada pelo CallMeBot
    DRY_RUN             -> (opcional) "1" imprime mas nao envia
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

# Football-Data.org
FD_BASE = "https://api.football-data.org/v4"
FLAMENGO_ID = 1783                  # CR Flamengo (Rio de Janeiro)
BRASILEIRAO_CODE = "BSA"            # Campeonato Brasileiro Serie A

BR_TZ = timezone(timedelta(hours=-3))

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# Emojis em escape Unicode (alguns como literal por ja terem funcionado)
E_RUBRO = "\U0001F534" + "⚫"
E_CLOCK = "⏰"
E_CUP   = "\U0001F3C6"
E_PIN   = "\U0001F4CD"
E_FIRE  = "\U0001F525"
E_CHART = "\U0001F4CA"
E_NOTE  = "\U0001F4CB"

DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
MESES_PT = ["", "jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


# ---------- utilidades ----------

def now_br():
    return datetime.now(BR_TZ)


def parse_utc_iso(s):
    """ISO-8601 UTC (ex '2026-05-20T22:00:00Z') -> datetime em BR. None se falhar."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(BR_TZ)
    except ValueError:
        return None


def format_event_datetime(dt):
    if dt is None:
        return "data a confirmar"
    hoje = now_br().date()
    if dt.date() == hoje:
        return u"HOJE às {}".format(dt.strftime("%H:%M"))
    if dt.date() == hoje + timedelta(days=1):
        return u"AMANHÃ às {}".format(dt.strftime("%H:%M"))
    dia = DIAS_PT[dt.weekday()].upper()
    return u"{} {}/{} às {}".format(dia, dt.strftime("%d"), dt.strftime("%m"), dt.strftime("%H:%M"))


def format_short_date(dt):
    if dt is None:
        return "?"
    return u"{}/{}".format(dt.strftime("%d"), MESES_PT[dt.month])


# ---------- chamadas Football-Data ----------

def fd_get(path, token, params=None, timeout=25):
    url = FD_BASE + path
    resp = requests.get(url, headers={"X-Auth-Token": token},
                        params=params or {}, timeout=timeout)
    if resp.status_code == 429:
        raise RuntimeError("Football-Data: rate limit atingido (free tier: 10 req/min)")
    if resp.status_code == 403:
        raise RuntimeError("Football-Data: token invalido ou recurso fora do plano")
    resp.raise_for_status()
    return resp.json() or {}


def fetch_last_match(token):
    """Ultima partida finalizada do Flamengo (qualquer competicao).

    NAO usar limit=1: a API trunca antes de ordenar, retornando jogo errado.
    Pegamos todos os FINISHED e ordenamos cronologicamente.
    """
    data = fd_get("/teams/{}/matches".format(FLAMENGO_ID), token,
                  {"status": "FINISHED"})
    matches = data.get("matches") or []
    matches.sort(key=lambda m: m.get("utcDate") or "")
    return matches[-1] if matches else None


def fetch_next_match(token):
    """Proxima partida agendada do Flamengo (qualquer competicao).

    Inclui Brasileirao E Libertadores (a API expoe ambos no /teams/matches).
    NAO usar limit=1: trunca antes de ordenar (testado: retornava jogo de dezembro
    em vez do amanha). Ordenamos manualmente por utcDate.
    """
    data = fd_get("/teams/{}/matches".format(FLAMENGO_ID), token,
                  {"status": "SCHEDULED,TIMED"})
    matches = data.get("matches") or []
    matches.sort(key=lambda m: m.get("utcDate") or "")
    return matches[0] if matches else None


def fetch_brasileirao_standing(token):
    """Devolve a linha do Flamengo na tabela do Brasileirao, ou None."""
    try:
        data = fd_get("/competitions/{}/standings".format(BRASILEIRAO_CODE), token)
    except Exception as e:
        print("AVISO: nao consegui buscar tabela do Brasileirao: {}".format(e))
        return None
    for s in data.get("standings") or []:
        if s.get("type") != "TOTAL":
            continue
        for row in s.get("table") or []:
            team = row.get("team") or {}
            if team.get("id") == FLAMENGO_ID:
                return row
    return None


# ---------- montagem ----------

def _name(side):
    if not side:
        return "?"
    return side.get("shortName") or side.get("name") or "?"


def _is_fla(side):
    return bool(side) and side.get("id") == FLAMENGO_ID


def build_last_result_section(match):
    if not match:
        return None
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    score = (match.get("score") or {}).get("fullTime") or {}
    sh = score.get("home")
    sa = score.get("away")
    if sh is None or sa is None:
        return None
    comp = (match.get("competition") or {}).get("name") or ""
    kickoff = parse_utc_iso(match.get("utcDate"))
    date_str = format_short_date(kickoff)

    placar = u"{} {} x {} {}".format(_name(home), sh, _name(away), sa)
    if _is_fla(home):
        tag = u"✅ vitória" if sh > sa else (u"❌ derrota" if sh < sa else u"➖ empate")
    elif _is_fla(away):
        tag = u"✅ vitória" if sa > sh else (u"❌ derrota" if sa < sh else u"➖ empate")
    else:
        tag = ""

    lines = [u"{} *Último resultado*".format(E_CHART)]
    head = placar + (u"  ({})".format(tag) if tag else "")
    lines.append(head)
    if comp:
        lines.append(u"{} • {}".format(comp, date_str))
    return "\n".join(lines)


def build_next_match_section(match):
    if not match:
        return None
    kickoff = parse_utc_iso(match.get("utcDate"))
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    comp = (match.get("competition") or {}).get("name") or ""
    matchday = match.get("matchday")
    stage = match.get("stage")

    is_today = kickoff is not None and kickoff.date() == now_br().date()
    if is_today:
        header = u"{} *HOJE TEM MENGÃO!* {}".format(E_FIRE, E_FIRE)
    else:
        header = u"{} *Próximo jogo*".format(E_CLOCK)

    lines = [header, format_event_datetime(kickoff),
             u"{} x {}".format(_name(home), _name(away))]
    foot_bits = []
    if comp:
        comp_full = comp
        if matchday:
            comp_full += u" — Rod. {}".format(matchday)
        elif stage and stage != "REGULAR_SEASON":
            comp_full += u" — {}".format(stage.replace("_", " ").title())
        foot_bits.append(u"{} {}".format(E_CUP, comp_full))
    if foot_bits:
        lines.append(u" • ".join(foot_bits))
    return "\n".join(lines)


def build_standing_section(row):
    if not row:
        return None
    pos = row.get("position", "?")
    pts = row.get("points", "?")
    played = row.get("playedGames", "?")
    wins = row.get("won", "?")
    draws = row.get("draw", "?")
    losses = row.get("lost", "?")
    gd = row.get("goalDifference")
    gd_str = u""
    if gd is not None:
        sign = "+" if gd >= 0 else ""
        gd_str = u" • SG {}{}".format(sign, gd)
    lines = [u"{} *Situação no Brasileirão*".format(E_NOTE)]
    lines.append(u"{} {}º lugar • {} pts em {} jogos ({}V {}E {}D){}".format(
        E_CUP, pos, pts, played, wins, draws, losses, gd_str))
    return "\n".join(lines)


def build_message(token):
    today_label = now_br().strftime("%d/%m/%Y")
    dia_semana = DIAS_PT[now_br().weekday()]
    header = u"{} *Boletim do Mengão* — {}, {}".format(E_RUBRO, dia_semana, today_label)

    try:
        last = fetch_last_match(token)
    except Exception as e:
        print("AVISO: falha em fetch_last_match: {}".format(e))
        last = None
    try:
        nxt = fetch_next_match(token)
    except Exception as e:
        print("AVISO: falha em fetch_next_match: {}".format(e))
        nxt = None
    standing = fetch_brasileirao_standing(token)

    sections = [header]
    s_last = build_last_result_section(last)
    if s_last:
        sections.append(s_last)
    s_next = build_next_match_section(nxt)
    if s_next:
        sections.append(s_next)
    s_stand = build_standing_section(standing)
    if s_stand:
        sections.append(s_stand)

    if not s_last and not s_next and not s_stand:
        sections.append(u"Sem novidades hoje. É hora de descansar, Mengão.")

    sections.append(u"VAMO MENGÃO! {}".format(E_FIRE))
    return "\n\n".join(sections).strip()


def send_whatsapp(phone, apikey, message):
    params = {"phone": phone, "text": message, "apikey": apikey}
    url = "{}?{}".format(CALLMEBOT_URL, urllib.parse.urlencode(params))
    resp = requests.get(url, timeout=30)
    print("CallMeBot status={}".format(resp.status_code))
    print("CallMeBot body={}".format(resp.text[:500]))
    resp.raise_for_status()


def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    dry_run = os.environ.get("DRY_RUN") == "1"

    missing = [k for k, v in {
        "FOOTBALL_DATA_TOKEN": token,
        "CALLMEBOT_PHONE": phone,
        "CALLMEBOT_APIKEY": apikey,
    }.items() if not v]
    if missing:
        print("ERRO: variaveis de ambiente faltando: {}".format(", ".join(missing)), file=sys.stderr)
        return 2

    msg = build_message(token)
    print(u"--- BOLETIM ---")
    print(msg)
    print(u"--- FIM ---")

    if dry_run:
        print("DRY_RUN=1, nao enviei.")
        return 0

    try:
        send_whatsapp(phone, apikey, msg)
        print("Mensagem enviada com sucesso.")
    except Exception as e:
        print("ERRO ao enviar WhatsApp: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
