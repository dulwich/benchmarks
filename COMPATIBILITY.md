# Dulwich Benchmarks Compatibility

This document describes the compatibility fixes implemented to allow benchmarking across different dulwich versions.

## Compatibility Fixes

### 1. Repository Initialization
- **Issue**: Older versions fail when parent directory doesn't exist
- **Fix**: Added `os.makedirs(self.repo_path, exist_ok=True)` before `Repo.init()`

### 2. Staging Files
- **Issue**: `repo.stage()` method doesn't exist in older versions
- **Fix**: Fall back to manual index manipulation using `index_entry_from_stat()`

### 3. Commit Creation
- **Issue**: API changed from `parents` to `parent_commits` parameter
- **Fix**: Try `parent_commits` first, fall back to setting HEAD and using no parent parameter

### 4. Teardown Method
- **Issue**: ASV passes parameters to teardown but base class didn't accept them
- **Fix**: Changed `teardown(self)` to `teardown(self, *args)`

## Version Compatibility

The benchmarks have been tested and work with:
- dulwich 0.20.x and later (fully tested)
- dulwich 0.18.x - 0.19.x (should work with current fixes)
- dulwich 0.15.x - 0.17.x (may work, untested)
- dulwich < 0.15.x (may have build issues with Python 3.13)

## Running Benchmarks

To run benchmarks on historical releases:

```bash
# Single release
asv run --quick dulwich-0.20.0^!

# Range of releases
asv run --quick dulwich-0.20.0..dulwich-0.23.0

# Generate report
asv publish
asv preview
```

## Known Limitations

1. Very old dulwich versions (< 0.15.0) may not build with Python 3.13 due to C extension incompatibilities
2. Some benchmarks may need additional fixes for versions older than 0.18.0
3. Performance comparisons across major API changes should be interpreted carefully