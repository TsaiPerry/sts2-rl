"""Which RNG stream an event's draws come off (audit/GAP-QUEUE.md entries
1, 6, 7, 8, 9 and 11).

Every C# ``EventModel`` owns an ``Rng`` seeded from the run seed plus its own
id and rolls its draws through ``base.Rng`` (EventModel ctor; the sim's
adapter is ``Event.event_rng`` — sts2_rl/events/base.py:84-88).  A few event
payouts instead draw on the per-player Rewards stream
(``Owner.PlayerRng.Rewards``).  **Nothing** an event rolls comes off the
shared run RNG, so in the parity path a driven event must leave
``run.rng`` untouched.

Covered here:
  EV-3  the per-event Rng (28 modules) — the sweep below
  EV-5  StableShuffle replaced by another algorithm (Doors of Light and Dark,
        Battleworn Dummy's Setting 2)
  EV-6  CreateForReward replaced by the in-combat generator (Infested
        Automaton, Endless Conveyor's Fried Eel)
  EV-7  StableShuffle's sort key is the UPPERCASE ModelId.Entry
  EV-8  a hand-rolled offer skips CreateForReward's hook tail (Room Full of
        Cheese, The Future of Potions)
  EV-9  the potion offer draws on PlayerRng.Rewards
"""
import random

import pytest

from sts2_rl.cards import make_card
from sts2_rl.events import make_event
from sts2_rl.potions import make_potion
from sts2_rl.run import RunState

_SEED = "EVENTRNG1"


class CountingRandom(random.Random):
    """A ``random.Random`` that counts every primitive draw taken off it.

    ``choice`` / ``sample`` / ``shuffle`` / ``randrange`` all bottom out in
    ``getrandbits``; ``random`` / ``uniform`` in ``random``.
    """

    def __init__(self, seed=None):
        super().__init__(seed)
        self.draws = 0

    def random(self):
        self.draws += 1
        return super().random()

    def getrandbits(self, k):
        self.draws += 1
        return super().getrandbits(k)


def _take_first(purpose, candidates, count):
    """A deterministic card selector so the screens themselves roll nothing."""
    return list(candidates)[:count]


def parity_run(**kwargs):
    """A run on the SP2 parity streams, with a fresh shared-draw counter."""
    kwargs.setdefault("card_selector", _take_first)
    run = RunState(rng=CountingRandom(0), string_seed=_SEED, **kwargs)
    run.rng.draws = 0
    return run


# ═════════════════════════════════════════════════════════════════════════
# EV-3 — the per-event Rng (base.Rng), one case per module that rolls on it
# ═════════════════════════════════════════════════════════════════════════

def _upgraded_deck(run, n=4):
    for card in run.deck[:n]:
        card.upgrade()


def _stock_potions(run, n=2):
    for pid in ("fire_potion", "block_potion", "energy_potion")[:n]:
        run.add_potion(make_potion(pid))


def _stock_relics(run):
    for rid in ("anchor", "akabeko", "bag_of_marbles", "blood_vial", "kunai"):
        run.add_relic(rid)


