"""Search packaged occupation and U.S. location data for GUI suggestions."""

import json
import math
import re
from functools import lru_cache
from importlib.resources import files
from typing import Any


STATE_ALIASES = {
    "alabama": "al",
    "alaska": "ak",
    "arizona": "az",
    "arkansas": "ar",
    "california": "ca",
    "colorado": "co",
    "connecticut": "ct",
    "delaware": "de",
    "district of columbia": "dc",
    "florida": "fl",
    "georgia": "ga",
    "hawaii": "hi",
    "idaho": "id",
    "illinois": "il",
    "indiana": "in",
    "iowa": "ia",
    "kansas": "ks",
    "kentucky": "ky",
    "louisiana": "la",
    "maine": "me",
    "maryland": "md",
    "massachusetts": "ma",
    "michigan": "mi",
    "minnesota": "mn",
    "mississippi": "ms",
    "missouri": "mo",
    "montana": "mt",
    "nebraska": "ne",
    "nevada": "nv",
    "new hampshire": "nh",
    "new jersey": "nj",
    "new mexico": "nm",
    "new york": "ny",
    "north carolina": "nc",
    "north dakota": "nd",
    "ohio": "oh",
    "oklahoma": "ok",
    "oregon": "or",
    "pennsylvania": "pa",
    "puerto rico": "pr",
    "rhode island": "ri",
    "south carolina": "sc",
    "south dakota": "sd",
    "tennessee": "tn",
    "texas": "tx",
    "utah": "ut",
    "vermont": "vt",
    "virginia": "va",
    "washington": "wa",
    "west virginia": "wv",
    "wisconsin": "wi",
    "wyoming": "wy",
}


def suggest_occupations(query: str, *, limit: int = 12) -> list[dict[str, str]]:
    """Return broad occupation suggestions without changing profile data."""

    terms = _query_terms(query)
    if not terms:
        return []

    occupations = _load_reference("occupations.json")["occupations"]
    occupations_by_code = {
        occupation["code"]: occupation for occupation in occupations
    }
    matches: list[tuple[int, dict[str, str]]] = []
    seen_labels: set[str] = set()

    for occupation in occupations:
        title = occupation["title"]
        searchable = _normalize(title)
        if all(term in searchable for term in terms):
            rank = _match_rank(searchable, terms)
            seen_labels.add(searchable)
            matches.append(
                (
                    rank,
                    {
                        "value": occupation["code"],
                        "label": title,
                        "description": occupation["description"],
                    },
                )
            )

    alternate_matches: dict[str, dict[str, Any]] = {}
    for job_title in _load_reference("job_titles.json")["job_titles"]:
        label = job_title["job_title"]
        searchable = _normalize(label)
        if searchable in seen_labels or not all(term in searchable for term in terms):
            continue

        occupation = occupations_by_code.get(job_title["code"])
        if occupation is None:
            continue

        match = alternate_matches.setdefault(
            searchable,
            {
                "label": label,
                "occupation_titles": set(),
            },
        )
        match["occupation_titles"].add(occupation["title"])

    for searchable, match in alternate_matches.items():
        related = sorted(match["occupation_titles"])
        relationship_label = (
            "Related occupation" if len(related) == 1 else "Possible occupations"
        )
        matches.append(
            (
                _match_rank(searchable, terms),
                {
                    "value": f"title:{searchable}",
                    "label": match["label"],
                    "description": f"{relationship_label}: {'; '.join(related)}",
                },
            )
        )

    matches.sort(key=lambda item: (item[0], item[1]["label"]))
    return [item[1] for item in matches[:limit]]


def _match_rank(searchable: str, terms: list[str]) -> int:
    query = " ".join(terms)
    if searchable == query:
        return 0
    if searchable.startswith(query):
        return 1
    return 2


