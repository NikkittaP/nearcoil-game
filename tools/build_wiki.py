#!/usr/bin/env python3
"""Build the NEARCOIL wiki: wiki-src/<lang>/<page>.html + wiki-src/game.json -> wiki/<lang>/<page>.html.

    python tools/build_wiki.py            # build every page
    python tools/build_wiki.py --check    # build into memory only, report problems
    python tools/build_wiki.py --lang=en  # one language only (drafting)

Text lives in the page sources (one file per page and language). Every number
comes from wiki-src/game.json, which the game repository exports
(NEARCOIL/tools/wiki_update.sh). A page writes {{ expression }} where it needs a
number or a table, e.g. {{ GameSim.FOOD_POINTS }}, {{ GameSim.FLOW_LEVELS[1] }},
{{ steps(Circuit.GATE_TIME) }}, {{ flow_table() }}, {{ img('squeeze', 'Caption') }}.
A name the game no longer has, or a missing screenshot, stops the build with
the page and line, so a renamed rule never goes stale silently.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "wiki-src"
OUT = ROOT / "wiki"
LANGS = ["en", "ru"]
PAGES = ["index", "basics", "close-calls", "charge", "events", "modules", "modes", "achievements", "campaign", "advanced", "glossary"]
STEP_MS = 150   # a typical early-run step, for "about N s" conversions
SITE = "https://nikkittap.github.io/nearcoil-game/"


class Safe(str):
    """Already HTML: inserted as is."""


class AD(dict):
    """Dict with attribute access; a missing key is an error, not None."""

    def __getattr__(self, k):
        try:
            return wrap(self[k])
        except KeyError:
            raise NameError(f"game data has no '{k}'")

    def __getitem__(self, k):
        return wrap(dict.__getitem__(self, k))


def wrap(v):
    if isinstance(v, dict) and not isinstance(v, AD):
        return AD(v)
    if isinstance(v, list):
        return [wrap(e) for e in v]
    return v


UI = {
    "en": {
        "wiki": "Guide", "home": "NEARCOIL", "contents": "On this page", "lang": "Русский",
        "footer": "Numbers and screenshots are taken from the game, version {v} ({d}).",
        "play": "Get it on Google Play", "privacy": "Privacy policy", "menu": "Pages",
        "mult": "Multiplier", "charge_from": "Charge from", "span": "Span", "speed": "Speed bonus",
        "minor": "Close-call charge kept", "drain_open": "Drain in open space", "drain_near": "Drain near body",
        "per_step": "/step", "foods": "Nodes eaten", "step_ms": "Step", "cells_s": "Cells per second",
        "food_n": "Node", "grow": "Growth", "length": "Length after",
        "level": "Level", "name": "Name", "goal": "Goal", "time": "Time", "pass": "PASS", "great": "GREAT",
        "perfect": "PERFECT", "notes": "Board", "chapter": "Chapter", "reward": "Reward", "fuse_free": "costs no fuses",
        "variant": "Variant", "label": "On screen", "from": "Unlocks at intensity", "weight": "Weight", "what": "What changes",
        "term": "Term", "ru": "In Russian", "meaning": "Meaning", "s": "s", "about": "about",
        "no_food": "no nodes", "walls": "insulators", "start_len": "starts {n} long", "start_x": "starts at ×{n}",
        "cap_x": "ceiling ×{n}", "speed_pct": "speed {n}%", "charge_pct": "charge {n}%", "drain_pct": "drain {n}%",
        "phase": "carries a PHASE", "surge": "starts in SURGE", "cut": "carries a CUT", "ports": "ports",
        "start_port": "{m} port ahead at the start",
        "no_events": "no events", "events": "events",
        "ach": "Achievement", "ach_what": "What it asks", "tier": "Tier", "hidden": "hidden: shows as ??? until you earn it",
    },
    "ru": {
        "wiki": "Справочник", "home": "NEARCOIL", "contents": "На этой странице", "lang": "English",
        "footer": "Числа и скриншоты взяты из игры, версия {v} ({d}).",
        "play": "Скачать в Google Play", "privacy": "Политика конфиденциальности", "menu": "Разделы",
        "mult": "Множитель", "charge_from": "Заряд от", "span": "Шаг шкалы", "speed": "Прибавка скорости",
        "minor": "Заряд за сближения", "drain_open": "Утечка на просторе", "drain_near": "Утечка у тела",
        "per_step": "/шаг", "foods": "Съедено узлов", "step_ms": "Шаг", "cells_s": "Клеток в секунду",
        "food_n": "Узел", "grow": "Рост", "length": "Длина после",
        "level": "Уровень", "name": "Название", "goal": "Задача", "time": "Время", "pass": "ЗАЧЁТ", "great": "ОТЛИЧНО",
        "perfect": "ИДЕАЛ", "notes": "Поле", "chapter": "Глава", "reward": "Награда", "fuse_free": "предохранители не тратятся",
        "variant": "Вариант", "label": "На экране", "from": "С интенсивности", "weight": "Вес", "what": "Что меняется",
        "term": "Термин", "ru": "По-английски", "meaning": "Что это", "s": "с", "about": "около",
        "no_food": "без узлов", "walls": "изоляторы", "start_len": "старт: длина {n}", "start_x": "старт с ×{n}",
        "cap_x": "потолок ×{n}", "speed_pct": "скорость {n}%", "charge_pct": "заряд {n}%", "drain_pct": "утечка {n}%",
        "phase": "с ФАЗОЙ", "surge": "старт на ФОРСАЖЕ", "cut": "со СРЕЗОМ", "ports": "порты",
        "start_port": "{m}: порт впереди на старте",
        "no_events": "без событий", "events": "события",
        "ach": "Достижение", "ach_what": "Что нужно", "tier": "Уровень", "hidden": "скрытое: до получения видно как ???",
    },
}


class Page:
    def __init__(self, data, lang, slug, meta, images):
        self.d = data
        self.lang = lang
        self.slug = slug
        self.meta = meta
        self.images = images
        self.ui = UI[lang]

    # ------------------------------------------------------------ formatting

    def n(self, v, digits=1):
        """A number in the page language: 1,150 / 1 150; 2.4 / 2,4."""
        if isinstance(v, float) and not v.is_integer():
            s = f"{v:,.{digits}f}"
        else:
            s = f"{int(round(v)):,}"
        if self.lang == "ru":
            s = s.replace(",", " ").replace(".", ",")
            if len(s.replace(" ", "")) <= 4 and "," not in s:
                s = s.replace(" ", "")   # 1150, not 1 150 (Russian style for four digits)
        return s

    def t(self, key):
        """The game's own text for a string key, in the page language."""
        s = self.d["strings"].get(key)
        if s is None:
            raise NameError(f"game strings have no key '{key}'")
        return s.get(self.lang) or s["en"]

    def term(self, key):
        return Safe(f'<b class="term">{html.escape(self.t(key))}</b>')

    def secs(self, steps, ms=STEP_MS):
        return f"{self.ui['about']} {self.n(steps * ms / 1000)} {self.ui['s']}"

    def steps(self, steps, ms=STEP_MS):
        """'85 steps (about 12.8 s)'."""
        word = self.plural(steps, ("step", "steps"), ("шаг", "шага", "шагов"))
        return f"{self.n(steps)} {word} ({self.secs(steps, ms)})"

    def plural(self, k, en, ru):
        k = abs(int(k))
        if self.lang == "en":
            return en[0] if k == 1 else en[1]
        if k % 10 == 1 and k % 100 != 11:
            return ru[0]
        if 2 <= k % 10 <= 4 and not 12 <= k % 100 <= 14:
            return ru[1]
        return ru[2]

    def pct(self, v):
        return f"{self.n(v)}%" if self.lang == "en" else f"{self.n(v)} %"

    def x(self, v):
        return f"×{self.n(v, 2)}" if isinstance(v, float) else f"×{self.n(v)}"

    def lst(self, values):
        return ", ".join(self.n(v) if isinstance(v, (int, float)) else str(v) for v in values)

    # ------------------------------------------------------------ blocks

    def img(self, name, caption="", cls=""):
        if name not in self.images[self.lang]:
            raise NameError(f"no screenshot wiki/img/{self.lang}/{name}.webp")
        cap = f"<figcaption>{caption}</figcaption>" if caption else ""
        c = f' class="{cls}"' if cls else ""
        return Safe(f'<figure{c}><a href="../img/{self.lang}/{name}.webp"><img src="../img/{self.lang}/{name}.webp" '
                    f'width="720" height="1280" loading="lazy" alt="{html.escape(re.sub("<[^>]+>", "", caption))}"></a>{cap}</figure>')

    def shots(self, *figs):
        return Safe('<div class="shots">' + "".join(figs) + "</div>")

    def meter(self, level, caption=""):
        name = f"meter_x{level}"
        if name not in self.images[self.lang]:
            raise NameError(f"no screenshot wiki/img/{self.lang}/{name}.webp")
        cap = f"<figcaption>{caption}</figcaption>" if caption else ""
        return Safe(f'<figure class="strip"><img src="../img/{self.lang}/{name}.webp" width="720" height="168" '
                    f'loading="lazy" alt="×{level}">{cap}</figure>')

    def table(self, head, rows, cls=""):
        h = "".join(f"<th>{c}</th>" for c in head)
        b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        return Safe(f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>')

    def flow_table(self):
        u = self.ui
        rows = []
        for lv in self.d["derived"]["levels"]:
            rows.append([f"<b>×{lv['mult']}</b>", self.n(lv["from"]), self.n(lv["span"]), "+" + self.pct(lv["speed_pct"]),
                         self.pct(lv["minor_pct"]), f"{lv['decay_open']}{u['per_step']}", f"{lv['decay_near']}{u['per_step']}"])
        return self.table([u["mult"], u["charge_from"], u["span"], u["speed"], u["minor"], u["drain_open"], u["drain_near"]], rows, "num")

    def speed_table(self):
        u = self.ui
        rows = [[self.n(t["foods"]) + "+", f"{t['ms']} ms" if self.lang == "en" else f"{t['ms']} мс", self.n(t["cells_per_s"])]
                for t in self.d["derived"]["speed_tiers"]]
        return self.table([u["foods"], u["step_ms"], u["cells_s"]], rows, "num")

    def growth_table(self):
        u = self.ui
        rows = [[self.n(g["food"]), "+" + self.n(g["grow"]), self.n(g["length"])] for g in self.d["derived"]["growth"][:12]]
        return self.table([u["food_n"], u["grow"], u["length"]], rows, "num")

    def director_table(self, kind):
        """Variants of one event kind: on-screen name, unlock intensity, weight."""
        u = self.ui
        labels = VARIANT_LABELS
        rows = []
        for v, lo, w in self.d["Circuit"]["DIRECTOR"][kind]:
            key = labels.get(v, v.upper())
            rows.append([f"<code>{v}</code>", html.escape(self.t(key)) if key in self.d["strings"] else key,
                         self.n(lo), self.n(w), VARIANT_TEXT[self.lang].get(v, "")])
        return self.table([u["variant"], u["label"], u["from"], u["weight"], u["what"]], rows)

    def variants_table(self, kind):
        """Variants of one event kind for players: on-screen name and what changes (no draw numbers)."""
        u = self.ui
        rows = []
        for v, lo, w in self.d["Circuit"]["DIRECTOR"][kind]:
            key = VARIANT_LABELS.get(v, v.upper())
            rows.append([html.escape(self.t(key)) if key in self.d["strings"] else key, VARIANT_TEXT[self.lang].get(v, "")])
        return self.table([u["label"], u["what"]], rows)

    def level_notes(self, l):
        u = self.ui
        out = []
        if not l["food"]:
            out.append(u["no_food"])
        if l["walls"]:
            out.append(f"{u['walls']} ({l['walls']})")
        if l["start_len"] != self.d["GameSim"]["START_LEN"]:
            out.append(u["start_len"].format(n=l["start_len"]))
        if l["start_level"]:
            out.append(u["start_x"].format(n=l["start_level"] + 1))
        if l["max_level"] < 7:
            out.append(u["cap_x"].format(n=l["max_level"] + 1))
        for k in ("speed_pct", "charge_pct", "decay_pct"):
            if l[k] != 100:
                out.append(u[k.replace("decay", "drain")].format(n=l[k]))
        if l["start_phase"]:
            out.append(u["phase"])
        if l["start_surge"]:
            out.append(u["surge"])
        if l["start_cut"]:
            out.append(u["cut"])
        if l.get("start_port"):
            out.append(u["start_port"].format(m=self.t(l["start_port"].upper())))
        ev = []
        for k in l["events"]:
            key = {"gate": "GATE", "relay": "RELAY", "hot": "HOT ZONE", "wire": "LIVE WIRE"}[k]
            vs = l["variants"].get(k)
            ev.append(self.t(key) + (f" ({', '.join(vs)})" if vs else ""))
        out.append(f"{u['events']}: {'; '.join(ev)}" if ev else u["no_events"])
        if l["modifiers"]:
            out.append("+ " + ", ".join(l["modifiers"]))
        if l["modules"]:
            out.append(f"{u['ports']}: " + ", ".join(self.t(m.upper()) for m in l["modules"]))
        return ", ".join(html.escape(o) for o in out)

    def chapter_table(self, n):
        u = self.ui
        ch = self.d["campaign"]["chapters"][n - 1]
        rows = []
        for l in ch["levels"]:
            p, g, pf = l["targets"]
            goal = ""
            if l.get("goal"):
                # The level goal, as the briefing words it: failing it fails the level.
                goal = f"<br><span class=\"small\"><b>{html.escape(self.t('GOAL'))}:</b> {html.escape('; '.join(l['goal'][self.lang]))}</span>"
            rows.append([f"<b>{l['id']}</b>", f"<b>{html.escape(self.t(l['name']))}</b><br><span class=\"muted\">{html.escape(self.t(l['hint']))}</span>{goal}",
                         f"{l['time']} {u['s']}", self.n(p), self.n(g), self.n(pf), f"<span class=\"small\">{self.level_notes(l)}</span>"])
        return self.table([u["level"], u["name"] + " / " + u["goal"], u["time"], u["pass"], u["great"], u["perfect"], u["notes"]], rows, "levels")

    def chapters(self):
        u = self.ui
        out = []
        for ch in self.d["campaign"]["chapters"]:
            reward = self.t(ch["reward"]) if ch["reward"] in self.d["strings"] else ch["reward"]
            extra = f" · {u['fuse_free']}" if ch["fuse_free"] else ""
            out.append(f'<h2 id="ch{ch["n"]}">{u["chapter"]} {ch["n"]}. {html.escape(self.t(ch["name"]))}</h2>'
                       f'<p class="muted">«{html.escape(self.t(ch["tag"]))}» · {u["reward"]}: {html.escape(reward)}{extra}</p>')
            out.append(self.chapter_table(ch["n"]))
        return Safe("".join(out))

    def achievement_table(self, cat):
        """One category's achievements as the game words them: name, what it
        asks, tier (rims of the badge)."""
        u = self.ui
        rows = []
        for a in self.d["achievements"]["list"]:
            if a["cat"] != cat:
                continue
            what = html.escape(a["desc"][self.lang])
            if a["hidden"]:
                what += f'<br><span class="muted small">{u["hidden"]}</span>'
            rows.append([f'<b class="term">{html.escape(a["title"][self.lang])}</b>', what, "●" * a["tier"] + "○" * (3 - a["tier"])])
        if not rows:
            raise NameError(f"no achievements in category '{cat}'")
        return self.table([u["ach"], u["ach_what"], u["tier"]], rows)

    def achievements_ranks(self, k):
        return self.n(self.d["achievements"]["ranks"][k])

    def glossary(self):
        u = self.ui
        other = "en" if self.lang == "ru" else "ru"
        rows = []
        for key, text in GLOSSARY:
            s = key if isinstance(key, dict) else self.d["strings"].get(key)
            if s is None:
                raise NameError(f"glossary: game strings have no key '{key}'")
            a, b = (s[self.lang].replace("%d", "N"), s[other].replace("%d", "N"))
            rows.append([f'<b class="term">{html.escape(a)}</b>', html.escape(b), text[self.lang]])
        return self.table([u["term"], u["ru"], u["meaning"]], rows, "gloss")

    # ------------------------------------------------------------ render

    def env(self):
        e = {k: wrap(v) for k, v in self.d.items() if k not in ("strings",)}
        for name in ("n", "t", "term", "secs", "steps", "pct", "x", "lst", "img", "shots", "meter", "table", "flow_table",
                     "speed_table", "growth_table", "director_table", "variants_table", "chapter_table", "chapters", "glossary", "plural",
                     "achievement_table", "achievements_ranks"):
            e[name] = getattr(self, name)
        e.update({"min": min, "max": max, "round": round, "len": len, "sum": sum, "int": int, "str": str, "Safe": Safe})
        return e

    def render(self, body, src):
        env = self.env()
        out = []
        pos = 0
        for m in re.finditer(r"\{\{(.+?)\}\}", body, re.S):
            out.append(body[pos:m.start()])
            line = body.count("\n", 0, m.start()) + 1 + self.meta.get("_offset", 0)
            try:
                v = eval(m.group(1).strip(), {"__builtins__": {}}, env)
            except Exception as ex:   # noqa: BLE001 - reported with the place
                raise SystemExit(f"{src}:{line}: {{{{{m.group(1).strip()}}}}}: {type(ex).__name__}: {ex}")
            if isinstance(v, Safe):
                out.append(v)
            elif isinstance(v, bool):
                out.append(str(v))
            elif isinstance(v, (int, float)):
                out.append(self.n(v))
            else:
                out.append(html.escape(str(v), quote=False))
            pos = m.end()
        out.append(body[pos:])
        return "".join(out)


VARIANT_LABELS = {
    "course": "NEEDLE GATE", "chain": "GATE CHAIN", "risk": "RISK GATE", "double": "DOUBLE GATE", "echo": "ECHO GATE",
    "three": "RELAY", "four": "RELAY 4", "timed": "FAST RELAY", "hidden": "DARK RELAY", "moving": "LIVE RELAY",
    "bridge": "BRIDGE RELAY", "static": "HOT ZONE", "escalate": "RISING ZONE", "drift": "DRIFT ZONE",
    "shrink": "SHRINK ZONE", "preserve": "HOLD ZONE", "unstable": "UNSTABLE ZONE", "patrol": "LIVE WIRE",
    "long": "LIVE WIRE", "twin": "LIVE WIRE",
}
VARIANT_TEXT = {
    "en": {
        "course": "three gates in a row, doors 1, 2 and 3 cells deep",
        "chain": "each next gate stands straight ahead of where you left the last one",
        "risk": "one shallow door and one deep door; only the first one you drive through counts",
        "double": "two doors at once, take either",
        "echo": "one gate: through, back, through again",
        "three": "three terminals in number order",
        "four": "four terminals, more time, bigger payout",
        "timed": "two thirds of the time, bigger payout",
        "hidden": "the last terminal shows only when it is next",
        "moving": "the last terminal keeps side-stepping",
        "bridge": "on completion the terminals are joined by live bars",
        "static": "the plain zone",
        "escalate": "lives longer; banks twice as fast in its second half",
        "drift": "slowly slides diagonally",
        "shrink": "closes to 3×3 at half time",
        "preserve": "no charge drain while your head is inside",
        "unstable": "random lifetime, very short warning",
        "patrol": "one 3-cell bar",
        "long": "one 5-cell bar",
        "twin": "two bars, one lane each",
    },
    "ru": {
        "course": "трое ворот подряд, двери глубиной 1, 2 и 3 клетки",
        "chain": "следующие ворота встают прямо по ходу, на линии выхода из прошлых",
        "risk": "мелкая и глубокая дверь; засчитывается только первая, в которую проехал",
        "double": "две двери сразу, подойдёт любая",
        "echo": "одни ворота: туда, обратно и снова туда",
        "three": "три клеммы по порядку номеров",
        "four": "четыре клеммы, больше времени, больше награда",
        "timed": "две трети времени, больше награда",
        "hidden": "последняя клемма видна, только когда до неё очередь",
        "moving": "последняя клемма всё время смещается",
        "bridge": "после завершения клеммы соединяются шинами под током",
        "static": "обычная зона",
        "escalate": "живёт дольше, во второй половине копит вдвое быстрее",
        "drift": "медленно плывёт по диагонали",
        "shrink": "к середине срока сжимается до 3×3",
        "preserve": "пока голова внутри, заряд не утекает",
        "unstable": "случайный срок жизни, предупреждение в самом конце",
        "patrol": "одна шина в 3 клетки",
        "long": "одна шина в 5 клеток",
        "twin": "две шины, у каждой своя полоса",
    },
}

# Glossary: string key in the game -> meaning in each language.
GLOSSARY = [
    ("CLOSE_CALLS", {"en": "Passing your head through a cell right next to (not diagonal to) your own older body, an obstacle or a live structure. The core move: it charges the meter.",
                     "ru": "Проход головой через клетку вплотную (не по диагонали) к своему старому телу, препятствию или живой конструкции. Главный приём: заряжает шкалу."}),
    ("GRAZE", {"en": "The word a close call shows. Each body cell pays once.", "ru": "Надпись при сближении. Каждая клетка тела срабатывает один раз."}),
    ("SKIM", {"en": "Riding along a line of body: close calls on consecutive steps. Charge less each but keep the meter from draining.",
              "ru": "Езда вдоль тела: сближения шаг за шагом. Каждое заряжает меньше, но шкала не утекает."}),
    ("SQUEEZE", {"en": "Driving 2–5 cells with something on both sides of the head.", "ru": "Проезд 2–5 клеток, когда по обе стороны от головы что-то есть."}),
    ("THREAD", {"en": "Driving through a gap that splits the board in two: there is no short way round.",
                "ru": "Проезд сквозь щель, которая делит поле надвое: короткого пути в обход нет."}),
    ("NEEDLE", {"en": "A corridor of 6 cells or more with something on both sides.", "ru": "Коридор от 6 клеток, с обеих сторон что-то есть."}),
    ("CHAIN %d", {"en": "Maneuvers in quick succession: each next one pays more, up to ×2.", "ru": "Манёвры один за другим, без долгих пауз: каждый следующий дороже, до ×2."}),
    ({"en": "CHARGE", "ru": "ЗАРЯД"}, {"en": "The segmented meter above the board. Risky moves fill it; it drains when you play safe.",
                                        "ru": "Сегментная шкала над полем. Рискованные манёвры её наполняют, в спокойной игре заряд утекает."}),
    ({"en": "MULTIPLIER ×N", "ru": "МНОЖИТЕЛЬ ×N"}, {"en": "×1…×8, set by how full the charge meter is. Multiplies every point and adds speed.",
                                                    "ru": "×1…×8, зависит от заполнения шкалы заряда. Умножает каждое очко и прибавляет скорость."}),
    ({"en": "NODE", "ru": "УЗЕЛ"}, {"en": "The red target (the food). Eating it scores 10 × multiplier and grows the body.",
                                  "ru": "Красная цель («еда»). Съеденный узел даёт 10 × множитель и удлиняет тело."}),
    ({"en": "HUNGER", "ru": "ГОЛОД"}, {"en": "Long without eating, close calls against your own body pay less and less. Eat to restore them.",
                                    "ru": "Если долго не есть, сближения со своим телом приносят всё меньше. Съешь узел, и всё вернётся."}),
    ("INSULATORS", {"en": "Fixed blocks on Campaign boards. Brush them for charge, never hit them. A brushed block goes dark for a while.",
                    "ru": "Неподвижные блоки на полях кампании. Проходи впритирку за зарядом, не врезайся. Задетый блок ненадолго гаснет."}),
    ({"en": "PYLON / DOOR", "ru": "СТОЛБ / ДВЕРЬ"}, {"en": "A gate is two rows of lethal pylons; the door is the passage between them. Its depth is its length.",
                                                     "ru": "Ворота — два ряда смертельных столбов, дверь — проход между ними. Глубина двери — её длина."}),
    ({"en": "TERMINAL / POST", "ru": "КЛЕММА / СТОЙКА"}, {"en": "Relay targets. A touched terminal turns into a live post: lethal, but good for close calls.",
                                                        "ru": "Цели реле. Тронутая клемма становится живой стойкой: врезаться нельзя, проходить впритирку можно."}),
    ("GATE", {"en": "Circuit Event: drive straight through the door between the pylons.", "ru": "Событие: проехать прямо сквозь дверь между столбами."}),
    ("RELAY", {"en": "Circuit Event: touch numbered terminals in order; touched ones stay live.", "ru": "Событие: коснуться клемм по порядку номеров; тронутые остаются под током."}),
    ("HOT ZONE", {"en": "Circuit Event: a square that banks charge and points while your head is inside; leave to cash in.",
                  "ru": "Событие: квадрат, в котором копятся заряд и очки, пока голова внутри; выйди, чтобы забрать."}),
    ("LIVE WIRE", {"en": "Circuit Event: a moving lethal bar; pass right next to it three times.", "ru": "Событие: движущаяся смертельная шина; пройди впритирку к ней три раза."}),
    ("CHOOSE", {"en": "Module ports appear after a won event: drive into one to take its module.", "ru": "После выигранного события появляются порты модулей: въедь в один, чтобы взять модуль."}),
    ("PHASE", {"en": "Module: your next crash into a conductor hops over it instead.", "ru": "Модуль: следующее столкновение с проводником превращается в прыжок через него."}),
    ("SURGE", {"en": "Module: about 8 s faster, with more charge and more points.", "ru": "Модуль: около 8 секунд быстрее, больше заряда и очков."}),
    ("CUT", {"en": "Module: the next node you eat cuts off the oldest part of your body.", "ru": "Модуль: следующий съеденный узел отрежет самую старую часть тела."}),
    ("CASH", {"en": "Leaving a hot zone pays out what it banked.", "ru": "Выход из горячей зоны выплачивает накопленное."}),
    ("BURNED", {"en": "Still inside when a hot zone overloads: the bank is lost.", "ru": "Голова в зоне, когда она перегрелась: накопленное сгорает."}),
    ("FUSES", {"en": "Campaign lives. Failing a level you have not cleared yet burns one. They come back over time.",
               "ru": "«Жизни» кампании. Провал ещё не пройденного уровня сжигает один. Восстанавливаются со временем."}),
    ("PASS", {"en": "First medal of a level; clearing it opens the next level.", "ru": "Первая медаль уровня; открывает следующий уровень."}),
    ("GREAT", {"en": "Second medal of a level.", "ru": "Вторая медаль уровня."}),
    ("PERFECT", {"en": "Top medal; reaching it ends the level at once.", "ru": "Высшая медаль; уровень сразу завершается."}),
    ("RANKED", {"en": "Endless mode with one world leaderboard.", "ru": "Бесконечный режим с общей таблицей рекордов."}),
    ("DAILY", {"en": "One board a day, the same for everyone; three counted tries.", "ru": "Одно поле в день, одинаковое для всех; три зачётные попытки."}),
    ("LEAGUE", {"en": "Weekly groups of about 30 players; the top moves up a tier, the bottom moves down.",
                "ru": "Недельные группы примерно по 30 игроков; лучшие поднимаются на ступень, худшие опускаются."}),
]


def read_page(path):
    raw = path.read_text(encoding="utf-8")
    meta = {}
    if "\n---\n" in raw:
        head, body = raw.split("\n---\n", 1)
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        meta["_offset"] = head.count("\n") + 2
    else:
        body = raw
    return meta, body


def slugify(s):
    s = re.sub(r"<[^>]+>", "", s).lower()
    s = re.sub(r"[^\w]+", "-", s, flags=re.U).strip("-")
    return s or "s"


def add_toc(body):
    """Ids on every <h2>, and the list of them."""
    items = []
    used = set()

    def fix(m):
        attrs, text = m.group(1), m.group(2)
        idm = re.search(r'id="([^"]+)"', attrs)
        hid = idm.group(1) if idm else slugify(text)
        while hid in used:
            hid += "-"
        used.add(hid)
        items.append((hid, re.sub(r"<[^>]+>", "", text)))
        if idm:
            return m.group(0)
        return f'<h2 id="{hid}"{attrs}>{text}</h2>'

    body = re.sub(r"<h2([^>]*)>(.*?)</h2>", fix, body, flags=re.S)
    return body, items


SHELL = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{head_title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{site}wiki/{lang}/{file}">
{alternates}
<meta name="theme-color" content="#0d0e12">
<link rel="icon" href="../../img/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="../../img/favicon-180.png">
<meta property="og:type" content="article">
<meta property="og:title" content="{head_title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{site}img/feature_big.jpg">
<link rel="stylesheet" href="../wiki.css">
</head>
<body>
<header class="top">
  <div class="bar">
    <a class="brand" href="index.html"><img src="../../img/favicon-32.png" width="22" height="22" alt="">NEARCOIL <span>{wiki}</span></a>
    <nav class="links"><a href="../../">{home_label}</a><a href="../{other}/{file}" hreflang="{other}" lang="{other}">{lang_label}</a></nav>
  </div>
</header>
<div class="layout">
  <aside class="side">
    <details open><summary>{menu}</summary>
    <ol>{nav}</ol>
    </details>
  </aside>
  <main class="content">
    <h1>{title}</h1>
    {lead}
    {toc}
    {body}
    {pager}
  </main>
</div>
<footer class="foot">
  <p>{footer}</p>
  <p><a href="https://play.google.com/store/apps/details?id=com.nikitapetrovapps.nearcoil">{play}</a> · <a href="../../privacy/">{privacy}</a> · <a href="mailto:nikitapetrovapps@gmail.com">nikitapetrovapps@gmail.com</a></p>
</footer>
</body>
</html>
"""


def build(check=False, langs=None):
    global LANGS
    if langs:
        LANGS = langs
    data = json.loads((SRC / "game.json").read_text(encoding="utf-8"))
    images = {lang: {p.stem for p in (OUT / "img" / lang).glob("*.webp")} for lang in LANGS}
    metas = {}
    for lang in LANGS:
        for slug in PAGES:
            path = SRC / lang / f"{slug}.html"
            if not path.exists():
                raise SystemExit(f"missing page source {path}")
            metas[(lang, slug)] = read_page(path)
    written = []
    for lang in LANGS:
        ui = UI[lang]
        other = "en" if lang == "ru" else "ru"
        for i, slug in enumerate(PAGES):
            meta, body = metas[(lang, slug)]
            src = SRC / lang / f"{slug}.html"
            page = Page(data, lang, slug, meta, images)
            html_body = page.render(body, src)
            html_body, toc_items = add_toc(html_body)
            toc = ""
            if len(toc_items) >= 3:
                toc = (f'<nav class="toc"><b>{ui["contents"]}</b><ol>'
                       + "".join(f'<li><a href="#{h}">{html.escape(t)}</a></li>' for h, t in toc_items) + "</ol></nav>")
            nav = "".join(
                f'<li{" class=\"on\"" if s == slug else ""}><a href="{s}.html">{html.escape(metas[(lang, s)][0].get("title", s))}</a></li>'
                for s in PAGES)
            prev_ = PAGES[i - 1] if i > 0 else None
            next_ = PAGES[i + 1] if i + 1 < len(PAGES) else None
            pager = '<nav class="pager">'
            if prev_:
                pager += f'<a href="{prev_}.html">← {html.escape(metas[(lang, prev_)][0]["title"])}</a>'
            pager += "<span></span>"
            if next_:
                pager += f'<a href="{next_}.html">{html.escape(metas[(lang, next_)][0]["title"])} →</a>'
            pager += "</nav>"
            file = f"{slug}.html"
            alternates = "\n".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}wiki/{l}/{file}">' for l in LANGS)
            lead = f'<p class="lead">{page.render(meta["lead"], src)}</p>' if meta.get("lead") else ""
            out = SHELL.format(
                lang=lang, other=other, title=html.escape(meta.get("title", slug)), wiki=ui["wiki"],
                head_title=html.escape(meta["title"] if slug == "index" else f'{meta.get("title", slug)} — NEARCOIL {ui["wiki"]}'),
                desc=html.escape(meta.get("description", "")), site=SITE, file=file, alternates=alternates,
                home_label=ui["home"], lang_label=ui["lang"], menu=ui["menu"], nav=nav, lead=lead, toc=toc,
                body=html_body, pager=pager, play=ui["play"], privacy=ui["privacy"],
                footer=ui["footer"].format(v=html.escape(data.get("version", "?")), d=html.escape(data.get("generated", "")[:10])))
            dest = OUT / lang / file
            written.append(dest)
            if not check:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(out, encoding="utf-8", newline="\n")
    # Unused screenshots are fine (spares), missing ones were errors above.
    for lang in LANGS:
        miss = images["en"] - images[lang]
        if miss:
            print(f"warning: {lang} lacks screenshots {sorted(miss)}")
    print(("checked" if check else "wrote") + f" {len(written)} pages, game {data.get('version')} ({data.get('generated')})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    only = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--lang=")]
    build(check="--check" in sys.argv, langs=only or None)