# (event id, setup(run), option keys to choose, expected base.Rng draws)
EVENT_RNG_CASES = [
    # AromaOfChaos.cs:33 — TransformToRandom(card, base.Rng): 1 NextItem.
    ("aroma_of_chaos", None, ["LET_GO"], 1),
    # DollRoom.cs:132 — StableShuffle(base.Rng) over 3 dolls: 2 NextInt.
    ("doll_room", None, ["EXAMINE"], 2),
    # DollRoom.cs:108 — NextItem(_dolls).
    ("doll_room", None, ["RANDOM"], 1),
    # DoorsOfLightAndDark.cs:28 — StableShuffle(base.Rng) of the upgradable
    # deck (10 Ironclad starters): 9 NextInt.
    ("doors_of_light_and_dark", None, ["LIGHT"], 9),
    # EndlessConveyor.cs:245 RollDish NextFloat (once in CalculateVars) plus
    # ObserveChef's NextItem (EndlessConveyor.cs:268).
    ("endless_conveyor", lambda r: setattr(r, "gold", 500),
     ["OBSERVE_CHEF"], 2),
    # FakeMerchant.cs:116 — UnstableShuffle(base.Rng) of 9 knock-offs.
    ("fake_merchant", lambda r: setattr(r, "gold", 500), [], 8),
    # JungleMazeAdventure.cs:54-55 — two NextFloat(-15, 15).
    ("jungle_maze_adventure", None, [], 2),
    # LostWisp.cs:44 — NextInt(-15, 16).
    ("lost_wisp", None, [], 1),
    # LuminousChoir.cs:30 — NextInt(0, 50).
    ("luminous_choir", lambda r: setattr(r, "gold", 500), [], 1),
    # MorphicGrove.cs:50 — TransformToRandom per chosen card (2).
    ("morphic_grove", lambda r: setattr(r, "gold", 500), ["GROUP"], 2),
    # RanwidTheElder.cs:80/94 — NextItem(Potions) then NextItem(tradables).
    ("ranwid_the_elder",
     lambda r: (setattr(r, "gold", 500), _stock_potions(r), _stock_relics(r)),
     [], 2),
    # Reflections.cs:41/54 — 2 downgrade NextItem then 4 upgrade NextItem.
    ("reflections", _upgraded_deck, ["TOUCH_A_MIRROR"], 6),
    # RelicTrader.cs:51 — StableShuffle(base.Rng) over the 5 tradables.
    ("relic_trader", _stock_relics, [], 4),
    # SlipperyBridge.cs:127 — NextItem over the removable deck.
    ("slippery_bridge", None, [], 1),
    # StoneOfAllTime.cs:77 NextItem(Potions), then Lift's NextInt(100).
    ("stone_of_all_time", _stock_potions, ["LIFT"], 2),
    # SunkenStatue.cs:30 — NextInt(-10, 11).
    ("sunken_statue", None, [], 1),
    # SunkenTreasury.cs:35-36 — NextInt(16) and NextInt(61).
    ("sunken_treasury", None, [], 2),
    # Symbiote.cs:72 — TransformToRandom for the chosen card.
    ("symbiote", None, ["KILL_WITH_FIRE"], 1),
    # TheFutureOfPotions.cs:59 — one NextItem(cardTypes) per held potion.
    ("the_future_of_potions", _stock_potions, [], 2),
    # ThisOrThat.cs:25 — NextInt(41, 69).
    ("this_or_that", None, [], 1),
    # TrashHeap.cs:65 — NextItem(Relics).
    ("trash_heap", None, ["DIVE_IN"], 1),
    # Trial.cs:73 — NextInt(3) picks the trial.
    ("trial", None, ["ACCEPT"], 1),
    # WelcomeToWongos.cs:158 — NextItem over the upgraded deck cards.
    ("welcome_to_wongos",
     lambda r: (setattr(r, "gold", 500), _upgraded_deck(r)), ["LEAVE"], 1),
    # WhisperingHollow.cs:38 — NextInt(-9, 10) (already parity-wired).
    ("whispering_hollow", lambda r: setattr(r, "gold", 500), [], 1),
]


@pytest.mark.parametrize(
    "event_id,setup,choices,expected",
    EVENT_RNG_CASES,
    ids=[f"{c[0]}-{'+'.join(c[2]) or 'begin'}" for c in EVENT_RNG_CASES],
)
def test_event_rolls_on_its_own_rng(event_id, setup, choices, expected):
    run = parity_run()
    if setup is not None:
        setup(run)
    run.rng.draws = 0
    event = make_event(event_id, run)
    event.begin()
    for key in choices:
        assert event.choose(key), f"{event_id}: option {key} not available"
    assert event.event_rng.counter == expected
    assert run.rng.draws == 0


# ═════════════════════════════════════════════════════════════════════════
# EV-7 / EV-5 — StableShuffle: sort on the UPPERCASE ModelId, then shuffle
# ═════════════════════════════════════════════════════════════════════════

def test_stable_shuffle_sorts_on_the_uppercase_id():
    """`_` is 0x5F: above 'A'-'Z' and below 'a'-'z', so the sim's lowercase
    slug orders `blood_wall` / `bloodletting` the opposite way from the
    game's ordinal compare over ModelId.Entry (ModelId.cs:49)."""
    from sts2_rl.actmap import stable_shuffle

    ids = ["bloodletting", "blood_wall"]
    assert sorted(ids) == ["blood_wall", "bloodletting"]
    assert sorted(ids, key=str.upper) == ["bloodletting", "blood_wall"]

    # Relic Trader shuffles its owned tradables; the sorted order must be the
    # game's, so a run holding pen_nib + pendulum sorts pendulum first.
    run = parity_run()
    for rid in ("pen_nib", "pendulum", "anchor", "akabeko", "kunai"):
        run.add_relic(rid)
    event = make_event("relic_trader", run).begin()
    order = [r.id for r in event._owned]
    # Whatever the shuffle does, it must have started from the game's sort.
    seeded = stable_shuffle(
        [r for r in run.relics if r.is_tradable],
        __import__("sts2_rl.rng", fromlist=["Rng"]).make_event_rng(
            run.rng_set.seed, "RELIC_TRADER"),
        key=lambda r: r.id.upper(),
    )
    assert order == [r.id for r in seeded[:3]]


