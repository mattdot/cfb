# Vegas SOR
[Weekly rankings](https://mattdot.github.io/cfb/) · [Methodology](https://mattdot.github.io/cfb/methodology.html)

2026 FBS strength of record derived from closing spreads and game results. AP and CFP rankings are dated display references. The model receives neither poll.

Run `python -m http.server --directory docs` to preview. To regenerate the weekly tables from the committed inputs, install NumPy and run `python scripts/build.py`. To refresh completed games and polls first, run `python scripts/collect.py`. Python 3.11+ is required. Each generated snapshot uses only results and lines through its date.

The published site is the contents of `docs/`. The Pages workflow deploys on pushes to main and refreshes the current season weekly.
