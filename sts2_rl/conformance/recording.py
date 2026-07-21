"""Parse RunReplays .sts2replay logs into structured Recordings (SP2 harness).

A recording is a header block (``# Key: Value``) followed by command lines of
the form ``Name arg arg # comment`` where the comment may carry a card id
(``# CARD.X (id)``) and/or a pre-state annotation
(``|| Hand: [names] Enemies: [name hp/maxhp, ...]``). See
docs/superpowers/specs/2026-07-20-sp2-map-economy-parity-design.md."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnemyState:
    name: str
    hp: int
    max_hp: int


@dataclass(frozen=True)
class Annotation:
    hand: list[str] | None = None
    enemies: list[EnemyState] | None = None
    card_name: str | None = None
    card_id: int | None = None


@dataclass(frozen=True)
class Command:
    name: str
    args: list[str]
    comment: str
    annotation: Annotation | None
    lineno: int


@dataclass
class Recording:
    seed: str
    acts: list[str]
    ascension: int
    character: str
    game: str
    mod: str
    commands: list[Command]


_HEADER = re.compile(r"^#\s*([A-Za-z]+):\s*(.*)$")
_CARD = re.compile(r"(CARD\.[A-Z0-9_]+)\s*\((\d+)\)")
_ENEMY = re.compile(r"^(.*?)\s+(\d+)/(\d+)$")


def _parse_enemies(blob: str) -> list[EnemyState]:
    blob = blob.strip()
    if not blob:
        return []
    out: list[EnemyState] = []
    for part in blob.split(","):
        m = _ENEMY.match(part.strip())
        if m:
            out.append(EnemyState(m.group(1).strip(), int(m.group(2)), int(m.group(3))))
    return out


def _parse_annotation(comment: str) -> Annotation | None:
    card_name = card_id = None
    m = _CARD.search(comment)
    if m:
        card_name, card_id = m.group(1), int(m.group(2))
    hand = enemies = None
    if "||" in comment:
        state = comment.split("||", 1)[1]
        hm = re.search(r"Hand:\s*\[(.*?)\]", state)
        em = re.search(r"Enemies:\s*\[(.*?)\]", state)
        if hm:
            inner = hm.group(1).strip()
            hand = [x.strip() for x in inner.split(",")] if inner else []
        if em:
            enemies = _parse_enemies(em.group(1))
    if card_name is None and hand is None and enemies is None:
        return None
    return Annotation(hand=hand, enemies=enemies, card_name=card_name, card_id=card_id)


def parse_recording(path) -> Recording:
    text = Path(path).read_text(encoding="utf-8-sig")
    header: dict[str, str] = {}
    commands: list[Command] = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            m = _HEADER.match(line.strip())
            if m:
                header[m.group(1).lower()] = m.group(2).strip()
            continue
        code, _sep, comment = line.partition("#")
        tokens = code.split()
        if not tokens:
            continue
        commands.append(Command(
            name=tokens[0], args=tokens[1:], comment=comment.strip(),
            annotation=_parse_annotation(comment), lineno=i,
        ))
    acts = [a.strip() for a in header.get("acts", "").split(",") if a.strip()]
    return Recording(
        seed=header.get("seed", ""), acts=acts,
        ascension=int(header.get("ascension", "0")),
        character=header.get("character", ""), game=header.get("game", ""),
        mod=header.get("mod", ""), commands=commands,
    )
