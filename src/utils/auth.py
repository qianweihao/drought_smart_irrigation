from functools import wraps
from flask import request, jsonify
from jwt import decode, InvalidTokenError
import os
import sys

project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.append(project_root)

from .logger import logger
from src.config.config import get_config

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        config = get_config()
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': '无效的认证头'}), 401
                
        if not token:
            return jsonify({'message': '缺少认证token'}), 401
            
        try:
            decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        except InvalidTokenError:
            return jsonify({'message': '无效的token'}), 401
            
        return f(*args, **kwargs)
    return decorated

def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        config = get_config()
        
        if not api_key or api_key != config.SECRET_KEY:
            return jsonify({'message': '无效的API密钥'}), 401
            
        return f(*args, **kwargs)
    return decorated