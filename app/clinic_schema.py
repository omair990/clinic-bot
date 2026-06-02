"""Canonical clinic_data schema — validate + normalize.

`clinic_data` is per-tenant JSONB consumed by the agent (`app/prompts.py`) and the
booking tools (`app/tools.py`). The tools index service/doctor/faq fields *directly*
(`s["price_sar"]`, `d["specialty"]`, `d["available_days"]`, `f["q"]`), so a missing or
mistyped field doesn't degrade gracefully — it raises mid-conversation on a live tool
call. This module is the single contract that prevents that:

- ``normalize(data)``  — coerce loose types (price ``"150"`` → ``150``), fill safe
  defaults, split comma-strings into lists, drop fully-empty rows. Never raises.
- ``validate(data)``   — return ``(errors, warnings)``. *errors* block the save
  (required field missing / wrong type the normalizer couldn't coerce); *warnings* are
  soft (no services yet, duplicate names, unknown weekday) and never block.
- ``validate_and_normalize(data)`` — the one call the save path uses.

Pure functions, no third-party deps (the repo has no pydantic). Unknown top-level keys
(``branches``, ``timings``, ``emergency_guidance``, ``booking_fields``, ``connector``)
are preserved untouched so the guided editor, the Advanced-JSON box, and the Connector
page round-trip cleanly. Connector validation lives in ``app/connectors.py``.
"""
from __future__ import annotations

# Canonical weekday names, as doctors' available_days are matched against the booking
# calendar by title-cased name elsewhere.
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_DAY_LOOKUP = {d.lower(): d for d in DAYS}

# Top-level sections the guided editor owns; everything else is passed through.
_GUIDED_KEYS = ("clinic", "services", "doctors", "appointment_policy", "faqs")


# --------------------------------------------------------------------------- helpers
def _s(v) -> str:
    """A trimmed string, tolerant of None/numbers."""
    if v is None:
        return ""
    return str(v).strip()


def _as_list(v) -> list:
    """Coerce a value into a list: a comma-separated string splits; a list passes
    through; anything else (incl. None) becomes empty."""
    if isinstance(v, list):
        return [x for x in v]
    if isinstance(v, str):
        return [p.strip() for p in v.split(",") if p.strip()]
    if v is None:
        return []
    return [v]


def _str_list(v) -> list[str]:
    return [_s(x) for x in _as_list(v) if _s(x)]