def test_doors_of_light_and_dark_pick_is_order_independent():
    """DoorsOfLightAndDark.cs:28 is `StableShuffle(base.Rng).Take(2)` — the
    sort makes the pick independent of the deck's incidental order.  A
    `random.sample` over the raw pile does not."""
    deck_a = [make_card(cid) for cid in
              ("strike", "defend", "bash", "anger", "armaments", "brand")]
    deck_b = list(reversed(deck_a))

    picked = []
    for deck in (deck_a, [make_card(c.id) for c in deck_b]):
        run = parity_run(deck=deck)
        run.rng.draws = 0
        event = make_event("doors_of_light_and_dark", run).begin()
        event.choose("LIGHT")
        picked.append(sorted(c.id for c in run.deck if c.upgrade_level > 0))
        assert run.rng.draws == 0
    assert picked[0] == picked[1]


def test_battleworn_dummy_setting_2_stable_shuffles_on_the_event_rng():
    """BattlewornDummy.cs:97 — `StableShuffle(base.Rng).Take(2)`, not a bare
    shuffle on the shared run RNG."""
    run = parity_run()
    event = make_event("battleworn_dummy", run)
    event.begin()
    event.choose("SETTING_2")
    run.rng.draws = 0

    class _Dummy:
        escaped = False

    class _Combat:
        enemies = [_Dummy()]

    assert event.resume_after_combat(_Combat()) == []
    assert sum(1 for c in run.deck if c.upgrade_level > 0) == 2
    # 10 upgradable starters => 9 UnstableShuffle draws after the sort.
    assert event.event_rng.counter == 9
    assert run.rng.draws == 0


# ═════════════════════════════════════════════════════════════════════════
# EV-9 — the potion offer draws on PlayerRng.Rewards
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "event_id,setup,choices,rewards_draws",
    [
        # TheLegendsWereTrue.cs:53 / Wellspring.cs:33 — one NextItem over the
        # whole unlocked potion pool.
        ("the_legends_were_true", None, ["SLOWLY_FIND_AN_EXIT"], 1),
        ("wellspring", None, ["BOTTLE"], 1),
        # EndlessConveyor.cs:153 — same idiom, reached through the belt dish.
        # WhisperingHollow.cs:53-57 offers two bare PotionRewards, each a
        # PotionFactory.CreateRandomPotionOutOfCombat (NextFloat + NextItem).
        ("whispering_hollow", lambda r: setattr(r, "gold", 500), ["GOLD"], 4),
    ],
    ids=["the_legends_were_true", "wellspring", "whispering_hollow"],
)
def test_potion_offer_draws_on_the_rewards_stream(
        event_id, setup, choices, rewards_draws):
    run = parity_run()
    if setup is not None:
        setup(run)
    before = run.player_rng.rewards.counter
    run.rng.draws = 0
    event = make_event(event_id, run)
    event.begin()
    for key in choices:
        assert event.choose(key)
    assert run.player_rng.rewards.counter - before == rewards_draws
    assert run.rng.draws == 0
    assert len(run.held_potions) >= 1


def test_battleworn_dummy_setting_1_potion_is_a_rewards_draw():
    run = parity_run()
    event = make_event("battleworn_dummy", run)
    event.begin()
    event.choose("SETTING_1")
    before = run.player_rng.rewards.counter
    run.rng.draws = 0

    class _Dummy:
        escaped = False

    class _Combat:
        enemies = [_Dummy()]

    offered = event.resume_after_combat(_Combat())
    assert len(offered) == 1
    assert run.player_rng.rewards.counter - before == 1
    assert run.rng.draws == 0


def test_endless_conveyor_condiment_is_a_rewards_draw():
    run = parity_run()
    run.gold = 500
    event = make_event("endless_conveyor", run)
    event.begin()
    before = run.player_rng.rewards.counter
    run.rng.draws = 0
    event._suspicious_condiment()
    assert run.player_rng.rewards.counter - before == 1
    assert run.rng.draws == 0
    assert len(run.held_potions) == 1


