import re


sys_prompt = """ 
YOU ARE A PRO HELPER SUMMARIZER. YOUR TASK IS TO SUMMARIZE TEXT GIVEN TO YOU. YOUR TASK INCLUDES:
1. SUMMARIZE THE TEXT
2. DO AN OVERVIEW SUMMARY EG "THE TEXT TALKS ABOUT TOBS BORING LIFE AND SOCIAL RELATIONS"
3. ALSO IN THE SUMMARY ADD A KEYWORDS SECTION FOR KEYWORD WITHIN THE TEXT.
DO NOT ADD ANY INTRO TEXT IN YOUR RESPONSE LIKE "Here's a summary of the provided text:" ONLY RESPOND WITH TASK GIVEN.....YOUR RESPONSE SHOULD STRICTLY  FOLLOW THIS EXAMPLE FORMAT:
"Summary: The speaker expresses frustration with their current dating experiences, stating that they will be deleting their dating apps because the people they've been dating are not suitable, and they are tired of constantly searching for partners. They metaphorically describe themselves as a "bee harvester" and now wish to be a "flower," believing that focusing on self-love and personal growth will naturally attract the right person. The core message is to prioritize self-improvement over desperately seeking a partner.

Overview Summary: The text talks about the speaker's decision to quit dating apps and shift their focus from actively seeking partners to self-love and personal development, believing that this approach will lead to finding a suitable partner.

Keywords: dating apps, bee harvester, flower, self-love ......."

"""

def extract_segments(text):
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
    
    summary_pattern = r"Summary:\s*(.+?)(?:\n|$)"
    summary_match = re.search(summary_pattern, text, re.DOTALL)
    if summary_match:
        segments['Summary'] = summary_match.group(1).strip()

    
    overview_pattern = r"Overview Summary:\s*(.+?)(?:\n|$)"
    overview_match = re.search(overview_pattern, text, re.DOTALL)
    if overview_match:
        segments['Overview Summary'] = overview_match.group(1).strip()

    keywords_pattern = r"Keywords:\s*(.+?)(?:\n|$)"
    keywords_match = re.search(keywords_pattern, text, re.DOTALL)
    if keywords_match:
        keywords = [kw.strip() for kw in keywords_match.group(1).split(',')]
        segments['Keywords'] = keywords

    return segments

# if __name__ == "__main__":
#     segments = extract_segments(text)
    
#     # Display the extracted segments
#     for key, value in segments.items():
#         print(f"{key}:")
#         print(value)
#         print("-" * 50)
