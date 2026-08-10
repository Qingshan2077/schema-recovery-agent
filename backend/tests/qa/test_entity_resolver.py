from backend.agent.qa.contracts import CatalogEntity, EntityMention
from backend.agent.qa.entity_resolver import EntityResolver


def table(name: str) -> CatalogEntity:
    return CatalogEntity(
        entity_id=f"cat_{name}",
        database="demo",
        schema_name="demo",
        name=name,
    )


def test_exact_resolution_wins_over_fuzzy_candidates():
    result = EntityResolver().resolve(
        [EntityMention(mention="products")],
        [table("products"), table("product_tags")],
    )[0]

    assert result.status == "resolved"
    assert result.canonical_name == "products"
    assert result.resolution_method == "exact"


def test_fuzzy_resolution_never_silently_selects_a_table():
    result = EntityResolver(fuzzy_threshold=0.5).resolve(
        [EntityMention(mention="product")],
        [table("products"), table("product_tags")],
    )[0]

    assert result.status == "ambiguous"
    assert {candidate.name for candidate in result.candidates} == {"products", "product_tags"}


def test_pronoun_uses_explicit_thread_focus():
    focused = table("orders")
    result = EntityResolver().resolve(
        [EntityMention(mention="这个表")],
        [focused],
        focus=[focused],
    )[0]

    assert result.status == "resolved"
    assert result.canonical_name == "orders"
    assert result.resolution_method == "focus"
