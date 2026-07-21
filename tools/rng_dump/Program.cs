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

static class Program
{
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

    static void Main()
    {
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
        };

        string outPath = Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory, "..", "..", "..", "..", "..", "test", "data", "rng_golden.json"));
        Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);
        File.WriteAllText(outPath, JsonSerializer.Serialize(root,
            new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"Wrote {outPath}");
    }
}
