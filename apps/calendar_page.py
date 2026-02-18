"""캘린더 페이지 Blueprint: /calendar."""
from flask import Blueprint, render_template

from apps.auth import login_required

calendar_bp = Blueprint('calendar', __name__, url_prefix='')


@calendar_bp.route('/calendar')
@login_required
def calendar():
    """캘린더 페이지."""
    return render_template('calendar.html')
