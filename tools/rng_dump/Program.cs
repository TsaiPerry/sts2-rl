using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using MegaCrit.Sts2.Core.Random;
using MegaCrit.Sts2.Core.Helpers;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Entities.Rngs;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Acts;
using System.Runtime.CompilerServices;

static class Program
{
    // A bit-exact oracle for the generated act map: build the real
    // StandardActMap from sts2.dll for a seed+act and dump the grid
    // (coords + types + edges + the map_N Rng counter). Used to fix the
    // Python actmap.py port to exact column/adjacency parity.
    static ActModel MakeAct(string act)
    {
        System.Type t = act switch
        {
            "overgrowth" => typeof(Overgrowth),
            "underdocks" => typeof(Underdocks),
            "hive" => typeof(Hive),
            "glory" => typeof(Glory),
            _ => throw new ArgumentException($"unknown act {act}"),
        };
        // GetNumberOfRooms (BaseNumberOfRooms constant) + GetMapPointTypes
        // (pure Rng) are all StandardActMap needs; skip the ctor entirely.
        return (ActModel)RuntimeHelpers.GetUninitializedObject(t);
    }

    static object DumpMap(string seedStr, int actIndex, string act, int eliteCount, bool prune = true)
    {
        uint runSeed = (uint)StringHelper.GetDeterministicHashCode(seedStr);
        var mapRng = new Rng(runSeed, $"act_{actIndex + 1}_map");
        // GetMapPointTypes draw order (Overgrowth/Underdocks): rest gaussian
        // THEN unknown gaussian. Replicate manually so we can pin NumOfElites
        // (SwarmingElites at Asc 1+ makes it 8) without a booted RunManager.
        int restCount = mapRng.NextGaussianInt(7, 1, 6, 7);
        int unknownCount = MapPointTypeCounts.StandardRandomUnknownCount(mapRng);
        var counts = new MapPointTypeCounts(unknownCount, restCount) { NumOfElites = eliteCount };
        var map = new StandardActMap(mapRng, MakeAct(act), false, false, false, counts, prune);
        var points = new List<object>();
        foreach (MapPoint p in map.GetAllMapPoints())
        {
            var kids = p.Children.OrderBy(c => c.coord.col).ThenBy(c => c.coord.row)
                .Select(c => new[] { c.coord.col, c.coord.row }).ToList();
            points.Add(new
            {
                col = p.coord.col, row = p.coord.row,
                type = p.PointType.ToString(), children = kids,
            });
        }
        points.Sort((a, b) =>
        {
            dynamic da = a, db = b;
            return da.row != db.row ? da.row - db.row : da.col - db.col;
        });
        var startKids = map.StartingMapPoint.Children
            .OrderBy(c => c.coord.col).ThenBy(c => c.coord.row)
            .Select(c => new[] { c.coord.col, c.coord.row }).ToList();
        return new
        {
            seed = seedStr, act, act_index = actIndex,
            elite_count = eliteCount, rest_count = restCount, unknown_count = unknownCount,
            start = new[] { map.StartingMapPoint.coord.col, map.StartingMapPoint.coord.row },
            start_children = startKids,
            boss = new[] { map.BossMapPoint.coord.col, map.BossMapPoint.coord.row },
            counter_after = mapRng.Counter,
            points,
        };
    }

    static string TypeCounts(StandardActMap map)
    {
        var c = new SortedDictionary<string, int>();
        foreach (var p in map.GetAllMapPoints())
        {
            string k = p.PointType.ToString();
            c[k] = c.GetValueOrDefault(k) + 1;
        }
        return string.Join(" ", c.Select(kv => $"{kv.Key[..4]}={kv.Value}"));
    }

