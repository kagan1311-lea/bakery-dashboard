# Bakery Sales Dashboard

A one-page sales dashboard for a small bakery (Streamlit + Postgres on Railway) with a small "ask a question" box powered by Claude. Data: mock transactions with Hebrew product names, built by `mock_data.py` from Kaggle's daily bakery revenue and weather files (`data/raw/`).

## Read first

| File | Part | What it holds |
|---|---|---|
| [spec.md](spec.md) | 1 · Design | users, jobs, not-in-v1, speed, data, limits, done checks |
| [architecture.md](architecture.md) | 1 + 2 · Design, Place | components, flows, storage, model, limits, hosting, secrets, decisions |
| [practice.md](practice.md) | 3 · Manage | the 8 steps per ticket, board, never-list |
| [tickets.md](tickets.md) | 3 · Manage | Issue drafts from spec.md |
| `tests/`, `evals/` | 4 · Test/Eval | pytest with the model mocked; 10 eval cases + history |

## Run locally

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in the values
python mock_data.py         # data/raw/*.csv -> data/sales.csv, data/weather.csv
python load_data.py
streamlit run app.py
```

## Tests and evals

```bash
pytest
python evals/run_evals.py --runs 3   # real model + real data, < $0.01; score saved to evals/history.csv
```

Run the evals before and after any change to the prompt, the tool or the model, and paste the score in the PR (practice.md step 5).

## Branches

`main` is protected. Every change comes from an Issue, gets its own branch (`<issue#>-<name>`) and is merged through a PR. See [practice.md](practice.md).
