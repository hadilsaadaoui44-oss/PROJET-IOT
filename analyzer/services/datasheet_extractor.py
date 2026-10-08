import io
import json
import logging
import re
from pathlib import Path

import requests
from django.conf import settings
from pypdf import PdfReader


logger = logging.getLogger(__name__)


DATASHEET_EXTRACTION_WEBHOOK_URL = getattr(
    settings,
    "DATASHEET_EXTRACTION_WEBHOOK_URL",
    "http://localhost:5678/webhook/datasheet-extraction",
)

DATASHEET_EXTRACTION_TIMEOUT_SECONDS = getattr(
    settings,
    "DATASHEET_EXTRACTION_TIMEOUT_SECONDS",
    120,
)

DATASHEET_EXTRACTION_API_KEY = getattr(
    settings,
    "DATASHEET_EXTRACTION_API_KEY",
    "",
)


BATTERY_DATASHEET_FIELDS = [
    "manufacturer",
    "model",
    "technology",
    "chemistry",
    "nominal_voltage_v",
    "capacity_mah",
    "charge_voltage_v",
    "cutoff_voltage_v",
    "max_charge_current_a",
    "max_discharge_current_a",
    "continuous_discharge_current_a",
    "weight_g",
    "cycle_life",
    "operating_temp_min_c",
    "operating_temp_max_c",
]


def _request_headers():
    """
    Construit les en-têtes utilisés pour contacter le workflow n8n.
    """
    headers = {
        "Accept": "application/json",
    }

    if DATASHEET_EXTRACTION_API_KEY:
        headers["X-AIDE-IOT-Key"] = DATASHEET_EXTRACTION_API_KEY

    return headers


def _normalize_response(data):
    """
    Normalise les différents formats de réponse que n8n peut retourner.
    """
    if isinstance(data, list):
        if not data:
            return {}

        first = data[0]

        if not isinstance(first, dict):
            return {}

        if isinstance(first.get("json"), dict):
            return first["json"]

        return first

    if isinstance(data, dict):
        if isinstance(data.get("json"), dict):
            return data["json"]

        if isinstance(data.get("data"), dict):
            return data["data"]

        if isinstance(data.get("result"), dict):
            return data["result"]

        return data

    return {}


