# -*- coding: utf-8 -*-
"""
Flamengo Daily Briefing
-----------------------
Boletim diario completo sobre o Mengao, via WhatsApp (CallMeBot).
Dados: Football-Data.org v4 (free tier).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

FD_BASE = "https://api.football-data.org/v4"
FLAMENGO_ID = 1783
BRASILEIRAO_CODE = "BSA"

BR_TZ = timezone(timedelta(hours=-3))

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# Limite seguro de chars na mensagem (a URL encoded fica ~3x maior; CallMeBot
# trunca em algum ponto da query string; testado: ate ~1500 chars funciona bem).
MAX_MESSAGE_CHARS = 1500

E_RUBRO = "\U0001F534" + "⚫"
E_CLOCK = "⏰"
E_CUP   = "\U0001F3C6"
E_PIN   = "\U0001F4CD"
E_FIRE  = "\U0001F525"
E_CHART = "\U0001F4CA"
E_NOTE  = "\U0001F4CB"
E_CAL   = "\U0001F4C5"
E_TREND = "\U0001F4C8"
E_BALL  = "⚽"
E_GLOBE = "\U0001F30E"
E_COACH = "\U0001F468"
E_OK    = "✅"
E_X     = "❌"
E_DRAW  = "➖"

DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
DIAS_PT_SHORT = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
MESES_PT = ["", "jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


def now_br():
    return datetime.now(BR_TZ)


def parse_utc_iso(s):
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


def format_calendar_line(dt):
    if dt is None:
        return "? data ?"
    dia = DIAS_PT_SHORT[dt.weekday()]
    return u"{} {}/{} {}".format(dia, dt.strftime("%d"), dt.strftime("%m"), dt.strftime("%H:%M"))


def _short_comp_name(comp_name):
    """Abrevia nomes de competicoes para economizar chars."""
    if not comp_name:
        return ""
    low = comp_name.lower()
    if "brasileiro" in low or "serie a" in low or "série a" in low:
        return "Brasileirão"
    if "libertadores" in low:
        return "Libertadores"
    if "copa do brasil" in low:
        return "Copa do Brasil"
    if "sul-americana" in low or "sulamericana" in low:
        return "Sul-Americana"
    return comp_name


def fd_get(path, token, params=None, timeout=25):
    """GET com retry em 429 (rate limit) e 5xx. 3 tentativas, backoff 2s/4s/8s."""
    url = FD_BASE + path
    for attempt in range(4):  # 1 inicial + 3 retries
        try:
            resp = requests.get(url, headers={"X-Auth-Token": token},
                                params=params or {}, timeout=timeout)
        except requests.exceptions.RequestException as e:
            if attempt < 3:
                wait = 2 ** attempt
                print("Request error: {}, retry {}/3 apos {}s...".format(e, attempt + 1, wait))
                time.sleep(wait)
                continue
            raise

        if resp.status_code == 429:
            if attempt < 3:
                wait = 2 ** attempt
                print("Rate limit (429), retry {}/3 apos {}s...".format(attempt + 1, wait))
                time.sleep(wait)
                continue
            raise RuntimeError("Football-Data: rate limit (10 req/min free tier)")

        if resp.status_code == 403:
            raise RuntimeError("Football-Data: 403 (token invalido ou recurso pago)")

        if resp.status_code >= 500 and attempt < 3:
            wait = 2 ** attempt
            print("Server error ({}), retry {}/3 apos {}s...".format(resp.status_code, attempt + 1, wait))
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json() or {}


def fetch_recent_finished(token, n=5):
    data = fd_get("/teams/{}/matches".format(FLAMENGO_ID), token, {"status": "FINISHED"})
    matches = data.get("matches") or []
    matches.sort(key=lambda m: m.get("utcDate") or "")
    return matches[-n:] if matches else []


def fetch_upcoming(token, n=5):
    data = fd_get("/teams/{}/matches".format(FLAMENGO_ID), token, {"status": "SCHEDULED,TIMED"})
    matches = data.get("matches") or []
    matches.sort(key=lambda m: m.get("utcDate") or "")
    return matches[:n]


def fetch_head2head(match_id, token, limit=5):
    """Busca historico de confrontos diretos (H2H). Pode falhar com 403 no free tier."""
    try:
        data = fd_get("/matches/{}/head2head".format(match_id), token, {"limit": str(limit)})
    except Exception as e:
        print("AVISO: nao consegui buscar head2head: {}".format(e))
        return None
    return data.get("matches") or []


def fetch_brasileirao_standings(token):
    try:
        data = fd_get("/competitions/{}/standings".format(BRASILEIRAO_CODE), token)
    except Exception as e:
        print("AVISO: nao consegui buscar tabela: {}".format(e))
        return None, None
    for s in data.get("standings") or []:
        if s.get("type") != "TOTAL":
            continue
        table = s.get("table") or []
        fla_row = None
        for row in table:
            if (row.get("team") or {}).get("id") == FLAMENGO_ID:
                fla_row = row
                break
        return fla_row, table
    return None, None


def fetch_team_info(token):
    try:
        data = fd_get("/teams/{}".format(FLAMENGO_ID), token)
    except Exception as e:
        print("AVISO: nao consegui buscar info do time: {}".format(e))
        return None
    return {
        "coach": (data.get("coach") or {}).get("name"),
        "running_competitions": [c.get("name") for c in data.get("runningCompetitions") or [] if c.get("name")],
    }


def _name(side):
    if not side:
        return "?"
    return side.get("shortName") or side.get("name") or "?"


def _is_fla(side):
    return bool(side) and side.get("id") == FLAMENGO_ID


def _match_outcome_for_fla(m):
    score = (m.get("score") or {}).get("fullTime") or {}
    sh, sa = score.get("home"), score.get("away")
    if sh is None or sa is None:
        return None
    if _is_fla(m.get("homeTeam")):
        if sh > sa: return "V"
        if sh < sa: return "D"
        return "E"
    if _is_fla(m.get("awayTeam")):
        if sa > sh: return "V"
        if sa < sh: return "D"
        return "E"
    return None


def _zona_brasileirao(pos):
    if pos is None:
        return ""
    try:
        p = int(pos)
    except (TypeError, ValueError):
        return ""
    if 1 <= p <= 4:
        return u"\U0001F30E zona de Libertadores (G4)"
    if 5 <= p <= 6:
        return u"pré-Libertadores (G6)"
    if 7 <= p <= 12:
        return u"zona de Sul-Americana"
    if 13 <= p <= 16:
        return u"meio de tabela"
    if 17 <= p <= 20:
        return u"⚠️ rebaixamento (Z4)"
    return ""


def section_last_and_form(recent_matches):
    if not recent_matches:
        return None
    last = recent_matches[-1]
    score = (last.get("score") or {}).get("fullTime") or {}
    sh, sa = score.get("home"), score.get("away")
    if sh is None or sa is None:
        return None
    home = last.get("homeTeam") or {}
    away = last.get("awayTeam") or {}
    comp = _short_comp_name((last.get("competition") or {}).get("name"))
    kickoff = parse_utc_iso(last.get("utcDate"))
    date_str = format_short_date(kickoff)

    placar = u"{} {} x {} {}".format(_name(home), sh, sa, _name(away))
    outcome = _match_outcome_for_fla(last)
    if outcome == "V": tag = E_OK
    elif outcome == "D": tag = E_X
    elif outcome == "E": tag = E_DRAW
    else: tag = ""

    lines = [u"{} {} {}".format(E_CHART, placar, tag)]
    if comp:
        lines.append(u"   {} • {}".format(comp, date_str))

    if len(recent_matches) >= 2:
        emojis = []
        v = e = d = 0
        for m in recent_matches:
            o = _match_outcome_for_fla(m)
            if o == "V": emojis.append(E_OK); v += 1
            elif o == "E": emojis.append(E_DRAW); e += 1
            elif o == "D": emojis.append(E_X); d += 1
        if emojis:
            pts_recent = v * 3 + e
            ratio = pts_recent / (len(emojis) * 3)
            if ratio >= 0.8: mood = u"— embalado"
            elif ratio >= 0.6: mood = u"— estável"
            elif ratio >= 0.4: mood = u"— oscilando"
            else: mood = u"— em má fase"

            trend = u"➡️"
            if len(emojis) >= 4:
                half = len(emojis) // 2
                def _pts(slice_emojis):
                    return sum(3 if em == E_OK else 1 if em == E_DRAW else 0 for em in slice_emojis)
                if _pts(emojis[half:]) > _pts(emojis[:half]):
                    trend = u"↗️"
                elif _pts(emojis[half:]) < _pts(emojis[:half]):
                    trend = u"↘️"

            lines.append(u"{} *Forma ({}j):* {} {} {}V {}E {}D {}".format(
                E_TREND, len(emojis), trend, "".join(emojis), v, e, d, mood))
    return "\n".join(lines)


def section_next_match(match):
    if not match:
        return None
    kickoff = parse_utc_iso(match.get("utcDate"))
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    comp = _short_comp_name((match.get("competition") or {}).get("name"))
    matchday = match.get("matchday")
    stage = match.get("stage")
    venue = match.get("venue")

    is_today = kickoff is not None and kickoff.date() == now_br().date()
    if is_today:
        header = u"{} *HOJE TEM MENGÃO!*".format(E_FIRE)
        if kickoff:
            delta = kickoff - now_br()
            hours_left = int(delta.total_seconds() / 3600)
            mins_left = int(delta.total_seconds() / 60)
            if mins_left <= 0:
                header += u" — COMEÇA AGORA"
            elif mins_left < 60:
                header += u" — em {}min".format(mins_left)
            else:
                header += u" — em {}h".format(hours_left)
    else:
        dia = DIAS_PT[kickoff.weekday()].upper() if kickoff else "?"
        header = u"{} *Próximo:* {} {}".format(E_CLOCK, dia, format_short_date(kickoff))

    lines = [header]
    lines.append(u"{} {} x {}".format(format_event_datetime(kickoff) if not is_today else kickoff.strftime("%H:%M") if kickoff else "?",
                                        _name(home), _name(away)))
    if comp:
        suffix = u" Rod. {}".format(matchday) if matchday else ""
        if not suffix and stage and stage != "REGULAR_SEASON":
            suffix = u" — {}".format(stage.replace("_", " ").title())
        lines.append(u"{} {}{}".format(E_CUP, comp, suffix))
    if venue:
        lines[-1] += u"  {} {}".format(E_PIN, venue)
    return "\n".join(lines)


def section_standings(fla_row, full_table):
    if not fla_row:
        return None
    pos = fla_row.get("position")
    pts = fla_row.get("points")
    played = fla_row.get("playedGames")
    wins = fla_row.get("won")
    draws = fla_row.get("draw")
    losses = fla_row.get("lost")
    gd = fla_row.get("goalDifference")

    sg = "+{}".format(gd) if gd is not None and gd >= 0 else str(gd) if gd is not None else "?"
    lines = [u"{} *Brasileirão:* {}º • {} pts • {}j ({}V {}E {}D) • SG {}".format(
        E_NOTE, pos, pts, played, wins, draws, losses, sg)]

    if full_table:
        leader = None
        for row in full_table:
            if row.get("position") == 1:
                leader = row
                break
        if leader and leader.get("team", {}).get("id") != FLAMENGO_ID:
            try:
                diff = leader.get("points") - pts
                lines.append(u"   {} pts do líder ({})".format(diff, _name(leader.get("team"))))
            except (TypeError, ValueError):
                pass
        elif leader and leader.get("team", {}).get("id") == FLAMENGO_ID:
            for row in full_table:
                if row.get("position") == 2:
                    try:
                        lines.append(u"   {} LÍDER +{} pts".format(E_FIRE, pts - row.get("points")))
                    except (TypeError, ValueError):
                        pass
                    break

    zona = _zona_brasileirao(pos)
    if zona:
        lines.append(u"   {}".format(zona))
    return "\n".join(lines)


def section_team_info(team_info):
    if not team_info:
        return None
    parts = []
    running = team_info.get("running_competitions") or []
    other_comps = [c for c in running if "brasileiro" not in c.lower() and "série a" not in c.lower() and "serie a" not in c.lower()]
    if other_comps:
        parts.append(u"{} *Também disputa:* {}".format(
            E_GLOBE, ", ".join(_short_comp_name(c) for c in other_comps)))
    coach = team_info.get("coach")
    if coach:
        parts.append(u"{} *Técnico:* {}".format(E_COACH, coach))
    return "\n".join(parts) if parts else None


def section_calendar(upcoming):
    if not upcoming or len(upcoming) < 2:
        return None
    rest = upcoming[1:4]
    if not rest:
        return None
    lines = [u"{} *Na agenda:*".format(E_CAL)]
    for m in rest:
        kickoff = parse_utc_iso(m.get("utcDate"))
        home = _name(m.get("homeTeam"))
        away = _name(m.get("awayTeam"))
        comp_short = _short_comp_name((m.get("competition") or {}).get("name"))
        lines.append(u"{} {} x {} ({})".format(
            format_calendar_line(kickoff), home, away, comp_short))
    return "\n".join(lines)


def section_head2head(h2h_matches, next_match):
    """Confrontos diretos recentes contra o proximo adversario (compacto)."""
    if not h2h_matches or not next_match:
        return None
    h2h = list(h2h_matches)
    h2h.sort(key=lambda m: m.get("utcDate") or "", reverse=True)
    recent = h2h[:5]
    if not recent:
        return None
    opponent = _name(next_match.get("awayTeam") if _is_fla(next_match.get("homeTeam"))
                     else next_match.get("homeTeam"))
    if not opponent or opponent == "?":
        return None
    emojis = []
    v = e = d = 0
    for m in recent:
        o = _match_outcome_for_fla(m)
        if o == "V": emojis.append(E_OK); v += 1
        elif o == "E": emojis.append(E_DRAW); e += 1
        elif o == "D": emojis.append(E_X); d += 1
    if not emojis:
        return None
    lines = [u"{} *vs {} ({}j):* {} {}V {}E {}D".format(
        E_BALL, opponent, len(emojis), "".join(emojis), v, e, d)]
    last_h2h = recent[0]
    score = (last_h2h.get("score") or {}).get("fullTime") or {}
    if score.get("home") is not None and score.get("away") is not None:
        h = _name(last_h2h.get("homeTeam"))
        a = _name(last_h2h.get("awayTeam"))
        kickoff = parse_utc_iso(last_h2h.get("utcDate"))
        date_str = format_short_date(kickoff)
        lines.append(u"   Último: {} {} {} x {} {}".format(date_str, h, score["home"], score["away"], a))
    return "\n".join(lines)


def build_message(token):
    today_label = now_br().strftime("%d/%m")
    dia_semana = DIAS_PT[now_br().weekday()]
    header = u"{} *MENGÃO* — {}, {}".format(E_RUBRO, dia_semana, today_label)

    try:
        recent = fetch_recent_finished(token, n=5)
    except Exception as e:
        print("AVISO: fetch_recent_finished: {}".format(e))
        recent = []
    try:
        upcoming = fetch_upcoming(token, n=5)
    except Exception as e:
        print("AVISO: fetch_upcoming: {}".format(e))
        upcoming = []
    fla_row, full_table = fetch_brasileirao_standings(token)

    sections = [header]
    s = section_last_and_form(recent)
    if s: sections.append(s)
    s = section_next_match(upcoming[0] if upcoming else None)
    if s: sections.append(s)

    # H2H contra o proximo adversario (se houver jogo futuro)
    if upcoming:
        try:
            next_match = upcoming[0]
            h2h = fetch_head2head(next_match.get("id"), token)
            s = section_head2head(h2h, next_match)
            if s: sections.append(s)
        except Exception as e:
            print("AVISO: section_head2head: {}".format(e))

    s = section_standings(fla_row, full_table)
    if s: sections.append(s)
    s = section_calendar(upcoming)
    if s: sections.append(s)

    if len(sections) == 1:
        sections.append(u"Sem novidades hoje. Amanhã tem mais, Mengão!")

    sections.append(u"*VAMO MENGÃO!* {} {}".format(E_FIRE, E_RUBRO))
    return "\n\n".join(sections).strip()


def build_prematch_message(token):
    """Monta lembrete compacto de pre-jogo (so se houver jogo nas proximas 2h)."""
    try:
        upcoming = fetch_upcoming(token, n=3)
    except Exception as e:
        print("AVISO: fetch_upcoming (prematch): {}".format(e))
        return None
    if not upcoming:
        return None

    next_match = upcoming[0]
    kickoff = parse_utc_iso(next_match.get("utcDate"))
    if not kickoff:
        return None

    delta = kickoff - now_br()
    hours_left = delta.total_seconds() / 3600
    # So dispara se o jogo comecar entre -10min e +2h
    if hours_left < -0.17 or hours_left > 2.0:
        return None

    home = _name(next_match.get("homeTeam"))
    away = _name(next_match.get("awayTeam"))
    comp = _short_comp_name((next_match.get("competition") or {}).get("name"))
    venue = next_match.get("venue")

    mins_left = int(delta.total_seconds() / 60)
    if mins_left <= 0:
        countdown = u"COMEÇA AGORA!"
    elif mins_left < 60:
        countdown = u"em {} minutos".format(mins_left)
    else:
        countdown = u"em {}h{}".format(hours_left,
                                       " e {}min".format(mins_left % 60) if mins_left % 60 else "")

    lines = [
        u"{} *FLA VAI A CAMPO {}!*".format(E_FIRE, countdown.upper()),
        u"{} {}".format(E_CLOCK, format_event_datetime(kickoff)),
        u"{} {} x {}".format(E_BALL, home, away),
    ]
    if comp:
        lines.append(u"{} {}".format(E_CUP, comp))
    if venue:
        lines.append(u"{} {}".format(E_PIN, venue))

    lines.append(u"\n{} *VAMO MENGÃO!*".format(E_RUBRO))
    return "\n".join(lines)


def send_whatsapp(phone, apikey, message):
    """Envia via CallMeBot (GET). Trunca defensivamente se passar do limite seguro."""
    if len(message) > MAX_MESSAGE_CHARS:
        # Trunca preservando o '\n\nVAMO MENGAO! 🔥' do fim
        suffix = u"\n\n*VAMO MENGÃO!* {} {}".format(E_FIRE, E_RUBRO)
        budget = MAX_MESSAGE_CHARS - len(suffix) - 4
        message = message[:budget].rstrip() + u" …" + suffix
        print("AVISO: mensagem truncada para {} chars (limite {})".format(len(message), MAX_MESSAGE_CHARS))

    params = {"phone": phone, "text": message, "apikey": apikey}
    url = "{}?{}".format(CALLMEBOT_URL, urllib.parse.urlencode(params))
    print("URL final tem {} chars".format(len(url)))
    resp = requests.get(url, timeout=30)
    print("CallMeBot status={} msg_len={}".format(resp.status_code, len(message)))
    print("CallMeBot body={}".format(resp.text[:500]))
    resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="Flamengo Daily Briefing")
    parser.add_argument("--mode", choices=["daily", "prematch"], default="daily",
                        help="daily = boletim completo (default); prematch = lembrete 2h antes do jogo")
    args = parser.parse_args()

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
        print("ERRO: variaveis faltando: {}".format(", ".join(missing)), file=sys.stderr)
        return 2

    if args.mode == "prematch":
        msg = build_prematch_message(token)
        if msg is None:
            print("Prematch: nenhum jogo nas proximas 2h. Saindo silenciosamente.")
            return 0
        label = "LEMBRETE PRE-JOGO"
    else:
        msg = build_message(token)
        label = "BOLETIM"

    print(u"--- {} ({} chars) ---".format(label, len(msg)))
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
