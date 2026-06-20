import os
import json
import re
from typing import List, Dict
from groq import Groq
from schemas import JiraTicket

class MoscowClassifier:
    def __init__(self):
        # Initialise Groq client; falls back to an environment variable
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model = "llama3-70b-8192"

    def classify_tickets(self, tickets: List[JiraTicket]) -> Dict[str, str]:
        """
        Classifies an array of Jira tickets into MoSCoW tiers.
        Returns a dict mapping ticket_id -> tier.
        """
        classifications = {}
        
        for ticket in tickets:
            prompt = f"""
            You are an elite Agile Project Manager Agent. Classify the following Jira ticket into exactly one of these MoSCoW categories:
            - MUST: Mission critical for the sprint.
            - SHOULD: High priority, but workarounds exist.
            - COULD: Nice to have, zero system dependencies.
            - WONT: Out of scope for this immediate sprint window.

            Ticket ID: {ticket.ticket_id}
            Summary: {ticket.summary}
            Description: {ticket.description}

            Respond strictly in valid JSON format with a single key "tier". Example:
            {{"tier": "MUST"}}
            """
            
            try:
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a deterministic classification engine that outputs only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    model=self.model,
                    response_format={"type": "json_object"},
                    temperature=0.0
                )
                
                raw_response = chat_completion.choices[0].message.content
                data = json.loads(raw_response)
                tier = data.get("tier", "SHOULD").upper()
                
                # Validation fallback
                if tier not in ["MUST", "SHOULD", "COULD", "WONT"]:
                    tier = "SHOULD"
                    
                classifications[ticket.ticket_id] = tier
                
            except Exception as e:
                # Rule-based fallback if API fails or rate limits hit
                print(f"Groq API Error on {ticket.ticket_id}: {e}. Falling back to rules.")
                classifications[ticket.ticket_id] = self._fallback_rule_classifier(ticket)
                
        return classifications

    def _fallback_rule_classifier(self, ticket: JiraTicket) -> str:
        """Fallback heuristics if LLM endpoint fails."""
        combined_text = (ticket.summary + " " + (ticket.description or "")).lower()
        if any(w in combined_text for w in ["blocker", "critical", "must", "broken", "fix"]):
            return "MUST"
        if any(w in combined_text for w in ["nice to have", "could", "maybe"]):
            return "COULD"
        if any(w in combined_text for w in ["defer", "wont", "future", "postpone"]):
            return "WONT"
        return "SHOULD"