def _call_webhook(payload):
    """
    Envoie un payload JSON simple au workflow d’extraction.

    Cette fonction reste utilisée pour les datasheets des composants
    déjà enregistrés dans Django.
    """
    try:
        response = requests.post(
            DATASHEET_EXTRACTION_WEBHOOK_URL,
            json=payload,
            headers=_request_headers(),
            timeout=DATASHEET_EXTRACTION_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        return _normalize_response(response.json())

    except requests.Timeout:
        logger.warning(
            "Délai dépassé pendant l’extraction de la datasheet."
        )

    except requests.ConnectionError:
        logger.warning(
            "Impossible de joindre le workflow d’extraction "
            "des datasheets."
        )

    except requests.HTTPError as exc:
        status_code = getattr(
            exc.response,
            "status_code",
            "inconnu",
        )

        logger.warning(
            "Erreur HTTP pendant l’extraction de la datasheet : %s.",
            status_code,
        )

    except ValueError:
        logger.warning(
            "Le workflow d’extraction a retourné une réponse non JSON."
        )

    except requests.RequestException as exc:
        logger.exception(
            "Erreur réseau pendant l’extraction de la datasheet : %s",
            exc,
        )

    return {}


def _call_webhook_with_pdf(payload, field_file):
    """
    Envoie la datasheet PDF elle-même au workflow n8n.

    Le fichier est transmis en multipart/form-data dans la propriété
    binaire nommée « datasheet ». Le payload JSON est transmis dans
    le champ texte « payload ».
    """
    if not field_file:
        return {}

    original_name = Path(field_file.name).name

    try:
        field_file.open("rb")

        files = {
            "datasheet": (
                original_name,
                field_file.file,
                "application/pdf",
            )
        }

        form_data = {
            "payload": json.dumps(
                payload,
                ensure_ascii=False,
            )
        }

        response = requests.post(
            DATASHEET_EXTRACTION_WEBHOOK_URL,
            data=form_data,
            files=files,
            headers=_request_headers(),
            timeout=DATASHEET_EXTRACTION_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        return _normalize_response(response.json())

    except requests.Timeout:
        logger.warning(
            "Délai dépassé pendant l’envoi de la datasheet batterie."
        )

    except requests.ConnectionError:
        logger.warning(
            "Impossible de joindre le workflow d’extraction "
            "pour la datasheet batterie."
        )

    except requests.HTTPError as exc:
        status_code = getattr(
            exc.response,
            "status_code",
            "inconnu",
        )

        logger.warning(
            "Erreur HTTP pendant l’extraction de la batterie : %s.",
            status_code,
        )

    except ValueError:
        logger.warning(
            "Le workflow d’extraction de la batterie a retourné "
            "une réponse non JSON."
        )

    except (OSError, IOError) as exc:
        logger.exception(
            "Impossible de lire la datasheet batterie : %s",
            exc,
        )

    except requests.RequestException as exc:
        logger.exception(
            "Erreur réseau pendant l’envoi de la datasheet "
            "batterie : %s",
            exc,
        )

    finally:
        try:
            field_file.close()
        except Exception:
            pass

    return {}


def _extract_allowed_fields(data, allowed_fields):
    """
    Conserve uniquement les propriétés attendues.

    Cela empêche une réponse libre du workflow d’ajouter des valeurs
    imprévues directement dans les données envoyées à l’Agent 2.
    """
    if not isinstance(data, dict):
        return {}

    possible_sources = [
        data.get("extracted_data"),
        data.get("battery"),
        data.get("values"),
        data,
    ]

    source = {}

    for candidate in possible_sources:
        if isinstance(candidate, dict):
            source = candidate
            break

    extracted = {}

    for field_name in allowed_fields:
        value = source.get(field_name)

        if value not in (None, ""):
            extracted[field_name] = value

    return extracted


def extract_component_values_from_datasheet(component):
    """
    Extrait les valeurs techniques manquantes d’un composant
    depuis sa datasheet.
    """
    if not component.datasheet:
        return {}

    payload = {
        "type": "component",
        "component_name": component.name,
        "category": component.category,
        "voltage": component.voltage,
        "datasheet_url": getattr(
            component.datasheet,
            "url",
            None,
        ),
        "datasheet_path": getattr(
            component.datasheet,
            "path",
            None,
        ),
        "needed_fields": [
            "voltage",
            "nominal_current_ma",
            "cores_count",
            "freq_min_mhz",
            "freq_max_mhz",
            "freq_used_mhz",
        ],
    }

    return _call_webhook(payload)


def extract_mode_values_from_datasheet(component, mode_name):
    """
    Extrait les valeurs manquantes d’un mode depuis la datasheet
    du composant.
    """
    if not component.datasheet:
        return {}

    payload = {
        "type": "mode",
        "component_name": component.name,
        "category": component.category,
        "mode_name": mode_name,
        "datasheet_url": getattr(
            component.datasheet,
            "url",
            None,
        ),
        "datasheet_path": getattr(
            component.datasheet,
            "path",
            None,
        ),
        "needed_fields": [
            "current_ma",
            "duration_ms",
            "count_per_cycle",
            "freq_mhz",
        ],
    }

    return _call_webhook(payload)


def extract_battery_values_from_datasheet(battery_preference):
    """
    Lit localement le PDF de batterie.

    Les valeurs sont extraites à partir de libellés et d'unités explicites.
    Une valeur absente ou ambiguë n'est pas inventée.

    Cette extraction ne détermine pas le montage série/parallèle du pack
    et ne remplace pas une vérification humaine de la datasheet.
    """
    datasheet = getattr(
        battery_preference,
        "battery_datasheet",
        None,
    )

    result = {
        "provided": bool(datasheet),
        "status": "not_provided",
        "source": "datasheet" if datasheet else None,
        "filename": (
            Path(datasheet.name).name
            if datasheet
            else None
        ),
        "extraction_method": "local_pdf_label_rules",
        "extracted_data": {},
        "source_text": {},
        "field_sources": {},
        "confidence": None,
        "requires_manual_validation": True,
        "warnings": [],
    }

    if not datasheet:
        return result

    try:
        # Lecture limitée à 10 Mo, sans dépendre d'un chemin local.
        try:
            datasheet.open("rb")
            content = datasheet.read(
                10 * 1024 * 1024 + 1
            )
        finally:
            datasheet.close()

        if len(content) > 10 * 1024 * 1024:
            raise ValueError(
                "La datasheet dépasse la taille maximale de 10 Mo."
            )

        if not content.startswith(b"%PDF-"):
            raise ValueError(
                "Le fichier ne possède pas une signature PDF valide."
            )

        reader = PdfReader(
            io.BytesIO(content),
            strict=False,
        )

        if reader.is_encrypted:
            if not reader.decrypt(""):
                raise ValueError(
                    "Le PDF est protégé par un mot de passe."
                )

        if len(reader.pages) > 50:
            raise ValueError(
                "Le PDF dépasse la limite de 50 pages."
            )

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            text = page.extract_text() or ""

            # Normalisation des espaces et des retours à la ligne.
            text = re.sub(r"\s+", " ", text).strip()

            if text:
                pages.append(
                    (page_number, text)
                )

        if not pages:
            result["status"] = "no_text_found"
            result["warnings"].append(
                "Aucun texte exploitable n'a été trouvé. "
                "Le PDF peut être scanné et nécessiter un traitement OCR."
            )
            return result

        number = r"(?P<value>\d+(?:[.,]\d+)?)"

        # Les motifs associent une valeur à un libellé précis.
        # Ils ne récupèrent pas simplement le premier nombre du document.
        rules = {
            "capacity_mah": (
                r"(?:nominal|rated)\s+capacity\s*[:=]?\s*"
                + number
                + r"\s*(?P<unit>mAh|Ah)\b"
            ),
            "nominal_voltage_v": (
                r"nominal\s+voltage\s*[:=]?\s*"
                + number
                + r"\s*(?P<unit>V)\b"
            ),
            "charge_voltage_v": (
                r"charging\s+voltage\s*[:=]?\s*"
                + number
                + r"\s*(?:±\s*\d+(?:[.,]\d+)?\s*)?"
                + r"(?P<unit>V)\b"
            ),
            "cutoff_voltage_v": (
                r"discharge\s+cut[- ]?off\s+voltage\s*[:=]?\s*"
                + number
                + r"\s*(?P<unit>V)\b"
            ),
            "max_charge_current_a": (
                r"max\.?\s*charge\s+current\s*[:=]?\s*"
                + number
                + r"\s*(?P<unit>mA|A)\b"
            ),
            "max_discharge_current_a": (
                r"max\.?\s*discharge\s+current\s*[:=]?\s*"
                + number
                + r"\s*(?P<unit>mA|A)\b"
            ),
            "weight_g": (
                r"cell\s+weight\s*[:=]?\s*"
                + number
                + r"\s*(?P<unit>g)\b"
            ),
        }

        extracted = result["extracted_data"]

        for field_name, pattern in rules.items():
            candidates = []

            for page_number, text in pages:
                for match in re.finditer(
                    pattern,
                    text,
                    flags=re.IGNORECASE,
                ):
                    raw_value = match.group("value")
                    original_unit = match.group("unit")
                    unit = original_unit.lower()

                    # Une virgule peut séparer les milliers ou les
                    # décimales. Dans les capacités et courants en mA,
                    # « 3,100 mA » vaut 3100 mA ; « 0,68 mA » vaut
                    # 0,68 mA. La forme ambiguë « 1,000 » doit être
                    # confirmée par la preuve de la fiche technique.
                    if (
                        field_name in {
                            "capacity_mah",
                            "max_charge_current_a",
                            "max_discharge_current_a",
                        }
                        and unit in {"mah", "ma"}
                        and re.fullmatch(
                            r"[1-9]\d{0,2}(?:,\d{3})+",
                            raw_value,
                        )
                    ):
                        value = float(raw_value.replace(",", ""))
                    else:
                        value = float(raw_value.replace(",", "."))

                    # Conversion vers les unités attendues par le payload.
                    if unit == "ma":
                        value /= 1000.0
                    elif unit == "ah":
                        value *= 1000.0

                    if value <= 0:
                        continue

                    evidence = text[
                        max(0, match.start() - 20):
                        min(len(text), match.end() + 45)
                    ]

                    candidates.append({
                        "value": value,
                        "page": page_number,
                        "original_unit": original_unit,
                        "text": evidence,
                    })

            unique_values = {
                candidate["value"]
                for candidate in candidates
            }

            if len(unique_values) > 1:
                result["warnings"].append(
                    f"Plusieurs valeurs différentes ont été trouvées "
                    f"pour {field_name}. Ce champ doit être vérifié."
                )
                continue

            if not candidates:
                continue

            candidate = candidates[0]

            extracted[field_name] = candidate["value"]

            result["source_text"][field_name] = (
                candidate["text"]
            )

            result["field_sources"][field_name] = {
                "source": "datasheet",
                "page": candidate["page"],
                "original_unit": candidate["original_unit"],
                "requires_manual_validation": True,
            }

        # Recherche du modèle dans les libellés de couverture/en-tête.
        model_candidates = []

        for page_number, text in pages:
            for match in re.finditer(
                r"(?:Model\s*:|Spec\.\s*No\.)\s*"
                r"([A-Za-z][A-Za-z0-9._/-]*\d[A-Za-z0-9._/-]*)",
                text,
                flags=re.IGNORECASE,
            ):
                model_candidates.append({
                    "value": match.group(1),
                    "page": page_number,
                    "text": match.group(0),
                })

        models = {
            candidate["value"].upper()
            for candidate in model_candidates
        }

        if len(models) == 1:
            candidate = model_candidates[0]
            extracted["model"] = candidate["value"]

            result["source_text"]["model"] = candidate["text"]

            result["field_sources"]["model"] = {
                "source": "datasheet",
                "page": candidate["page"],
                "requires_manual_validation": True,
            }

        elif len(models) > 1:
            result["warnings"].append(
                "Plusieurs modèles apparaissent dans le document. "
                "Le modèle de batterie doit être confirmé."
            )

        # Identification limitée à des mentions explicites.
        # Aucun fabricant ou type n'est déduit du nom du fichier.
        for page_number, text in pages:
            manufacturer = re.search(
                r"\bSamsung\s+SDI\b",
                text,
                flags=re.IGNORECASE,
            )

            if manufacturer and "manufacturer" not in extracted:
                extracted["manufacturer"] = "Samsung SDI"
                result["source_text"]["manufacturer"] = (
                    manufacturer.group(0)
                )
                result["field_sources"]["manufacturer"] = {
                    "source": "datasheet",
                    "page": page_number,
                    "requires_manual_validation": True,
                }

            chemistry = re.search(
                r"\blithium[-\s]+ion\b",
                text,
                flags=re.IGNORECASE,
            )

            if chemistry and "technology" not in extracted:
                extracted["technology"] = "Li-ion"
                extracted["chemistry"] = "Lithium-ion"

                for field_name in ("technology", "chemistry"):
                    result["source_text"][field_name] = (
                        chemistry.group(0)
                    )
                    result["field_sources"][field_name] = {
                        "source": "datasheet",
                        "page": page_number,
                        "requires_manual_validation": True,
                    }

        numeric_fields = set(rules).intersection(extracted)

        result["status"] = (
            "extracted"
            if numeric_fields
            else "no_values_found"
        )

        if not numeric_fields:
            result["warnings"].append(
                "Du texte a été lu, mais aucun libellé numérique "
                "pris en charge n'a été reconnu."
            )

        for field_name in (
            "nominal_voltage_v",
            "capacity_mah",
        ):
            if field_name not in extracted:
                result["warnings"].append(
                    f"Le champ essentiel {field_name} "
                    "n'a pas pu être extrait sans ambiguïté."
                )

        if "weight_g" in extracted:
            result["warnings"].append(
                "Vérifier le qualificatif de masse dans la preuve : "
                "la valeur peut être une limite maximale."
            )

        result["warnings"].append(
            "Les valeurs extraites ne définissent pas le nombre "
            "de cellules ni leur montage série/parallèle."
        )

        logger.info(
            "Extraction locale de la batterie : statut=%s, champs=%s",
            result["status"],
            ", ".join(sorted(extracted)),
        )

        return result

    except Exception:
        logger.exception(
            "Échec de l'extraction locale de la datasheet batterie."
        )

        result["status"] = "extraction_failed"
        result["warnings"].append(
            "Impossible de lire ou d'exploiter la datasheet batterie. "
            "Consulter les journaux Django."
        )

        return result

