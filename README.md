# Airspeed Velocity Benchmarks for Dulwich

This directory contains ASV (Airspeed Velocity) benchmarks for Dulwich core operations.

## Installation

First, install airspeed velocity:

```bash
pip install asv
```

## Running Benchmarks

### Quick benchmark of current code:

```bash
asv run
```

### Run specific benchmarks:

```bash
# Run only large history benchmarks
asv run -b LargeHistoryBenchmarks

# Run with specific parameters
asv run -b "LargeHistoryBenchmarks.time_walk_full_history"
```

### Continuous benchmarking across commits:

```bash
# Benchmark last 10 commits
asv run HEAD~10..HEAD

# Benchmark specific commit range
asv run v1.0.0..master
```

### Compare results:

```bash
# Compare current commit with master
asv continuous master HEAD

# Compare two commits
asv compare v1.0.0 HEAD
```

### Generate HTML reports:

```bash
asv publish
asv preview  # Opens in browser
```

## Benchmark Categories

### 1. Large History Operations (`LargeHistoryBenchmarks`)
- Walking full commit history
- Limited history walks
- Path-filtered logs
- Rev-list operations
- Merge base calculations
- **Log with patches** (`porcelain.log` - equivalent to `git log -p`)
- **Show commits** (`porcelain.show` - equivalent to `git show`)
- **Diff tree** (`porcelain.diff_tree` - diff between commits)

Parameters:
- `num_commits`: 100, 1000, 5000
- `files_per_commit`: 10, 50, 100

### 2. Disk Object Store (`DiskObjectStoreBenchmarks`)
- Reading objects from disk (loose, packed, or mixed storage)
- Object existence checks
- Iterating all objects

Parameters:
- `num_objects`: 1000, 10000, 50000
- `storage_type`: 'loose', 'packed', 'mixed'

### 3. Pack File Disk Operations (`PackFileDiskBenchmarks`)
- Random access to packed objects
- Sequential pack reading
- Pack index loading
- Pack verification

Parameters:
- `num_objects`: 1000, 10000, 50000
- `with_deltas`: False, True

### 4. Client/Server Operations (`ClientServerBenchmarks`)
- Local protocol clone
- Local protocol fetch
- Local protocol push

Parameters:
- `num_commits`: 100, 1000
- `operation`: 'fetch', 'push', 'clone'

### 5. HTTP Protocol Operations (`HTTPProtocolBenchmarks`)
- HTTP smart protocol clone
- HTTP fetch-pack operations
- With/without compression

Parameters:
- `num_commits`: 100, 1000
- `use_compression`: True, False

### 6. Pack Negotiation (`PackNegotiationBenchmarks`)
- Negotiation with varying common history
- Pack generation simulation

Parameters:
- `num_commits`: 100, 1000, 5000
- `common_history_percent`: 0, 50, 90

### 7. Large File Handling (`LargeFileBenchmarks`)
- Adding large files
- Diffing large file changes

Parameters:
- `file_size_mb`: 1, 10, 50, 100

### 8. Branch Operations (`BranchOperationBenchmarks`)
- Listing branches
- Switching branches
- Merging branches

Parameters:
- `num_branches`: 10, 100, 1000

### 9. Status Operations (`StatusBenchmarks`)
- Repository status with many files
- Index diffing

Parameters:
- `num_files`: 100, 1000, 5000
- `percent_modified`: 10, 50, 100

### 10. Garbage Collection (`GarbageCollectionBenchmarks`)
- Counting objects with `porcelain.count_objects`
- Full GC with `porcelain.gc`
- Repacking with `porcelain.repack`
- Pruning unreachable objects with `porcelain.prune`
- Filesystem check with `porcelain.fsck`

Parameters:
- `num_loose_objects`: 100, 1000, 5000
- `unreachable_percent`: 0, 10, 50

### 11. Repacking Operations (`RepackingBenchmarks`)
- Full repository repack
- Incremental repacking
- Reference packing
- Pack file optimization/verification

Parameters:
- `num_packs`: 10, 50, 100
- `objects_per_pack`: 100, 1000, 5000
- `with_deltas`: False, True

### 12. Symbolic Reference Operations (`SymrefBenchmarks`)
- Reading symbolic references
- Following symref chains
- Setting new symrefs
- Updating symref targets
- Listing all refs including symrefs
- Reading remote HEAD symrefs
- Resolving remote symrefs

Parameters:
- `num_refs`: 10, 100, 1000
- `symref_depth`: 1, 2, 4

## Benchmark Development

To add new benchmarks:

1. Add a new class inheriting from `BenchmarkBase`
2. Implement `setup()` method for test data preparation
3. Add benchmark methods prefixed with `time_` for timing benchmarks
4. Use `params` and `param_names` for parameterized benchmarks

Example:

```python
class MyBenchmarks(BenchmarkBase):
    params = [10, 100, 1000]
    param_names = ['size']
    
    def setup(self, size):
        super().setup()
        # Setup code
        
    def time_my_operation(self, size):
        # Code to benchmark
```

## Integration with CI

The ASV benchmarks can be integrated with GitHub Actions for continuous performance monitoring.

## Tips

1. Use `--quick` for faster test runs during development
2. Set `ASV_USE_CONDA=no` to use virtualenv instead of conda
3. Use `--show-stderr` to debug benchmark failures
4. Results are stored in `.asv/results/` as JSON files
