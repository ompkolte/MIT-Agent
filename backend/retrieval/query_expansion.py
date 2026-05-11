import regex as re


SYNONYM_MAP: dict[str, list[str]] = {
    "eligibility": ["requirements", "criteria", "qualification", "minimum"],
    "fees": ["tuition", "cost", "charges", "structure"],
    "fee": ["tuition", "cost", "charges"],
    "tuition": ["fees", "cost"],
    "scholarship": ["financial aid", "stipend"],
    "placement": ["recruitment", "package", "lpa", "ctc"],
    "hostel": ["accommodation", "residential"],
    "faculty": ["professor", "teaching staff"],
    "professor": ["faculty", "instructor"],
    "curriculum": ["syllabus", "course structure", "scheme"],
    "club": ["society", "committee"],
    "research": ["publication", "patent", "journal"],
    "btech": ["b.tech", "bachelor of technology"],
    "mtech": ["m.tech", "master of technology"],
    "mca": ["master of computer applications"],
    "hod": ["head of department"],
    "dean": ["head", "director"],
    "head": ["dean", "director"],
    "director": ["dean", "head"],
    "principal": ["dean", "head", "director"],
    "department": ["school", "branch", "dept"],
    "school": ["department", "branch"],
    "ieee": ["ieee student branch"],
    "nss": ["national service scheme"],
    # Common typos / abbreviations
    "nac": ["naac"],
    "naac": ["nac", "accreditation"],
    "nba": ["nba accreditation"],
    "cap": ["cet cell", "centralised admission process"],
    # Branch / department abbreviations used by MITAOE students. Corpus uses the long
    # forms ("Electronics and Telecommunication", "Computer Science and Engineering"),
    # so abbreviated queries miss without these synonyms.
    "entc": ["electronics", "telecommunication", "e&tc"],
    "e&tc": ["electronics", "telecommunication", "entc"],
    "etc": ["electronics", "telecommunication"],
    "electronics": ["entc", "e&tc", "telecommunication"],
    "cse": ["computer science", "computer engineering"],
    "ce": ["computer engineering"],
    "it": ["information technology"],
    "ai": ["artificial intelligence", "machine learning"],
    "ml": ["machine learning"],
    "ds": ["data science"],
    "civil": ["civil engineering"],
    "mech": ["mechanical", "mechanical engineering"],
    "mechanical": ["mech"],
    "chem": ["chemical", "chemical engineering"],
    "chemical": ["chem"],
}


_TOKEN_RE = re.compile(r"[\p{L}\p{N}][\p{L}\p{N}&.+-]*")


def expand_query(query: str) -> tuple[list[str], list[str]]:
    """Return (original_tokens, expanded_tokens). Expanded is the unique set of original
    tokens plus their synonyms, preserving first-seen order."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(query or "")]
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            expanded.append(token)
            seen.add(token)
    for token in tokens:
        for synonym in SYNONYM_MAP.get(token, []):
            for sub in _TOKEN_RE.findall(synonym):
                lowered = sub.lower()
                if lowered not in seen:
                    expanded.append(lowered)
                    seen.add(lowered)
    return tokens, expanded
