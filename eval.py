"""Model evaluation harness: win rate, lethal-probe accuracy, run-scale reports.

    py eval.py sts2_ppo --episodes 1000                      # toy STS2CombatEnv model (SB3)
    py eval.py sts2_ppo_full --env full                      # full combat env: + probe accuracy
    py eval.py sts2_ppo_ablated --env full --ablated         # trained on AblatedObsEnv
    py eval.py --env full --baselines                        # no model: random + oracle

    py eval.py runs/sts2_torch.pt --env full                 # raw-torch combat checkpoint
    py eval.py runs/sts2_column_torch.pt --env column        # raw-torch full runs (curriculum)
    py eval.py runs/sts2_run_torch.pt --env run --episodes 50 --baselines
    py eval.py runs/sts2_run_torch.pt --env run --sample     # stochastic instead of greedy
    py eval.py runs/x.pt --env column --reward-hist          # + return distribution
    py eval.py runs/x.pt --env column --csv out              # + out.episodes.csv / out.hist.csv

A ``.pt`` model is a ``train_torch.py`` checkpoint (the current training path);
anything else is loaded as a stable-baselines3 MaskablePPO zip (the legacy
path). Torch checkpoints carry their own ``arch``/``obs_schema``/``env_kind``
stamps, so the right architecture is rebuilt automatically and a mismatched
env or observation layout is refused up front.

For the combat envs, probe accuracy is reported as a first-class metric
alongside win rate: the probes (sts2_rl/probes.py) are micro-scenarios where
the right move hinges on exact numbers — strike-lethal edges, block-or-die
edges, Weak/Vulnerable variants — so the score measures numeric grasp
directly. The toy env has its own 17-float observation, so probes don't apply
there.

For the run-scale envs, floors reached is the headline number: win rate stays
near zero for a long time, so how far a policy gets is what actually
distinguishes two checkpoints. Those envs also report two behavior metrics in
every row — ``e_unspent`` (energy left unspent per end-turn) and ``take`` (share
of card rewards taken) — the same two ``train_torch.py`` logs per training
window, so an eval row and a CSV row are directly comparable, plus
``rest_heal`` / ``rest_up`` (share of rest-site visits spent healing /
upgrading; both are per visit, so they can sum above 100%). ``--reward-hist``
adds the episode-return distribution, and ``--csv`` exports both the per-episode
rows and that distribution for a spreadsheet.
"""
import argparse
import random

import numpy as np

from sts2_rl import STS2CombatEnv, STS2FullCombatEnv
from sts2_rl.full_env import AblatedObsEnv
from sts2_rl.evaluation import (
    EVAL_SEEDS,
    PairedRunDelta,
    RunEvalReport,
    ablation_transform,
    compare_runs,
    evaluate_probes,
    evaluate_run,
    evaluate_win_rate,
    load_torch_policy,
    masked_random_policy,
    model_policy,
    probe_summary,
    reward_histogram_lines,
    write_cards_csv,
    write_run_csv,
)
from sts2_rl.probes import lethal_oracle

RUN_SCALE = ("run", "column")

# Width of the leading "policy" column in every report table.
LABEL_WIDTH = 40


def is_torch_checkpoint(path: str) -> bool:
    """``train_torch.py`` checkpoint (``.pt``) vs SB3 zip."""
    return path.endswith(".pt")


def load_sb3(model_path: str, env=None):
    """Load a MaskablePPO zip, importing SB3 lazily.

    SB3 is only needed for the legacy path, and it drags in a torch-load shim
    (below) — a torch-checkpoint evaluation shouldn't pay for either, nor
    require sb3 to be installed at all.

    The shim: PyTorch 2.12 changed its internal pth format in a way that breaks
    SB3 2.9's load path. SB3 passes a non-seekable zipfile stream and uses
    weights_only=True; both cause PyTorchFileReader to fail. Patch th.load
    inside SB3's save_util to read into a seekable BytesIO with
    weights_only=False.
    """
    import io

    import torch
    import stable_baselines3.common.save_util as _sb3_save_util

    class _TorchProxy:
        def __getattr__(self, name):
            return getattr(torch, name)

        def load(self, file, map_location=None, **kwargs):
            kwargs["weights_only"] = False
            if hasattr(file, "read"):
                file = io.BytesIO(file.read())
            return torch.load(file, map_location=map_location, **kwargs)

    _sb3_save_util.th = _TorchProxy()

    from sb3_contrib import MaskablePPO

    # Inference on a 256x256 MLP: CPU avoids SB3's auto-to-GPU warning and the
    # host<->device copy per predict() call.
    if env is not None:
        return MaskablePPO.load(model_path, env=env, device="cpu")
    return MaskablePPO.load(model_path, device="cpu")


