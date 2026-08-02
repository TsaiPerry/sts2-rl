from __future__ import annotations

from ..cards import make_card
from ..rewards import CardRewardGroup, create_reward_cards
from .base import Event, EventOption, register_event

_NOBLE_HEAL = 10       # NobleGuilty: heal 10
_NOBLE_GOLD = 300      # NobleInnocent: gain 300 gold
_MERCHANT_RELICS = 2   # MerchantGuilty: 2 relics from the front
_UPGRADES = 2          # MerchantInnocent: upgrade 2 chosen
_TRANSFORMS = 2        # NondescriptInnocent: transform 2 chosen
_CARD_REWARDS = 2      # NondescriptGuilty: 2 card-reward offers


class _NonCombatCardRewardGroup(CardRewardGroup):
    """CardRewardGroup for a `CardCreationOptions.ForNonCombatWithDefaultOdds`
    screen whose pool is the run's own (un-overridden) character pool —
    Nondescript Guilty's two CardReward instances (Trial.cs:177-187, :183).

    The base `CardRewardGroup.populate` (rewards.py) infers `mutate_pity` from
    whether `pool` is set on the group: `pool is not None` (a caller narrowed
    the pool, e.g. Brain Leech's Rip to Colorless) means non-mutating, `pool
    is None` means mutating. That heuristic happens to be right for a
    pool-overriding screen and for a real post-combat CardReward (never
    overrides its pool, IS Encounter-sourced), but it is not what actually
    determines mutation in C#: `CardFactory.RollForRarity` only takes the
    pity-mutating `Roll` path for `options.Source == CardCreationSource.
    Encounter` (CardFactory.cs:244-260), and `Source` is set by the
    *factory method*, not by whether a pool was overridden
    (CardCreationOptions.cs:150-153: `ForNonCombatWithDefaultOdds` sets
    `Source = Other` regardless of which pool it reads). Nondescript Guilty
    uses `ForNonCombatWithDefaultOdds` with the character pool — Source=
    Other, pool=None on the group — so the base class's heuristic gives the
    wrong answer here specifically. This subclass hardcodes `mutate_pity=
    False`, correct for both the first draw and every Driftwood reroll."""

    def populate(self, run) -> None:
        self.populated = True
        self.cards = create_reward_cards(
            run, self._odds(), count=self.count,
            mutate_pity=False,
            pool=list(self.pool) if self.pool is not None else None,
            is_card_reward=True,
            extra_flags=self.flags,
        )


