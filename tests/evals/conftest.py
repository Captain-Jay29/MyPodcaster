"""Fixtures for evaluation tests."""

import pytest

EVAL_ARTICLES = [
    {
        "hn_id": "sample1",
        "title": "Show HN: I built a database in Rust that's 10x faster than SQLite",
        "url": "https://example.com/rust-db",
        "content": (
            "RustDB is a new embedded database written entirely in Rust. "
            "In benchmarks, it achieves 10x the throughput of SQLite for write-heavy workloads. "
            "The project is open-sourced under the MIT license. "
            "It uses a log-structured merge tree (LSM) storage engine."
        ),
        "points": 342,
        "expected_key_points": [
            "New database written in Rust",
            "10x throughput vs SQLite for writes",
            "Open-sourced under MIT license",
        ],
    },
]


@pytest.fixture
def eval_articles():
    return EVAL_ARTICLES
