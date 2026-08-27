"""
Lead scoring & auto-priority calculation based on website status, rating, and review counts.
"""
from typing import Optional
from app.models import LeadPriority


def calculate_lead_priority(
    has_website: bool,
    rating_avg: Optional[float],
    total_review: int = 0
) -> LeadPriority:
    """
    Business Rules (Bagian 6.3):
    - High priority: has_website is False AND (rating_avg >= 4.0 OR total_review >= 20)
    - Medium priority: has_website is False but rating/review is below the high threshold
    - Low priority: has_website is True
    """
    if has_website:
        return LeadPriority.LOW

    rating = float(rating_avg) if rating_avg is not None else 0.0
    reviews = int(total_review) if total_review is not None else 0

    if rating >= 4.0 or reviews >= 20:
        return LeadPriority.HIGH

    return LeadPriority.MEDIUM