def make_run_env(env_kind: str, acts: list[str] | None, ascension: int = 0):
    if env_kind == "column":
        from sts2_rl.curriculum_env import STS2CurriculumRunEnv

        return STS2CurriculumRunEnv(acts=acts, ascension=ascension)
    from sts2_rl.run_env import STS2RunEnv

    return STS2RunEnv(acts=acts, ascension=ascension)


def evaluate_simple(model_path: str, n_episodes: int = 1000) -> None:
    """The original toy-env evaluation (STS2CombatEnv, 3 actions)."""
    env = STS2CombatEnv()
    model = load_sb3(model_path, env=env)

    final_hp = []
    wins = 0

    for _ in range(n_episodes):
        obs, info = env.reset()
        done = False
        while not done:
            action, _ = model.predict(obs, action_masks=env.action_masks(), deterministic=True)
            obs, _, terminated, truncated, info = env.step(int(action))
            done = terminated or truncated

        result = env._state.result
        if result.player_won:
            wins += 1
            final_hp.append(env._state.player.hp)
        else:
            final_hp.append(0)

    hp = np.array(final_hp)
    max_hp = env._state.player.max_hp

    print(f"Episodes : {n_episodes}")
    print(f"Win rate : {wins / n_episodes:.1%}")
    print()
    print(f"Final HP (all episodes, deaths = 0):")
    print(f"  Mean : {hp.mean():.1f} / {max_hp}")
    print(f"  Std  : {hp.std():.1f}")
    print(f"  Min  : {hp.min():.0f}")
    print(f"  Max  : {hp.max():.0f}")

    if wins > 0:
        hp_wins = hp[hp > 0]
        print(f"\nFinal HP (wins only):")
        print(f"  Mean : {hp_wins.mean():.1f} / {max_hp}")
        print(f"  Std  : {hp_wins.std():.1f}")
        print(f"  Min  : {hp_wins.min():.0f}")
        print(f"  Max  : {hp_wins.max():.0f}")


def evaluate_full(
    model_path: str | None,
    n_episodes: int,
    seed: int,
    ablated: bool,
    baselines: bool,
    sample: bool = False,
    device: str = "cpu",
) -> None:
    """Full combat-env evaluation: win rate + probe accuracy for every policy row.

    Win rate runs on the env the policy was trained for (ablated models get an
    AblatedObsEnv); the probes always hand out raw observations, so ablated
    models see them through the same zeroing they were trained with.
    """
    # name -> (win-rate policy, win-rate env or None for default, probe policy)
    specs: dict[str, tuple] = {}
    if baselines or model_path is None:
        random_pol = masked_random_policy(seed)
        specs["masked-random"] = (random_pol, None, random_pol)
        specs["oracle"] = (lethal_oracle, None, lethal_oracle)
    if model_path is not None and is_torch_checkpoint(model_path):
        pol, ckpt = load_torch_policy(
            model_path, env_kind="combat", env=STS2FullCombatEnv(),
            device=device, sample=sample, seed=seed)
        specs[label(model_path, ckpt)] = (pol, None, pol)
    elif model_path is not None:
        model = load_sb3(model_path)
        if ablated:
            specs[f"model:{model_path}"] = (
                model_policy(model),
                AblatedObsEnv(STS2FullCombatEnv()),
                model_policy(model, ablation_transform()),
            )
        else:
            pol = model_policy(model)
            specs[f"model:{model_path}"] = (pol, None, pol)

    print(f"\n{n_episodes} episodes over the Act 1 pool, seed {seed}\n")
    header = f"{'policy':<{LABEL_WIDTH}} {'win%':>6} {'turns':>6} {'hp_left':>8}   probes"
    print(header)
    print("-" * len(header))
    for name, (win_pol, env, probe_pol) in specs.items():
        report = evaluate_win_rate(win_pol, episodes=n_episodes, seed=seed, env=env)
        accuracy, results = evaluate_probes(probe_pol)
        print(
            f"{name:<{LABEL_WIDTH}} {100 * report.win_rate:>5.1f}% {report.mean_turns:>6.1f} "
            f"{report.mean_hp_left:>8.1f}   {100 * accuracy:.0f}% = {probe_summary(results)}"
        )


