"""
    cloudalbum/api/users.py
    ~~~~~~~~~~~~~~~~~~~~~~~
    REST API for users

    :description: CloudAlbum is a fully featured sample application for 'Moving to AWS serverless' training course
    :copyright: © 2019 written by Dayoungle Jun, Sungshik Jou.
    :license: MIT, see LICENSE for more details.
"""
import hashlib
import boto3, hmac, base64
from botocore.exceptions import ClientError
from flask import Blueprint, request
from flask import current_app as app
from flask import jsonify, make_response
from flask_restplus import Api, Resource, fields
from jsonschema import ValidationError
from werkzeug.exceptions import InternalServerError, BadRequest, Conflict

from cloudalbum.schemas import validate_user
from cloudalbum.solution import solution_signup_cognito
from cloudalbum.util.jwt_helper import get_token_from_header, cog_jwt_required


users_blueprint = Blueprint('users', __name__)
api = Api(users_blueprint, doc='/swagger/', title='Users',
          description='CloudAlbum-users: \n prefix url "/users" is already exist.', version='0.1')


response = api.model('Response', {
    'code': fields.Integer,
    'message': fields.String,
    'data': fields.String
})

signup_user = api.model('Signup_user', {
    'email': fields.String,
    'username': fields.String,
    'password': fields.String
})

signin_user = api.model('Signin_user', {
    'email': fields.String,
    'password': fields.String
})


@api.route('/ping')
class Ping(Resource):
    @api.doc(responses={200: 'pong!'})
    def get(self):
        """Ping api"""
        app.logger.debug('success:ping pong!')
        return make_response({'ok': True, 'Message': 'pong'}, 200)


@api.route('/', strict_slashes=False)
class UsersList(Resource):
    @api.doc(
        responses=
            {
                200: 'Return the whole users list',
                500: 'Internal server error'
            }
        )
    def get(self):
        """Get all users as list"""
        try:
            client = boto3.client('cognito-idp')
            response = client.list_users(
                UserPoolId=app.config['COGNITO_POOL_ID'],
                AttributesToGet=['sub', 'email', 'name']
            )
            data = []
            for user in response['Users']:
                one_user = {}
                for attr in user['Attributes']:
                    key = attr['Name']
                    if key == 'sub':
                        key = 'user_id'
                    one_user[key] = attr['Value']
                data.append(one_user)

            app.logger.debug('success:users_list: {0}'.format(data))
            return make_response({'ok': True, 'users': data}, 200)

        except Exception as e:
            app.logger.error('users list failed')
            app.logger.error(e)
            raise InternalServerError('Retrieve user list failed')


@api.route('/<user_id>')
class Users(Resource):
    @api.doc(responses={
                200: 'Return a user data',
                500: 'Internal server error'
            })
    def get(self, user_id):
        """Get a single user details"""
        client = boto3.client('cognito-idp')
        try:
            response = client.admin_get_user(
                UserPoolId=app.config['COGNITO_POOL_ID'],
                Username=user_id
            )
            user_data ={}
            for attr in response['UserAttributes']:
                key = attr['Name']
                if key == 'sub':
                    key = 'user_id'
                val = attr['Value']
                user_data[key] = val
            app.logger.debug('success: get Cognito user data: {}'.format(user_data))
            return make_response({'ok': True, 'users': user_data}, 200)
        except ValueError as e:
            app.logger.error('ERROR:user_get_by_id:{}'.format(user_id))
            app.logger.error(e)
            raise BadRequest(e)
        except Exception as e:
            app.logger.error('ERROR:user_get_by_id:{}'.format(user_id))
            app.logger.error(e)
            raise InternalServerError('Unexpected Error:{0}'.format(e))


def cognito_signup(signup_user):
    user = signup_user;
    msg = '{0}{1}'.format(user['email'], app.config['COGNITO_CLIENT_ID'])
    dig = hmac.new(app.config['COGNITO_CLIENT_SECRET'].encode('utf-8'),
                   msg=msg.encode('utf-8'),
                   digestmod=hashlib.sha256).digest()
    # TODO 7: Implement following solution code to sign up user into cognito user pool
    try:
        return solution_signup_cognito(user, dig)
    except ClientError as e:
        if e.response['Error']['Code'] == 'UsernameExistsException':
            raise Conflict('ERROR: Existed user!')
    except Exception as e:
        raise BadRequest(e.response['Error']['Message'])


