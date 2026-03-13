# MVP Build Todo

This file stores the working implementation plan derived from the earlier MVP outline.

## Build tracker

- [x] Re-read [plan.txt](plan.txt) and extract the MVP-safe core
- [x] Convert the MVP outline into a tracked todo list
- [x] Scaffold the Python project and dependency manifest
- [x] Add provider abstraction and prompt assets
- [x] Implement persistent storage and seed model/task loading
- [x] Implement the sequential round engine
- [x] Implement market scoring and calibration updates
- [x] Add generated-task flow with lightweight validation
- [x] Expose a read-only web dashboard and round controls
- [x] Add smoke tests and setup documentation

## Current limitations

- Real rounds still require valid provider API keys.
- The evaluator reputation system is intentionally weak until more anchor rounds exist.
- Generated-task validation is lightweight and does not yet include semantic dedup or anomaly review.

## MVP scope decisions

- Local research prototype
- Real providers from day one
- Web dashboard first
- Mostly generated tasks, but keep a small anchor set
- Peer-council-first evaluation
- Show both task bidding and price-discovery market layers

## Execution order

1. backend core
2. storage
3. orchestration loop
4. dashboard
5. tests and docs
