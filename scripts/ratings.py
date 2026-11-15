"""Week-by-week random-walk team ratings fitted to closing point spreads.

Each FBS team starts a week at its previous estimate, give or take a weekly
drift. Each spread observes home rating - away rating + home field with
noise. A Kalman filter combines the two, so a rating holds its last value
when no new line involves the team instead of sliding toward the average.
Conference membership is never used.
"""
import numpy as np

LINE_NOISE = 3.2 ** 2     # variance of a closing spread around the rating difference
WEEKLY_DRIFT = 4.0        # variance added to every FBS rating each week
HOME_FIELD = 2.5          # prior home-field advantage in points
FBS_PRIOR = LINE_NOISE / 0.1      # preseason uncertainty of an FBS rating
FCS_SPREAD = LINE_NOISE / 2       # FCS teams vary around a shared FCS rating
FCS_BASE_PRIOR = LINE_NOISE / 0.001
HOME_FIELD_PRIOR = LINE_NOISE


class State:
    """Mean and covariance of every rating, plus the FCS baseline and home field."""

    def __init__(self, teams):
        self.ids = sorted(teams)
        self.index = {team: i for i, team in enumerate(self.ids)}
        self.fbs = np.array([bool(teams[t]['fbs']) for t in self.ids])
        n = len(self.ids)
        self.mean = np.zeros(n + 2)
        self.mean[-1] = HOME_FIELD
        self.cov = np.diag(np.concatenate([np.where(self.fbs, FBS_PRIOR, FCS_SPREAD),
                                           [FCS_BASE_PRIOR, HOME_FIELD_PRIOR]]))

    def copy(self):
        other = object.__new__(State)
        other.ids, other.index, other.fbs = self.ids, self.index, self.fbs
        other.mean, other.cov = self.mean.copy(), self.cov.copy()
        return other

    def drift(self, variance=WEEKLY_DRIFT):
        rows = np.flatnonzero(self.fbs)
        self.cov[rows, rows] += variance

    def design(self, games):
        h = np.zeros((len(games), len(self.mean)))
        fbs = self.fbs
        for row, g in enumerate(games):
            home, away = self.index[g['home']], self.index[g['away']]
            h[row, home] += 1
            h[row, away] -= 1
            h[row, -2] = int(not fbs[home]) - int(not fbs[away])
            h[row, -1] = int(not g['neutral'])
        return h

    def observe(self, games, values, noise):
        """Kalman update from observed home margins (spreads or results)."""
        if not games:
            return
        h = self.design(games)
        innovation = np.asarray(values, dtype=float) - h @ self.mean
        ph = self.cov @ h.T
        gain = np.linalg.solve(h @ ph + noise * np.eye(len(games)), ph.T).T
        self.mean = self.mean + gain @ innovation
        self.cov = self.cov - gain @ ph.T
        self.cov = (self.cov + self.cov.T) / 2

    def predict(self, game):
        return float(self.design([game])[0] @ self.mean)

    def ratings(self):
        """Point rating per team (FCS teams include the shared FCS rating) and home field."""
        base = self.mean[-2]
        values = {t: float(self.mean[i] + (0 if self.fbs[i] else base)) for t, i in self.index.items()}
        return values, float(self.mean[-1])


def run(lines, teams, through_week, drift=WEEKLY_DRIFT):
    """Filter every line with week <= through_week, one week at a time."""
    state = State(teams)
    for week in range(1, through_week + 1):
        if week > 1:
            state.drift(drift)
        batch = [g for g in lines if g['week'] == week]
        state.observe(batch, [g['margin'] for g in batch], LINE_NOISE)
    return state
