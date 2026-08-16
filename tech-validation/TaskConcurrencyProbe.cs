using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

public sealed class TaskOrderState
{
    private readonly object gate = new object();
    private readonly HashSet<string> active = new HashSet<string>(StringComparer.Ordinal);
    private readonly HashSet<string> locked = new HashSet<string>(StringComparer.Ordinal);

    public TaskOrderState(int capacity)
    {
        if (capacity <= 0) throw new ArgumentOutOfRangeException("capacity");
        Capacity = capacity;
    }

    public int Capacity { get; private set; }

    public bool TryClaim(string workerId)
    {
        lock (gate)
        {
            if (active.Contains(workerId) || locked.Contains(workerId)) return false;
            if (active.Count + locked.Count >= Capacity) return false;
            active.Add(workerId);
            return true;
        }
    }

    public bool TryCompleteActive(string workerId)
    {
        lock (gate)
        {
            if (!active.Remove(workerId)) return false;
            if (locked.Count >= Capacity) throw new InvalidOperationException("capacity invariant violated");
            locked.Add(workerId);
            return true;
        }
    }

    public bool TryCompleteLate(string workerId)
    {
        lock (gate)
        {
            if (active.Contains(workerId) || locked.Contains(workerId)) return false;
            if (active.Count + locked.Count >= Capacity) return false;
            locked.Add(workerId);
            return true;
        }
    }

    public int ActiveCount { get { lock (gate) { return active.Count; } } }
    public int LockedCount { get { lock (gate) { return locked.Count; } } }
    public bool InvariantHolds { get { lock (gate) { return locked.Count + active.Count <= Capacity; } } }
}

public sealed class ConcurrencyScenarioResult
{
    public string Scenario { get; set; }
    public bool Passed { get; set; }
    public int Accepted { get; set; }
    public int Capacity { get; set; }
    public int Attempts { get; set; }
}

public static class TaskConcurrencyProbe
{
    private static int RunClaims(TaskOrderState state, IEnumerable<string> workerIds)
    {
        var start = new ManualResetEventSlim(false);
        var tasks = workerIds.Select(workerId => Task.Run(() =>
        {
            start.Wait();
            return state.TryClaim(workerId) ? 1 : 0;
        })).ToArray();
        start.Set();
        Task.WaitAll(tasks);
        return tasks.Sum(task => task.Result);
    }

    public static ConcurrencyScenarioResult[] Run()
    {
        var results = new List<ConcurrencyScenarioResult>();

        foreach (var capacity in new[] { 1, 5, 10 })
        {
            var state = new TaskOrderState(capacity);
            var workers = Enumerable.Range(0, 100).Select(i => "worker-" + i).ToArray();
            var accepted = RunClaims(state, workers);
            results.Add(new ConcurrencyScenarioResult
            {
                Scenario = "parallel-claims-n" + capacity,
                Capacity = capacity,
                Attempts = workers.Length,
                Accepted = accepted,
                Passed = accepted == capacity && state.ActiveCount == capacity && state.InvariantHolds
            });
        }

        {
            var state = new TaskOrderState(1);
            var accepted = RunClaims(state, Enumerable.Repeat("same-worker", 50));
            results.Add(new ConcurrencyScenarioResult
            {
                Scenario = "duplicate-worker-idempotency",
                Capacity = 1,
                Attempts = 50,
                Accepted = accepted,
                Passed = accepted == 1 && state.ActiveCount == 1 && state.InvariantHolds
            });
        }

        {
            var successfulRaces = 0;
            var allPassed = true;
            const int iterations = 200;
            for (var i = 0; i < iterations; i++)
            {
                var state = new TaskOrderState(1);
                var start = new ManualResetEventSlim(false);
                var late = Task.Run(() => { start.Wait(); return state.TryCompleteLate("late"); });
                var fresh = Task.Run(() => { start.Wait(); return state.TryClaim("fresh"); });
                start.Set();
                Task.WaitAll(late, fresh);
                var winners = (late.Result ? 1 : 0) + (fresh.Result ? 1 : 0);
                successfulRaces += winners;
                if (winners != 1 || !state.InvariantHolds) allPassed = false;
            }
            results.Add(new ConcurrencyScenarioResult
            {
                Scenario = "late-vs-fresh-last-slot",
                Capacity = 1,
                Attempts = iterations * 2,
                Accepted = successfulRaces,
                Passed = allPassed && successfulRaces == iterations
            });
        }

        {
            var state = new TaskOrderState(1);
            var protectedClaim = state.TryClaim("fresh");
            var displaced = state.TryCompleteLate("late");
            results.Add(new ConcurrencyScenarioResult
            {
                Scenario = "active-claim-protects-slot",
                Capacity = 1,
                Attempts = 2,
                Accepted = (protectedClaim ? 1 : 0) + (displaced ? 1 : 0),
                Passed = protectedClaim && !displaced && state.ActiveCount == 1 && state.InvariantHolds
            });
        }

        if (results.Any(result => !result.Passed))
            throw new InvalidOperationException("One or more concurrency scenarios failed.");

        return results.ToArray();
    }
}

