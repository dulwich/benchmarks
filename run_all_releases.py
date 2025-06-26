#!/usr/bin/env python3
"""Run ASV benchmarks on all dulwich releases."""

import subprocess

# Get all release tags
result = subprocess.run(
    ["git", "ls-remote", "--tags", "https://github.com/jelmer/dulwich.git"],
    capture_output=True,
    text=True,
)

tags = []
for line in result.stdout.strip().split("\n"):
    if "refs/tags/dulwich-" in line and "^{}" not in line:
        tag = line.split("refs/tags/")[1]
        # Only include version tags (x.y.z format)
        if tag.count(".") == 2 and all(
            part.isdigit() for part in tag.replace("dulwich-", "").split(".")
        ):
            tags.append(tag)

# Sort tags by version
tags.sort(key=lambda x: tuple(map(int, x.replace("dulwich-", "").split("."))))

# Select releases to benchmark (every 5th release plus recent ones)
selected_tags = []
for i in range(0, len(tags) - 10, 5):
    selected_tags.append(tags[i])
# Add all recent releases
selected_tags.extend(tags[-10:])

print(f"Selected {len(selected_tags)} releases to benchmark:")
for tag in selected_tags:
    print(f"  {tag}")

# Don't set PURE environment variable - let ASV handle the build
# The build will try to compile C/Rust extensions by default,
# but we'll update asv.conf.json to handle failures gracefully

# Run ASV on selected tags with all benchmarks
for tag in selected_tags:
    print(f"\n{'=' * 60}")
    print(f"Benchmarking {tag}")
    print("=" * 60)

    # Run all benchmarks (no --bench filter means run everything)
    cmd = ["asv", "run", "--quick", f"{tag}^!"]

    # Run the benchmark command
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Print output
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    # Check if there were build errors and suggest pure Python fallback
    if result.returncode != 0 and "error" in result.stderr.lower():
        print(f"\nBuild or benchmark errors detected for {tag}.")
        print(
            "ASV will automatically fall back to pure Python if C/Rust extensions fail to build."
        )

print("\nDone! Generate report with:")
print("  asv publish")
print("  asv preview")
