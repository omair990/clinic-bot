"""Convert Markdown-ish model output to WhatsApp's text formatting.

WhatsApp understands *bold*, _italic_, ~strike~, ```mono``` — but NOT Markdown's
**bold**, ## headings, or [label](url) links, which otherwise show up with their
raw symbols visible to the patient. This normalises the common cases.
"""
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)          # **bold** -> *bold*
_BOLD_UNDERSCORE = re.compile(r"__(.+?)__", re.DOTALL)   # __bold__ -> *bold*
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*(.+?)[ \t]*#*$", re.MULTILINE)  # ## Title -> *Title*
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")         # [label](url) -> label (url)

# Characters that look fine in a browser but render oddly / inconsistently on phones.
_REPLACEMENTS = {
    "‑": "-",   # non-breaking hyphen (e.g. "Al‑Otaibi")
    " ": " ",   # non-breaking space
    "​": "",    # zero-width space
}


def to_whatsapp(text: str) -> str:
    if not text:
        return text
    text = _HEADING.sub(r"*\1*", text)        # headings before bold
    text = _BOLD.sub(r"*\1*", text)
    text = _BOLD_UNDERSCORE.sub(r"*\1*", text)
    text = _LINK.sub(r"\1 (\2)", text)
    for bad, good in _REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text