    static void PruneTrace(string seedStr, int actIndex, string act, int eliteCount)
    {
        uint runSeed = (uint)StringHelper.GetDeterministicHashCode(seedStr);
        var mapRng = new Rng(runSeed, $"act_{actIndex + 1}_map");
        int restCount = mapRng.NextGaussianInt(7, 1, 6, 7);
        int unknownCount = MapPointTypeCounts.StandardRandomUnknownCount(mapRng);
        var counts = new MapPointTypeCounts(unknownCount, restCount) { NumOfElites = eliteCount };
        var actModel = MakeAct(act);
        int mapLength = actModel.GetNumberOfRooms(false) + 1;

        var t = typeof(StandardActMap);
        var map = (StandardActMap)RuntimeHelpers.GetUninitializedObject(t);
        const BindingFlags BF = BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance;
        void Set(Type owner, string field, object val) => owner.GetField(field, BF)!.SetValue(map, val);
        var grid = new MapPoint[7, mapLength];
        Set(t, "<Grid>k__BackingField", grid);
        Set(t, "_rng", mapRng);
        Set(t, "_mapLength", mapLength);
        Set(t, "_pointTypeCounts", counts);
        Set(t, "<ShouldReplaceTreasureWithElites>k__BackingField", false);
        Set(t, "<StartingMapPoint>k__BackingField", new MapPoint(3, 0));
        Set(t, "<BossMapPoint>k__BackingField", new MapPoint(3, mapLength));
        Set(t, "<SecondBossMapPoint>k__BackingField", null!);
        typeof(ActMap).GetField("startMapPoints", BF)!.SetValue(map, new HashSet<MapPoint>());

        t.GetMethod("GenerateMap", BF)!.Invoke(map, null);
        t.GetMethod("AssignPointTypes", BF)!.Invoke(map, null);
        Console.WriteLine($"[{seedStr} {act} e{eliteCount}] pre-prune counter={mapRng.Counter}");

        var startField = typeof(ActMap).GetField("startMapPoints", BF)!;
        Func<MapPointType, MapPoint, bool> isValid = map.IsValidPointType;

        // Dump the initial duplicate groups (before any pruning) for diffing.
        var groups0 = MapPathPruning.FindMatchingSegments(map.StartingMapPoint);
        Console.WriteLine($"  round0 groups={groups0.Count}");
        for (int g = 0; g < groups0.Count; g++)
        {
            var segs = groups0[g].Select(seg =>
                "[" + string.Join(" ", seg.Select(p => $"{p.coord.col},{p.coord.row}")) + "]");
            Console.WriteLine($"    g{g}: {string.Join(" | ", segs)}");
        }
        for (int i = 0; i < 3; i++)
        {
            int b = mapRng.Counter;
            var start = (HashSet<MapPoint>)startField.GetValue(map)!;
            MapPathPruning.PruneDuplicateSegments(grid, start, map.StartingMapPoint, mapRng);
            int ap = mapRng.Counter;
            string afterPrune = TypeCounts(map);
            bool repaired = MapPathPruning.RepairPrunedPointTypes(map, counts, mapRng, isValid);
            int ar = mapRng.Counter;
            Console.WriteLine($"  round {i}: prune_draws={ap - b} [{afterPrune}] repair_draws={ar - ap} [{TypeCounts(map)}] repaired={repaired}");
            if (!repaired) break;
        }
        Console.WriteLine($"  final counter={mapRng.Counter}");
    }

