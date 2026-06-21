import re
from typing import Tuple, List, Optional
from groq import Groq

# Initialize Groq client
client = Groq()

# Confidence Keyword Arrays from Design Document
KEYWORDS_FRONTEND = ["ui", "component", "form", "screen", "react", "css", "page", "modal", "layout", "animation"]
KEYWORDS_BACKEND = ["api", "endpoint", "rest", "database", "schema", "migration", "query", "service", "controller"]
KEYWORDS_DEVOPS = ["pipeline", "ci/cd", "docker", "deploy", "infra", "terraform", "kubernetes", "monitoring"]
KEYWORDS_QA = ["test", "testing", "regression", "coverage", "e2e", "cypress", "playwright", "qa", "validation"]
KEYWORDS_ARCH = ["design", "architect", "system design", "adr", "technical spec", "schema design", "data model"]

def rule_based_team_classify(text: str) -> Optional[str]:
    text_lower = text.lower()
    matches = {
        "FRONTEND": sum(1 for kw in KEYWORDS_FRONTEND if re.search(r'\b' + kw + r'\b', text_lower)),
        "BACKEND": sum(1 for kw in KEYWORDS_BACKEND if re.search(r'\b' + kw + r'\b', text_lower)),
        "DEVOPS": sum(1 for kw in KEYWORDS_DEVOPS if re.search(r'\b' + kw + r'\b', text_lower)),
        "QA": sum(1 for kw in KEYWORDS_QA if re.search(r'\b' + kw + r'\b', text_lower)),
        "ARCHITECTURE": sum(1 for kw in KEYWORDS_ARCH if re.search(r'\b' + kw + r'\b', text_lower)),
    }
    
    # Section 2.2 rule: If 2+ keyword signals match, use rule result
    best_match = max(matches, key=matches.get)
    if matches[best_match] >= 2:
        return best_match
    return None

def llm_fallback_classify(title: str, description: str) -> str:
    """Uses Groq (llama-3.3-70b-versatile) to evaluate ambiguous items."""
    prompt = f"""You are an elite Engineering Manager. Classify this engineering subtask into exactly ONE of these teams:
FRONTEND, BACKEND, DEVOPS, QA, ARCHITECTURE.

Task Title: {title}
Description: {description}

Respond with exactly one word (the team name) and nothing else."""
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    result = completion.choices[0].message.content.strip().upper()
    return result if result in ["FRONTEND", "BACKEND", "DEVOPS", "QA", "ARCHITECTURE"] else "BACKEND"

def classify_moscow(title: str, description: str) -> str:
    # Rule fallback directly to LLM context processing for MoSCoW values
    prompt = f"""Classify this subtask into a MoSCoW tier: MUST, SHOULD, COULD, or WON_T.
- MUST: Core flows, data integrity, security, auth, payments. Critical to ship.
- SHOULD: Important UX/feature enhancement, non-breaking if missing.
- COULD: Nice to have.
- WON_T: Completely out of scope.

Task Title: {title}
Description: {description}

Respond with exactly one word (MUST, SHOULD, COULD, or WON_T) and nothing else."""
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    result = completion.choices[0].message.content.strip().upper()
    return "WON'T" if "WON_T" in result else (result if result in ["MUST", "SHOULD", "COULD"] else "SHOULD")