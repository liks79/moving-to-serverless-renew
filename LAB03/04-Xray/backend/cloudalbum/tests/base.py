"""
    cloudalbum/tests/base.py
    ~~~~~~~~~~~~~~~~~~~~~~~
    Base test cases

    :description: CloudAlbum is a fully featured sample application for 'Moving to AWS serverless' training course
    :copyright: © 2019 written by Dayoungle Jun, Sungshik Jou.
    :license: MIT, see LICENSE for more details.
"""
import hmac
import boto3
import base64
import hashlib
from cloudalbum import create_app
from cloudalbum.database import Photo
from flask_testing import TestCase


user = {
    'username': 'test001',
    'email': 'test001@testuser.com',
    'password': 'Password1!'
}


class BaseTestCase(TestCase):
    app = create_app()

    def create_app(self):
        self.app.config.from_object('cloudalbum.config.TestingConfig')
        return self.app

    def setUp(self):
        # Delete any test data that may be remained.
        for item in Photo.scan(Photo.filename_orig.startswith('test')):
            item.delete()

        # Create test user
        msg = '{0}{1}'.format(user['email'], self.app.config['COGNITO_CLIENT_ID'])
        dig = hmac.new(self.app.config['COGNITO_CLIENT_SECRET'].encode('utf-8'),
                       msg=msg.encode('utf-8'),
                       digestmod=hashlib.sha256).digest()
        try:
            cognito_client = boto3.client('cognito-idp')
            response = cognito_client.sign_up(
                ClientId=self.app.config['COGNITO_CLIENT_ID'],
                SecretHash=base64.b64encode(dig).decode(),
                Username=user['email'],
                Password=user['password'],
                UserAttributes=[{
                    'Name': 'name',
                    'Value': user['username']
                }],
                ValidationData=[{
                    'Name': 'name',
                    'Value': user['username']
                }]
            )
            username = response['UserSub']
            cognito_client.admin_confirm_sign_up(
                UserPoolId=self.app.config['COGNITO_POOL_ID'],
                Username=username
            )
        except cognito_client.exceptions.UsernameExistsException as e:
            pass

    def tearDown(self):
        # Delete test data in Photo table
        for item in Photo.scan(Photo.user_id.startswith('test')):
            item.delete()

        cognito_client = boto3.client('cognito-idp')
        response = cognito_client.admin_delete_user(
            UserPoolId=self.app.config['COGNITO_POOL_ID'],
            Username=user['email']
        )
        # Remove signed up user during the User API test
        try:
            response = cognito_client.admin_delete_user(
                UserPoolId=self.app.config['COGNITO_POOL_ID'],
                Username='test002@testuser.com'
            )
        except cognito_client.exceptions.UserNotFoundException as e:
            # Do nothing
            pass