def _num(v):
    """Return an int/float if v is a number or numeric string, else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    s = _s(v)
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def _as_bool(v):
    if isinstance(v, bool):
        return v
    s = _s(v).lower()
    if s in ("true", "yes", "1", "on"):
        return True
    if s in ("false", "no", "0", "off", ""):
        return False
    return None


def _row_is_empty(row: dict) -> bool:
    return not any(_s(x) for x in row.values()) if isinstance(row, dict) else not _s(row)


# --------------------------------------------------------------------------- normalize
def normalize(data) -> dict:
    """Return a cleaned copy of ``data``. Never raises; best-effort coercion only.
    Type problems the coercion can't fix are left in place for :func:`validate`."""
    if not isinstance(data, dict):
        return {}
    out = dict(data)  # preserve unknown/pass-through keys (branches, connector, …)

    # clinic
    clinic = data.get("clinic")
    if isinstance(clinic, dict):
        c = {k: (_s(v) if isinstance(v, str) else v) for k, v in clinic.items()}
        if "languages" in c:
            c["languages"] = _str_list(c["languages"])
        if "default_language" in c:
            c["default_language"] = _s(c.get("default_language"))
        out["clinic"] = c
    elif clinic is not None:
        out["clinic"] = clinic  # wrong type; validate() will flag it

    # services
    if "services" in out:
        svcs = []
        for s in _as_list(data.get("services")):
            if not isinstance(s, dict) or _row_is_empty(s):
                if isinstance(s, dict):
                    continue  # drop blank rows the editor left behind
                svcs.append(s)
                continue
            row = dict(s)
            row["name"] = _s(s.get("name"))
            if (n := _num(s.get("price_sar"))) is not None:
                row["price_sar"] = n
            if (n := _num(s.get("duration_min"))) is not None:
                row["duration_min"] = n
            svcs.append(row)
        out["services"] = svcs

    # doctors
    if "doctors" in out:
        docs = []
        for d in _as_list(data.get("doctors")):
            if not isinstance(d, dict) or _row_is_empty(d):
                if isinstance(d, dict):
                    continue
                docs.append(d)
                continue
            row = dict(d)
            row["name"] = _s(d.get("name"))
            row["specialty"] = _s(d.get("specialty"))
            row["available_hours"] = _s(d.get("available_hours"))
            row["available_days"] = [_DAY_LOOKUP.get(x.lower(), x)
                                     for x in _str_list(d.get("available_days"))]
            if "languages" in d:
                row["languages"] = _str_list(d.get("languages"))
            docs.append(row)
        out["doctors"] = docs

    # appointment_policy
    pol = data.get("appointment_policy")
    if isinstance(pol, dict):
        p = dict(pol)
        for k in ("booking_lead_time_hours", "cancellation_notice_hours"):
            if k in p and (n := _num(p[k])) is not None:
                p[k] = n
        if "walk_ins_accepted" in p and (b := _as_bool(p["walk_ins_accepted"])) is not None:
            p["walk_ins_accepted"] = b
        if "payment_methods" in p:
            p["payment_methods"] = _str_list(p["payment_methods"])
        if "walk_in_note" in p:
            p["walk_in_note"] = _s(p["walk_in_note"])
        out["appointment_policy"] = p
    elif pol is not None:
        out["appointment_policy"] = pol

    # faqs
    if "faqs" in out:
        faqs = []
        for f in _as_list(data.get("faqs")):
            if not isinstance(f, dict):
                faqs.append(f)
                continue
            if _row_is_empty(f):
                continue
            faqs.append({**f, "q": _s(f.get("q")), "a": _s(f.get("a"))})
        out["faqs"] = faqs

    return out


