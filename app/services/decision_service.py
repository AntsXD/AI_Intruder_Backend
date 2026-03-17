from app.models.entities import EventStatus


def map_similarity_to_status(similarity_score: float) -> EventStatus:
    if similarity_score > 70:
        return EventStatus.VERIFIED_OWNER
    if similarity_score < 50:
        return EventStatus.VERIFIED_INTRUDER
    return EventStatus.HUMAN_REVIEW
