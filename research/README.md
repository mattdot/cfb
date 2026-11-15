# Line-prediction research

This folder is separate from the published site. It tests how well the ratings predict what Vegas posts, and it builds a results-aware **line predictor**. The predictor can carry the final week's games into a final ranking when no later line exists.

- `collect_history.py` pulls the 2021–2025 seasons from ESPN into `data/season-YYYY.json`: regular season including conference championships, plus College Football Playoff games. Other bowls are excluded on purpose, because opt-outs mean the teams aren't the ones that played the season.
- `backtest.py` tunes and scores both models. `results.txt` is its latest output.

```
python research/collect_history.py --cache /tmp/espn   # about 2 minutes; the cache makes reruns instant
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
| 2021 | 538 | 4.80 | 3.02 |
| 2022 | 540 | 4.74 | 3.39 |
| 2023 | 547 | 4.48 | 3.34 |
| 2024 | 566 | 4.81 | 3.43 |
| 2025 | 577 | 4.49 | 3.00 |
| 2026 holdout | 485 | 4.63 | 3.31 |

The predictor is better in every season, with paired t between 8.5 and 11.7. It also beats VPI on cross-conference games and on games right after a bye. Calibration slopes are 0.95–0.99 for both models.

**End of season**

| Freeze | Games | VPI | Predictor | Paired t |
|---|---|---|---|---|
| Before championship week, predict championship lines | 48 | 3.23 | 2.62 | 1.7 |
| Selection day, predict playoff lines | 31 | 3.64 | 2.87 | 1.8 |

On playoff games, win-probability Brier scores are 0.192 for VPI, 0.176 for the predictor and 0.173 for the closing line itself. Brier on 31–48 games has a standard error of about 0.02–0.025, so treat it only as a sanity check.

## Against the bar we set

1. **Clearly better than VPI-as-is in every season:** met, including the 2026 holdout.
2. **No systematic lean on cross-conference or post-bye games:** met relative to VPI. Post-bye errors are still somewhat higher than average for both models, as expected.
3. **End-of-season accuracy in line with in-season accuracy:** met. Playoff-line error (2.87) is below the typical weekly error (3.0–3.4). With only 31 and 48 games, the end-of-season gains are suggestive (t ≈ 1.7–1.8), not conclusive.

## What it means for the final ranking

At selection day, the predictor's power ranking differs from market-only VPI by 2.3–4.5 places on average in the top 25. The big moves are late-season collapses and surges that no later line ever priced. For example, 2022 North Carolina lost its last four games, including the ACC title game, and goes from #22 to #44.

The predictor uses results all season, not only in the last week. So a final ranking taken from it would differ from the last in-season VPI by that amount, even though both are measured against the same lines. Options to decide before wiring it into the site:

- Publish the predictor all season next to VPI (for example as "projected lines"), so the final ranking isn't a surprise.
- Use the predictor only for the final post-season ranking, labeled as including projected results.

## Caveats

- 2021–2023 lines come from ESPN's per-book `spread` field (mostly the consensus book). ESPN doesn't document whether that's the opening or closing number. 2024–2025 use explicit closing spreads. The results look alike across both eras, but the early seasons may be scoring "predict the line" against a slightly different target.
- ESPN stored prices (−110) in the closing-spread field for some 2022–2023 books. Both collectors now reject values of 75 or more.
- The predictor's optimum is a flat plateau: drift SD 1–1.4 points and result SD 4.5–5 points all score 3.23–3.24. The chosen point sits at the edge of the grid, but nearby settings are equivalent.
- The predictor gives a final score roughly half the weight of a closing line. It reproduces how strongly the market reacts to results. That's the right target for predicting Vegas, but it isn't a claim about true team strength.
