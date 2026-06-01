# ArionStrategists — SCML Standard Agent

**Course:** CS 451 / CS 551 Introduction to AI (Spring 2026)  
**Team:** Muhammad Raees Azam (S050683), Mehak Arshid (S050293)  
**Competition:** [ANAC 2026](https://anac.cs.brown.edu/anac) SCML Standard track

Factory negotiation agent built on top of `SyncRandomStdAgent` from the SCML library.  
We add partner price memory, utility-aware bundle acceptance, and several strategy modes; the submitted class is **`ArionAgent`** (default strategy: `game`).

## Repository layout

```
ArionStrategists/
├── README.md
├── requirements.txt
├── arion_strategists/
│   ├── arion_agent.py          # main agent (ANAC submission class)
│   ├── experiments/            # benchmark CSV outputs
│   └── helpers/
│       ├── runner.py           # run / benchmark / compare strategies
│       └── preflight.py        # compile check + ANAC zip builder
└── docs/
    └── REPORT.md               # pointer to LaTeX report
```

## Setup

Requires Python 3.10+.

**Recommended (fastest on this machine):** use the course virtual environment already under `scml_resources\std_local\.venv`.

```powershell
cd "c:\OZU-MS\Introduction to AI\Project\ArionStrategists"
& "c:\OZU-MS\Introduction to AI\Project\scml_resources\std_local\.venv\Scripts\Activate.ps1"
pip install -r requirements.txt
```

**Or** create a local venv in this folder:

```powershell
cd ArionStrategists
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The same `arion_strategists` code is also copied to  
`scml_resources\std_local\arion_strategists\` for the original course layout.

## Quick test

From the `ArionStrategists` folder (do **not** press Ctrl+C while waiting):

```powershell
# Option A — helper script (picks course venv if present)
.\scripts\run_smoke.ps1

# Option B — manual
python -m arion_strategists.helpers.runner smoke-all 5 1
python -m arion_strategists.arion_agent std
```

### First run is slow (important)

The first time Python loads `scml` / `negmas`, **scipy can take 1–2 minutes** to import on Windows (especially with the Microsoft Store Python). That is normal. Wait until you see `=== ArionAgent strategy smoke tests ===` — do not interrupt with Ctrl+C.

If you already installed packages with Store `python` but runs feel stuck, switch to the course venv (commands above) or run from `std_local`:

```powershell
cd "c:\OZU-MS\Introduction to AI\Project\scml_resources\std_local"
.\.venv\Scripts\Activate.ps1
python -m arion_strategists.helpers.runner smoke-all 5 1
```

## Benchmarks

```powershell
python -m arion_strategists.helpers.runner compare-strategies 15 2
python -m arion_strategists.helpers.preflight
```

Results are saved under `arion_strategists/experiments/`.

## ANAC submission

Upload the zip produced by preflight: `ArionStrategists_ArionAgent.zip`  
(contains only `arion_agent.py`, `helpers/runner.py`, `requirements.txt`, and `__init__.py` files).

## Strategies

| Key | Description |
|-----|-------------|
| `baseline` | Greedy / small exhaustive bundles + memory |
| `optimize` | Lexicographic subset scoring |
| `search` | Beam search over bundles |
| `game` | Baseline bundles + Nash-style counter prices (**default**) |
| `hybrid` | Search bundles + game anchors + urgent salvage |

Set `ARION_STRATEGY=search` in the environment to override at runtime.

## Acknowledgments

- Base planner: `SyncRandomStdAgent` (SCML / NegMAS course distribution).
- Ideas from game theory and search/optimization literature (see project report).
- LLMs were used for writing feedback and implementation guidance; all submitted code was reviewed by the authors (see report Section 9).

## Report

LaTeX project report: `../ArionAgent_Report_Complete/` (or `ArionAgent_Report_Complete_Overleaf.zip` in the parent folder).
