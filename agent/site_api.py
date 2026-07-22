"""Talk to the site's public REST API with the agent's organizer token. Coverage-omitted I/O."""

from __future__ import annotations

import json
import urllib.request

from agent.models import Candidate, KnownEvents, Taxonomy
from agent.pipeline import normalize_key


class SiteApiClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> object:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode())

    def _get_list(self, path: str) -> list:
        result = self._request("GET", path)
        return result if isinstance(result, list) else []

    def _list(self, status: str) -> list[dict]:
        return self._get_list(f"/api/v1/competitions/?status={status}")

    def taxonomy(self) -> Taxonomy:
        """Event types + disciplines the LLM classifies an event into (ids validated on parse)."""
        tax = Taxonomy()
        for event_type in self._get_list("/api/v1/event-types/"):
            if isinstance(event_type, dict) and "id" in event_type:
                tax.event_types.append({"id": event_type["id"], "name": _ru(event_type.get("name"))})
        for category in self._get_list("/api/v1/disciplines/"):
            if not isinstance(category, dict):
                continue
            category_name = _ru(category.get("name"))
            for discipline in category.get("disciplines") or []:
                if isinstance(discipline, dict) and "id" in discipline:
                    tax.disciplines.append(
                        {"id": discipline["id"], "name": _ru(discipline.get("name")), "category": category_name}
                    )
        return tax

    def known(self) -> KnownEvents:
        """Approved + own pending become dedup keys; own rejected carry their reasons to learn from."""
        known = KnownEvents()
        for comp in self._list("approved") + self._list("pending_approval"):
            title, date_start = _ru(comp.get("title")), comp.get("date_start", "")
            known.existing_keys.add(normalize_key(title, date_start))
            known.existing.append({"title": title, "titles": _titles(comp.get("title")), "date_start": date_start})
        for comp in self._list("rejected"):
            title, date_start = _ru(comp.get("title")), comp.get("date_start", "")
            known.rejected.append(
                {
                    "key": normalize_key(title, date_start),
                    "title": title,
                    "titles": _titles(comp.get("title")),
                    "date_start": date_start,
                    "reason": comp.get("rejection_reason", ""),
                }
            )
        return known

    def location_tree(self) -> list:
        """The visible country -> region -> city -> venue hierarchy (hidden venues excluded)."""
        return self._get_list("/api/v1/locations/")

    def propose_venue(
        self,
        city_id: int,
        name_ru: str,
        name_kk: str = "",
        name_en: str = "",
        lat: float | None = None,
        lng: float | None = None,
    ) -> int:
        """Create a start venue (depth 4) under a city and return its id. Approved for organizers."""
        payload: dict = {"parent_id": city_id, "name": _loc(name_ru, name_kk, name_en)}
        if lat is not None:
            payload["lat"] = lat
        if lng is not None:
            payload["lng"] = lng
        result = self._request("POST", "/api/v1/locations/", payload)
        return int(result["id"]) if isinstance(result, dict) else 0

    def propose_place(self, parent_id: int, name: str) -> int:
        """Propose a region or city under ``parent_id`` and return its id.

        Unlike a venue this always lands pending: the site reviews geography before publishing it.
        The one name is stored in all three locales -- a reviewer renames it when approving, which
        beats asking the model to translate a place name it may not know.
        """
        payload = {"parent_id": parent_id, "name": _loc(name, name, name)}
        result = self._request("POST", "/api/v1/locations/", payload)
        return int(result["id"]) if isinstance(result, dict) else 0

    def fallback_venue(self, city_id: int) -> int:
        """Get (or create) the city's hidden catch-all venue and return its id."""
        result = self._request("POST", f"/api/v1/locations/{city_id}/fallback-venue/", {})
        return int(result["id"]) if isinstance(result, dict) else 0

    def create(self, candidate: Candidate, location_id: int | None = None) -> None:
        payload: dict = {
            "title": _loc(candidate.title, candidate.title_kk, candidate.title_en),
            "date_start": candidate.date_start,
        }
        if candidate.date_end:
            payload["date_end"] = candidate.date_end
        if candidate.description:
            payload["description"] = _loc(candidate.description, candidate.description_kk, candidate.description_en)
        if candidate.source_url:
            payload["url_announcement"] = candidate.source_url
        if candidate.url_route:
            payload["url_route"] = candidate.url_route
        if candidate.url_registration:
            payload["url_registration"] = candidate.url_registration
        if candidate.event_type_id is not None:
            payload["event_type_id"] = candidate.event_type_id
        if candidate.discipline_ids:
            payload["discipline_ids"] = candidate.discipline_ids
        if location_id is not None:
            payload["location_id"] = location_id
        self._request("POST", "/api/v1/competitions/", payload)


def _ru(title: object) -> str:
    """Pull the ru string out of a LocalizedStr dict (or accept a plain string)."""
    if isinstance(title, dict):
        return str(title.get("ru") or title.get("en") or title.get("kk") or "")
    return str(title or "")


def _loc(ru: str, kk: str = "", en: str = "") -> dict:
    """A LocalizedStr payload with every locale filled -- empty ones fall back to the ru text."""
    return {"ru": ru, "kk": kk or ru, "en": en or ru}


def _titles(title: object) -> list[str]:
    """Every non-empty localized form of a title, for cross-language duplicate detection."""
    if isinstance(title, dict):
        values = (title.get("ru"), title.get("kk"), title.get("en"))
        return [str(v).strip() for v in values if v and str(v).strip()]
    text = str(title or "").strip()
    return [text] if text else []
