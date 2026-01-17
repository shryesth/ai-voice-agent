"""
Urgency keyword detector for patient feedback calls.

Scans conversation transcripts for keywords indicating medical emergencies
that require immediate clinical review.
"""

from typing import List, Set
import re


class UrgencyDetector:
    """
    Detects urgency keywords in patient responses.

    Urgency keywords indicate potential medical emergencies that need
    immediate clinical attention:
    - Severe symptoms: severe pain, can't breathe, chest pain, bleeding
    - Emergency situations: hospital, ambulance, 911, emergency
    - Critical conditions: dizzy, fainted, collapsed, unconscious
    """

    # Urgency keywords (case-insensitive)
    URGENCY_KEYWORDS: Set[str] = {
        # Emergency services
        "hospital",
        "ambulance",
        "911",
        "emergency",
        "emergency room",
        "er",
        
        # Severe symptoms
        "severe",
        "severe pain",
        "can't breathe",
        "can not breathe",
        "cannot breathe",
        "difficulty breathing",
        "hard to breathe",
        "chest pain",
        "bleeding",
        "heavy bleeding",
        "blood",
        
        # Critical conditions
        "dizzy",
        "fainted",
        "passed out",
        "collapsed",
        "unconscious",
        "stroke",
        "heart attack",
        "seizure",
        "convulsion",
        
        # Severe reactions
        "swelling",
        "swollen",
        "rash all over",
        "allergic reaction",
        "anaphylaxis",
        
        # Pain descriptors
        "unbearable",
        "excruciating",
        "worst pain",
        "intense pain",
    }

    def __init__(self, custom_keywords: List[str] = None):
        """
        Initialize urgency detector.

        Args:
            custom_keywords: Additional keywords to detect (optional)
        """
        self.keywords = self.URGENCY_KEYWORDS.copy()
        if custom_keywords:
            self.keywords.update(k.lower() for k in custom_keywords)

    def scan(self, text: str) -> List[str]:
        """
        Scan text for urgency keywords.

        Args:
            text: Text to scan (patient response, transcript, etc.)

        Returns:
            List of detected urgency keywords
        """
        if not text:
            return []

        text_lower = text.lower()
        detected = []

        for keyword in self.keywords:
            # Use word boundaries to avoid false positives
            # e.g., "server" shouldn't match "severe"
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_lower):
                detected.append(keyword)

        return detected

    def scan_transcript(self, transcript: List[dict]) -> List[str]:
        """
        Scan full conversation transcript for urgency keywords.

        Args:
            transcript: List of conversation turns (each with 'speaker' and 'text')

        Returns:
            List of all detected urgency keywords across transcript
        """
        all_keywords = []

        for turn in transcript:
            # Only scan patient turns (not AI responses)
            if turn.get("speaker") == "patient":
                keywords = self.scan(turn.get("text", ""))
                all_keywords.extend(keywords)

        # Remove duplicates while preserving order
        return list(dict.fromkeys(all_keywords))

    def is_urgent(self, text: str) -> bool:
        """
        Quick check if text contains any urgency keywords.

        Args:
            text: Text to check

        Returns:
            True if any urgency keywords detected
        """
        return len(self.scan(text)) > 0
