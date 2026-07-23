# -*- coding: utf-8 -*-
"""
Flamengo Daily Briefing
-----------------------
Boletim diario completo sobre o Mengao, via WhatsApp (wa-bridge/Baileys local).
Dados: Football-Data.org v4 (free tier).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta

import requests

FD_BASE = "https://api.football-data.org/v4"
FLAMENGO_ID = 1783
BRASILEIRAO_CODE = "BSA"

BR_TZ = timezone(timedelta(hours=-3))

# Prematch: uma unica mensagem ~10 min antes (cron a cada 15 min → janela 5–20 min).
PREMATCH_MIN_MINUTES = 5
PREMATCH_MAX_MINUTES = 20
# Postmatch: notifica placar se o kickoff foi ha entre 1h30 e 6h (jogo ja deve ter acabado).
POSTMATCH_MIN_HOURS_AFTER_KO = 1.5
POSTMATCH_MAX_HOURS_AFTER_KO = 6.0

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

DIAS_PT = [u"segunda", u"terça", u"quarta", u"quinta", u"sexta", u"sábado", u"domingo"]
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


# O 'shortName' da Football-Data corta nomes compostos pela metade
# (ex: Athletico-PR vira "Paranaense", Atlético-MG vira "Mineiro").
TEAM_NAME_FIX = {
    "Paranaense": "Athletico-PR",
    "Mineiro": "Atlético-MG",
    "Goianiense": "Atlético-GO",
}


def _name(side):
    if not side:
        return "?"
    n = side.get("shortName") or side.get("name") or "?"
    return TEAM_NAME_FIX.get(n, n)


# Siglas de 3 letras pra tabela (largura fixa, nao quebra em telas estreitas).
TEAM_CODE = {
    "Palmeiras": "PAL", "Flamengo": "FLA", "Fluminense": "FLU",
    "Athletico-PR": "CAP", "Bragantino": "RBB", "Bahia": "BAH",
    "Coritiba": "CFC", "São Paulo": "SAO", "Atlético-MG": "CAM",
    "Corinthians": "COR", "Cruzeiro": "CRU", "Botafogo": "BOT",
    "Vitória": "VIT", "Internacional": "INT", "Santos": "SAN",
    "Grêmio": "GRE", "Vasco da Gama": "VAS", "Clube do Remo": "REM",
    "Mirassol": "MIR", "Chapecoense": "CHA", "Fortaleza": "FOR",
    "Ceará": "CEA", "Sport": "SPT", "Atlético-GO": "ACG",
    "Goiás": "GOI", "Cuiabá": "CUI", "Juventude": "JUV",
    "Criciúma": "CRI", "América-MG": "AME", "Avaí": "AVA",
    "Ponte Preta": "PON",
}


def _code(name):
    return TEAM_CODE.get(name) or (name[:3].upper() if name and name != "?" else "?")


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

    lines = [u"{} *Último jogo*".format(E_CHART), u"{} {}".format(placar, tag)]
    if comp:
        lines.append(u"{} • {}".format(comp, date_str))

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
            if ratio >= 0.8: mood = u"embalado 🔥"
            elif ratio >= 0.6: mood = u"estável 👍"
            elif ratio >= 0.4: mood = u"oscilando ⚠️"
            else: mood = u"em má fase 😰"

            trend = u"➡️"
            if len(emojis) >= 4:
                half = len(emojis) // 2
                def _pts(slice_emojis):
                    return sum(3 if em == E_OK else 1 if em == E_DRAW else 0 for em in slice_emojis)
                if _pts(emojis[half:]) > _pts(emojis[:half]):
                    trend = u"↗️"
                elif _pts(emojis[half:]) < _pts(emojis[:half]):
                    trend = u"↘️"

            lines.append(u"")
            lines.append(u"{} *Forma ({}j)*".format(E_TREND, len(emojis)))
            lines.append(u"{} {}".format(trend, " ".join(emojis)))
            lines.append(u"{}V • {}E • {}D — {}".format(v, e, d, mood))
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
        header = u"{} *Próximo jogo*".format(E_CLOCK)

    lines = [header, u"{} x {}".format(_name(home), _name(away))]
    if is_today:
        lines.append(kickoff.strftime("%H:%M") if kickoff else "?")
    else:
        lines.append(format_event_datetime(kickoff))
    if comp:
        suffix = u" • Rod. {}".format(matchday) if matchday else ""
        if not suffix and stage and stage != "REGULAR_SEASON":
            suffix = u" • {}".format(stage.replace("_", " ").title())
        lines.append(u"{} {}{}".format(E_CUP, comp, suffix))
    if venue:
        lines.append(u"{} {}".format(E_PIN, venue))
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
    lines = [u"{} *Próximos jogos*".format(E_CAL)]
    for m in rest:
        kickoff = parse_utc_iso(m.get("utcDate"))
        home = _name(m.get("homeTeam"))
        away = _name(m.get("awayTeam"))
        comp_short = _short_comp_name((m.get("competition") or {}).get("name"))
        lines.append(u"{} • {} x {} ({})".format(
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
    lines = [
        u"{} *Histórico vs {} ({}j)*".format(E_BALL, opponent, len(emojis)),
        u" ".join(emojis),
        u"{}V • {}E • {}D".format(v, e, d),
    ]
    last_h2h = recent[0]
    score = (last_h2h.get("score") or {}).get("fullTime") or {}
    if score.get("home") is not None and score.get("away") is not None:
        h = _name(last_h2h.get("homeTeam"))
        a = _name(last_h2h.get("awayTeam"))
        kickoff = parse_utc_iso(last_h2h.get("utcDate"))
        date_str = format_short_date(kickoff)
        lines.append(u"Último: {} {} {} x {} {}".format(date_str, h, score["home"], score["away"], a))
    return "\n".join(lines)


def section_standings(full_table):
    """Monta a tabela completa do Brasileirao em bloco monoespacado, alinhada em colunas.
    Usa siglas de 3 letras pro time (largura fixa) pra nao quebrar linha em telas estreitas."""
    if not full_table:
        return None
    header = u"{} *TABELA BRASILEIRÃO*".format(E_NOTE)
    rows = [u" {:>2} {:<3} {:>2} {:>2} {:>3}".format("#", "Cod", "Pt", "J", "SG")]
    for row in full_table:
        pos = row.get("position")
        code = _code(_name(row.get("team")))
        pts = row.get("points")
        played = row.get("playedGames")
        gd = row.get("goalDifference")
        sg = "+{}".format(gd) if gd is not None and gd >= 0 else str(gd) if gd is not None else "?"
        is_fla = (row.get("team") or {}).get("id") == FLAMENGO_ID
        marker = u">" if is_fla else u" "
        rows.append(u"{}{:>2} {:<3} {:>2} {:>2} {:>3}".format(
            marker, pos, code, pts, played, sg))
    table_block = u"```\n{}\n```".format("\n".join(rows))
    return u"{}\n{}".format(header, table_block)


def build_message(token, full_table):
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

    s = section_calendar(upcoming)
    if s: sections.append(s)

    if len(sections) == 1:
        sections.append(u"Sem jogos hoje. Amanhã tem mais! {} {}".format(E_FIRE, E_RUBRO))

    s = section_standings(full_table)
    if s: sections.append(s)

    sections.append(u"*VAMO MENGÃO!* {} {}".format(E_FIRE, E_RUBRO))
    return "\n\n".join(sections).strip()


def _default_state_path():
    return os.environ.get(
        "STATE_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"),
    )


def load_state(path=None):
    path = path or _default_state_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"prematch_sent": [], "postmatch_sent": []}


def save_state(state, path=None):
    path = path or _default_state_path()
    # Mantem listas curtas (ultimos 50 ids) pra nao crescer pra sempre.
    for key in ("prematch_sent", "postmatch_sent"):
        ids = state.get(key) or []
        if len(ids) > 50:
            state[key] = ids[-50:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _already_sent(state, key, match_id):
    if match_id is None:
        return False
    return match_id in (state.get(key) or [])


def _mark_sent(state, key, match_id):
    if match_id is None:
        return
    ids = state.setdefault(key, [])
    if match_id not in ids:
        ids.append(match_id)


def build_prematch_message(token, state):
    """Lembrete unico ~10 min antes do kickoff (janela 5–20 min + state)."""
    try:
        upcoming = fetch_upcoming(token, n=3)
    except Exception as e:
        print("AVISO: fetch_upcoming (prematch): {}".format(e))
        return None
    if not upcoming:
        return None

    next_match = upcoming[0]
    match_id = next_match.get("id")
    kickoff = parse_utc_iso(next_match.get("utcDate"))
    if not kickoff:
        return None

    mins_left = int((kickoff - now_br()).total_seconds() / 60)
    if mins_left < PREMATCH_MIN_MINUTES or mins_left > PREMATCH_MAX_MINUTES:
        print("Prematch: jogo em {} min (fora da janela {}–{}).".format(
            mins_left, PREMATCH_MIN_MINUTES, PREMATCH_MAX_MINUTES))
        return None

    if _already_sent(state, "prematch_sent", match_id):
        print("Prematch: ja enviado pro match_id={}. Pulando.".format(match_id))
        return None

    home = _name(next_match.get("homeTeam"))
    away = _name(next_match.get("awayTeam"))
    comp = _short_comp_name((next_match.get("competition") or {}).get("name"))
    venue = next_match.get("venue")

    lines = [
        u"{} *FLA VAI A CAMPO EM ~{} MINUTOS!*".format(E_FIRE, mins_left),
        u"{} {}".format(E_CLOCK, format_event_datetime(kickoff)),
        u"{} {} x {}".format(E_BALL, home, away),
    ]
    if comp:
        lines.append(u"{} {}".format(E_CUP, comp))
    if venue:
        lines.append(u"{} {}".format(E_PIN, venue))

    lines.append(u"{} *VAMO MENGÃO!*".format(E_RUBRO))
    return "\n".join(lines), match_id


def build_postmatch_message(token, state):
    """Placar final do jogo recem-terminado (uma vez por match_id)."""
    try:
        recent = fetch_recent_finished(token, n=5)
    except Exception as e:
        print("AVISO: fetch_recent_finished (postmatch): {}".format(e))
        return None
    if not recent:
        return None

    now = now_br()
    # Do mais recente pro mais antigo; pega o primeiro elegivel.
    candidates = list(reversed(recent))
    for match in candidates:
        match_id = match.get("id")
        kickoff = parse_utc_iso(match.get("utcDate"))
        if not kickoff:
            continue

        hours_since_ko = (now - kickoff).total_seconds() / 3600
        if hours_since_ko < POSTMATCH_MIN_HOURS_AFTER_KO:
            continue
        if hours_since_ko > POSTMATCH_MAX_HOURS_AFTER_KO:
            continue
        if _already_sent(state, "postmatch_sent", match_id):
            print("Postmatch: ja enviado pro match_id={}. Pulando.".format(match_id))
            continue

        score = (match.get("score") or {}).get("fullTime") or {}
        sh, sa = score.get("home"), score.get("away")
        if sh is None or sa is None:
            print("Postmatch: match_id={} sem placar ainda.".format(match_id))
            continue

        home = match.get("homeTeam") or {}
        away = match.get("awayTeam") or {}
        comp = _short_comp_name((match.get("competition") or {}).get("name"))
        outcome = _match_outcome_for_fla(match)
        if outcome == "V":
            tag = u"{} *VITÓRIA!*".format(E_OK)
            vibe = u"VAMO MENGÃO!"
        elif outcome == "D":
            tag = u"{} *DERROTA*".format(E_X)
            vibe = u"Seguimos. Vamo Flamengo!"
        elif outcome == "E":
            tag = u"{} *EMPATE*".format(E_DRAW)
            vibe = u"Ponto conquistado. Vamo Mengão!"
        else:
            tag = u"*FIM DE JOGO*"
            vibe = u"VAMO MENGÃO!"

        placar = u"{} {} x {} {}".format(_name(home), sh, sa, _name(away))
        lines = [
            u"{} *FIM DE JOGO*".format(E_BALL),
            u"{} {}".format(placar, tag),
        ]
        if comp:
            lines.append(u"{} {}".format(E_CUP, comp))
        date_str = format_short_date(kickoff)
        if date_str:
            lines.append(u"{} {}".format(E_CLOCK, date_str))
        lines.append(u"{} *{}*".format(E_RUBRO, vibe))
        return "\n".join(lines), match_id

    print("Postmatch: nenhum jogo recem-terminado pra notificar.")
    return None


def send_whatsapp(bridge_dir, jid, message):
    """Envia via wa-bridge local (Baileys), rodando `node index.js --send <jid> <arquivo>`."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(message)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["node", "index.js", "--send", jid, tmp_path],
            cwd=bridge_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        print("wa-bridge stdout: {}".format(result.stdout.strip()))
        if result.stderr:
            print("wa-bridge stderr: {}".format(result.stderr.strip()))
        if result.returncode != 0:
            raise RuntimeError("wa-bridge saiu com codigo {}".format(result.returncode))
    finally:
        os.remove(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Flamengo Daily Briefing")
    parser.add_argument(
        "--mode",
        choices=["daily", "prematch", "postmatch"],
        default="daily",
        help=(
            "daily = boletim completo (default); "
            "prematch = 1 lembrete ~10 min antes; "
            "postmatch = placar final apos o jogo"
        ),
    )
    args = parser.parse_args()

    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    jid = os.environ.get("WA_GROUP_JID")
    bridge_dir = os.environ.get("WA_BRIDGE_DIR", os.path.expanduser("~/flaapp/wa-bridge"))
    dry_run = os.environ.get("DRY_RUN") == "1"
    state_path = _default_state_path()

    missing = [k for k, v in {
        "FOOTBALL_DATA_TOKEN": token,
        "WA_GROUP_JID": jid,
    }.items() if not v]
    if missing:
        print("ERRO: variaveis faltando: {}".format(", ".join(missing)), file=sys.stderr)
        return 2

    match_id = None
    state_key = None
    state = None

    if args.mode == "prematch":
        state = load_state(state_path)
        result = build_prematch_message(token, state)
        if result is None:
            print("Prematch: nada a enviar. Saindo silenciosamente.")
            return 0
        msg, match_id = result
        state_key = "prematch_sent"
        label = "LEMBRETE PRE-JOGO"
    elif args.mode == "postmatch":
        state = load_state(state_path)
        result = build_postmatch_message(token, state)
        if result is None:
            print("Postmatch: nada a enviar. Saindo silenciosamente.")
            return 0
        msg, match_id = result
        state_key = "postmatch_sent"
        label = "PLACAR FINAL"
    else:
        _, full_table = fetch_brasileirao_standings(token)
        msg = build_message(token, full_table)
        label = "BOLETIM"

    print(u"--- {} ({} chars) ---".format(label, len(msg)))
    print(msg)
    print(u"--- FIM ---")

    if dry_run:
        print("DRY_RUN=1, nao enviei.")
        return 0

    try:
        send_whatsapp(bridge_dir, jid, msg)
        print("Mensagem enviada com sucesso.")
    except Exception as e:
        print("ERRO ao enviar WhatsApp: {}".format(e), file=sys.stderr)
        return 1

    # So marca como enviado apos sucesso no WhatsApp (evita perder o aviso se falhar).
    if state is not None and state_key and match_id is not None:
        _mark_sent(state, state_key, match_id)
        try:
            save_state(state, state_path)
            print("State atualizado: {} += {}".format(state_key, match_id))
        except OSError as e:
            print("AVISO: nao consegui salvar state: {}".format(e))

    return 0


if __name__ == "__main__":
    sys.exit(main())
