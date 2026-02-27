import json
import logging
import os
import time

import dotenv
import requests
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from client_payload import CasePayload, ClientPayload

dotenv.load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CALLBACK_URL = os.getenv("CALLBACK_URL")
API_KEY = os.getenv("API_KEY")
SCOPE = os.getenv("SCOPE")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


logging.basicConfig(
    level=logging.INFO,  # Could be DEBUG for more verbosity
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


logging.info(app)

TOKENS_FILE = "tokens.json"


def _load_tokens() -> dict:
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE) as f:
            return json.load(f)
    return {}


def _save_tokens() -> None:
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f)


tokens = _load_tokens()

token_url = "https://oauth.acreplatforms.co.uk/oauth2/token"
refresh_url = "https://oauth.acreplatforms.co.uk/oauth2/auth/refresh"

oauth = OAuth()
acre_auth = oauth.register(
    name="acre",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    access_token_url=token_url,
    authorize_url="https://oauth.acreplatforms.co.uk/oauth2/auth",
    redirect_uri="CALLBACK_URL",
    client_kwargs={
        "scope": "offline_access",
        "token_endpoint_auth_method": "client_secret_post",
    },
)


@app.get("/login")
async def login(request: Request):
    return await acre_auth.authorize_redirect(request, CALLBACK_URL)


@app.get("/callback")
async def callback(request: Request):
    logging.info("Callback using client_id: %s", CLIENT_ID)
    token = await acre_auth.authorize_access_token(request)
    print(token)
    access_token = token["access_token"]
    refresh_token = token["refresh_token"]
    expires_at = token["expires_at"]
    print("expires at: ", expires_at)
    tokens["access_token"] = access_token
    tokens["refresh_token"] = refresh_token
    tokens["expires_at"] = expires_at
    _save_tokens()
    return {"access_token": access_token, "refresh_token": refresh_token}


@app.get("/")
async def root():

    return {"status": "okay"}


@app.get("/home", response_class=HTMLResponse)
async def homepage():
    return """
    <h1>Acre OAuth Test App</h1>
    <p><a href="/login">Login with Acre</a></p>
    """


def _do_refresh() -> str:
    """Exchange the stored refresh token for a new access token.

    Returns the new access token.
    """
    if not tokens.get("refresh_token"):
        raise HTTPException(
            status_code=401, detail="No refresh token available. Visit /login first."
        )

    response = requests.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )
    if not response.ok:
        logging.error(
            "Token refresh failed %s: %s", response.status_code, response.text
        )
    response.raise_for_status()
    token_data = response.json()

    tokens["access_token"] = token_data["access_token"]
    if "refresh_token" in token_data:
        tokens["refresh_token"] = token_data["refresh_token"]
    if "expires_at" in token_data:
        tokens["expires_at"] = token_data["expires_at"]
    _save_tokens()

    logging.info("Access token refreshed successfully.")
    return tokens["access_token"]


def get_valid_access_token() -> str:
    """Return a valid access token, refreshing proactively if expired or near expiry."""
    expires_at = tokens.get("expires_at")
    if not tokens.get("access_token") or (
        expires_at is not None and time.time() > expires_at - 60
    ):
        return _do_refresh()
    return tokens["access_token"]


@app.get("/refresh")
async def refresh_route():
    """Manually trigger a token refresh (useful for testing)."""
    new_token = _do_refresh()
    return {"access_token": new_token}


@app.post("/client")
async def create_client(payload: ClientPayload):
    access_token = get_valid_access_token()

    client_url = "https://api.acreplatforms.co.uk/v1/acre/client"

    first_name, last_name = payload.contact_name.split(" ", 1)
    body = {
        "client": {
            "details": {
                "first_name": first_name,
                "last_name": last_name,
                "contact_details_email": payload.email_address,
                "contact_details_mobile_phone": payload.number,
            }
        }
    }

    response = requests.post(
        client_url,
        json=body,
        headers={"X-API-KEY": API_KEY},
        cookies={"authorization": access_token},
    )

    if response.status_code == 401:
        # Token was rejected — refresh once and retry
        logging.info("Refreshed token")
        access_token = _do_refresh()
        response = requests.post(
            client_url,
            json=body,
            headers={"X-API-KEY": API_KEY},
            cookies={"authorization": access_token},
        )

    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logging.error("Acre API error %s: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.post("/case")
async def create_case(payload: CasePayload):
    access_token = get_valid_access_token()

    case_url = "https://api.acreplatforms.co.uk/v1/acre/case"

    details: dict = {"client_ids": payload.client_ids}
    if payload.owner_user_id:
        details["owner_user_id"] = payload.owner_user_id

    body = {"case": {"details": details}}

    response = requests.post(
        case_url,
        json=body,
        headers={"X-API-KEY": API_KEY},
        cookies={"authorization": access_token},
    )

    if response.status_code == 401:
        logging.info("Refreshed token")
        access_token = _do_refresh()
        response = requests.post(
            case_url,
            json=body,
            headers={"X-API-KEY": API_KEY},
            cookies={"authorization": access_token},
        )

    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logging.error("Acre API error %s: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()
