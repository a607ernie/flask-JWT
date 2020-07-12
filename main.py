import redis
import json
from datetime import timedelta
from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token, get_jti,
    jwt_refresh_token_required, get_jwt_identity, jwt_required, get_raw_jwt,decode_token
)

app = Flask(__name__)
app.secret_key = 'ChangeMe!'

# Setup the flask-jwt-extended extension. See:
ACCESS_EXPIRES = timedelta(minutes=1)
app.config['JWT_TOKEN_LOCATION'] = ['query_string']
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = ACCESS_EXPIRES
app.config['JWT_BLACKLIST_ENABLED'] = True
app.config['JWT_BLACKLIST_TOKEN_CHECKS'] = ['access', 'refresh']
jwt = JWTManager(app)

# Setup our redis connection for storing the blacklisted tokens
revoked_store = redis.StrictRedis(host='localhost', port=6379, db=0,
                                  decode_responses=True)

user_store = redis.StrictRedis(host='localhost', port=6379, db=1,
                                  decode_responses=True)


@jwt.token_in_blacklist_loader
def check_if_token_is_revoked(decrypted_token):
    jti = decrypted_token['jti']
    entry = revoked_store.get(jti)
    if entry is None:
        return True
    return entry == 'true'


@app.route('/auth/login', methods=['POST'])
def login():
    username = request.json.get('username', None)
    password = request.json.get('password', None)

    #check this user in redis, if yes then revoke
    if user_store.exists(username) > 0:
        access_jti = user_store.get(username)
        jti = get_jti(access_jti)
        revoked_store.set(jti, 'true', ACCESS_EXPIRES * 0.1)

    #if no , login first
    #check this user in user.json , if no , return "This user was rejected"
    else:
        with open('user.json','r') as f:
            jsonfile = json.loads(f.read())
            if username not in jsonfile['user']:
                return "This user was rejected"

    # Create our JWTs
    access_token = create_access_token(identity=username)
    access_jti = get_jti(encoded_token=access_token)


    revoked_store.set(access_jti,'false', ACCESS_EXPIRES * 1.2)
    user_store.set(username,access_token,ACCESS_EXPIRES * 1.2)
    
    ret = {
        'access_token': access_token
    }
    return jsonify(ret), 201


# Endpoint for revoking the current users access token
@app.route('/auth/access_revoke', methods=['DELETE'])
@jwt_required
def logout():
    jti = get_raw_jwt()['jti']
    revoked_store.set(jti, 'true', ACCESS_EXPIRES * 0.1)
    return jsonify({"msg": "Access token revoked"}), 200



# A blacklisted access token will not be able to access this any more
@app.route('/protected', methods=['GET'])
@jwt_required
def protected():
    username = get_jwt_identity()
    return jsonify(logged_in_as=username), 200



if __name__ == '__main__':
    app.run(debug=True)