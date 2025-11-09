
# Hybrid-Chaotic-PRNG

Educational PRNG combining xorshift64*, a logistic chaotic map, and SHA-256 mixing.
This repository contains an implementation ready to upload to GitHub.

**Not cryptographically secure.** Use for simulations, learning, and experiments only.

## Files
- `hybrid_prng.py` : main implementation and simple tests
- `README.md` : this file
- `LICENSE` : MIT license

## Usage
```bash
# run demo
python3 hybrid_prng.py

# run with explicit seed (integer or string)
python3 hybrid_prng.py --seed 12345
python3 hybrid_prng.py --seed "hello"

# run quick tests
python3 hybrid_prng.py --test
```

## API example
```python
from hybrid_prng import HybridChaoticPRNG
pr = HybridChaoticPRNG(seed=12345)
print(pr.random())          # float
print(pr.random_uint64())   # 64-bit unsigned integer
print(pr.randint(1, 100))
print(pr.random_bytes(64))
```

## License
MIT