@api.route('/signup')
class Signup(Resource):
    @api.doc(responses={
        201: 'Return a user data',
        400: 'Invalidate email/password',
        500: 'Internal server error'
    })
    @api.expect(signup_user)
    def post(self):
        """Enroll a new user"""
        req_data = request.get_json()
        try:
            validated = validate_user(req_data)
            user_data = validated['data']
            user = cognito_signup(user_data)
            app.logger.debug('success: enroll user into Cognito user pool:{}'.format(user))
            return make_response({'ok': True, 'users': user}, 201)

        except ValidationError as e:
            app.logger.error('ERROR:invalid signup data format:{0}'.format(req_data))
            app.logger.error(e)
            raise BadRequest(e.message)


def cognito_signin(cognito_client, user):
    msg = '{0}{1}'.format(user['email'], app.config['COGNITO_CLIENT_ID'])
    dig = hmac.new(app.config['COGNITO_CLIENT_SECRET'].encode('utf-8'),
                   msg=msg.encode('utf-8'),
                   digestmod=hashlib.sha256).digest()
    auth= base64.b64encode(dig).decode()
    resp = cognito_client.admin_initiate_auth(UserPoolId=app.config['COGNITO_POOL_ID'],
                                      ClientId=app.config['COGNITO_CLIENT_ID'],
                                      AuthFlow='ADMIN_NO_SRP_AUTH',
                                      AuthParameters={'SECRET_HASH': auth,'USERNAME': user['email'], 'PASSWORD': user['password']})
    access_token = resp['AuthenticationResult']['AccessToken']
    refresh_token = resp['AuthenticationResult']['RefreshToken']
    return access_token, refresh_token


@api.route('/signin')
class Signin(Resource):
    @api.doc(responses={
        200: 'login success',
        400: 'Invalidate data',
        500: 'Internal server error'
    })
    @api.expect(signin_user)
    def post(self):
        """user signin"""
        req_data = request.get_json()
        client = boto3.client('cognito-idp')
        try:
            signin_data = validate_user(req_data)['data']
            access_token, refresh_token = cognito_signin(client, signin_data)
            res = jsonify({'accessToken': access_token, 'refreshToken': refresh_token})
            app.logger.debug('success:user signin:access_token:{}, refresh_token:{}'.format(access_token, refresh_token))
            return make_response(res, 200)

        except client.exceptions.UserNotFoundException as e:
            app.logger.error('User does not exist: {0}'.format(signin_data))
            app.logger.error(e)
            raise BadRequest('User does not exist')
        except client.exceptions.NotAuthorizedException as e:
            app.logger.error('Password is mismatched or invalid user: {0}'.format(signin_data))
            app.logger.error(e)
            raise BadRequest('Password is mismatched or invalid user')
        except ValidationError as e:
            app.logger.error('Invalid data format: {0}'.format(req_data))
            app.logger.error(e)
            raise BadRequest(e.message)
        except Exception as e:
            app.logger.error('Unexpected error: {0}'.format(req_data))
            app.logger.error(e)
            raise InternalServerError('Unexpected error: {0}'.format(req_data))


@api.route('/signout')
class Signout(Resource):
    @cog_jwt_required
    @api.doc(responses={
        200: 'signout success',
        500: 'login required'
    })
    def post(self):
        """user signout"""
        token = get_token_from_header(request)
        try:
            client = boto3.client('cognito-idp')
            response = client.global_sign_out(
                AccessToken=token
            )
            app.logger.debug('Access token expired: {}'.format(token))
            return make_response({'ok': True}, 200)
        except Exception as e:
            app.logger.error('Sign-out:unknown issue:token:{}'.format(token))
            app.logger.error(e)
            raise InternalServerError(e)