# ═════════════════════════════════════════════════════════════════════════
# EV-6 — CreateForReward, not the in-combat generator
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("choice", ["STUDY", "TOUCH_CORE"])
def test_infested_automaton_uses_create_for_reward(choice):
    """InfestedAutomaton.cs:31/46 — CardFactory.CreateForReward over the
    character pool with a filter, on PlayerRng.Rewards."""
    run = parity_run()
    before_rewards = run.player_rng.rewards.counter
    run.rng.draws = 0
    event = make_event("infested_automaton", run)
    event.begin()
    assert event.choose(choice)
    assert run.player_rng.rewards.counter > before_rewards
    assert run.rng.draws == 0
    assert len(run.deck) == 11


def test_infested_automaton_study_offers_rarities_at_reward_odds():
    """ForNonCombatWithDefaultOdds rolls a rarity per card (RegularEncounter
    base odds: 3% Rare) instead of picking uniformly out of the pool, where
    Powers are ~28% Rare."""
    from sts2_rl.cards import CardRarity

    rares = 0
    for i in range(200):
        run = RunState(rng=random.Random(i), string_seed=f"ODDS{i}",
                       card_selector=_take_first)
        event = make_event("infested_automaton", run)
        event.begin()
        event.choose("STUDY")
        if run.deck[-1].rarity == CardRarity.RARE:
            rares += 1
    assert rares / 200 < 0.15


def test_endless_conveyor_fried_eel_uses_create_for_reward():
    """EndlessConveyor.cs:182 — CreateForReward over the Colorless pool."""
    from sts2_rl.cards.pool import COLORLESS_POOL

    run = parity_run()
    run.gold = 500
    event = make_event("endless_conveyor", run)
    event.begin()
    before = run.player_rng.rewards.counter
    run.rng.draws = 0
    event._fried_eel()
    assert run.player_rng.rewards.counter > before
    assert run.rng.draws == 0
    assert run.deck[-1].id in COLORLESS_POOL


# ═════════════════════════════════════════════════════════════════════════
# EV-8 — the hand-rolled offer skips CreateForReward's hook tail
# ═════════════════════════════════════════════════════════════════════════

def test_room_full_of_cheese_offer_runs_the_reward_hooks():
    """RoomFullOfCheese.cs:40-42 does NOT set NoModifyHooks, so
    Hook.TryModifyCardRewardOptions runs over the relics — Molten Egg
    upgrades every Attack ON THE OFFER SCREEN (CardFactory.cs:262-266)."""
    from sts2_rl.cards import CardType

    offered = {}

    def selector(purpose, candidates, count):
        offered.setdefault(purpose, [
            (c.id, c.card_type, c.upgrade_level) for c in candidates])
        return list(candidates)[:count]

    run = parity_run(card_selector=selector)
    run.add_relic("molten_egg")
    run.rng.draws = 0
    event = make_event("room_full_of_cheese", run)
    event.begin()
    event.choose("GORGE")

    cards = offered["card_reward"]
    assert len(cards) == 8
    attacks = [c for c in cards if c[1] == CardType.ATTACK]
    assert attacks, "the Common pool must contain Attacks"
    assert all(c[2] >= 1 for c in attacks)
    assert run.rng.draws == 0


def test_the_future_of_potions_offer_runs_the_reward_hooks():
    """TheFutureOfPotions.cs:127 is the same CreateForReward call; its
    AfterGenerated upgrades every offered card on top.

    R2 (round 13): the offer now rides `pending_rewards` (the mid-event
    OfferCustom channel brain_leech.py / trial.py use) instead of
    `run.select_cards`, so the offered cards are read off
    `event.pending_rewards.cards` rather than a `card_selector` callback —
    matching how `test_brain_leech_rip_costs_5_and_offers_colorless`
    (test_shared_events.py) inspects a mid-event reward without a driver."""
    run = parity_run()
    _stock_potions(run)
    run.rng.draws = 0
    event = make_event("the_future_of_potions", run)
    event.begin()
    assert event.choose("POTION_0")
    assert event.pending_rewards is not None
    cards = event.pending_rewards.cards
    assert cards and all(c.upgrade_level >= 1 for c in cards)
    assert run.rng.draws == 0