def gimmick_probes(
    model_path: str | None,
    ascension: int,
    seed: int,
    sample: bool,
    device: str,
    episodes: int = 100,
) -> None:
    """v7 gimmick-fight probes (plan Task 10): the three fights Perry watched
    the bot fail mechanically, each rolled as a dedicated combat-env eval at
    the given ascension — turns "couldn't understand the gimmick" into a
    tracked number. Encounters are resolved BY CONSTANT from the top-level
    package (they live in the hive/glory registries, NOT vec_env's
    overgrowth-only ENCOUNTERS dict)."""
    from sts2_rl.monsters import (
        DECIMILLIPEDE_ELITE,
        TEST_SUBJECT_BOSS,
        THE_INSATIABLE_BOSS,
    )

    probes = [("decimillipede", DECIMILLIPEDE_ELITE),
              ("the_insatiable", THE_INSATIABLE_BOSS),
              ("test_subject", TEST_SUBJECT_BOSS)]
    print(f"\ngimmick probes (asc {ascension}, {episodes} episodes each):")
    for key, encounter in probes:
        env = STS2FullCombatEnv(encounter=encounter, ascension=ascension)
        if model_path is not None:
            try:
                policy, _ = load_torch_policy(
                    model_path, env_kind="combat", env=env,
                    device=device, sample=sample, seed=seed)
            except Exception as exc:
                # e.g. a run-scale checkpoint: its obs layout can't drive the
                # combat env — report and keep the rest of the eval usable.
                print(f"  probes skipped: {exc}")
                return
        else:
            policy = masked_random_policy(seed)
        env.reset(seed=seed)
        max_hp = env.unwrapped._state.player.max_hp
        report = evaluate_win_rate(policy, episodes=episodes, seed=seed, env=env)
        print(f"  {key:<16} win {100 * report.win_rate:5.1f}%  "
              f"mean_hp_lost {max_hp - report.mean_hp_left:6.1f}")


def label(model_path: str, ckpt: dict) -> str:
    """"runs/x.pt (entity, iter 500)" — provenance in the report row.

    Left-truncated to the column width: a long absolute path would otherwise
    push every following column out of alignment, and the informative end of a
    path is its tail."""
    text = f"{model_path} ({ckpt.get('arch', 'mlp')}, iter {ckpt.get('iteration', '?')})"
    return text if len(text) <= LABEL_WIDTH else "..." + text[-(LABEL_WIDTH - 3):]


def run_row(name: str, report: RunEvalReport) -> str:
    acts = " ".join(f"{a + 1}:{n}" for a, n in report.act_histogram.items())
    win_hp = f"{float(np.mean(report.win_hp)):.1f}" if report.win_hp else "-"
    return (
        f"{name:<{LABEL_WIDTH}} {100 * report.win_rate:>5.1f}% "
        f"{report.mean_floor:>7.1f} {report.median_floor:>5.0f}  "
        f"{acts:<16} {win_hp:>7} {report.mean_decisions:>8.1f} "
        f"{report.energy_unspent_per_turn:>9.2f} {100 * report.card_take_rate:>5.0f}%"
        f" {100 * report.rest_heal_rate:>9.0f}% {100 * report.rest_upgrade_rate:>7.0f}%"
        f" {100 * report.potion_use_rate:>9.0f}%"
    )


