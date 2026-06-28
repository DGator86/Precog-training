#!/usr/bin/env python3
"""
Atemporal ESP Trainer

Local command-line protocol for precognition / atemporal ESP practice.

Protocol:
1. Start a new trial. No target is chosen yet.
2. You enter your perception/guess and lock it in.
3. Only at reveal time does the program generate the target, using fresh
   randomness drawn *after* your guess was locked.
4. Results are logged and scored against chance.

Because the target does not exist until reveal, there is nothing to peek at
in the database while a trial is open. This keeps the protocol genuinely
blind (and genuinely atemporal: the guess precedes the target).

Run:
    python esp_trainer.py            # show help
    python esp_trainer.py new        # start a blinded trial
    python esp_trainer.py guess      # lock your perception
    python esp_trainer.py reveal     # generate + reveal the target
    python esp_trainer.py stats      # hit rate and p-value
    python esp_trainer.py export out.json

Use --db PATH to point at an alternate database file.
"""

import argparse
import json
import math
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("esp_trials.db")

TARGETS = [
    "circle",
    "square",
    "triangle",
    "star",
    "cross",
    "spiral",
    "crescent",
    "diamond",
    "hexagon",
    "wavy line",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    # Treat naive timestamps as UTC so comparisons never raise.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            reveal_after TEXT NOT NULL,
            target TEXT,
            guess TEXT,
            guess_at TEXT,
            revealed_at TEXT,
            hit INTEGER
        )
    """)
    conn.commit()
    return conn


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


NORMALIZED_TARGETS = {normalize(t) for t in TARGETS}


def new_trial(db_path, hours_until_reveal: float = 24.0) -> int | None:
    if hours_until_reveal < 0:
        print("--hours must be zero or positive.")
        return None

    created = now_utc()
    reveal_after = created + timedelta(hours=hours_until_reveal)

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO trials (created_at, reveal_after)
            VALUES (?, ?)
            """,
            (iso(created), iso(reveal_after)),
        )
        trial_id = cur.lastrowid
        conn.commit()

    print(f"New trial #{trial_id} created.")
    print(f"Target pool size: {len(TARGETS)}")
    print(f"Reveal allowed after: {iso(reveal_after)}")
    print("The target does not exist yet; it is generated at reveal time.")
    print("Next: run `python esp_trainer.py guess`")
    return trial_id