    static void MapMain()
    {
        if (Environment.GetCommandLineArgs().Contains("prunetrace"))
        {
            PruneTrace("89U21BV1TZ", 0, "overgrowth", 8);
            return;
        }
        // seed -> act-1 act name (89U21BV1TZ etc. are Overgrowth/Underdocks).
        var jobs = new (string seed, int idx, string act, int elites, bool prune)[]
        {
            ("89U21BV1TZ", 0, "overgrowth", 8, true),   // asc-1 (SwarmingElites), full pipeline
        };
        var outMaps = new List<object>();
        foreach (var (seed, idx, act, elites, prune) in jobs)
            outMaps.Add(DumpMap(seed, idx, act, elites, prune));
        string outPath = Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory, "..", "..", "..", "..", "..",
            "test", "data", "map_golden.json"));
        Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);
        File.WriteAllText(outPath, JsonSerializer.Serialize(outMaps,
            new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"Wrote {outPath}");
    }

    static object MegaBlock(uint seed)
    {
        List<string> u = new(); var m = new MegaRandom(seed);
        for (int i = 0; i < 8; i++) u.Add(m.NextULong().ToString());
        List<double> d = new(); m = new MegaRandom(seed);
        for (int i = 0; i < 8; i++) d.Add(m.NextDouble());
        List<int> ni = new(); m = new MegaRandom(seed);
        for (int i = 0; i < 8; i++) ni.Add(m.NextInt());
        List<double> nf = new(); m = new MegaRandom(seed);
        for (int i = 0; i < 8; i++) nf.Add(m.NextFloat());          // widen float->double
        List<int> n100 = new(); m = new MegaRandom(seed);
        for (int i = 0; i < 8; i++) n100.Add(m.Next(100));
        List<int> nr = new(); m = new MegaRandom(seed);
        for (int i = 0; i < 8; i++) nr.Add(m.Next(-5, 5));
        return new
        {
            next_ulong = u, next_double = d, next_int_full = ni,
            next_float = nf, next_100 = n100, next_range_neg5_5 = nr
        };
    }

    static void Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "map") { MapMain(); return; }
        // splitmix64 seed-0 state (read s0..s3 after Reinitialise via reflection).
        var mr = new MegaRandom(0);
        var f = typeof(MegaRandom);
        string[] sf = { "_s0", "_s1", "_s2", "_s3" };
        var state = sf.Select(n =>
            ((ulong)f.GetField(n, BindingFlags.NonPublic | BindingFlags.Instance)!
                .GetValue(mr)!).ToString()).ToArray();

        var mega = new Dictionary<string, object>();
        foreach (uint s in new uint[] { 0, 1, 42 }) mega[s.ToString()] = MegaBlock(s);

        var rng = new Rng(12345);
        List<int> ri = new(); for (int i = 0; i < 10; i++) ri.Add(rng.NextInt(100));
        rng = new Rng(12345); List<bool> rb = new();
        for (int i = 0; i < 10; i++) rb.Add(rng.NextBool());
        rng = new Rng(12345); List<double> rfl = new();
        for (int i = 0; i < 5; i++) rfl.Add(rng.NextFloat());
        rng = new Rng(12345); List<double> rflb = new();       // non-power-of-2 bounds
        for (int i = 0; i < 5; i++) rflb.Add(rng.NextFloat(0.85f, 1.15f));
        rng = new Rng(12345); List<uint> rui = new();
        for (int i = 0; i < 5; i++) rui.Add(rng.NextUnsignedInt(0, 1000));
        rng = new Rng(12345); List<double> rd = new();
        for (int i = 0; i < 5; i++) rd.Add(rng.NextDouble());
        rng = new Rng(12345);
        var lst = Enumerable.Range(0, 10).ToList(); rng.Shuffle(lst);
        rng = new Rng(12345); var pool = new[] { "a", "b", "c", "d", "e" };
        List<string> items = new(); for (int i = 0; i < 10; i++) items.Add(rng.NextItem(pool)!);
        var named = new Rng(12345, "shuffle");
        var namedFirst = new Rng(12345, "shuffle").NextInt(1000);

        var hashKeys = new[] { "", "a", "ab", "shuffle", "monster_ai", "ABCDEFGHIJ", "up_front" };
        var hash = hashKeys.ToDictionary(k => k, k => StringHelper.GetDeterministicHashCode(k));
        var names = new[]
        {
            "UpFront", "Shuffle", "UnknownMapPoint", "CombatCardGeneration",
            "CombatPotionGeneration", "CombatCardSelection", "CombatEnergyCosts",
            "CombatTargets", "MonsterAi", "Niche", "CombatOrbs", "TreasureRoomRelics"
        };
        var snake = names.ToDictionary(n => n, n => StringHelper.SnakeCase(n));

        var set = new RunRngSet("ABCDEFGHIJ");
        var streams = new Dictionary<string, object>();
        // Read the private _rngs dictionary by enum key: property names don't
        // always match the enum (CombatOrbs -> property CombatOrbGeneration).
        var rngsField = typeof(RunRngSet).GetField(
            "_rngs", BindingFlags.NonPublic | BindingFlags.Instance)!;
        foreach (RunRngType t in Enum.GetValues<RunRngType>())
        {
            // Fresh set per stream so first_next_int_1000 is measured from counter 0.
            var probe = new RunRngSet("ABCDEFGHIJ");
            var dict = (System.Collections.IDictionary)rngsField.GetValue(probe)!;
            var probeRng = (Rng)dict[t]!;
            streams[t.ToString()] = new { seed = probeRng.Seed, first_next_int_1000 = probeRng.NextInt(1000) };
        }

        var ff = new Rng(777, 5).NextInt(1000);

        // --- Gaussians (Rng.NextGaussianInt/Double/Float). Data-dependent
        // counter (rejection loop): dump the resulting Counter alongside the
        // values so the Python port's counter accounting can be asserted. ---
        var gi = new Rng(12345); var giVals = new List<int>();
        for (int i = 0; i < 8; i++) giVals.Add(gi.NextGaussianInt(12, 1, 10, 14));
        var gr = new Rng(12345); var grVals = new List<int>();
        for (int i = 0; i < 8; i++) grVals.Add(gr.NextGaussianInt(7, 1, 6, 7));
        var gd = new Rng(12345); var gdVals = new List<double>();
        for (int i = 0; i < 8; i++) gdVals.Add(gd.NextGaussianDouble(0.0, 1.0, 0.0, 1.0));
        var gf = new Rng(12345); var gfVals = new List<double>();
        for (int i = 0; i < 8; i++) gfVals.Add(gf.NextGaussianFloat(0f, 1f, 0f, 1f));
        var gaussian = new
        {
            next_gaussian_int_12_1_10_14 = new { values = giVals, counter_after = gi.Counter },
            next_gaussian_int_7_1_6_7 = new { values = grVals, counter_after = gr.Counter },
            next_gaussian_double = new { values = gdVals, counter_after = gd.Counter },
            next_gaussian_float = new { values = gfVals, counter_after = gf.Counter },
        };

        // --- PlayerRngSet: single-player slot-0 seed == run seed. Probe each
        // stream from a fresh set so first draw is measured from counter 0. ---
        uint playerSeed = (uint)StringHelper.GetDeterministicHashCode("89U21BV1TZ");
        var playerStreams = new Dictionary<string, object>();
        foreach (var nm in new[] { "Rewards", "Shops", "Transformations" })
        {
            var pset = new PlayerRngSet(playerSeed);
            Rng pr = nm switch
            {
                "Rewards" => pset.Rewards,
                "Shops" => pset.Shops,
                _ => pset.Transformations,
            };
            playerStreams[nm] = new { seed = pr.Seed, first_next_int_1000 = pr.NextInt(1000) };
        }
        var playerRngset = new
        {
            seed_str = "89U21BV1TZ", player_seed = playerSeed, streams = playerStreams,
        };

        var root = new Dictionary<string, object>
        {
            ["splitmix64_seed0_state"] = state,
            ["megarandom"] = mega,
            ["rng"] = new Dictionary<string, object>
            {
                ["seed_12345"] = new
                {
                    next_int_100 = ri, next_bool = rb, next_float = rfl,
                    next_float_bounded_085_115 = rflb, next_unsigned_int_1000 = rui,
                    next_double = rd, shuffle_0_9 = lst, next_item_abcde = items
                },
                ["named_shuffle"] = new { seed = named.Seed, first_next_int_1000 = namedFirst }
            },
            ["hash"] = hash,
            ["snake_case"] = snake,
            ["runrngset"] = new { seed_str = "ABCDEFGHIJ", run_seed = set.Seed, streams = streams },
            ["fast_forward"] = new { seed_777_to_5_then_next_int_1000 = ff },
            ["gaussian"] = gaussian,
            ["player_rngset"] = playerRngset,
        };

        string outPath = Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory, "..", "..", "..", "..", "..", "test", "data", "rng_golden.json"));
        Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);
        File.WriteAllText(outPath, JsonSerializer.Serialize(root,
            new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"Wrote {outPath}");
    }
}