@register_event
class Trial(Event):
    """Trial — stand trial and be judged guilty or innocent, or reject it.

    Source: Trial.cs
      ACCEPT: roll one of three trials, each with a Guilty / Innocent verdict:
        Merchant  — Guilty: add Regret, 2 relics; Innocent: add Shame, upgrade 2
        Noble     — Guilty: heal 10;             Innocent: add Regret, +300 gold
        Nondescript — Guilty: add Doubt, 2 card rewards;
                      Innocent: add Doubt, transform 2
      REJECT → ACCEPT (stand trial after all) or DOUBLE_DOWN (abandon the run)
    The Entrant Number is cosmetic (rolled from a separate Chaotic RNG in the
    game) and is not modelled."""

    id = "trial"
    name = "Trial"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("ACCEPT", self._accept),
            EventOption("REJECT", self._reject),
        ]

    # ── Accept: roll a trial ─────────────────────────────────────────────

    def _accept(self) -> None:
        er = self.event_rng          # base.Rng.NextInt(3) — Trial.cs:73
        roll = er.next_int(3) if er is not None else self.rng.randrange(3)
        if roll == 0:
            self._set_state("MERCHANT", [
                EventOption("GUILTY", self._merchant_guilty),
                EventOption("INNOCENT", self._merchant_innocent),
            ])
        elif roll == 1:
            self._set_state("NOBLE", [
                EventOption("GUILTY", self._noble_guilty),
                EventOption("INNOCENT", self._noble_innocent),
            ])
        else:
            self._set_state("NONDESCRIPT", [
                EventOption("GUILTY", self._nondescript_guilty),
                EventOption("INNOCENT", self._nondescript_innocent),
            ])

    def _reject(self) -> None:
        self._set_state("REJECT", [
            EventOption("ACCEPT", self._accept),
            EventOption("DOUBLE_DOWN", self._double_down),
        ])

    def _double_down(self) -> None:
        self.run.kill()  # ThatWillKillPlayerIf(_ => true): abandon the run
        self._finish("DOUBLE_DOWN")

    # ── Verdicts ─────────────────────────────────────────────────────────

    def _merchant_guilty(self) -> None:
        self.run.add_card(make_card("regret"))
        for _ in range(_MERCHANT_RELICS):
            self.run.obtain_relic_from_grab_bag()
        self._finish("MERCHANT_GUILTY")

    def _merchant_innocent(self) -> None:
        self.run.add_card(make_card("shame"))
        for card in self.run.select_cards("upgrade", self.run.upgradable_cards(), _UPGRADES):
            card.upgrade()
        self._finish("MERCHANT_INNOCENT")

    def _noble_guilty(self) -> None:
        self.run.heal(_NOBLE_HEAL)
        self._finish("NOBLE_GUILTY")

    def _noble_innocent(self) -> None:
        self.run.add_card(make_card("regret"))
        self.run.gain_gold(_NOBLE_GOLD)
        self._finish("NOBLE_INNOCENT")

    def _nondescript_guilty(self) -> None:
        from ..rewards import (CardCreationFlags, CombatRewards, RarityOddsType,
                               apply_reward_modifiers)
        from ..rooms import RoomType

        self.run.add_card(make_card("doubt"))
        # Trial.cs:177-187 — after the Doubt, TWO `CardReward(CardCreationOptions
        # .ForNonCombatWithDefaultOdds([Owner.Character.CardPool]), 3, Owner)`
        # entries handed to `RewardsCmd.OfferCustom`. The port added the Doubt and
        # stopped, so the screens, the cards AND every Rewards-stream draw
        # CreateForReward takes were absent — a deck delta of exactly 1 where the
        # game's is 1 to 3. Both halves of the capability already existed:
        # create_reward_cards is the faithful CreateForReward port for exactly
        # this ForNonCombatWithDefaultOdds(characterPool) shape (brain_leech.py
        # calls it), and `pending_rewards` is the mid-event OfferCustom channel.
        #
        # F-R13a (round 13, filed as g17) recorded this as "the reroll redraws
        # from the CHARACTER pool" — copied verbatim from event/brain_leech/g6.
        # That framing does not actually transplant: this screen's pool was
        # ALREADY the (un-overridden) character pool before any reroll, so a
        # reroll draws from the same pool either way — there is no Colorless
        # narrowing here to lose. Re-deriving both draws against Trial.cs:183's
        # `ForNonCombatWithDefaultOdds` (Source=Other, CardCreationOptions.cs:
        # 150-153) found the REAL live defect instead: `create_reward_cards(...,
        # count=3)` below defaulted `mutate_pity=True` — the pity-mutating mode
        # `CardFactory.RollForRarity` reserves for `Source == Encounter`
        # (CardFactory.cs:244-260) — on the FIRST draw, not just on reroll, and
        # never set `is_card_reward=True` (missing `IsCardReward`, CardReward.
        # cs:114-115) either, so Silken Tress / Silver Crucible could not fire
        # here — the same shape of defect as g7 on Brain Leech's Rip, just
        # never filed for this screen. `_NonCombatCardRewardGroup` (above)
        # fixes both, on the first draw and every Driftwood reroll alike, the
        # same way `CardRewardGroup` already does for a pool-overriding screen
        # (brain_leech.py's Rip). `ForNonCombatWithDefaultOdds` also always
        # adds `NoUpgradeRoll` (CardCreationOptions.cs:139), which Trial.cs:183
        # never adds to on top of — unlike Rip, no other flag applies.
        groups = []
        for _ in range(2):
            group = _NonCombatCardRewardGroup(
                room_type=RoomType.MONSTER, count=3,
                odds_type=RarityOddsType.REGULAR,
                flags=CardCreationFlags.NO_UPGRADE_ROLL,
            )
            group.populate(self.run)
            groups.append(group)
        rewards = CombatRewards(room_type=RoomType.MONSTER, card_rewards=groups)
        # `RewardsCmd.OfferCustom` -> `RewardsSet.WithCustomRewards(rewards)
        # .Offer()` -> `GenerateWithoutOffering` runs Hook.ModifyRewards
        # (RewardsSet.cs:136) on BOTH CardReward entries the same pass —
        # Driftwood.TryModifyRewardsLate iterates every CardReward on the set
        # (Driftwood.cs:20-23) and doesn't check room (there is none here),
        # so both of Nondescript Guilty's screens come back rerollable.
        apply_reward_modifiers(self.run, rewards)
        self.pending_rewards = rewards
        self._finish("NONDESCRIPT_GUILTY")

    def _nondescript_innocent(self) -> None:
        self.run.add_card(make_card("doubt"))
        chosen = self.run.select_cards("transform", self.run.transformable_cards(), _TRANSFORMS)
        for card in chosen:
            # CardCmd.TransformToRandom(item, base.Rng) — Trial.cs:195.
            self.run.transform_card(card, pick_rng=self.event_rng)
        self._finish("NONDESCRIPT_INNOCENT")
