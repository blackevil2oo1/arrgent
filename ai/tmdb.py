"""
tmdb.py – Holt Empfehlungen und Filminformationen von TMDB.

TMDB (The Movie Database) ist eine kostenlose Film-Datenbank.
API Key: https://www.themoviedb.org/settings/api
"""

import httpx
import config

TMDB_BASE = "https://api.themoviedb.org/3"

GENRE_MAP_MOVIES = {
    "action": 28, "abenteuer": 12, "animation": 16, "komödie": 35,
    "krimi": 80, "dokumentation": 99, "drama": 18, "fantasy": 14,
    "horror": 27, "musik": 10402, "mystery": 9648, "romance": 10749,
    "sci-fi": 878, "science fiction": 878, "thriller": 53,
    "western": 37, "familie": 10751,
}

GENRE_MAP_TV = {
    "action": 10759, "animation": 16, "komödie": 35, "krimi": 80,
    "dokumentation": 99, "drama": 18, "fantasy": 10765, "kinder": 10762,
    "mystery": 9648, "romance": 10749, "sci-fi": 10765,
    "science fiction": 10765, "thriller": 9648,
}


def get_recommendations(genre: str, media_type: str) -> list[dict]:
    """
    Holt aktuelle beliebte Filme oder Serien eines bestimmten Genres von TMDB.

    genre: z.B. "sci-fi", "action", "horror"
    media_type: "movie" oder "tv"
    """
    genre_lower = genre.lower()
    genre_map = GENRE_MAP_MOVIES if media_type == "movie" else GENRE_MAP_TV
    genre_id = genre_map.get(genre_lower)

    params = {
        "api_key": config.TMDB_API_KEY,
        "language": "de-DE",
        "sort_by": "popularity.desc",
        "include_adult": False,
        "page": 1,
    }

    if genre_id:
        params["with_genres"] = genre_id

    endpoint = "discover/movie" if media_type == "movie" else "discover/tv"

    response = httpx.get(f"{TMDB_BASE}/{endpoint}", params=params)
    response.raise_for_status()

    results = []
    for item in response.json().get("results", [])[:8]:
        results.append({
            "title": item.get("title") or item.get("name"),
            "year": (item.get("release_date") or item.get("first_air_date") or "")[:4],
            "tmdb_id": item.get("id"),
            "rating": item.get("vote_average"),
            "overview": (item.get("overview") or "")[:200],
            "media_type": media_type,
        })

    return results
