import logging
import os
import re
from typing import Dict, Any

try:
    from google import genai
    from google.genai import types

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google Gemini not available - AI insights will be disabled")

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Initialize Gemini client if available
client = None
if GEMINI_AVAILABLE:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info("✅ Gemini AI client initialized successfully")
        except Exception as e:
            logger.error("❌ Failed to initialize Gemini client: %s", e)
            client = None
    else:
        logger.warning("GEMINI_API_KEY not found in environment variables")

sys_prompt = """ 
YOU ARE A PRO HELPER SUMMARIZER. YOUR TASK IS TO SUMMARIZE TEXT GIVEN TO YOU. YOUR TASK INCLUDES:
1. SUMMARIZE THE TEXT
2. DO AN OVERVIEW SUMMARY EG "THE TEXT TALKS ABOUT TOBS BORING LIFE AND SOCIAL RELATIONS"
3. ALSO IN THE SUMMARY ADD A KEYWORDS SECTION FOR KEYWORD WITHIN THE TEXT.
DO NOT ADD ANY INTRO TEXT IN YOUR RESPONSE LIKE "Here's a summary of the provided text:" ONLY RESPOND WITH TASK GIVEN.....YOUR RESPONSE SHOULD STRICTLY  FOLLOW THIS EXAMPLE FORMAT:
"Summary: The speaker expresses frustration with their current dating experiences, stating that they will be deleting their dating apps because the people they've been dating are not suitable, and they are tired of constantly searching for partners. They metaphorically describe themselves as a "bee harvester" and now wish to be a "flower," believing that focusing on self-love and personal growth will naturally attract the right person. The core message is to prioritize self-improvement over desperately seeking a partner.

Overview Summary: The text talks about the speaker's decision to quit dating apps and shift their focus from actively seeking partners to self-love and personal development, believing that this approach will lead to finding a suitable partner.

Keywords: dating apps, bee harvester, flower, self-love, personal development, partner search, self-improvement"

"""


def extract_segments(text: str) -> Dict[str, Any]:
    """
    Extracts segments from the input text based on markers.

    Expected segments in text:
          - Summary: <text...>
      - Overview Summary: <text...>
      - Keywords: <text...>

    Returns:
        A dictionary with segment names as keys and the corresponding text as values.
    """
    segments = {}

    # Extract Summary
    summary_pattern = r"Summary:\s*(.+?)(?=\n\n|\nOverview Summary:|$)"
    summary_match = re.search(summary_pattern, text, re.DOTALL | re.IGNORECASE)
    if summary_match:
        segments["summary"] = summary_match.group(1).strip()

    # Extract Overview Summary
    overview_pattern = r"Overview Summary:\s*(.+?)(?=\n\n|\nKeywords:|$)"
    overview_match = re.search(overview_pattern, text, re.DOTALL | re.IGNORECASE)
    if overview_match:
        segments["overview"] = overview_match.group(1).strip()

    # Extract Keywords
    keywords_pattern = r"Keywords:\s*(.+?)(?=\n\n|$)"
    keywords_match = re.search(keywords_pattern, text, re.DOTALL | re.IGNORECASE)
    if keywords_match:
        keywords_text = keywords_match.group(1).strip()
        # Split by commas and clean up
        keywords = [kw.strip() for kw in keywords_text.split(",") if kw.strip()]
        segments["keywords"] = keywords

    return segments


def get_ai_insights(full_transcript: str) -> Dict[str, Any]:
    """
    Sends the full transcript to Google Gemini and returns the parsed insights.
    Falls back to basic processing if Gemini is not available.
    """
    if not full_transcript or not full_transcript.strip():
        logger.warning("Transcript is empty, skipping AI processing.")
        return {
            "summary": "No content to summarize.",
            "overview": "Empty transcript provided.",
            "keywords": [],
        }

    # If Gemini is not available, provide basic fallback
    if not client or not GEMINI_AVAILABLE:
        logger.warning("Gemini AI not available, using fallback processing.")
        words = full_transcript.split()
        basic_keywords = []

        # Extract some basic keywords (simple word frequency)
        word_freq = {}
        for word in words:
            clean_word = re.sub(r"[^a-zA-Z]", "", word.lower())
            if len(clean_word) > 3:  # Only words longer than 3 chars
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1

        # Get top 5 most frequent words as keywords
        basic_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        basic_keywords = [word for word, freq in basic_keywords]

        return {
            "summary": f"Transcript contains {len(words)} words of spoken content.",
            "overview": f"The conversation/content spans approximately {len(words)} words covering various topics.",
            "keywords": basic_keywords,
        }

    try:
        logger.info("Sending transcript to Google Gemini for summarization...")

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            config=types.GenerateContentConfig(system_instruction=sys_prompt),
            contents=full_transcript,
        )

        if not response or not response.text:
            logger.error("Empty response from Gemini AI")
            return get_ai_insights("")  # Fallback to basic processing

        insights = extract_segments(response.text)

        # Validate that we got the expected segments
        if not all(k in insights for k in ["summary", "overview", "keywords"]):
            logger.warning("AI response incomplete. Got: %s", list(insights.keys()))
            # Fill in missing segments
            if "summary" not in insights:
                insights["summary"] = "AI summary generation incomplete."
            if "overview" not in insights:
                insights["overview"] = "AI overview generation incomplete."
            if "keywords" not in insights:
                insights["keywords"] = []

        logger.info("✅ Successfully generated and parsed AI insights.")
        return insights

    except Exception as e:
        logger.error("Failed to get summary from Gemini AI: %s", e)
        # Fallback to basic processing
        return get_ai_insights("")
