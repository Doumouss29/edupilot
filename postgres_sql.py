"""SQL placeholder conversion for PostgreSQL migration testing."""

def placeholders(query):
    out=[]
    quote=None
    for ch in query:
        if ch in ("\'",'"'):
            quote = None if quote == ch else (ch if quote is None else quote)
        out.append("%s" if ch == "?" and quote is None else ch)
    return "".join(out)
