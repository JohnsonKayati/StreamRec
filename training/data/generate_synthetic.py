"""
training/data/generate_synthetic.py

Generates realistic synthetic e-commerce interaction data.

Design choices:
  - Power-law item popularity (most items are rarely seen — mimics real retail)
  - Per-user taste profiles (each user prefers 1–3 categories)
  - Session structure (view → view → sometimes cart → sometimes purchase)
  - Temporal decay (recent events weighted more in training)

Run:
    python -m training.data.generate_synthetic --users 1000 --items 500 --events 100000
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import numpy as np
import psycopg2

CATEGORIES = [
    "Electronics", "Books", "Clothing", "Home & Kitchen",
    "Sports", "Toys", "Beauty", "Automotive", "Music", "Movies",
]
SUBCATEGORIES = {
    "Electronics": ["Phones", "Laptops", "Headphones", "Cameras", "Tablets"],
    "Books": ["Fiction", "Science", "History", "Technology", "Self-Help"],
    "Clothing": ["Men", "Women", "Kids", "Shoes", "Accessories"],
    "Home & Kitchen": ["Cookware", "Furniture", "Decor", "Appliances", "Bedding"],
    "Sports": ["Running", "Cycling", "Swimming", "Team Sports", "Fitness"],
    "Toys": ["Action Figures", "Board Games", "LEGO", "Educational", "Outdoor"],
    "Beauty": ["Skincare", "Makeup", "Hair", "Fragrance", "Tools"],
    "Automotive": ["Parts", "Accessories", "Tools", "Electronics", "Care"],
    "Music": ["Instruments", "Equipment", "Accessories", "Vinyl", "Sheet Music"],
    "Movies": ["Action", "Comedy", "Drama", "Sci-Fi", "Documentary"],
}

ADJECTIVES = ["Premium", "Classic", "Ultra", "Pro", "Deluxe", "Essential", "Smart", "Elite"]
PRODUCT_WORDS = ["Gadget", "Device", "Kit", "Bundle", "Set", "Pack", "Edition", "Series"]


class SyntheticItem(NamedTuple):
    item_id: str
    title: str
    category: str
    subcategory: str
    price: float
    avg_rating: float
    review_count: int
    tags: list[str]


class SyntheticUser(NamedTuple):
    user_id: str
    preferred_categories: list[str]


def generate_items(n_items: int, seed: int = 42) -> list[SyntheticItem]:
    """Generate n_items with realistic attributes and power-law price distribution."""
    rng = random.Random(seed)
    items = []
    for i in range(n_items):
        cat = rng.choice(CATEGORIES)
        subcat = rng.choice(SUBCATEGORIES[cat])
        adj = rng.choice(ADJECTIVES)
        noun = rng.choice(PRODUCT_WORDS)
        items.append(SyntheticItem(
            item_id=f"item_{i:04d}",
            title=f"{adj} {subcat} {noun} {i}",
            category=cat,
            subcategory=subcat,
            price=round(rng.lognormvariate(3.5, 1.0), 2),   # log-normal ~ $5–$500
            avg_rating=round(rng.gauss(4.0, 0.5), 1),
            review_count=int(rng.lognormvariate(4.0, 1.5)),  # power law reviews
            tags=[subcat.lower(), cat.lower(), adj.lower()],
        ))
    return items


def generate_users(n_users: int, seed: int = 42) -> list[SyntheticUser]:
    """Generate users, each with 1–3 category preferences."""
    rng = random.Random(seed)
    users = []
    for i in range(n_users):
        n_prefs = rng.randint(1, 3)
        prefs = rng.sample(CATEGORIES, n_prefs)
        users.append(SyntheticUser(user_id=f"user_{i:04d}", preferred_categories=prefs))
    return users


def _item_popularity_weights(items: list[SyntheticItem]) -> np.ndarray:
    """
    Power-law popularity distribution: item rank r gets weight 1/r^alpha.
    This mimics real retail where a few items get most traffic.
    """
    alpha = 1.2
    weights = np.array([1.0 / ((i + 1) ** alpha) for i in range(len(items))])
    return weights / weights.sum()


def simulate_sessions(
    users: list[SyntheticUser],
    items: list[SyntheticItem],
    n_events: int,
    seed: int = 42,
) -> list[dict]:
    """
    Simulate user sessions producing events.

    Session structure:
      1. User selects 1–5 items to view (biased toward their category prefs)
      2. With 20% prob, one item gets add_to_cart
      3. With 40% prob of cart, item gets purchased
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    # Global popularity weights
    global_weights = _item_popularity_weights(items)

    # Category → item index map
    cat_to_indices: dict[str, list[int]] = {}
    for idx, item in enumerate(items):
        cat_to_indices.setdefault(item.category, []).append(idx)

    events = []
    start_time = datetime.now(timezone.utc) - timedelta(days=90)
    event_id_counter = 0

    while len(events) < n_events:
        user = rng.choice(users)
        session_id = f"sess_{event_id_counter:07d}"
        session_start = start_time + timedelta(
            seconds=rng.randint(0, 90 * 24 * 3600)
        )

        # Build item weights for this user (preference boost)
        weights = global_weights.copy()
        for cat in user.preferred_categories:
            for idx in cat_to_indices.get(cat, []):
                weights[idx] *= 3.0
        weights /= weights.sum()

        # Select 1–8 items to view in this session
        n_views = rng.randint(1, 8)
        viewed_indices = np_rng.choice(len(items), size=n_views, replace=False, p=weights)

        for offset, item_idx in enumerate(viewed_indices):
            item = items[item_idx]
            ts = session_start + timedelta(seconds=offset * rng.randint(10, 120))

            # product_view event
            events.append({
                "user_id": user.user_id,
                "event_type": "product_view",
                "item_id": item.item_id,
                "session_id": session_id,
                "timestamp": ts.isoformat(),
            })
            event_id_counter += 1

            # Maybe add to cart
            if rng.random() < 0.20:
                ts += timedelta(seconds=rng.randint(5, 60))
                events.append({
                    "user_id": user.user_id,
                    "event_type": "add_to_cart",
                    "item_id": item.item_id,
                    "session_id": session_id,
                    "timestamp": ts.isoformat(),
                })
                event_id_counter += 1

                # Maybe purchase
                if rng.random() < 0.40:
                    ts += timedelta(seconds=rng.randint(10, 300))
                    events.append({
                        "user_id": user.user_id,
                        "event_type": "purchase",
                        "item_id": item.item_id,
                        "session_id": session_id,
                        "timestamp": ts.isoformat(),
                    })
                    event_id_counter += 1

            if len(events) >= n_events:
                break

    # Sort by timestamp for realistic ordering
    events.sort(key=lambda e: e["timestamp"])
    return events[:n_events]


