from backend.retrieval.query_expansion import expand_query


def test_expansion_includes_originals() -> None:
    original, expanded = expand_query("MCA eligibility")
    assert original == ["mca", "eligibility"]
    assert "mca" in expanded
    assert "eligibility" in expanded


def test_expansion_adds_synonyms() -> None:
    _, expanded = expand_query("eligibility")
    assert "requirements" in expanded
    assert "criteria" in expanded


def test_expansion_no_synonyms_for_unknown_term() -> None:
    original, expanded = expand_query("foobar")
    assert original == ["foobar"]
    assert expanded == ["foobar"]


def test_expansion_unique_tokens() -> None:
    _, expanded = expand_query("hostel hostel")
    assert expanded.count("hostel") == 1


def test_expansion_handles_empty() -> None:
    original, expanded = expand_query("")
    assert original == []
    assert expanded == []


def test_expansion_maps_dean_to_head_director() -> None:
    """Regression: 'dean of placement' couldn't find Dr. Hemant Mali whose title is
    'Head' not 'Dean'. Synonym expansion now bridges the vocabulary gap."""
    _, expanded = expand_query("dean")
    assert "head" in expanded
    assert "director" in expanded


def test_expansion_maps_fees_to_tuition() -> None:
    _, expanded = expand_query("fees structure")
    assert "tuition" in expanded
    assert "cost" in expanded


def test_expansion_maps_department_to_school() -> None:
    _, expanded = expand_query("computer department")
    assert "school" in expanded


def test_expansion_handles_nac_typo() -> None:
    """Regression: user typed 'nac graded' (missing one 'a'). Map nac→naac so retrieval
    still finds the accreditation chunks."""
    _, expanded = expand_query("is the college nac graded")
    assert "naac" in expanded


def test_expansion_handles_branch_abbreviations() -> None:
    """Regression: 'fees for entc' missed the Electronics admission page because the
    corpus uses 'Electronics and Telecommunication' / 'E&TC'."""
    _, expanded = expand_query("fees for entc")
    assert "electronics" in expanded
    assert "telecommunication" in expanded

    _, expanded_cse = expand_query("cse curriculum")
    assert "computer" in expanded_cse

    _, expanded_mech = expand_query("mech placements")
    assert "mechanical" in expanded_mech
