from storage.json_store import JSONStore
from models.journal import ReviewResult
from config.settings import settings


class MemoryBank:
    MAX_RECENT_REVIEWS = 50

    def __init__(self):
        self.store = JSONStore(settings.MEMORY_DIR)

    def get_dm_feedback(self) -> dict:
        """Return aggregated stats for the Decision Maker."""
        return self.store.load_or_default("dm_feedback.json", {
            "total_trades": 0,
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "avg_best_pnl": 0.0,
            "recent_reviews": [],
        })

    def get_rm_feedback(self) -> dict:
        """Return aggregated stats for the Risk Manager."""
        return self.store.load_or_default("rm_feedback.json", {
            "total_trades": 0,
            "stops_hit": 0,
            "stop_hit_rate": 0.0,
            "avg_worst_pnl": 0.0,
            "recent_reviews": [],
        })

    def update_dm_feedback(self, reviews: list[ReviewResult]):
        """Aggregate review results into DM learning stats."""
        existing = self.get_dm_feedback()
        for r in reviews:
            existing["total_trades"] += 1
            if r.target_hit:
                existing["hits"] += 1
            else:
                existing["misses"] += 1
            existing["recent_reviews"].append(r.model_dump())

        existing["recent_reviews"] = existing["recent_reviews"][-self.MAX_RECENT_REVIEWS:]
        existing["hit_rate"] = existing["hits"] / max(existing["total_trades"], 1)
        if reviews:
            existing["avg_best_pnl"] = sum(
                r.best_pnl_pct for r in reviews
            ) / len(reviews)
        self.store.save("dm_feedback.json", existing)

    def update_rm_feedback(self, reviews: list[ReviewResult]):
        """Aggregate review results for the Risk Manager."""
        existing = self.get_rm_feedback()
        for r in reviews:
            existing["total_trades"] += 1
            if r.stop_hit:
                existing["stops_hit"] += 1
            existing["recent_reviews"].append(r.model_dump())

        existing["recent_reviews"] = existing["recent_reviews"][-self.MAX_RECENT_REVIEWS:]
        existing["stop_hit_rate"] = existing["stops_hit"] / max(existing["total_trades"], 1)
        if reviews:
            existing["avg_worst_pnl"] = sum(
                r.worst_pnl_pct for r in reviews
            ) / len(reviews)
        self.store.save("rm_feedback.json", existing)
