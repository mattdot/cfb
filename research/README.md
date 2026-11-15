# Line-prediction research

This folder is separate from the published site. It tests how well the ratings predict what Vegas posts, and it builds a results-aware **line predictor**. The predictor can carry the final week's games into a final ranking when no later line exists.

- `collect_history.py` pulls the 2021–2025 seasons from ESPN and CollegeFootballData into `data/season-YYYY.json`: regular season including conference championships, plus College Football Playoff games. Other bowls are excluded on purpose, because opt-outs mean the teams aren't the ones that played the season. Lines prefer DraftKings closing spreads, the book the live site uses (details under Data).
- `backtest.py` tunes and scores both models. `results.txt` is its latest output.

```
python research/collect_history.py --cache /tmp/cfb-cache   # about 2 minutes; needs a CollegeFootballData key (or --no-cfbd)
python research/backtest.py                             # tune on 2021-25, then report (a few seconds)
```

## Two models, one engine

Both run `scripts/ratings.py`, the same random-walk Kalman filter the live site uses.

| | Sees | Weekly drift | Purpose |
|---|---|---|---|
| **VPI** (live) | closing spreads only | SD 2 pts | the published power index |
| **Predictor** (research) | spreads **and** final scores (score treated as a margin with SD 4.5 pts) | SD 1 pt | forecast the next line; finish the season after the last line |

Settings were chosen on the weekly test for 2021–2025 only. The end-of-season freezes and the 2026 season (through Nov 15) were never used for tuning.

## Results

Line error is root-mean-square points between the prediction and the closing line that was eventually posted.

**Weekly, from Week 5 on, using only earlier weeks**

| Season | Games | VPI | Predictor |
|---|---|---|---|
| 2021 | 538 | 4.79 | 3.02 |
| 2022 | 540 | 4.74 | 3.38 |
| 2023 | 547 | 4.44 | 3.30 |
| 2024 | 568 | 4.75 | 3.35 |
| 2025 | 577 | 4.47 | 2.97 |
| 2026 holdout | 485 | 4.63 | 3.31 |

The predictor is better in every season, with paired t between 8.7 and 11.8. It also beats VPI on cross-conference games and on games right after a bye. Calibration slopes are 0.95–0.99 for both models.

**End of season**

| Freeze | Games | VPI | Predictor | Paired t |
|---|---|---|---|---|
| Before championship week, predict championship lines | 48 | 3.16 | 2.57 | 1.7 |
| Selection day, predict playoff lines | 31 | 3.71 | 3.04 | 1.5 |

On playoff games, win-probability Brier scores are 0.195 for VPI, 0.178 for the predictor and 0.172 for the closing line itself. Brier on 31–48 games has a standard error of about 0.02–0.025, so treat it only as a sanity check.

## Against the bar we set

1. **Clearly better than VPI-as-is in every season:** met, including the 2026 holdout.
2. **No systematic lean on cross-conference or post-bye games:** met relative to VPI. Post-bye errors are still somewhat higher than average for both models, as expected.
3. **End-of-season accuracy in line with in-season accuracy:** met. Playoff-line error (3.04) is within the typical weekly range (3.0–3.4). With only 31 and 48 games, the end-of-season gains are suggestive (t ≈ 1.5–1.7), not conclusive.

The live site now leaves conference championships out of the rankings, so its final ranking is the state after the last regular-season week. The "before championship week" freeze is exactly that situation.

## What it means for the final ranking

At selection day, the predictor's power ranking differs from market-only VPI by 2.4–4.4 places on average in the top 25. The big moves are late-season collapses and surges that no later line ever priced. For example, 2022 North Carolina lost its last four games, including the ACC title game, and goes from #22 to #44.

The predictor uses results all season, not only in the last week. So a final ranking taken from it would differ from the last in-season VPI by that amount, even though both are measured against the same lines. Options to decide before wiring it into the site:

- Publish the predictor all season next to VPI (for example as "projected lines"), so the final ranking isn't a surprise.
- Use the predictor only for the final post-season ranking, labeled as including projected results.

## Data

Line sources, in priority order: DraftKings from ESPN's per-book odds, DraftKings closing spread from CollegeFootballData, ESPN BET, ESPN consensus, then Bovada's closing spread from CollegeFootballData.

| Season | DraftKings | ESPN BET | Other | No line |
|---|---|---|---|---|
| 2021 | 828 | – | 24 | 0 |
| 2022 | 836 | 16 | 3 | 2 |
| 2023 | 863 | 8 | – | 0 |
| 2024 | 777 | 92 | – | 15 |
| 2025 | 770 | 123 | 6 | 0 |

- **2021–2022 timing check.** No source has DraftKings opening and closing lines for these seasons. ESPN's single DraftKings number per game is undocumented, so it was checked against Bovada, which has both. It sits within 0.2–0.45 points of Bovada's close (51–65% exact) and 1.3 points from Bovada's open (17% exact). It also predicts results as well as the closing line does. So it's treated as a closing line.
- **CollegeFootballData's 2023 DraftKings "spread"** sits about a point from every other closing source and predicts results slightly worse, which looks like an earlier snapshot. That's why ESPN's DraftKings number takes priority where both exist.
- **Prices in the spread field.** ESPN stored prices (−110) in the closing-spread field for some 2022–2023 books. Both collectors now reject values of 75 or more.

## Caveats

- The predictor's optimum is a flat plateau: drift SD 1–1.4 points and result SD 4.5–5 points all score 3.23–3.24. The chosen point sits at the edge of the grid, but nearby settings are equivalent.
- The predictor gives a final score roughly half the weight of a closing line. It reproduces how strongly the market reacts to results. That's the right target for predicting Vegas, but it isn't a claim about true team strength.
