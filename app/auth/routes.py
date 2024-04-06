from flask import Blueprint, request, redirect, render_template, url_for, session, jsonify
from .utils import verify_id_token

auth_blueprint = Blueprint('auth', __name__)

@auth_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        id_token = data.get('idToken')

        if not id_token:
            return jsonify({'error': 'No ID token provided'}), 400

        user = verify_id_token(id_token)

        if user:
            session['user'] = user
            print(session['user'])
            return redirect(url_for('.access_granted'))
        else:
            return 'Login Failed', 401
    return render_template('login.html')

@auth_blueprint.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('.login'))

@auth_blueprint.route('/access_granted')
def access_granted():
    if 'user' not in session:
        return redirect(url_for('.login'))
    return render_template('access_granted.html')
