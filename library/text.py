"""Text normalisation so search is case-, accent- and punctuation-insensitive."""
import unicodedata


def fold(text):
    """Casefold and strip accents from Latin letters ("Misérables" -> "miserables").

    Other scripts (Devanagari, Kannada, ...) keep their vowel signs, because removing
    those would change the word.
    """
    out = []
    for ch in unicodedata.normalize("NFKD", text):
        if unicodedata.category(ch) == "Mn" and out and out[-1].isascii() and out[-1].isalpha():
            continue
        out.append(ch)
    return "".join(out).casefold()


def tokenize(text):
    """Split into lowercase words. Combining marks stay inside the word they belong to."""
    tokens, current = [], []
    for ch in fold(text):
        if ch.isalnum() or unicodedata.category(ch).startswith("M"):
            current.append(ch)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens
