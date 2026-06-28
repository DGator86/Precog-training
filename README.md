# Precog Training — Atemporal ESP Trainer

A tiny, dependency-free command-line tool for practicing precognition /
atemporal ESP under a self-honest, blinded protocol. You record a perception
*before* the target exists, and the program scores your hit rate against
chance with a binomial test.

## Why "atemporal"

In a naive ESP trainer the target is chosen up front and stored somewhere,
so the answer already exists while you guess — and it can be peeked at. This
trainer defers target generation to **reveal time**, using fresh randomness
drawn *after* your guess is locked. While a trial is open there is literally
nothing in the database to peek at: the guess genuinely precedes the target.

## Install

No third-party dependencies — Python 3.10+ and the standard library.

```bash
python esp_trainer.py --help
```

## Usage

```bash
# 1. Start a blinded trial (default: reveal allowed after 24h)
python esp_trainer.py new
python esp_trainer.py new --hours 0.5

# 2. Lock in your perception
python esp_trainer.py guess

# 3. After the reveal time, generate + score the target
python esp_trainer.py reveal
python esp_trainer.py reveal --force      # bypass the wait (testing only)

# 4. Review performance
python esp_trainer.py stats
python esp_trainer.py stats --recent 25

# 5. Export the full history
python esp_trainer.py export trials.json
```

Point the tool at a different database with the global `--db` flag:

```bash
python esp_trainer.py --db practice.db new
```

## Target pool

There are 10 symbols: circle, square, triangle, star, cross, spiral,
crescent, diamond, hexagon, wavy line. Chance performance is therefore 10%.

## Scoring

`stats` reports your hit rate, the expected number of hits under chance, and a
one-sided binomial p-value `P(X >= hits)`. A result below `p < 0.05` with
hits above expectation is flagged as above-chance — but a single run proves
nothing. Replicate before drawing conclusions, and remember that running many
sessions and reporting the best one inflates false positives.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The trials database (`*.db`) is git-ignored.
