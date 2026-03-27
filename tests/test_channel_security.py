import json
import hmac
import hashlib
import time
import os
from flask import Flask
import pytest

from services.channel_security import (
    generate_wam_short_link_token,
    verify_channel_signature,
    require_channel_signature,
    generate_wam_launch_token,
    verify_wam_launch_token,
    verify_wam_short_link_token,
)

@pytest.fixture
def test_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    @app.route('/test-webhook', methods=['POST'])
    @require_channel_signature
    def test_webhook():
        from flask import jsonify
        return jsonify({"success": True})
        
    return app

def test_verify_channel_signature_success(monkeypatch):
    monkeypatch.setenv('CHANNEL_SIGNING_KEY', 'test-secret')
    
    # Reload module variable that was loaded at import time
    import services.channel_security
    monkeypatch.setattr(services.channel_security, 'CHANNEL_SIGNING_KEY', 'test-secret')
    
    payload = b'{"hello":"world"}'
    
    # Compute valid signature
    valid_signature = hmac.new(
        b'test-secret',
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    assert verify_channel_signature(payload, valid_signature) is True

def test_verify_channel_signature_failure(monkeypatch):
    monkeypatch.setenv('CHANNEL_SIGNING_KEY', 'test-secret')
    import services.channel_security
    monkeypatch.setattr(services.channel_security, 'CHANNEL_SIGNING_KEY', 'test-secret')
    
    payload = b'{"hello":"world"}'
    invalid_signature = 'invalid1234'
    
    assert verify_channel_signature(payload, invalid_signature) is False

def test_require_channel_signature_middleware_success(test_app, monkeypatch):
    monkeypatch.setenv('CHANNEL_SIGNING_KEY', 'test-secret')
    import services.channel_security
    monkeypatch.setattr(services.channel_security, 'CHANNEL_SIGNING_KEY', 'test-secret')
    
    client = test_app.test_client()
    payload = b'{"hello":"world"}'
    valid_signature = hmac.new(
        b'test-secret',
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    response = client.post('/test-webhook', data=payload, headers={'x-signature': valid_signature})
    assert response.status_code == 200
    assert response.json['success'] is True

def test_require_channel_signature_middleware_missing_header(test_app, monkeypatch):
    monkeypatch.setenv('CHANNEL_SIGNING_KEY', 'test-secret')
    import services.channel_security
    monkeypatch.setattr(services.channel_security, 'CHANNEL_SIGNING_KEY', 'test-secret')
    
    client = test_app.test_client()
    response = client.post('/test-webhook', data=b'{}')
    assert response.status_code == 401
    assert response.json['error'] == 'unauthorized'

def test_require_channel_signature_middleware_invalid_signature(test_app, monkeypatch):
    monkeypatch.setenv('CHANNEL_SIGNING_KEY', 'test-secret')
    import services.channel_security
    monkeypatch.setattr(services.channel_security, 'CHANNEL_SIGNING_KEY', 'test-secret')
    
    client = test_app.test_client()
    response = client.post('/test-webhook', data=b'{}', headers={'x-signature': 'bad'})
    assert response.status_code == 401
    assert response.json['error'] == 'unauthorized'

def test_replay_attack_prevention(test_app, monkeypatch):
    monkeypatch.setenv('CHANNEL_SIGNING_KEY', 'test-secret')
    import services.channel_security
    monkeypatch.setattr(services.channel_security, 'CHANNEL_SIGNING_KEY', 'test-secret')
    
    # Create payload with timestamp 10 minutes ago
    old_time_ms = (time.time() - 600) * 1000
    payload_dict = {"entity": {"createdAt": old_time_ms}}
    payload = json.dumps(payload_dict).encode('utf-8')
    
    valid_signature = hmac.new(
        b'test-secret',
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    client = test_app.test_client()
    response = client.post(
        '/test-webhook', 
        data=payload, 
        headers={'x-signature': valid_signature, 'Content-Type': 'application/json'}
    )
    assert response.status_code == 403
    assert response.json['error'] == 'forbidden'
    assert 'timestamp out of valid window' in response.json['message']

def test_wam_token_generation_and_verification():
    token = generate_wam_launch_token('manager_123', 456)
    assert token is not None
    
    payload = verify_wam_launch_token(token)
    assert payload is not None
    assert payload['manager_id'] == 'manager_123'
    assert payload['order_id'] == 456
    
def test_wam_token_expiration(monkeypatch):
    token = generate_wam_launch_token('mgr', 1)
    
    # max_age = -1 should immediately expire it
    payload = verify_wam_launch_token(token, max_age=-1)
    assert payload is None


def test_wam_short_link_generation_and_verification():
    token = generate_wam_short_link_token(456)
    assert token is not None

    payload = verify_wam_short_link_token(token)
    assert payload is not None
    assert payload['order_id'] == 456


def test_wam_short_link_expiration():
    token = generate_wam_short_link_token(1)

    payload = verify_wam_short_link_token(token, max_age=-1)
    assert payload is None
