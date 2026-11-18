"""Oddiy ball tizimiga asoslangan matching (0-100)."""
from difflib import SequenceMatcher

from django.conf import settings

from .models import Listing, Match


def score_pair(lost, found):
    reasons = {}

    reasons["category"] = 30 if lost.category_id == found.category_id else 0

    same_color = lost.color and found.color and lost.color.strip().lower() == found.color.strip().lower()
    reasons["color"] = 15 if same_color else 0

    same_place = lost.location_id and lost.location_id == found.location_id
    reasons["location"] = 20 if same_place else 0

    days = abs((lost.event_date - found.event_date).days)
    reasons["date"] = 15 if days <= 3 else 8 if days <= 7 else 0

    sim = SequenceMatcher(None, lost.title.strip().lower(), found.title.strip().lower()).ratio()
    reasons["title"] = round(sim * 20, 1)

    return round(sum(reasons.values()), 2), reasons


def run_matching(listing):
    """Faol e'lon uchun qarama-qarshi turdagi faol e'lonlar bilan moslikni hisoblaydi."""
    if listing.status != Listing.Status.ACTIVE:
        return 0

    opposite = Listing.Type.FOUND if listing.type == Listing.Type.LOST else Listing.Type.LOST
    candidates = (
        Listing.objects.filter(type=opposite, status=Listing.Status.ACTIVE, category_id=listing.category_id)
        .exclude(user_id=listing.user_id)
    )

    created = 0
    for other in candidates:
        lost, found = (listing, other) if listing.type == Listing.Type.LOST else (other, listing)
        score, reasons = score_pair(lost, found)
        if score >= settings.FINDIT_MATCH_MIN_SCORE:
            Match.objects.update_or_create(
                lost_listing=lost, found_listing=found,
                defaults={"score": score, "reasons": reasons},
            )
            created += 1
    return created