def evaluate_run_scale(
    model_path: str | None,
    env_kind: str,
    n_episodes: int,
    seed: int,
    acts: list[str] | None,
    baselines: bool,
    sample: bool,
    device: str,
    reward_hist: bool = False,
    csv_path: str | None = None,
    ascension: int = 0,
) -> None:
    """Run-scale evaluation: N seeded full runs on STS2RunEnv/STS2CurriculumRunEnv."""
    from sts2_rl.run_env import masked_random_run_policy

    rows: list[tuple[str, RunEvalReport]] = []

    if baselines or model_path is None:
        env = make_run_env(env_kind, acts, ascension)
        rows.append((
            "masked-random",
            evaluate_run(masked_random_run_policy(random.Random(seed)),
                         episodes=n_episodes, seed=seed, env=env),
        ))

    if model_path is not None:
        env = make_run_env(env_kind, acts, ascension)
        policy, ckpt = load_torch_policy(
            model_path, env_kind=env_kind, env=env,
            device=device, sample=sample, seed=seed)
        rows.append((
            label(model_path, ckpt),
            evaluate_run(policy, episodes=n_episodes, seed=seed, env=env),
        ))

    mode = "sampled" if sample else "greedy"
    act_str = " ".join(acts) if acts else "default act rolls"
    print(f"\n{n_episodes} full runs on the {env_kind!r} env, seed {seed}, "
          f"{mode} ({act_str})\n")
    header = (f"{'policy':<{LABEL_WIDTH}} {'win%':>6} {'floor~':>7} {'med':>5}  "
              f"{'acts reached':<16} {'hp@win':>7} {'dec/ep':>8} "
              f"{'e_unspent':>9} {'take':>6} {'rest_heal':>10} {'rest_up':>8}"
              f" {'potion_use':>10}")
    print(header)
    print("-" * len(header))
    for name, report in rows:
        print(run_row(name, report))

    # v8 HP-economy / potion-ledger / relic summary (plan Task 5) --
    # informational, no targets: hp_lost is the combat-sloppiness gauge,
    # potion elite-share is (elite+boss uses)/all uses pooled over episodes,
    # potions_used/potions_expired are raw per-episode means (hoarding
    # gauge), and relics is the per-episode mean gained.
    print("\nv8 HP/potion/relic summary:")
    for name, report in rows:
        print(f"  {name:<{LABEL_WIDTH}} hp_lost {report.mean_hp_lost:6.1f}  "
              f"potion_elite_share {100 * report.potion_elite_share:5.1f}%  "
              f"potions_used {report.mean_potions_used:5.2f}  "
              f"potions_expired {report.mean_potions_expired:5.2f}  "
              f"relics {report.mean_relics:5.2f}")

    print("\ndeaths (floor reached, losses only):")
    for name, report in rows:
        deaths = report.death_floors
        if not deaths:
            print(f"  {name:<{LABEL_WIDTH}} no deaths "
                  f"({report.wins} wins, {report.truncated} truncated)")
            continue
        d = np.array(deaths)
        print(f"  {name:<{LABEL_WIDTH}} n={len(d):<4} mean {d.mean():>5.1f}  "
              f"median {np.median(d):>4.0f}  max {d.max():>3}"
              + (f"  ({report.truncated} truncated)" if report.truncated else ""))

    if reward_hist:
        for name, report in rows:
            print()
            print("\n".join(reward_histogram_lines(name, report)))

    # The archetype-forcing signal (plan Task 8): cards the policy keeps
    # being offered and never takes.
    for name, report in rows:
        never = [(card, offered) for card, (offered, taken)
                 in report.card_take_counts.items() if taken == 0]
        if never:
            top = ", ".join(f"{c}x{o}" for c, o in never[:10])
            print(f"\nmost-offered never-taken ({name}): {top}")

    if csv_path is not None:
        ep_path, hist_path = write_run_csv(csv_path, rows)
        stem = csv_path[:-4] if csv_path.lower().endswith(".csv") else csv_path
        cards_path = f"{stem}.cards.csv"
        write_cards_csv(cards_path, rows)
        print(f"\nwrote {ep_path} ({sum(r.episodes for _, r in rows)} episode rows)"
              f"\nwrote {hist_path}"
              f"\nwrote {cards_path}")


