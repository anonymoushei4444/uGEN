import re

def extract_questions(text: str) -> list[str]:
    """
    Extracts questions from the provided text and returns them as a list of strings.

    Args:
        text (str): The input text containing questions.

    Returns:
        list: A list of questions found in the text.
    """
    # Define a regular expression pattern to match questions
    pattern = r'^(.*\?)$'
    
    # Use re.MULTILINE to handle multi-line strings
    matches = re.findall(pattern, text, re.MULTILINE)
    
    # Strip leading and trailing whitespace from each match
    questions = [match.strip() for match in matches]
    
    return questions
