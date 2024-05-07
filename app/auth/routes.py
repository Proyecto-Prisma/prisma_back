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
    id_token = data.get("id_token", "")

    if not id_token:
        return jsonify({"error": "ID token is required"}), 400

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        return jsonify({"uid": uid, "email": decoded_token.get("email", "")}), 200
    except exceptions.FirebaseError as e:
        return jsonify({"error": str(e)}), 500


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
