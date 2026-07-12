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
            known.existing_keys.add(normalize_key(_ru(comp.get("title")), comp.get("date_start", "")))
        for comp in self._list("rejected"):
            title, date_start = _ru(comp.get("title")), comp.get("date_start", "")
            known.rejected.append(
                {
                    "key": normalize_key(title, date_start),
                    "title": title,
                    "date_start": date_start,
                    "reason": comp.get("rejection_reason", ""),
                }
            )
        return known

    def create(self, candidate: Candidate) -> None:
        payload: dict = {
            "title": {"ru": candidate.title},
            "date_start": candidate.date_start,
        }
        if candidate.date_end:
            payload["date_end"] = candidate.date_end
        if candidate.description:
            payload["description"] = {"ru": candidate.description}
        if candidate.source_url:
            payload["url_announcement"] = candidate.source_url
        if candidate.event_type_id is not None:
            payload["event_type_id"] = candidate.event_type_id
        if candidate.discipline_ids:
            payload["discipline_ids"] = candidate.discipline_ids
        self._request("POST", "/api/v1/competitions/", payload)


def _ru(title: object) -> str:
    """Pull the ru string out of a LocalizedStr dict (or accept a plain string)."""
    if isinstance(title, dict):
        return str(title.get("ru") or title.get("en") or title.get("kk") or "")
    return str(title or "")