def get_open_trial(conn):
    row = conn.execute(
        """
        SELECT id, created_at, reveal_after, target, guess, guess_at, revealed_at, hit
        FROM trials
        WHERE revealed_at IS NULL
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return row


def enter_guess(db_path, guess_text: str | None = None) -> None:
    with connect(db_path) as conn:
        row = get_open_trial(conn)
        if not row:
            print("No open trial found. Run `python esp_trainer.py new` first.")
            return

        trial_id, created_at, reveal_after, target, guess, guess_at, revealed_at, hit = row

        if guess is not None:
            print(f"Trial #{trial_id} already has a locked guess: {guess!r}")
            print("You cannot edit it. That protects the protocol.")
            return

        print(f"Trial #{trial_id}")
        print(f"Target options: {', '.join(TARGETS)}")

        if guess_text is None:
            guess_text = input("Enter your guess/perception: ")
        user_guess = normalize(guess_text)

        if not user_guess:
            print("Empty guess rejected.")
            return

        if user_guess not in NORMALIZED_TARGETS:
            print(f"Note: {user_guess!r} is not one of the target symbols.")
            print("It will be recorded, but it can never score a hit.")

        conn.execute(
            """
            UPDATE trials
            SET guess = ?, guess_at = ?
            WHERE id = ?
            """,
            (user_guess, iso(now_utc()), trial_id),
        )
        conn.commit()

        print(f"Guess locked for trial #{trial_id}: {user_guess!r}")
        print(f"Reveal allowed after: {reveal_after}")


def reveal(db_path, force: bool = False) -> None:
    with connect(db_path) as conn:
        row = get_open_trial(conn)
        if not row:
            print("No open trial found.")
            return

        trial_id, created_at, reveal_after, target, guess, guess_at, revealed_at, hit = row

        if guess is None:
            print("No guess has been locked yet. Run `python esp_trainer.py guess` first.")
            return

        reveal_time = parse_iso(reveal_after)
        current = now_utc()

        if current < reveal_time and not force:
            remaining = reveal_time - current
            print(f"Too early to reveal trial #{trial_id}.")
            print(f"Reveal allowed after: {reveal_after}")
            print(f"Time remaining: {remaining}")
            print("For testing only, you can use: python esp_trainer.py reveal --force")
            return

        # The target is generated now, with fresh randomness drawn after the
        # guess was locked. This is the atemporal part of the protocol.
        target = secrets.choice(TARGETS)
        hit = int(normalize(guess) == normalize(target))

        conn.execute(
            """
            UPDATE trials
            SET target = ?, revealed_at = ?, hit = ?
            WHERE id = ?
            """,
            (target, iso(current), hit, trial_id),
        )
        conn.commit()

        print(f"Trial #{trial_id} revealed.")
        print(f"Your guess: {guess}")
        print(f"Target:     {target}")
        print("Result:    HIT" if hit else "Result:    MISS")


def binomial_tail(k: int, n: int, p: float) -> float:
    """
    P(X >= k) for X~Binomial(n, p), using direct summation.
    Fine for normal personal trial counts.
    """
    if n <= 0:
        return float("nan")
    k = max(k, 0)
    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return total


def stats(db_path, recent: int = 10) -> None:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, reveal_after, target, guess, guess_at, revealed_at, hit
            FROM trials
            WHERE revealed_at IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    n = len(rows)
    hits = sum((r[7] or 0) for r in rows)

    print("Atemporal ESP Trainer Stats")
    print("---------------------------")
    print(f"Completed trials: {n}")
    print(f"Hits:             {hits}")

    if n == 0:
        print("No completed trials yet.")
        return

    chance = 1 / len(TARGETS)
    hit_rate = hits / n
    expected = n * chance
    p_value = binomial_tail(hits, n, chance)

    print(f"Target pool size: {len(TARGETS)}")
    print(f"Chance rate:      {chance:.2%}")
    print(f"Your hit rate:    {hit_rate:.2%}")
    print(f"Expected hits:    {expected:.2f}")
    print(f"Binomial p-value: {p_value:.6f}")

    if p_value < 0.05 and hits > expected:
        print("Interpretation: above-chance result by conventional p<0.05 threshold.")
        print("Caution: replicate before taking it seriously.")
    else:
        print("Interpretation: not enough evidence of above-chance performance yet.")

    if recent > 0:
        print(f"\nRecent completed trials (last {recent}):")
        for r in rows[-recent:]:
            trial_id, created_at, reveal_after, target, guess, guess_at, revealed_at, hit = r
            result = "HIT" if hit else "MISS"
            print(f"#{trial_id}: {result} | guess={guess!r} | target={target!r}")


def export_json(db_path, path: str) -> None:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, reveal_after, target, guess, guess_at, revealed_at, hit
            FROM trials
            ORDER BY id
            """
        ).fetchall()

    data = []
    for r in rows:
        data.append({
            "id": r[0],
            "created_at": r[1],
            "reveal_after": r[2],
            "target": r[3],
            "guess": r[4],
            "guess_at": r[5],
            "revealed_at": r[6],
            "hit": r[7],
        })

    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Exported {len(data)} trials to {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atemporal ESP training protocol")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to the trials database (default: {DEFAULT_DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="Create a new blinded trial")
    p_new.add_argument("--hours", type=float, default=24.0, help="Hours until reveal is allowed")

    sub.add_parser("guess", help="Enter and lock your guess")

    p_reveal = sub.add_parser("reveal", help="Generate and reveal the target after reveal time")
    p_reveal.add_argument("--force", action="store_true", help="Force reveal early for testing")

    p_stats = sub.add_parser("stats", help="Show hit rate and p-value")
    p_stats.add_argument("--recent", type=int, default=10, help="How many recent trials to list")

    p_export = sub.add_parser("export", help="Export all trials to JSON")
    p_export.add_argument("path", help="Output JSON path")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = args.db

    if args.command == "new":
        new_trial(db_path, args.hours)
    elif args.command == "guess":
        enter_guess(db_path)
    elif args.command == "reveal":
        reveal(db_path, args.force)
    elif args.command == "stats":
        stats(db_path, args.recent)
    elif args.command == "export":
        export_json(db_path, args.path)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
