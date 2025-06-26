#!/bin/bash
# Test benchmarks on key dulwich releases

echo "Testing benchmarks on key dulwich releases..."

# Test older releases that might have compatibility issues
for tag in dulwich-0.10.0 dulwich-0.12.0 dulwich-0.15.0 dulwich-0.18.0 dulwich-0.20.0 dulwich-0.22.0 dulwich-0.23.0; do
    echo ""
    echo "===================="
    echo "Testing $tag"
    echo "===================="
    asv run --quick --bench="time_walk_full_history" "${tag}^!"
    
    # Check if successful
    if [ $? -ne 0 ]; then
        echo "ERROR: Benchmark failed for $tag"
    else
        echo "SUCCESS: Benchmark passed for $tag"
    fi
done

echo ""
echo "All tests complete!"