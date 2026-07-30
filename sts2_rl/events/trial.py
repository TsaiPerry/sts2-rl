from __future__ import annotations

from ..cards import make_card
from .base import Event, EventOption, register_event

_NOBLE_HEAL = 10       # NobleGuilty: heal 10
_NOBLE_GOLD = 300      # NobleInnocent: gain 300 gold
_MERCHANT_RELICS = 2   # MerchantGuilty: 2 relics from the front
_UPGRADES = 2          # MerchantInnocent: upgrade 2 chosen
_TRANSFORMS = 2        # NondescriptInnocent: transform 2 chosen
_CARD_REWARDS = 2      # NondescriptGuilty: 2 card-reward offers


@register_event
class Trial(Event):
    """Trial — stand trial and be judged guilty or innocent, or reject it.

    Source: Trial.cs
      ACCEPT: roll one of three trials, each with a Guilty / Innocent verdict:
        Merchant  — Guilty: add Regret, 2 relics; Innocent: add Shame, upgrade 2
        Noble     — Guilty: heal 10;             Innocent: add Regret, +300 gold
        Nondescript — Guilty: add Doubt, 2 card rewards (offers unmodelled);
                      Innocent: add Doubt, transform 2
      REJECT → ACCEPT (stand trial after all) or DOUBLE_DOWN (abandon the run)
    The Entrant Number is cosmetic (rolled from a separate Chaotic RNG in the
    game) and is not modelled. Card-reward offers are not modelled."""

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
        from ..rewards import (CardRewardGroup, CombatRewards, RarityOddsType,
                               create_reward_cards)
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
        groups = []
        for _ in range(2):
            cards = create_reward_cards(self.run, RarityOddsType.REGULAR, count=3)
            groups.append(CardRewardGroup(cards=cards, room_type=RoomType.MONSTER,
                                          count=3, populated=True))
        self.pending_rewards = CombatRewards(room_type=RoomType.MONSTER,
                                             card_rewards=groups)
        self._finish("NONDESCRIPT_GUILTY")

    def _nondescript_innocent(self) -> None:
        self.run.add_card(make_card("doubt"))
        chosen = self.run.select_cards("transform", self.run.transformable_cards(), _TRANSFORMS)
        for card in chosen:
            # CardCmd.TransformToRandom(item, base.Rng) — Trial.cs:195.
            self.run.transform_card(card, pick_rng=self.event_rng)
        self._finish("NONDESCRIPT_INNOCENT")
