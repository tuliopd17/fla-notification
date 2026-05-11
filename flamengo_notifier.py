# -*- coding: utf-8 -*-
"""
Flamengo Daily Briefing
-----------------------
Boletim diario sobre o Flamengo, enviado por WhatsApp via CallMeBot.
Dados: TheSportsDB (gratuita, sem chave).

Contem:
  - Ultimo resultado
  - Proximo jogo (com destaque se for HOJE)
  - Situacao nas competicoes ativas (posicao no Brasileirao, fase de mata-matas)

Variaveis de ambiente:
    CALLMEBOT_PHONE   -> seu numero internacional, ex: 5521999999999
    CALLMEBOT_APIKEY  -> apikey gerada pelo CallMeBot
    DRY_RUN           -> (opcional) "1" imprime mas nao envia
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

# ATENCAO: nao usar ID hardcoded. O 134301 e' do AFC Bournemouth.
# Resolvemos o ID dinamicamente filtrando por nome+pais.
FLAMENGO_NAME = "Flamengo"
FLAMENGO_COUNTRY = "Brazil"
BRASILEIRAO_ID = "4351"

# Cache resolvido em runtime
_FLAMENGO_ID_CACHE = None

BR_TZ = timezone(timedelta(hours=-3))

SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"
SPORTSDB_NEXT = SPORTSDB_BASE + "/eventsnext.php"
SPORTSDB_LAST = SPORTSDB_BASE + "/eventslast.php"
SPORTSDB_TABLE = SPORTSDB_BASE + "/lookuptable.php"
SPORTSDB_SEARCH = SPORTSDB_BASE + "/searchteams.php"

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

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


def now_br():
    return datetime.now(BR_TZ)


def today_br_str():
    return now_br().strftime("%Y-%m-%d")


def parse_event_kickoff(ev):
    ts = ev.get("strTimestamp")
    if ts:
        try:
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


def _http_get_json(url, params, timeout=20):
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json() or {}


def resolve_flamengo_id():
    """Descobre o idTeam do Flamengo (RJ) na TheSportsDB.

    Buscamos pelo nome e filtramos por pais=Brazil + esporte=Soccer pra evitar
    pegar o AFC Bournemouth (que se chama Bournemouth mas a busca por
    'Flamengo' tambem retorna times homonimos do exterior em alguns casos).
    """
    global _FLAMENGO_ID_CACHE
    if _FLAMENGO_ID_CACHE:
        return _FLAMENGO_ID_CACHE
    data = _http_get_json(SPORTSDB_SEARCH, {"t": FLAMENGO_NAME})
    teams = data.get("teams") or []
    # Priorizar Flamengo do RJ: nome exato + Brazil + Soccer
    for t in teams:
        name = (t.get("strTeam") or "").strip().lower()
        country = (t.get("strCountry") or "").strip().lower()
        sport = (t.get("strSport") or "").strip().lower()
        if name == "flamengo" and country == "brazil" and sport == "soccer":
            _FLAMENGO_ID_CACHE = t.get("idTeam")
            print("Flamengo resolvido: idTeam={}".format(_FLAMENGO_ID_CACHE))
            return _FLAMENGO_ID_CACHE
    # Fallback: qualquer time brasileiro chamado Flamengo
    for t in teams:
        country = (t.get("strCountry") or "").strip().lower()
        if country == "brazil":
            _FLAMENGO_ID_CACHE = t.get("idTeam")
            print("Flamengo (fallback BR) resolvido: idTeam={}".format(_FLAMENGO_ID_CACHE))
            return _FLAMENGO_ID_CACHE
    raise RuntimeError("Nao consegui resolver o idTeam do Flamengo RJ. Resposta: {}".format(teams[:2]))


def fetch_next_events():
    data = _http_get_json(SPORTSDB_NEXT, {"id": resolve_flamengo_id()})
    return data.get("events") or []


def fetch_last_events():
    data = _http_get_json(SPORTSDB_LAST, {"id": resolve_flamengo_id()})
    return data.get("results") or data.get("events") or []


def fetch_brasileirao_table():
    season = str(now_br().year)
    try:
        data = _http_get_json(SPORTSDB_TABLE, {"l": BRASILEIRAO_ID, "s": season})
    except Exception as e:
        print("AVISO: nao consegui buscar tabela do Brasileirao ({}): {}".format(season, e))
        return None
    table = data.get("table") or []
    for row in table:
        name = (row.get("strTeam") or "").lower()
        if "flamengo" in name:
            return row
    return None


def is_flamengo(team_name):
    return "flamengo" in (team_name or "").lower()


def build_last_result_section(last_events):
    if not last_events:
        return None
    ev = last_events[0]
    home = ev.get("strHomeTeam") or "?"
    away = ev.get("strAwayTeam") or "?"
    score_h = ev.get("intHomeScore")
    score_a = ev.get("intAwayScore")
    league = ev.get("strLeague") or ""
    venue = ev.get("strVenue") or ""
    kickoff = parse_event_kickoff(ev)
    date_str = format_short_date(kickoff)

    if score_h is None or score_a is None:
        return None

    placar = u"{} {} x {} {}".format(home, score_h, away, score_a)
    try:
        sh = int(score_h)
        sa = int(score_a)
        if is_flamengo(home):
            tag = u"✅ vitória" if sh > sa else (u"❌ derrota" if sh < sa else u"➖ empate")
        elif is_flamengo(away):
            tag = u"✅ vitória" if sa > sh else (u"❌ derrota" if sa < sh else u"➖ empate")
        else:
            tag = ""
    except (TypeError, ValueError):
        tag = ""

    lines = [u"{} *Último resultado*".format(E_CHART)]
    head = placar
    if tag:
        head = u"{}  ({})".format(head, tag)
    lines.append(head)
    if league and venue:
        lines.append(u"{} • {} • {}".format(league, venue, date_str))
    elif league:
        lines.append(u"{} • {}".format(league, date_str))
    elif venue:
        lines.append(u"{} • {}".format(venue, date_str))
    return "\n".join(lines)


def build_next_match_section(next_events):
    if not next_events:
        return None
    ev = next_events[0]
    kickoff = parse_event_kickoff(ev)
    home = ev.get("strHomeTeam") or "?"
    away = ev.get("strAwayTeam") or "?"
    league = ev.get("strLeague") or ""
    venue = ev.get("strVenue") or "Local a confirmar"

    is_today = kickoff is not None and kickoff.date() == now_br().date()
    if is_today:
        header = u"{} *HOJE TEM MENGÃO!* {}".format(E_FIRE, E_FIRE)
    else:
        header = u"{} *Próximo jogo*".format(E_CLOCK)

    lines = [header, format_event_datetime(kickoff), u"{} x {}".format(home, away)]
    foot_bits = []
    if league:
        foot_bits.append(u"{} {}".format(E_CUP, league))
    if venue:
        foot_bits.append(u"{} {}".format(E_PIN, venue))
    if foot_bits:
        lines.append(u" • ".join(foot_bits))
    return "\n".join(lines)


def build_competitions_section(next_events, last_events, br_table_row):
    leagues = []
    seen = set()
    for ev in (next_events + last_events):
        lg = (ev.get("strLeague") or "").strip()
        if lg and lg.lower() not in seen:
            seen.add(lg.lower())
            leagues.append(lg)

    if not leagues and not br_table_row:
        return None

    lines = [u"{} *Situação nas competições*".format(E_NOTE)]
    br_added = False
    for lg in leagues:
        lg_lower = lg.lower()
        is_brasileirao = ("serie a" in lg_lower or "série a" in lg_lower or "brasileir" in lg_lower)
        if is_brasileirao and br_table_row:
            pos = br_table_row.get("intRank") or "?"
            pts = br_table_row.get("intPoints") or "?"
            played = br_table_row.get("intPlayed") or "?"
            wins = br_table_row.get("intWin") or "?"
            draws = br_table_row.get("intDraw") or "?"
            losses = br_table_row.get("intLoss") or "?"
            lines.append(u"{} {}: {}º lugar • {} pts em {} jogos ({}V {}E {}D)".format(
                E_CUP, lg, pos, pts, played, wins, draws, losses))
            br_added = True
        elif is_brasileirao:
            lines.append(u"{} {} (tabela indisponível agora)".format(E_CUP, lg))
            br_added = True
        else:
            round_info = ""
            for ev in next_events:
                if (ev.get("strLeague") or "").lower() == lg_lower:
                    r = ev.get("intRound") or ""
                    if r:
                        round_info = u" — {}".format(r)
                    break
            lines.append(u"{} {}{}".format(E_CUP, lg, round_info))

    if br_table_row and not br_added:
        pos = br_table_row.get("intRank") or "?"
        pts = br_table_row.get("intPoints") or "?"
        played = br_table_row.get("intPlayed") or "?"
        lines.append(u"{} Brasileirão Série A: {}º lugar • {} pts em {} jogos".format(
            E_CUP, pos, pts, played))

    return "\n".join(lines)


def build_message():
    today_label = now_br().strftime("%d/%m/%Y")
    dia_semana = DIAS_PT[now_br().weekday()]
    header = u"{} *Boletim do Mengão* — {}, {}".format(E_RUBRO, dia_semana, today_label)

    try:
        next_events = fetch_next_events()
    except Exception as e:
        print("AVISO: falha em fetch_next_events: {}".format(e))
        next_events = []
    try:
        last_events = fetch_last_events()
    except Exception as e:
        print("AVISO: falha em fetch_last_events: {}".format(e))
        last_events = []
    br_row = fetch_brasileirao_table()

    sections = [header]
    s_last = build_last_result_section(last_events)
    if s_last:
        sections.append(s_last)
    s_next = build_next_match_section(next_events)
    if s_next:
        sections.append(s_next)
    s_comp = build_competitions_section(next_events, last_events, br_row)
    if s_comp:
        sections.append(s_comp)

    if not s_last and not s_next and not s_comp:
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
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    dry_run = os.environ.get("DRY_RUN") == "1"

    if not phone or not apikey:
        print("ERRO: defina CALLMEBOT_PHONE e CALLMEBOT_APIKEY", file=sys.stderr)
        return 2

    msg = build_message()
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