# --------------------------------------------------------------------------- validate
def validate(data) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for an already-normalized ``data``.
    Errors block the save; warnings are advisory. Paths use ``section[i].field``."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["Clinic data must be a JSON object."], []

    # clinic ---------------------------------------------------------------
    clinic = data.get("clinic", {})
    if not isinstance(clinic, dict):
        errors.append("clinic: must be an object.")
    else:
        if not _s(clinic.get("name")):
            errors.append("clinic.name: required (the clinic's display name).")
        dl = _s(clinic.get("default_language"))
        langs = clinic.get("languages") or []
        if dl and isinstance(langs, list) and langs and dl not in langs:
            warnings.append(f"clinic.default_language: \"{dl}\" is not in the clinic's "
                            "languages list — add it there so staff see it as supported.")

    # services -------------------------------------------------------------
    services = data.get("services", [])
    if not isinstance(services, list):
        errors.append("services: must be a list.")
    else:
        seen = set()
        for i, s in enumerate(services):
            p = f"services[{i}]"
            if not isinstance(s, dict):
                errors.append(f"{p}: must be an object with name/price_sar/duration_min.")
                continue
            name = _s(s.get("name"))
            if not name:
                errors.append(f"{p}.name: required.")
            else:
                key = name.lower()
                if key in seen:
                    warnings.append(f"{p}.name: duplicate service \"{name}\".")
                seen.add(key)
            if not isinstance(s.get("price_sar"), (int, float)) or isinstance(s.get("price_sar"), bool):
                errors.append(f"{p}.price_sar: required, must be a number "
                              f"(got {s.get('price_sar')!r}).")
            elif s["price_sar"] < 0:
                errors.append(f"{p}.price_sar: must not be negative.")
            if not isinstance(s.get("duration_min"), int) or isinstance(s.get("duration_min"), bool):
                errors.append(f"{p}.duration_min: required, must be a whole number of "
                              f"minutes (got {s.get('duration_min')!r}).")
            elif s["duration_min"] <= 0:
                errors.append(f"{p}.duration_min: must be greater than zero.")
        if not services:
            warnings.append("services: none defined — the assistant can't quote prices "
                            "or set slot lengths.")

    # doctors --------------------------------------------------------------
    doctors = data.get("doctors", [])
    if not isinstance(doctors, list):
        errors.append("doctors: must be a list.")
    else:
        seen = set()
        for i, d in enumerate(doctors):
            p = f"doctors[{i}]"
            if not isinstance(d, dict):
                errors.append(f"{p}: must be an object.")
                continue
            name = _s(d.get("name"))
            if not name:
                errors.append(f"{p}.name: required.")
            else:
                if name.lower() in seen:
                    warnings.append(f"{p}.name: duplicate doctor \"{name}\".")
                seen.add(name.lower())
            if not _s(d.get("specialty")):
                errors.append(f"{p}.specialty: required.")
            days = d.get("available_days")
            if not isinstance(days, list) or not days:
                errors.append(f"{p}.available_days: required, a non-empty list of weekdays.")
            else:
                for day in days:
                    if _s(day).lower() not in _DAY_LOOKUP:
                        warnings.append(f"{p}.available_days: \"{day}\" is not a recognised "
                                        f"weekday (expected one of {', '.join(DAYS)}).")
            if not _s(d.get("available_hours")):
                errors.append(f"{p}.available_hours: required, e.g. \"5:00 PM - 9:00 PM\".")
        if not doctors:
            warnings.append("doctors: none defined — the assistant can't offer availability "
                            "or book appointments.")

    # appointment_policy ---------------------------------------------------
    pol = data.get("appointment_policy", {})
    if not isinstance(pol, dict):
        errors.append("appointment_policy: must be an object.")
    else:
        for k in ("booking_lead_time_hours", "cancellation_notice_hours"):
            if k in pol and pol[k] is not None:
                if not isinstance(pol[k], (int, float)) or isinstance(pol[k], bool):
                    errors.append(f"appointment_policy.{k}: must be a number of hours "
                                  f"(got {pol[k]!r}).")
                elif pol[k] < 0:
                    errors.append(f"appointment_policy.{k}: must not be negative.")
        if "walk_ins_accepted" in pol and not isinstance(pol["walk_ins_accepted"], bool):
            errors.append("appointment_policy.walk_ins_accepted: must be true or false.")
        if "payment_methods" in pol and not isinstance(pol["payment_methods"], list):
            errors.append("appointment_policy.payment_methods: must be a list.")

    # faqs -----------------------------------------------------------------
    faqs = data.get("faqs", [])
    if not isinstance(faqs, list):
        errors.append("faqs: must be a list.")
    else:
        for i, f in enumerate(faqs):
            p = f"faqs[{i}]"
            if not isinstance(f, dict):
                errors.append(f"{p}: must be an object with q/a.")
                continue
            if not _s(f.get("q")):
                errors.append(f"{p}.q: question text required.")
            if not _s(f.get("a")):
                errors.append(f"{p}.a: answer text required.")

    return errors, warnings


def validate_and_normalize(data) -> tuple[dict, list[str], list[str]]:
    """Normalize, then validate the normalized form. The save path's single entry point."""
    if data is not None and not isinstance(data, dict):
        return {}, ["Clinic data must be a JSON object."], []
    norm = normalize(data)
    errors, warnings = validate(norm)
    return norm, errors, warnings


def blank_template() -> dict:
    """A minimal valid skeleton for a brand-new clinic (used by the editor's reset)."""
    return {
        "clinic": {"name": "", "address": "", "phone": "", "languages": ["Arabic", "English"],
                   "default_language": "Arabic"},
        "services": [],
        "doctors": [],
        "appointment_policy": {
            "booking_lead_time_hours": 2, "cancellation_notice_hours": 4,
            "walk_ins_accepted": True, "payment_methods": ["Cash", "Card", "mada"]},
        "faqs": [],
    }


def summary(data) -> dict:
    """Small counts for the editor header / inventory display."""
    data = data if isinstance(data, dict) else {}
    return {
        "services": len(data.get("services") or []),
        "doctors": len(data.get("doctors") or []),
        "faqs": len(data.get("faqs") or []),
        "branches": len(data.get("branches") or []),
        "connector": (data.get("connector") or {}).get("type", "native"),
    }
