#!/usr/bin/env python3
"""
hybrid_prng.py

HybridChaotic PRNG - educational hybrid PRNG combining xorshift64* (fast bitwise),
a logistic chaotic map (nonlinear), and SHA-256 block mixing.

NOT cryptographically secure. Use for simulations, experimentation, learning.
"""

from __future__ import annotations
import os
import time
import struct
import hashlib
import argparse
from collections import Counter
from typing import Optional

# ---------------------
# Helper / utilities
# ---------------------
def _int_to_bytes_be(x: int, length: int) -> bytes:
    return x.to_bytes(length, 'big', signed=False)

def _bytes_to_int_be(b: bytes) -> int:
    return int.from_bytes(b, 'big')

# ---------------------
# HybridChaotic PRNG
# ---------------------
class HybridChaoticPRNG:
    """
    HybridChaoticPRNG:
      - xorshift64* core (fast linear-ish component)
      - logistic map (double precision chaotic component)
      - SHA-256 mixing per block for diffusion
    Public methods:
      - seed(s)
      - random_uint64()
      - random() -> float in [0,1)
      - randint(a,b)
      - random_bytes(n)
    """
    def __init__(self, seed: Optional[object] = None):
        # xorshift64* internal state (must be non-zero)
        self._xs = 0x9e3779b97f4a7c15  # will be replaced on seed()
        # logistic map state in (0,1)
        self._log = 0.3141592653589793
        # buffer for hashed bytes
        self._buf = bytearray()
        # block counter
        self._ctr = 0
        self.seed(seed)

    # -----------------
    # seeding
    # -----------------
    def seed(self, s: Optional[object] = None):
        """Seed the generator. Accepts None, int, bytes, or str."""
        if s is None:
            # combine OS entropy + time
            sbytes = os.urandom(32) + struct.pack(">d", time.time())
        elif isinstance(s, bytes):
            sbytes = s
        elif isinstance(s, str):
            sbytes = s.encode('utf-8')
        elif isinstance(s, int):
            # convert int to 32 bytes big-endian (pad/truncate)
            blen = max(1, (s.bit_length() + 7) // 8)
            sbytes = s.to_bytes(blen, 'big', signed=False)
        else:
            sbytes = str(s).encode('utf-8')

        h = hashlib.sha256(sbytes).digest()
        # init xorshift state from first 8 bytes (ensure non-zero)
        xs = int.from_bytes(h[:8], 'big')
        if xs == 0:
            xs = 0xDEADBEEFCAFEBABE
        self._xs = xs & ((1 << 64) - 1)

        # init logistic from next 8 bytes mapped into (0,1)
        v = int.from_bytes(h[8:16], 'big') / float(1 << 64)
        if not (0.0 < v < 1.0):
            v = 0.3141592653
        # mix slightly toward a sane non-extreme value
        self._log = 0.5 * (v + 0.3141592653)

        # reset buffer and counter, mix remaining hash material
        self._buf = bytearray()
        self._ctr = 0
        self._mix_into_state(h[16:])

    # -----------------
    # core primitives
    # -----------------
    def _xorshift64star(self) -> int:
        # xorshift64* with multiplier (as typical)
        x = self._xs
        x ^= (x >> 12) & ((1 << 64) - 1)
        x ^= (x << 25) & ((1 << 64) - 1)
        x ^= (x >> 27) & ((1 << 64) - 1)
        self._xs = x & ((1 << 64) - 1)
        result = (self._xs * 0x2545F4914F6CDD1D) & ((1 << 64) - 1)
        return result

    def _logistic_iter(self, r: float = 3.9999999) -> int:
        # logistic map: x_{n+1} = r * x_n * (1 - x_n)
        x = self._log
        x = r * x * (1.0 - x)
        # avoid collapse
        if x <= 0.0:
            x = 1e-12
        if x >= 1.0:
            x = 1.0 - 1e-12
        self._log = x
        return int(x * (1 << 64)) & ((1 << 64) - 1)

    def _mix_into_state(self, extra: bytes):
        # Mix bytes into internal states using SHA-256
        h = hashlib.sha256()
        h.update(_int_to_bytes_be(self._xs, 8))
        h.update(struct.pack(">d", float(self._log)))
        h.update(_int_to_bytes_be(self._ctr & ((1 << 64) - 1), 8))
        h.update(extra)
        digest = h.digest()
        # fold to xs
        fold_xs = int.from_bytes(digest[:8], 'big')
        if fold_xs != 0:
            self._xs ^= fold_xs
            self._xs &= ((1 << 64) - 1)
        # fold into logistic state
        v = int.from_bytes(digest[8:16], 'big') / float(1 << 64)
        self._log = 0.5 * (self._log + v)
        # append remainder to buffer for immediate output availability
        self._buf.extend(digest[16:] + digest[:8])

    def _refill_buffer(self):
        # create a block combining several primitives then hash
        parts = bytearray()
        # produce 3 xorshift + logistic pairs for good mixing
        for _ in range(3):
            parts.extend(_int_to_bytes_be(self._xorshift64star(), 8))
            parts.extend(_int_to_bytes_be(self._logistic_iter(), 8))
        parts.extend(_int_to_bytes_be(self._ctr & ((1 << 64) - 1), 8))
        self._ctr += 1
        digest = hashlib.sha256(parts).digest()
        # feed digest back into state
        self._mix_into_state(digest)
        # also put digest into output buffer
        self._buf.extend(digest)

    # -----------------
    # public API
    # -----------------
    def random_uint64(self) -> int:
        """Return 64-bit unsigned integer."""
        if len(self._buf) < 8:
            self._refill_buffer()
        out = int.from_bytes(self._buf[:8], 'big')
        del self._buf[:8]
        return out

    def random(self) -> float:
        """Return float in [0,1)."""
        u = self.random_uint64()
        return u / float(1 << 64)

    def randint(self, a: int, b: int) -> int:
        """Return integer in [a, b] inclusive without modulo bias (rejection)."""
        if a > b:
            raise ValueError("a must be <= b")
        span = b - a + 1
        if span <= 0:
            # span too big for 64-bit; fallback to using random() (less ideal)
            return a + int(self.random() * span)
        # rejection sampling
        lim = (1 << 64) - ((1 << 64) % span)
        while True:
            r = self.random_uint64()
            if r < lim:
                return a + (r % span)

    def random_bytes(self, n: int) -> bytes:
        out = bytearray()
        while n > 0:
            if not self._buf:
                self._refill_buffer()
            take = min(n, len(self._buf))
            out.extend(self._buf[:take])
            del self._buf[:take]
            n -= take
        return bytes(out)

# ---------------------
# Simple tests (educational)
# ---------------------
def _bytes_to_bitstring(b: bytes) -> str:
    return ''.join(f"{byte:08b}" for byte in b)

def monobit_test(bits: str) -> dict:
    n = len(bits)
    ones = bits.count('1')
    return {'n': n, 'ones': ones, 'zeros': n - ones, 'ones_ratio': ones / n if n else None}

def runs_test(bits: str) -> dict:
    if not bits:
        return {}
    runs = []
    cur = bits[0]
    L = 1
    for ch in bits[1:]:
        if ch == cur:
            L += 1
        else:
            runs.append(L)
            cur = ch
            L = 1
    runs.append(L)
    c = Counter(runs)
    return {'total_runs': len(runs), 'run_length_counts': dict(sorted(c.items())[:10])}

def chi_square_bytes(b: bytes) -> float:
    n = len(b)
    if n == 0:
        return 0.0
    cnt = Counter(b)
    exp = n / 256.0
    chi2 = sum(((cnt[i] - exp) ** 2) / exp for i in range(256))
    return chi2

# ---------------------
# CLI / demo
# ---------------------
def demo(prng: HybridChaoticPRNG, count: int = 5):
    print("Demo: 5 uint64 hex values:")
    for _ in range(count):
        print(hex(prng.random_uint64()))
    print("\nDemo: 5 floats [0,1):")
    for _ in range(count):
        print(prng.random())

def run_quick_tests(prng: HybridChaoticPRNG, n_bytes: int = 16384):
    print(f"\nGenerating {n_bytes} bytes for simple tests...")
    b = prng.random_bytes(n_bytes)
    bits = _bytes_to_bitstring(b[:1024])  # analyze first 1024 bytes -> 8192 bits for speed
    m = monobit_test(bits)
    r = runs_test(bits)
    chi2 = chi_square_bytes(b)
    print("Monobit (first 8192 bits):", m)
    print("Runs summary (first 1024 bytes):", r)
    print("Chi-square (256 bins, all bytes):", chi2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HybridChaoticPRNG demo & quick tests")
    parser.add_argument("--seed", type=str, default=None, help="Seed (int or string). If omitted uses OS entropy.")
    parser.add_argument("--test", action="store_true", help="Run quick tests")
    args = parser.parse_args()

    seed_value = None
    if args.seed is not None:
        s = args.seed
        # try int parse
        try:
            if s.startswith("0x") or s.startswith("0X"):
                seed_value = int(s, 16)
            else:
                seed_value = int(s)
        except Exception:
            seed_value = s

    pr = HybridChaoticPRNG(seed=seed_value)
    demo(pr)
    if args.test:
        run_quick_tests(pr, n_bytes=32768)
