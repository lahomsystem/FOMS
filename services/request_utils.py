"""요청 관련 유틸리티 (get_preserved_filter_args 등)."""


def get_preserved_filter_args(request_args):
    """필터링 상태를 유지하기 위한 URL 매개변수를 반환합니다."""
    redirect_args = {}
    preserved_params = ['search', 'status', 'region', 'page', 'sort', 'direction', 'sort_by', 'sort_order']
    preserved_params += [k for k in request_args.keys() if k.startswith('filter_')]
    for key in preserved_params:
        if key in request_args:
            redirect_args[key] = request_args.get(key)
    return redirect_args
