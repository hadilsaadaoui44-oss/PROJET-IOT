from __future__ import annotations

from typing import Any

import requests
from django.conf import settings


class Agent1ClientError(RuntimeError):
    """Erreur lors de l'appel au microservice Agent 1."""


def get_agent1_base_url() -> str:
    return getattr(
        settings,
        "AGENT1_API_URL",
        "http://127.0.0.1:8002",
    ).rstrip("/")


def check_agent1_health() -> dict[str, Any]:
    url = f"{get_agent1_base_url()}/health"

    try:
        response = requests.get(
            url,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    except requests.RequestException as exc:
        raise Agent1ClientError(
            f"Agent 1 indisponible : {exc}"
        ) from exc


def analyze_firmware_with_agent1(
    payload: dict[str, Any],
) -> dict[str, Any]:
    url = f"{get_agent1_base_url()}/agent1/analyze"

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=240,
        )
        response.raise_for_status()

    except requests.Timeout as exc:
        raise Agent1ClientError(
            "Agent 1 a dépassé le délai d'attente."
        ) from exc

    except requests.RequestException as exc:
        detail = ""

        if exc.response is not None:
            try:
                detail = str(exc.response.json())
            except ValueError:
                detail = exc.response.text

        raise Agent1ClientError(
            f"Erreur Agent 1 : {exc}. {detail}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise Agent1ClientError(
            "Agent 1 a renvoyé une réponse non JSON."
        ) from exc

    if data.get("status") not in {
        "success",
        "needs_validation",
    }:
        raise Agent1ClientError(
            f"Statut Agent 1 invalide : {data.get('status')}"
        )

    return data