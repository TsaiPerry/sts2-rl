"""pytest plugin producing seam/hook_dispatch gap **G7**'s dormancy evidence.

C# yields hook listeners through a per-item liveness re-check
(`CombatState.IterateHookListeners` 482-488 + `Contains` 549-599); the sim
walks a `list(self._listeners)` snapshot with none. G7 is recorded DORMANT,
and this plugin is how that is established.

Instrumentation: every `HookSystem` dispatcher is wrapped. For the duration of
one dispatch, each snapshot listener's bound hook method is shadowed by an
*instance* attribute that re-checks `listener in hooks._listeners` **at the
moment the dispatcher actually calls it** -- exactly C#'s lazy `Contains`
filter -- and records a hit when the listener has already been removed by an
earlier listener in the same walk. `hasattr` still sees the method, so the
dispatch is otherwise unchanged, and the shadow is removed in a `finally`.

Run it over the whole suite from the repo root:

    py -m pytest test/ -q -p tools.audit.stale_listener_plugin

The report is printed at session finish. A non-empty report is not
automatically a bug -- C#'s `Contains` also lets a *power* through on
`Owner.CombatState != null` alone (`CombatState.cs:599`), never checking that
the power is still on its owner -- but every entry has to be explained before
G7 can stay dormant.
"""
from __future__ import annotations

from collections import Counter

_HITS: Counter = Counter()
_CALLS = [0]
_PATCHED = False


def _patch() -> None:
    global _PATCHED
    if _PATCHED:
        return
    from sts2_rl.hooks import HookSystem

    names = [n for n, v in vars(HookSystem).items()
             if callable(v) and not n.startswith("_")
             and n not in ("register", "unregister")]

    for name in names:
        orig = getattr(HookSystem, name)

        def make(name=name, orig=orig):
            def wrapper(self, *args, **kwargs):
                live = self._listeners
                shadowed = []
                for l in list(live):
                    bound = getattr(l, name, None)
                    if bound is None:
                        continue

                    def probe(*a, _l=l, _b=bound, _n=name, **kw):
                        _CALLS[0] += 1
                        if _l not in live:
                            _HITS[f"{_n} -> {type(_l).__name__}"] += 1
                        return _b(*a, **kw)

                    try:
                        object.__setattr__(l, name, probe)
                    except (AttributeError, TypeError):
                        continue
                    shadowed.append(l)
                try:
                    return orig(self, *args, **kwargs)
                finally:
                    for l in shadowed:
                        try:
                            object.__delattr__(l, name)
                        except (AttributeError, TypeError):
                            pass
            return wrapper

        setattr(HookSystem, name, make())
    _PATCHED = True


def pytest_configure(config):          # noqa: D401  (pytest hook)
    _patch()


def pytest_sessionfinish(session, exitstatus):   # noqa: D401  (pytest hook)
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    lines = ["", "=== stale-listener probe (seam/hook_dispatch G7) ===",
             f"instrumented listener calls: {_CALLS[0]}"]
    if not _HITS:
        lines.append("no listener was invoked while absent from _listeners")
    else:
        for k, v in sorted(_HITS.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {k}: x{v}")
    lines.append(f"distinct (hook, listener-type) pairs: {len(_HITS)}")
    text = "\n".join(lines)
    if tr is not None:
        tr.write_line(text)
    else:                                        # pragma: no cover
        print(text)
