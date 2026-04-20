from flask import Blueprint, request, jsonify

from foms.services.channel_security import require_channel_signature

channel_functions_bp = Blueprint('channel_functions', __name__, url_prefix='/api/channel/functions')

# CT-C-01: X-Signature 검증 적용
@channel_functions_bp.before_request
@require_channel_signature
def verify_functions_signature():
    """모든 Function Endpoint에 대해 X-Signature를 검증한다."""
    pass

@channel_functions_bp.route('', methods=['POST'])
def handle_function():
    payload = request.json or {}
    method = payload.get('method')
    
    if method == 'foms':
        from foms.services.channel_quick_actions import process_foms_command
        params = payload.get('params', {})
        text = params.get('text', '')
        
        # Get manager_id from context.caller if available
        context = payload.get('context', {})
        caller = context.get('caller', {})
        manager_id = caller.get('id') if caller.get('type') == 'manager' else None
        
        response_data = process_foms_command(text, manager_id)
        return jsonify(response_data)
        
    return jsonify({"error": {"message": "Unknown method"}}), 400
