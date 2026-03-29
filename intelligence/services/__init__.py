# Re-export for backward compatibility with `from intelligence.services import ...`

# Existing (moved in Phase 2)
from .scoring import calculate_relationship_score
from .briefing import generate_dashboard_briefing
from .excel import detect_header_and_map, classify_sheets
from .legacy import analyze_contact_relationship, analyze_sentiments

# New (Phase 3)
from .embedding import build_contact_text, embed_contact, embed_contacts_batch
from .sentiment import classify_sentiment, classify_sentiments_batch
from .task_detect import detect_task, detect_tasks_batch
from .similarity import find_similar_contacts, find_contacts_like
from .orchestration import ensure_embedding, ensure_sentiments_and_tasks, ensure_deep_analysis
from .deep_analysis import generate_summary, generate_insights

__all__ = [
    # Scoring
    "calculate_relationship_score",
    # Briefing
    "generate_dashboard_briefing",
    # Excel
    "detect_header_and_map",
    "classify_sheets",
    # Embedding
    "build_contact_text",
    "embed_contact",
    "embed_contacts_batch",
    # Sentiment
    "classify_sentiment",
    "classify_sentiments_batch",
    # Task detection
    "detect_task",
    "detect_tasks_batch",
    # Similarity
    "find_similar_contacts",
    "find_contacts_like",
    # Orchestration
    "ensure_embedding",
    "ensure_sentiments_and_tasks",
    "ensure_deep_analysis",
    # Deep analysis
    "generate_summary",
    "generate_insights",
    # Legacy (Phase 6 removal)
    "analyze_contact_relationship",
    "analyze_sentiments",
]
