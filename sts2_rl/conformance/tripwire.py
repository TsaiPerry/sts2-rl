"""RNG tripwire: record every draw on a wrapped random.Random that happens
while a combat.py frame is on the stack. In a parity combat every legitimate
draw goes through combat.combat_rng — a shared-rng draw in combat is a
wrong-stream bug by construction (converge_triage DETECTOR 1, now also a
standalone fuzz gate in test_rng_tripwire.py)."""
from __future__ import annotations

# Public draw methods combat code calls directly (skip getrandbits/randbytes —
# those are randint/randrange internals; a reentrancy guard counts top-level).
_PUBLIC = ("random", "choice", "choices", "sample", "shuffle",
           "randint", "randrange", "uniform")
# Plumbing frames to skip so we name the code that *decided* to draw.
_PLUMBING = ("\\rng.py", "\\combat_rng.py", "\\hooks.py",
             "/rng.py", "/combat_rng.py", "/hooks.py")


class Tripwire:
    """Wraps a random.Random instance and records the innermost sts2_rl
    call-site of every draw made while a combat.py frame is on the stack."""

    def __init__(self) -> None:
        self.hits: dict[tuple, int] = {}
        self._depth = 0

    def _innermost_combat_site(self):
        """Innermost sts2_rl frame that isn't RNG/hook plumbing — the code
        that actually decided to draw — but only when a combat.py frame is
        on the stack. Also grabs the nearest monster/card `self` for the
        source cross-reference."""
        import traceback
        site = None
        owner = ""
        in_combat = False
        for frame, lineno in traceback.walk_stack(None):
            fn = frame.f_code.co_filename
            if "\\combat.py" in fn or "/combat.py" in fn:
                in_combat = True
            if "sts2_rl" not in fn or any(p in fn for p in _PLUMBING):
                continue
            short = "sts2_rl" + fn.split("sts2_rl")[-1]
            if site is None:
                site = (short, lineno, frame.f_code.co_name)
            this = frame.f_locals.get("self")
            if not owner and this is not None:
                if "sts2_rl\\monsters" in short or "sts2_rl/monsters" in short \
                   or "sts2_rl\\cards" in short or "sts2_rl/cards" in short:
                    owner = type(this).__name__
        if site is None or not in_combat:
            return None
        return (*site, owner)

    def install(self, rng) -> None:
        for meth in _PUBLIC:
            orig = getattr(rng, meth, None)
            if orig is None:
                continue

            def make(orig):
                def wrapper(*a, **kw):
                    if self._depth == 0:
                        site = self._innermost_combat_site()
                        if site is not None:
                            self.hits[site] = self.hits.get(site, 0) + 1
                    self._depth += 1
                    try:
                        return orig(*a, **kw)
                    finally:
                        self._depth -= 1
                return wrapper
            setattr(rng, meth, make(orig))

    def bug_sites(self) -> dict[tuple, int]:
        """Everything except the benign constructor-HP bucket (Monster
        __init__'s legacy randint HP roll, overwritten by the Niche parity
        roll)."""
        return {k: v for k, v in self.hits.items() if k[2] != "__init__"}
