import firebase_admin
from firebase_admin import credentials
from firebase_admin import auth

cred = credentials.Certificate('app/NO_SEGURO/prisma-58a39-firebase-adminsdk-omwbz-ca1f403bc3.json')
firebase_admin.initialize_app(cred)

def verify_id_token(token):
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(e)
        return None
