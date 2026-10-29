from modules.courses.catalog import load_catalog


def test_catalog_loads_and_has_unique_ids() -> None:
    courses = load_catalog()

    ids = [course.id for course in courses]
    assert courses, "courses.json must contain at least one course"
    assert len(ids) == len(set(ids))


def test_catalog_has_no_unauthorized_promotions() -> None:
    # Promotions are authorized by the business, never invented by the LLM.
    for course in load_catalog():
        assert course.promociones_autorizadas == []