def write_to_postgres(
    items: list[SyntheticItem],
    users: list[SyntheticUser],
    events: list[dict],
    database_url: str,
) -> None:
    """Write all synthetic data to PostgreSQL (for training / feature pipeline)."""
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            # Items
            print(f"Inserting {len(items)} items...")
            for item in items:
                cur.execute(
                    """
                    INSERT INTO items (item_id, title, category, subcategory, price, avg_rating, review_count, tags)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO NOTHING
                    """,
                    (item.item_id, item.title, item.category, item.subcategory,
                     item.price, item.avg_rating, item.review_count, item.tags),
                )

            # Users
            print(f"Inserting {len(users)} users...")
            for user in users:
                cur.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (user.user_id,),
                )

            # Events (batched for performance)
            print(f"Inserting {len(events)} events...")
            batch_size = 500
            for i in range(0, len(events), batch_size):
                batch = events[i: i + batch_size]
                args = [
                    (
                        e["user_id"], e["event_type"], e.get("item_id"),
                        e.get("session_id"), e.get("query"),
                        e.get("rating"), json.dumps({}), e["timestamp"]
                    )
                    for e in batch
                ]
                cur.executemany(
                    """
                    INSERT INTO events
                        (user_id, event_type, item_id, session_id, query, rating, metadata, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    args,
                )

        conn.commit()
        print("Done — data written to PostgreSQL.")
    finally:
        conn.close()


def save_to_json(
    items: list[SyntheticItem],
    users: list[SyntheticUser],
    events: list[dict],
    output_dir: Path,
) -> None:
    """Save data to JSON files (fallback when PostgreSQL is not running)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "items.json", "w") as f:
        json.dump([item._asdict() for item in items], f, indent=2)

    with open(output_dir / "users.json", "w") as f:
        json.dump([user._asdict() for user in users], f, indent=2)

    with open(output_dir / "events.json", "w") as f:
        json.dump(events, f, indent=2)

    print(f"Saved to {output_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic StreamRec data")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--items", type=int, default=500)
    parser.add_argument("--events", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="data/synthetic")
    parser.add_argument("--db-url", type=str, default=None,
                        help="PostgreSQL URL. If omitted, saves to JSON files.")
    args = parser.parse_args()

    print(f"Generating {args.users} users, {args.items} items, {args.events} events...")
    users = generate_users(args.users, args.seed)
    items = generate_items(args.items, args.seed)
    events = simulate_sessions(users, items, args.events, args.seed)
    print(f"Generated {len(events)} events across {len(set(e['user_id'] for e in events))} users.")

    if args.db_url:
        write_to_postgres(items, users, events, args.db_url)
    else:
        save_to_json(items, users, events, Path(args.output_dir))


if __name__ == "__main__":
    main()
