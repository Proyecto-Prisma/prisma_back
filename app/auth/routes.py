from flask import (
    Blueprint,
    request,
    redirect,
    render_template,
    url_for,
    session,
    jsonify,
)
from .utils import verify_id_token
import requests
from firebase_admin import auth, exceptions  # type: ignore

auth_blueprint = Blueprint("auth", __name__)


@auth_blueprint.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "")
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Correo y contraseña son requeridos"}), 400

    payload = {"email": email, "password": password, "returnSecureToken": True}

    api_url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    params = {"key": "AIzaSyDMqn9X38QQQ_FQLEVsKd3XCMDfDaNGVnc"}

    response = requests.post(api_url, params=params, json=payload)

    if response.status_code == 200:
        id_token = response.json().get("idToken")
        return jsonify({"token": id_token}), 200
    else:
        error_message = (
            response.json().get("error", {}).get("message", "Error de autenticación")
        )
        return jsonify({"error": error_message}), response.status_code


@auth_blueprint.route("/verify_token", methods=["POST"])
def verify_token():
    data = request.get_json()
    id_token = data.get("token")

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]

        user = auth.get_user(uid)

        return (
            jsonify(
                {
                    "uid": uid,
                    "email": user.email,
                    "roles": decoded_token.get("claims", {}).get("roles", []),
                }
            ),
            200,
        )
    except exceptions.FirebaseError as e:
        return jsonify({"error": str(e)}), 401


@auth_blueprint.route("/logout", methods=["GET", "POST"])
def logout():
    return jsonify({"message": "Logout successful"}), 200


@auth_blueprint.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    api_url = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
    params = {"key": "AIzaSyDMqn9X38QQQ_FQLEVsKd3XCMDfDaNGVnc"}

    payload = {"email": email, "password": password, "returnSecureToken": True}

    response = requests.post(api_url, params=params, json=payload)

    if response.status_code == 200:
        user_data = response.json()
        return jsonify(user_data), 200
    else:
        return jsonify(response.json()), response.status_code