def suggest_locations(query: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """Return normalized U.S. place or ZIP suggestions for the preview form."""

    cleaned_query = query.strip()
    if len(cleaned_query) < 2:
        return []

    if cleaned_query.isdigit():
        return _suggest_zip_areas(cleaned_query, limit=limit)

    terms = _location_query_terms(cleaned_query)
    matches: list[tuple[int, dict[str, Any]]] = []
    for place in _load_reference("us_places.json")["places"]:
        searchable = _normalize(
            f"{place['name']} {place['state']} {place['state_code']}"
        )
        if all(term in searchable for term in terms):
            normalized_name = f"{place['name']}, {place['state']}"
            rank = 0 if searchable.startswith(" ".join(terms)) else 1
            matches.append(
                (
                    rank,
                    {
                        "value": f"place:{place['state_code']}:{place['name']}",
                        "label": normalized_name,
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "kind": "place",
                    },
                )
            )

    matches.sort(key=lambda item: (item[0], item[1]["label"]))
    return [item[1] for item in matches[:limit]]


def _suggest_zip_areas(query: str, *, limit: int) -> list[dict[str, Any]]:
    matches = []
    for area in _load_reference("us_zip_areas.json")["zip_areas"]:
        if area["zip"].startswith(query):
            nearest_place = _nearest_place(
                float(area["latitude"]),
                float(area["longitude"]),
            )
            matches.append(
                {
                    "value": f"zip:{area['zip']}",
                    "label": (
                        f"ZIP {area['zip']} — {nearest_place['label']}"
                        if nearest_place
                        else f"ZIP {area['zip']}"
                    ),
                    "latitude": area["latitude"],
                    "longitude": area["longitude"],
                    "kind": "zip",
                }
            )
        if len(matches) >= limit:
            break
    return matches


def cities_within_radius(
    latitude: float,
    longitude: float,
    radius_miles: int,
) -> dict[str, Any]:
    """Describe the Census places covered by a preview attendance radius."""

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Location coordinates are outside the valid range.")
    if radius_miles not in {10, 25, 50, 75, 100}:
        raise ValueError("Distance must be 10, 25, 50, 75, or 100 miles.")

    nearby: list[dict[str, Any]] = []
    for place in _load_reference("us_places.json")["places"]:
        distance = _distance_miles(
            latitude,
            longitude,
            float(place["latitude"]),
            float(place["longitude"]),
        )
        if distance <= radius_miles:
            nearby.append(
                {
                    "distance_miles": round(distance),
                    "label": f"{place['name']}, {place['state']}",
                    "population": place.get("population"),
                }
            )

    nearby.sort(key=lambda item: (item["distance_miles"], item["label"]))
    nearest = _nearest_place(latitude, longitude)
    featured, additional = _display_cities(
        nearby,
        nearest["label"] if nearest else None,
    )
    return {
        "center_city": nearest["label"] if nearest else None,
        "featured_cities": featured,
        "additional_cities": additional,
        "covered_community_count": len(nearby),
    }


def _display_cities(
    nearby: list[dict[str, Any]],
    center_city: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Show major cities without changing the actual geographic coverage."""

    major = [
        item
        for item in nearby
        if isinstance(item["population"], int) and item["population"] >= 50_000
    ]
    major_by_distance = sorted(
        major,
        key=lambda item: (
            item["distance_miles"],
            -item["population"],
            item["label"],
        ),
    )
    major_by_population = sorted(
        major,
        key=lambda item: (
            -item["population"],
            item["distance_miles"],
            item["label"],
        ),
    )
    center = next((item for item in nearby if item["label"] == center_city), None)
    featured: list[dict[str, Any]] = []
    if center is not None:
        featured.append(center)
    for item in [*major_by_distance[:5], *major_by_population[:5]]:
        if item not in featured and len(featured) < 10:
            featured.append(item)
    for item in major_by_distance:
        if item not in featured and len(featured) < 10:
            featured.append(item)
    featured.sort(key=lambda item: (item["distance_miles"], item["label"]))
    additional = [item for item in major_by_distance if item not in featured]
    return featured, additional


def _nearest_place(latitude: float, longitude: float) -> dict[str, Any] | None:
    nearest: tuple[float, dict[str, Any]] | None = None
    for place in _load_reference("us_places.json")["places"]:
        distance = _distance_miles(
            latitude,
            longitude,
            float(place["latitude"]),
            float(place["longitude"]),
        )
        if nearest is None or distance < nearest[0]:
            nearest = (
                distance,
                {"label": f"{place['name']}, {place['state']}"},
            )
    return nearest[1] if nearest else None


def _distance_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Calculate straight-line distance between two latitude/longitude points."""

    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    lat_delta = math.radians(latitude_b - latitude_a)
    lon_delta = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(lon_delta / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(math.sqrt(haversine))


def _location_query_terms(query: str) -> list[str]:
    normalized = _normalize(query)
    normalized = re.sub(r"^ft\.?\s+", "fort ", normalized)
    normalized = re.sub(r"\bst\.?\s+", "saint ", normalized)
    for state_name, abbreviation in STATE_ALIASES.items():
        normalized = re.sub(
            rf"\b{re.escape(state_name)}\b",
            abbreviation,
            normalized,
        )
    return normalized.split()


def _query_terms(query: str) -> list[str]:
    return _normalize(query).split()


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


@lru_cache(maxsize=3)
def _load_reference(filename: str) -> dict[str, Any]:
    resource = files("job_radar").joinpath("reference_data", filename)
    return json.loads(resource.read_text(encoding="utf-8"))