def compare_checkpoints(
    ckpt_a: str,
    ckpt_b: str,
    env_kind: str,
    n_episodes: int,
    acts: list[str] | None,
    sample: bool,
    device: str,
    ascension: int = 0,
) -> None:
    """``--compare``: paired-seed A/B of two run-scale checkpoints on the
    SAME ``EVAL_SEEDS`` slice — per-seed floor/win/hp deltas plus the
    aggregate the CLI table needs (evaluation.compare_runs)."""

    def make_policy(path: str):
        # A fresh env is only needed to read obs_dim/n_actions for the load
        # check; compare_runs supplies the env each arm actually plays on.
        env = make_run_env(env_kind, acts, ascension)
        policy, ckpt = load_torch_policy(
            path, env_kind=env_kind, env=env, device=device, sample=sample)
        return policy, ckpt

    # Loaded once per arm and reused for that arm's whole seed sweep — see
    # compare_runs' docstring: greedy TorchPolicy carries no advancing state,
    # so a `lambda: policy` factory (not a fresh load per seed) is safe and
    # avoids reloading the checkpoint 200 times.
    policy_a, ckpt_a_data = make_policy(ckpt_a)
    policy_b, ckpt_b_data = make_policy(ckpt_b)

    seeds = EVAL_SEEDS[:n_episodes]
    delta: PairedRunDelta = compare_runs(
        lambda: policy_a, lambda: policy_b,
        seeds=seeds, env_factory=lambda: make_run_env(env_kind, acts, ascension))

    name_a = label(ckpt_a, ckpt_a_data)
    name_b = label(ckpt_b, ckpt_b_data)
    print(f"\npaired-seed A/B on {len(seeds)} seeds, {env_kind!r} env\n"
          f"  A = {name_a}\n  B = {name_b}\n")
    header = f"{'seed':>6} {'floor_a':>7} {'floor_b':>7} {'delta':>6} {'win_a':>6} {'win_b':>6} {'hp_a':>5} {'hp_b':>5}"
    print(header)
    print("-" * len(header))
    for i, s in enumerate(delta.seeds):
        d = delta.floor_deltas[i]
        print(f"{s:>6} {delta.floors_a[i]:>7} {delta.floors_b[i]:>7} {d:>+6} "
              f"{str(delta.wins_a[i]):>6} {str(delta.wins_b[i]):>6} "
              f"{delta.hp_a[i]:>5} {delta.hp_b[i]:>5}")

    print(f"\nmean floor delta   : {delta.mean_floor_delta:+.2f}")
    print(f"median floor delta : {delta.median_floor_delta:+.1f}")
    print(f"win delta (B - A)  : {delta.win_delta:+d}")
    print(f"better/worse/tie   : {delta.better}/{delta.worse}/{delta.tie}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", default=None,
                        help="Path to a saved model: a train_torch.py checkpoint "
                             "(*.pt) or an SB3 zip (e.g. sts2_ppo); optional with --baselines")
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--env", choices=["simple", "full", "run", "column"], default="simple",
                        help="'simple' = STS2CombatEnv (default, matches sts2_ppo); "
                             "'full' = STS2FullCombatEnv (matches train.py / "
                             "train_torch.py --env combat); "
                             "'run' = STS2RunEnv, 'column' = STS2CurriculumRunEnv "
                             "(both torch-only, match train_torch.py --env run|column)")
    parser.add_argument("--seed", type=int, default=0, help="full/run/column envs only")
    parser.add_argument("--acts", nargs="+", default=None,
                        help="run/column envs only: the act list (default: rolled per episode)")
    parser.add_argument("--ascension", type=int, default=0,
                        help="run/column envs only: the ascension level to evaluate at "
                             "(0 = no ascension, the old behavior); matches "
                             "train_torch.py --ascension")
    parser.add_argument("--ablated", action="store_true",
                        help="the model was trained on AblatedObsEnv observations (full env only)")
    parser.add_argument("--baselines", action="store_true",
                        help="also report baseline rows (masked-random + oracle on "
                             "--env full, masked-random on the run-scale envs)")
    parser.add_argument("--sample", action="store_true",
                        help="torch checkpoints: sample from the policy instead of "
                             "acting greedily (still deterministic given --seed)")
    parser.add_argument("--device", default="cpu", help="torch checkpoints (default: cpu)")
    parser.add_argument("--reward-hist", action="store_true",
                        help="run/column envs only: also print the episode-return "
                             "distribution as an ASCII bar chart (one row per "
                             "distinct return value)")
    parser.add_argument("--csv", default=None, metavar="PATH",
                        help="run/column envs only: export the evaluation as two "
                             "spreadsheet-ready CSVs — PATH.episodes.csv (one row "
                             "per episode: outcome, return, and the behavior "
                             "tallies) and PATH.hist.csv (the return histogram). "
                             "A trailing '.csv' on PATH is stripped")
    parser.add_argument("--gimmick-probes", action="store_true",
                        help="also roll the three gimmick fights "
                             "(Decimillipede, The Insatiable, Test Subject) "
                             "as dedicated combat-env probes at --ascension: "
                             "per-encounter win rate + mean HP lost over 100 "
                             "seeded combats (--env full/run/column)")
    parser.add_argument("--compare", nargs=2, metavar=("CKPT_A", "CKPT_B"), default=None,
                        help="paired-seed A/B of two run-scale checkpoints on EVAL_SEEDS "
                             "(--env run/column only); prints per-seed floor/win/hp deltas "
                             "plus aggregate mean/median delta and better/worse/tie counts. "
                             "--episodes N uses the first N of EVAL_SEEDS (default: all 200)")
    args = parser.parse_args()

    # --reward-hist / --csv read RunEvalReport fields that only the run-scale
    # report path produces. --compare returns a PairedRunDelta, which carries
    # neither the per-episode returns nor the behavior tallies.
    if args.env not in RUN_SCALE or args.compare is not None:
        for flag, value in (("--reward-hist", args.reward_hist), ("--csv", args.csv)):
            if value:
                parser.error(f"{flag} applies to the --env run/column report "
                             f"(not --compare, not the combat envs)")

    if args.compare is not None:
        if args.env not in RUN_SCALE:
            parser.error(f"--compare needs --env run or column (the run-scale envs), got {args.env!r}")
        if args.model is not None:
            parser.error("--compare takes two checkpoints of its own; drop the positional model arg")
        if args.baselines:
            parser.error("--compare has no baseline row (it's a two-arm A/B, not a report table)")
        if args.ablated:
            parser.error("--ablated applies to --env full only")
        for path in args.compare:
            if not is_torch_checkpoint(path):
                parser.error(f"--compare evaluates train_torch.py checkpoints (*.pt), got {path!r}")
        # EVAL_SEEDS[:n] clips at 200 automatically, so the plain --episodes
        # default (1000) already means "all of EVAL_SEEDS" with no sentinel
        # needed.
        compare_checkpoints(args.compare[0], args.compare[1], args.env, args.episodes,
                            args.acts, args.sample, args.device, args.ascension)
    elif args.env in RUN_SCALE:
        if args.model is None and not args.baselines:
            parser.error(f"--env {args.env} needs a model, --baselines, or both")
        if args.model is not None and not is_torch_checkpoint(args.model):
            parser.error(f"--env {args.env} evaluates train_torch.py checkpoints (*.pt); "
                         f"the SB3 path only covers the combat envs")
        if args.ablated:
            parser.error("--ablated applies to --env full only")
        evaluate_run_scale(args.model, args.env, args.episodes, args.seed,
                           args.acts, args.baselines, args.sample, args.device,
                           args.reward_hist, args.csv, args.ascension)
        if args.gimmick_probes:
            gimmick_probes(args.model, args.ascension, args.seed,
                           args.sample, args.device)
    elif args.env == "full":
        if args.model is None and not args.baselines:
            parser.error("--env full needs a model, --baselines, or both")
        if args.acts:
            parser.error("--acts applies to the run-scale envs only")
        # --ascension is allowed here since v7 Task 10: the combat env takes
        # an ascension kwarg (gimmick probes fight at the stage's level).
        if args.ablated and args.model is not None and is_torch_checkpoint(args.model):
            parser.error("--ablated is an SB3-path flag; train_torch.py has no ablated arm")
        evaluate_full(args.model, args.episodes, args.seed, args.ablated,
                      args.baselines, args.sample, args.device)
        if args.gimmick_probes:
            gimmick_probes(args.model, args.ascension, args.seed,
                           args.sample, args.device)
    else:
        if args.model is None:
            parser.error("--env simple needs a model path")
        if is_torch_checkpoint(args.model):
            parser.error("--env simple is the toy SB3 env; a train_torch.py "
                         "checkpoint wants --env full, run, or column")
        evaluate_simple(args.model, args.episodes)
