from backend.reranking.aggregator_boost import AGGREGATOR_BOOST, boost_score, is_aggregator_chunk


def test_student_clubs_url_is_aggregator() -> None:
    assert is_aggregator_chunk("https://mitaoe.ac.in/student-clubs.php", "") is True


def test_mitaoe_courses_url_is_aggregator() -> None:
    assert is_aggregator_chunk("https://mitaoe.ac.in/mitaoe-courses.php", "") is True


def test_individual_club_url_is_not_aggregator() -> None:
    assert is_aggregator_chunk("https://mitaoe.ac.in/club-Spiritual-Minds.php", "") is False


def test_aggregator_by_paragraph_density() -> None:
    """Paragraph-density heuristic catches aggregator pages without URL signals."""
    text = "\n\n".join(
        f"{name} is a student club at MITAOE that focuses on specific activities."
        for name in [
            "AALEKH Art Club", "MITAOE Aero", "Robotics Group", "GirlScript Chapter",
            "Drama Society", "GOONJ Music", "Vertex Animation", "Spiritual Minds", "Maths AXES",
        ]
    )
    assert is_aggregator_chunk("https://mitaoe.ac.in/anything", text) is True


def test_boost_score_lifts_aggregator() -> None:
    boosted = boost_score(0.65, "https://mitaoe.ac.in/student-clubs.php", "")
    assert abs(boosted - (0.65 + AGGREGATOR_BOOST)) < 1e-9


def test_boost_score_passes_through_non_aggregator() -> None:
    assert boost_score(0.65, "https://mitaoe.ac.in/club-X.php", "short text") == 0.65


def test_boost_score_clamps_to_one() -> None:
    assert boost_score(0.99, "https://mitaoe.ac.in/student-clubs.php", "") == 1.0
