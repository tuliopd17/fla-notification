# -*- coding: utf-8 -*-
"""
Flamengo Daily Briefing
-----------------------
Boletim diario completo sobre o Mengao, via WhatsApp (CallMeBot).
Dados: Football-Data.org v4 (free tier).

Secoes:
  - Ultimo resultado + forma recente (ultimos 5)
  - Proximo jogo (com destaque HOJE TEM MENGAO)
  - Tabela do Brasileirao + distancia pro lider + zona de classificacao
  - Competicoes ativas + tecnico
  - Calendario dos proximos 3 jogos

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

# Emojis
E_RUBRO = "\U0001F534" + "⚫"
E_CLOCK = "⏰"
E_CUP   = "\U0001F3C6"
E_PIN   = "\U0001F4CD"
E_FIRE  = "\U0001F525"
E_CHART = "\U0001F4CA"
E_NOTE  = "\U0001F4CB"
E_CAL   = "\U0001F4C5"           # calendario
E_TREND = "\U0001F4C8"           # grafico subindo
E_BALL  = "⚽"
E_GLOBE = "\U0001F30E"           # globo (Libertadores)
E_COACH = "\U0001F468"           # pessoa (tecnico)
E_OK    = "✅"
E_X     = "❌"
E_DRAW  = "➖"

DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
DIAS_PT_SHORT = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
MESES_PT = ["", "jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


# ---------- utilidades ----------

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
    """'QUA 20/05 21:30' -- formato compacto pro calendario."""
    if dt is None:
        return "? data ?"
    dia = DIAS_PT_SHORT[dt.weekday()]
    return u"{} {}/{} {}".format(dia, dt.strftime("%d"), dt.strftime("%m"), dt.strftime("%H:%M"))


# ---------- chamadas Football-Data ----------

def fd_get(path, token, params=None, timeout=25):
    url = FD_BASE + path
    resp = requests.get(url, headers={"X-Auth-Token": token},
                        params=params or {}, timeout=timeout)
    if resp.status_code == 429:
        raise RuntimeError("Football-Data: rate limit (10 req/min free tier)")
    if resp.status_code == 403:
        raise RuntimeError("Football-Data: 403 (token invalido ou recurso pago)")
    resp.raise_for_status()
    return resp.json() or {}


def fetch_recent_finished(token, n=5):
    """Devolve os N jogos FINISHED mais recentes, em ordem cronologica
    crescente (do mais antigo pro mais recente — facilita 'forma recente')."""
    data = fd_get("/teams/{}/matches".format(FLAMENGO_ID), token,
                  {"status": "FINISHED"})
    matches = data.get("matches") or []
    matches.sort(key=lambda m: m.get("utcDate") or "")
    return matches[-n:] if matches else []


def fetch_upcoming(token, n=5):
    """Devolve os N proximos jogos SCHEDULED/TIMED, ordem crescente."""
    data = fd_get("/teams/{}/matches".format(FLAMENGO_ID), token,
                  {"status": "SCHEDULED,TIMED"})
    matches = data.get("matches") or []
    matches.sort(key=lambda m: m.get("utcDate") or "")
    return matches[:n]


def fetch_brasileirao_standings(token):
    """Devolve a tabela inteira do Brasileirao (lista de linhas) e a linha do Flamengo.

    Retorna (linha_flamengo, tabela_inteira) — None se falhar.
    """
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
    """Info do time: tecnico e competicoes em andamento. Retorna dict ou None."""
    try:
        data = fd_get("/teams/{}".format(FLAMENGO_ID), token)
    except Exception as e:
        print("AVISO: nao consegui buscar info do time: {}".format(e))
        return None
    return {
        "coach": (data.get("coach") or {}).get("name"),
        "running_competitions": [c.get("name") for c in data.get("runningCompetitions") or [] if c.get("name")],
    }


# ---------- helpers ----------

def _name(side):
    if not side:
        return "?"
    return side.get("shortName") or side.get("name") or "?"


def _is_fla(side):
    return bool(side) and side.get("id") == FLAMENGO_ID


def _match_outcome_for_fla(m):
    """Retorna 'V', 'E', 'D' ou None pro Flamengo nesse jogo."""
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
    """Devolve string descritiva da zona (Libertadores / Sul-Am / nada / Z4)."""
    if pos is None:
        return ""
    try:
        p = int(pos)
    except (TypeError, ValueError):
        return ""
    if 1 <= p <= 4:
        return u"\U0001F30E zona de Libertadores (G4)"
    if 5 <= p <= 6:
        return u"\U0001F3C6 pré-Libertadores (G6)"
    if 7 <= p <= 12:
        return u"🇸 zona de Sul-Americana"
    if 13 <= p <= 16:
        return u"meio de tabela"
    if 17 <= p <= 20:
        return u"⚠️ zona de rebaixamento (Z4)"
    return ""


# ---------- secoes do boletim ----------

def section_last_and_form(recent_matches):
    """Junta 'ultimo resultado' + 'forma recente'."""
    if not recent_matches:
        return None
    last = recent_matches[-1]
    score = (last.get("score") or {}).get("fullTime") or {}
    sh, sa = score.get("home"), score.get("away")
    if sh is None or sa is None:
        return None

    home = last.get("homeTeam") or {}
    away = last.get("awayTeam") or {}
    comp = (last.get("competition") or {}).get("name") or ""
    kickoff = parse_utc_iso(last.get("utcDate"))
    date_str = format_short_date(kickoff)

    placar = u"{} {} x {} {}".format(_name(home), sh, _name(away), sa)
    outcome = _match_outcome_for_fla(last)
    tag = ""
    if outcome == "V": tag = u"{} vitória".format(E_OK)
    elif outcome == "D": tag = u"{} derrota".format(E_X)
    elif outcome == "E": tag = u"{} empate".format(E_DRAW)

    lines = [u"{} *Último resultado*".format(E_CHART)]
    lines.append(placar + (u"  ({})".format(tag) if tag else ""))
    if comp:
        lines.append(u"{} • {}".format(comp, date_str))

    # Forma recente (todos os jogos do recent_matches, em ordem)
    if len(recent_matches) >= 2:
        emojis = []
        v = e = d = 0
        for m in recent_matches:
            o = _match_outcome_for_fla(m)
            if o == "V": emojis.append(E_OK); v += 1
            elif o == "E": emojis.append(E_DRAW); e += 1
            elif o == "D": emojis.append(E_X); d += 1
        if emojis:
            pts_recent = v * 3 + e  # pontos somados nos ultimos jogos
            max_pts = len(emojis) * 3
            mood = ""
            if max_pts > 0:
                ratio = pts_recent / max_pts
                if ratio >= 0.8:
                    mood = u" 🔥 embalado"
                elif ratio >= 0.6:
                    mood = u" 💪 bem"
                elif ratio >= 0.4:
                    mood = u" 😐 irregular"
                elif ratio >= 0.2:
                    mood = u" 😬 mal"
                else:
                    mood = u" 😱 péssimo"
            lines.append("")
            lines.append(u"{} *Forma recente:* {}".format(E_TREND, "".join(emojis)))
            lines.append(u"   ({}V {}E {}D • {} pts em {} jogos{})".format(
                v, e, d, pts_recent, len(emojis), mood))
    return "\n".join(lines)


def section_next_match(match):
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
    if comp:
        suffix = ""
        if matchday:
            suffix = u" — Rod. {}".format(matchday)
        elif stage and stage != "REGULAR_SEASON":
            suffix = u" — {}".format(stage.replace("_", " ").title())
        lines.append(u"{} {}{}".format(E_CUP, comp, suffix))
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
    gf = fla_row.get("goalsFor")
    ga = fla_row.get("goalsAgainst")

    lines = [u"{} *Brasileirão*".format(E_NOTE)]
    lines.append(u"{} {}º lugar • {} pts em {} jogos ({}V {}E {}D)".format(
        E_CUP, pos, pts, played, wins, draws, losses))
    if gf is not None and ga is not None and gd is not None:
        sg = "+{}".format(gd) if gd >= 0 else str(gd)
        lines.append(u"{} {} gols pró • {} contra • SG {}".format(E_BALL, gf, ga, sg))

    # Distancia pro lider
    if full_table:
        leader = None
        for row in full_table:
            if row.get("position") == 1:
                leader = row
                break
        if leader and leader.get("team", {}).get("id") != FLAMENGO_ID:
            lead_pts = leader.get("points")
            lead_name = _name(leader.get("team") or {})
            try:
                diff = lead_pts - pts
                lines.append(u"{} A {} pt(s) do líder ({} — {})".format(
                    E_TREND, diff, lead_name, lead_pts))
            except (TypeError, ValueError):
                pass
        elif leader and leader.get("team", {}).get("id") == FLAMENGO_ID:
            # Flamengo eh o lider
            second_pts = None
            for row in full_table:
                if row.get("position") == 2:
                    second_pts = row.get("points")
                    break
            if second_pts is not None:
                try:
                    lines.append(u"{} LÍDER, {} pt(s) à frente do 2º".format(E_FIRE, pts - second_pts))
                except (TypeError, ValueError):
                    pass

    zona = _zona_brasileirao(pos)
    if zona:
        lines.append(u"   {}".format(zona))

    # Distancia pro 5o (margem da zona da Libertadores) - so se Flamengo estiver no G4
    if full_table and isinstance(pos, int) and 1 <= pos <= 4:
        fifth = None
        for row in full_table:
            if row.get("position") == 5:
                fifth = row
                break
        if fifth and fifth.get("points") is not None and pts is not None:
            try:
                margin = pts - fifth.get("points")
                if margin >= 0:
                    lines.append(u"   margem de {} pt(s) sobre o 5º".format(margin))
            except (TypeError, ValueError):
                pass

    return "\n".join(lines)


def section_team_info(team_info):
    if not team_info:
        return None
    parts = []
    running = team_info.get("running_competitions") or []
    # Filtra para excluir o Brasileirao (ja tem secao propria)
    other_comps = [c for c in running if "brasileiro" not in c.lower() and "serie a" not in c.lower()]
    if other_comps:
        parts.append(u"{} *Competições ativas*".format(E_GLOBE))
        for c in other_comps:
            parts.append(u"{} {}".format(E_CUP, c))
    coach = team_info.get("coach")
    if coach:
        if parts:
            parts.append("")
        parts.append(u"{} *Técnico:* {}".format(E_COACH, coach))
    return "\n".join(parts) if parts else None


def section_calendar(upcoming):
    """Lista compacta dos proximos jogos. O 1o ja apareceu como 'proximo jogo',
    entao aqui mostramos do 2o em diante (ate 3 total)."""
    if not upcoming or len(upcoming) < 2:
        return None
    rest = upcoming[1:4]  # ate 3 jogos extras
    if not rest:
        return None
    lines = [u"{} *Próximos jogos*".format(E_CAL)]
    for m in rest:
        kickoff = parse_utc_iso(m.get("utcDate"))
        home = _name(m.get("homeTeam"))
        away = _name(m.get("awayTeam"))
        comp = (m.get("competition") or {}).get("name") or ""
        comp_short = comp
        if "brasileiro" in comp.lower() or "serie a" in comp.lower():
            comp_short = "Brasileirão"
        elif "libertadores" in comp.lower():
            comp_short = "Libertadores"
        elif "copa do brasil" in comp.lower():
            comp_short = "Copa do Brasil"
        lines.append(u"• {} — {} x {} ({})".format(
            format_calendar_line(kickoff), home, away, comp_short))
    return "\n".join(lines)


def section_classics_warning(upcoming, full_table):
    """Se houver classico (vs top 4 do Brasileirao) nos proximos 3 jogos, destaca."""
    if not upcoming or not full_table:
        return None
    top4_ids = set()
    for row in full_table:
        if row.get("position") and row["position"] <= 4:
            tid = (row.get("team") or {}).get("id")
            if tid and tid != FLAMENGO_ID:
                top4_ids.add(tid)
    if not top4_ids:
        return None
    classicos = []
    for m in upcoming[:3]:
        comp = (m.get("competition") or {}).get("name") or ""
        if "brasileiro" not in comp.lower() and "serie a" not in comp.lower():
            continue  # so brasileirao
        for side_key in ("homeTeam", "awayTeam"):
            side = m.get(side_key) or {}
            if side.get("id") in top4_ids:
                kickoff = parse_utc_iso(m.get("utcDate"))
                classicos.append((kickoff, _name(side)))
                break
    if not classicos:
        return None
    # so mostra o primeiro/mais proximo classico
    kickoff, adv = classicos[0]
    return u"⚔️  *Clássico chegando:* vs {} em {} — confronto direto na briga pela liderança.".format(
        adv, format_calendar_line(kickoff))


# ---------- montagem ----------

def build_message(token):
    today_label = now_br().strftime("%d/%m/%Y")
    dia_semana = DIAS_PT[now_br().weekday()]
    header = u"{} *Boletim do Mengão* — {}, {}".format(E_RUBRO, dia_semana, today_label)

    # 4 chamadas a API — bem abaixo do limite de 10/min
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
    team_info = fetch_team_info(token)

    sections = [header]
    s = section_last_and_form(recent)
    if s: sections.append(s)
    s = section_next_match(upcoming[0] if upcoming else None)
    if s: sections.append(s)
    s = section_standings(fla_row, full_table)
    if s: sections.append(s)
    s = section_team_info(team_info)
    if s: sections.append(s)
    s = section_calendar(upcoming)
    if s: sections.append(s)
    s = section_classics_warning(upcoming, full_table)
    if s: sections.append(s)

    if len(sections) == 1:  # so o header
        sections.append(u"Sem novidades hoje. É hora de descansar, Mengão.")

    sections.append(u"VAMO MENGÃO! {}".format(E_FIRE))
    return "\n\n".join(sections).strip()


def send_whatsapp(phone, apikey, message):
    """Envia via CallMeBot usando POST (evita truncamento de URL para mensagens longas)."""
    # Tamanho seguro: WhatsApp aceita ~4000 chars; o boletim costuma ter 1500-2000.
    # GET na query string trunca em ~2000 bytes URL-encoded — por isso o '%' no fim.
    # Solucao: enviar phone+apikey na query (sao curtos) e o text no corpo via POST.
    params = {"phone": phone, "apikey": apikey}
    url = "{}?{}".format(CALLMEBOT_URL, urllib.parse.urlencode(params))
    resp = requests.post(url, data={"text": message}, timeout=30)
    print("CallMeBot status={} msg_len={}".format(resp.status_code, len(message)))
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
        print("ERRO: variaveis faltando: {}".format(", ".join(missing)), file=sys.stderr)
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
