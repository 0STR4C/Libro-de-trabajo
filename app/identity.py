"""Identidad corporativa y servicios geográficos compartidos."""

from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

try:
    from .quotes import round_distance
except ImportError:
    from quotes import round_distance


ALLOWED_GOOGLE_DOMAIN = "portoservicios.com.uy"
GOOGLE_JWKS = {"expires": 0, "keys": {}}


def valid_corporate_email(value):
    email = str(value or "").strip().lower()
    return email if re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@portoservicios\.com\.uy", email, re.I) else None


def b64url_decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def google_public_keys():
    if GOOGLE_JWKS["expires"] > time.time() and GOOGLE_JWKS["keys"]:
        return GOOGLE_JWKS["keys"]
    with urlopen(Request("https://www.googleapis.com/oauth2/v3/certs", headers={"User-Agent": "CentroOperativo/1.0"}), timeout=10) as response:
        data = json.loads(response.read())
        cache = response.headers.get("Cache-Control", "")
    max_age_match = re.search(r"max-age=(\d+)", cache)
    max_age = int(max_age_match.group(1)) if max_age_match else 3600
    GOOGLE_JWKS["keys"] = {item["kid"]: item for item in data.get("keys", [])}
    GOOGLE_JWKS["expires"] = time.time() + max_age
    return GOOGLE_JWKS["keys"]


def verify_google_id_token(token, client_id, expected_nonce):
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        header = json.loads(b64url_decode(encoded_header))
        payload_data = json.loads(b64url_decode(encoded_payload))
        jwk = google_public_keys().get(header.get("kid"))
        if header.get("alg") != "RS256" or not jwk:
            raise ValueError()
        public_key = rsa.RSAPublicNumbers(
            int.from_bytes(b64url_decode(jwk["e"]), "big"),
            int.from_bytes(b64url_decode(jwk["n"]), "big"),
        ).public_key()
        public_key.verify(
            b64url_decode(encoded_signature),
            f"{encoded_header}.{encoded_payload}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        if payload_data.get("aud") != client_id or payload_data.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError()
        if int(payload_data.get("exp", 0)) <= int(time.time()) or payload_data.get("nonce") != expected_nonce:
            raise ValueError()
        if payload_data.get("email_verified") not in (True, "true") or str(payload_data.get("hd", "")).lower() != ALLOWED_GOOGLE_DOMAIN:
            raise ValueError()
        email = valid_corporate_email(payload_data.get("email"))
        if not email:
            raise ValueError()
        payload_data["email"] = email
        return payload_data
    except Exception as exc:
        raise ValueError("No se pudo verificar la identidad de Google") from exc


def parse_coordinates(value):
    text = unquote(str(value or "").strip())
    patterns = [
        r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$",
        r"!3d(-?\d{1,2}(?:\.\d+)?).*?!4d(-?\d{1,3}(?:\.\d+)?)",
        r"(?:query|q|destination|origin)=(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)",
        r"@(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            if -36.5 <= lat <= -29 and -59.5 <= lon <= -52:
                return lat, lon
    dms = re.search(r"(\d{1,2})[°º]\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NS]).*?(\d{1,3})[°º]\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([EW])", text, re.I)
    if dms:
        lat = float(dms.group(1)) + float(dms.group(2)) / 60 + float(dms.group(3)) / 3600
        lon = float(dms.group(5)) + float(dms.group(6)) / 60 + float(dms.group(7)) / 3600
        if dms.group(4).upper() == "S":
            lat = -lat
        if dms.group(8).upper() == "W":
            lon = -lon
        if -36.5 <= lat <= -29 and -59.5 <= lon <= -52:
            return lat, lon
    if text.startswith(("http://", "https://")):
        host = (urlparse(text).hostname or "").lower()
        if host.endswith(("google.com", "google.com.uy", "goo.gl", "maps.app.goo.gl")):
            try:
                response = urlopen(Request(text, headers={"User-Agent": "Mozilla/5.0"}), timeout=8)
                final = response.geturl()
                response.close()
                if final != text:
                    return parse_coordinates(final)
            except Exception:
                pass
    raise ValueError("No se pudieron obtener coordenadas. Use un enlace de Google Maps que incluya la ubicación o escriba latitud,longitud.")


def route_data(start, end):
    lat1, lon1 = start
    lat2, lon2 = end
    url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson&alternatives=false&steps=false"
    try:
        with urlopen(Request(url, headers={"User-Agent": "CentroOperativo/1.0"}), timeout=15) as response:
            data = json.loads(response.read())
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError()
        route = data["routes"][0]
        return {"km": round_distance(route["distance"] / 1000), "coordinates": route.get("geometry", {}).get("coordinates", [])}
    except Exception as exc:
        raise ValueError("No se pudo calcular la ruta automáticamente. Verifique las ubicaciones o use la distancia manual.") from exc


def route_km(start, end):
    return route_data(start, end)["km"]
